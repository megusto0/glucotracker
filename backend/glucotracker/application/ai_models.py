"""Aggregate private model attempts without exposing prompts, photos or secrets."""

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.api.ai_models_schemas import (
    AIModelAttemptHistory,
    AIModelChoice,
    AIModelErrorCount,
    AIModelOverview,
    AIModelsResponse,
    AIRequestHistory,
)
from glucotracker.config import get_settings
from glucotracker.infra.db.repositories.ai_models import AIModelsRepository
from glucotracker.infra.gemini.quota_cooldown import GeminiQuotaCooldownStore


def default_models() -> list[AIModelChoice]:
    settings = get_settings()
    names = [
        settings.gemini_model,
        *settings.gemini_fallback_models.split(","),
        settings.gemini_fallback_model,
    ]
    models = [
        AIModelChoice(provider="gemini", model=name.strip())
        for name in dict.fromkeys(names)
        if name and name.strip() and "pro" not in name.lower()
    ]
    models += [
        AIModelChoice(
            provider="grok",
            model=settings.grok_photo_model,
            enabled=settings.grok_photo_fallback_enabled,
        ),
        AIModelChoice(
            provider="openai-codex",
            model=settings.openai_photo_model,
            enabled=settings.openai_photo_fallback_enabled,
        ),
    ]
    return models


def error_category(attempt: dict) -> str:
    """Return fixed diagnostic categories; never echo provider exception strings."""
    message = (
        f"{attempt.get('message', '')} "
        f"{attempt.get('error_status', attempt.get('status', ''))}"
    ).lower()
    code = attempt.get("error_code", attempt.get("code"))
    category = attempt.get("error_category", attempt.get("category", "unknown"))
    if code == 504 or any(
        word in message for word in ("timeout", "timed out", "deadline_exceeded")
    ):
        return "timeout"
    if code in (401, 403):
        return "authentication"
    if code == 429:
        return "quota"
    if code in (400, 404):
        return "invalid_request"
    if category == "parse" or "could not be parsed" in message:
        return "parse"
    if code in (500, 502, 503):
        return "overload"
    return (
        category
        if category
        in {"quota", "overload", "parse", "invalid_request", "authentication"}
        else "unknown"
    )


def _number(value) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    ):
        return float(value)
    return None


def overview(
    session: Session,
    user_id: UUID,
    days: int,
    history_offset: int = 0,
    history_limit: int = 30,
) -> AIModelsResponse:
    from glucotracker.infra.grok.auth import load_session_credentials
    from glucotracker.infra.openai_codex.client import OpenAICodexPhotoClient

    settings = get_settings()
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    repository = AIModelsRepository(session, user_id)
    routing = repository.routing()
    choices = (
        [AIModelChoice.model_validate(m) for m in routing.models_json]
        if routing
        else default_models()
    )
    available = {
        "gemini": bool(settings.gemini_api_key or settings.gemini_fallback_api_key),
        "grok": settings.grok_photo_fallback_enabled
        and bool(
            settings.xai_api_key
            or load_session_credentials(settings.grok_auth_json, refresh=False)
        ),
        "openai-codex": settings.openai_photo_fallback_enabled
        and OpenAICodexPhotoClient(
            access_token=settings.openai_hermes_access_token,
            base_url=settings.openai_codex_base_url,
            model=settings.openai_photo_model,
            auth_json_path=settings.openai_hermes_auth_json,
        ).configured,
    }
    cooldowns = GeminiQuotaCooldownStore(settings.gemini_quota_cooldown_path)
    rows = {}
    times = {}
    response_times = {}
    request_times = {}
    confidences = {}
    errors = {}

    def row_for(provider, model, choice=None):
        key = (provider, model)
        if key not in rows:
            rows[key] = AIModelOverview(
                provider=provider,
                model=model,
                enabled=choice.enabled if choice else False,
                in_routing=choice is not None,
                available=available.get(provider, False),
                cooldown_until=cooldowns.active_until(model)
                if provider == "gemini"
                else None,
            )
            (
                times[key],
                response_times[key],
                request_times[key],
                confidences[key],
                errors[key],
            ) = (
                [],
                [],
                [],
                [],
                {},
            )
        return key, rows[key]

    for choice in choices:
        row_for(choice.provider, choice.model, choice)
    runs = repository.runs(since)
    history: list[AIRequestHistory] = []
    for run_index, run in enumerate(runs[:5000]):
        called_at = run.created_at
        if called_at.tzinfo is None:
            called_at = called_at.replace(tzinfo=UTC)
        summary = run.request_summary or {}
        attempts = _attempts_for_run(run, summary)
        if history_offset <= run_index < history_offset + history_limit:
            history.append(_request_history(run, summary, attempts, called_at))
        final_provider = summary.get("provider") or run.provider
        final_model = run.model_used or summary.get("model_used") or run.model
        chain_duration = _number(summary.get("latency_ms"))
        if (
            final_provider in available
            and isinstance(final_model, str)
            and chain_duration is not None
            and chain_duration >= 0
        ):
            try:
                AIModelChoice(provider=final_provider, model=final_model)
            except ValueError:
                pass
            else:
                key, _ = row_for(final_provider, final_model)
                request_times[key].append(chain_duration)
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            provider = attempt.get("provider", "gemini")
            model = attempt.get("model")
            if provider not in available or not isinstance(model, str):
                continue
            try:
                # Historical model names are still restricted to identifiers.
                AIModelChoice(provider=provider, model=model)
            except ValueError:
                continue
            key, row = row_for(provider, model)
            status = attempt.get("status")
            if status == "skipped":
                row.skipped += 1
                continue
            if status not in ("success", "error"):
                continue
            row.attempts += 1
            row.last_called_at = row.last_called_at or called_at
            duration = _number(attempt.get("latency_ms"))
            if duration is not None and duration >= 0:
                times[key].append(duration)
            response_duration = _number(attempt.get("response_latency_ms"))
            if response_duration is not None and response_duration >= 0:
                response_times[key].append(response_duration)
            if status == "success":
                row.successes += 1
                confidence = _number(attempt.get("confidence"))
                if confidence is not None and 0 <= confidence <= 1:
                    confidences[key].append(confidence)
            else:
                row.failures += 1
                category = error_category(attempt)
                if category not in errors[key]:
                    errors[key][category] = AIModelErrorCount(
                        category=category, count=0, last_at=called_at
                    )
                errors[key][category].count += 1
    for key, row in rows.items():
        row.success_rate = row.successes / row.attempts if row.attempts else None
        row.timed_attempts = len(times[key])
        row.average_latency_ms = (
            sum(times[key]) / len(times[key]) if times[key] else None
        )
        row.timed_responses = len(response_times[key])
        row.average_response_latency_ms = (
            sum(response_times[key]) / len(response_times[key])
            if response_times[key]
            else None
        )
        row.timed_requests = len(request_times[key])
        row.average_request_latency_ms = (
            sum(request_times[key]) / len(request_times[key])
            if request_times[key]
            else None
        )
        row.confidence_samples = len(confidences[key])
        row.average_confidence = (
            sum(confidences[key]) / len(confidences[key]) if confidences[key] else None
        )
        row.errors = sorted(errors[key].values(), key=lambda e: -e.count)
    return AIModelsResponse(
        revision=routing.revision if routing else 0,
        custom_routing=routing is not None,
        since=since,
        generated_at=now,
        history_truncated=len(runs) > 5000,
        models=list(rows.values()),
        history_total=min(len(runs), 5000),
        history_offset=history_offset,
        history=history,
    )


def _attempts_for_run(run, summary: dict) -> list[dict]:
    attempts = summary.get("attempts")
    if isinstance(attempts, list) and attempts:
        return [attempt for attempt in attempts if isinstance(attempt, dict)]
    # Older audit rows cannot reconstruct retries or per-attempt latency.
    errors = run.error_history_json or []
    result = [
        dict(error, status="error") for error in errors if isinstance(error, dict)
    ]
    if run.status == "success":
        result.append(
            {
                "provider": summary.get("provider", run.provider),
                "model": run.model_used or run.model,
                "status": "success",
            }
        )
    elif not result:
        result.append(
            {
                "provider": summary.get("provider", run.provider),
                "model": run.model_used or run.model,
                "status": "error",
            }
        )
    return result


def _request_history(
    run, summary: dict, attempts: list[dict], called_at: datetime
) -> AIRequestHistory:
    safe_attempts = []
    for attempt in attempts:
        provider = attempt.get("provider", "gemini")
        model = attempt.get("model")
        status = attempt.get("status")
        if (
            provider not in {"gemini", "grok", "openai-codex"}
            or not isinstance(model, str)
            or status not in {"success", "error", "skipped"}
        ):
            continue
        duration = _number(attempt.get("latency_ms"))
        response_duration = _number(attempt.get("response_latency_ms"))
        confidence = _number(attempt.get("confidence"))
        safe_attempts.append(
            AIModelAttemptHistory(
                provider=provider,
                model=model[:120],
                status=status,
                latency_ms=duration if duration is not None and duration >= 0 else None,
                response_latency_ms=response_duration
                if response_duration is not None and response_duration >= 0
                else None,
                confidence=confidence
                if confidence is not None and 0 <= confidence <= 1
                else None,
                error_category=error_category(attempt) if status == "error" else None,
            )
        )
    duration = _number(summary.get("latency_ms"))
    provider = summary.get("provider") or run.provider
    return AIRequestHistory(
        id=run.id,
        created_at=called_at,
        request_type=run.request_type,
        status=run.status,
        model_requested=run.model_requested,
        model_used=run.model_used or run.model,
        provider=provider,
        fallback_used=run.fallback_used,
        latency_ms=duration if duration is not None and duration >= 0 else None,
        attempts=safe_attempts,
    )
