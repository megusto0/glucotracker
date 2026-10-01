"""OpenAI Codex (Hermes OAuth) photo nutrition estimate client.

Final photo-estimate fallback after Gemini and Grok. Reuses the ChatGPT Codex
OAuth session that Hermes already holds, so no separate OpenAI API key is
required. Talks to the Codex Responses backend over SSE and parses the reply
into the shared ``EstimationResult`` schema.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
from pathlib import Path
from typing import Any

import httpx

from glucotracker.config import get_settings
from glucotracker.infra.gemini.client import PHOTO_ESTIMATION_PROMPT_V2, PhotoInput
from glucotracker.infra.gemini.schemas import EstimationResult
from glucotracker.infra.openai_codex.auth import (
    CodexCredentials,
    resolve_hermes_codex_credentials,
)

logger = logging.getLogger(__name__)

FAILED_EVENT_TYPES = {"response.failed", "response.incomplete", "error"}


class OpenAICodexClientError(RuntimeError):
    """Raised when the OpenAI Codex photo estimate cannot be completed."""

    def __init__(self, message: str, *, http_status_code: int | None = None) -> None:
        super().__init__(message)
        self.http_status_code = http_status_code


class OpenAICodexPhotoClient:
    """Estimate meal macros from photos via the OpenAI Codex backend."""

    def __init__(
        self,
        *,
        access_token: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        auth_json_path: str | Path | None = None,
        credentials: CodexCredentials | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._explicit_access_token = access_token
        self._auth_json_path = auth_json_path or settings.openai_hermes_auth_json
        self.base_url = (base_url or settings.openai_codex_base_url).rstrip("/")
        self.model = model or settings.openai_photo_model
        self.timeout = timeout
        self._credentials = credentials
        self._http_client = http_client
        self.last_used_model: str | None = None
        self.last_auth_source: str | None = None
        self.last_raw_response: dict[str, Any] | None = None
        self.last_response_latency_ms: int | None = None

    @property
    def configured(self) -> bool:
        """Return whether a Hermes/OpenAI Codex session is available."""
        return self._resolve_credentials() is not None

    def _resolve_credentials(self) -> CodexCredentials | None:
        if self._credentials is not None:
            return self._credentials
        settings = get_settings()
        return resolve_hermes_codex_credentials(
            access_token=self._explicit_access_token
            if self._explicit_access_token is not None
            else settings.openai_hermes_access_token,
            auth_json_path=self._auth_json_path,
        )

    def estimate_photos(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None = None,
        products_context: list[dict[str, Any]] | None = None,
        user_context: str | None = None,
    ) -> EstimationResult:
        """Estimate visible meal items from photos using OpenAI Codex vision."""
        self.last_response_latency_ms = None
        creds = self._resolve_credentials()
        if creds is None:
            raise OpenAICodexClientError(
                "OpenAI Codex не авторизован. Выполните `hermes auth add "
                "openai-codex` и синхронизируйте hermes-auth.json."
            )
        if not photos:
            raise OpenAICodexClientError(
                "at least one photo is required for estimation"
            )

        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": self._build_prompt(
                    photos,
                    patterns_context=patterns_context,
                    products_context=products_context,
                    user_context=user_context,
                ),
            }
        ]
        for photo in photos:
            content.append(
                {
                    "type": "input_image",
                    "image_url": _data_url(photo.path, photo.content_type),
                }
            )

        payload = {
            "model": self.model,
            "instructions": (
                "You return only valid JSON matching the requested schema. "
                "No markdown fences, no commentary outside JSON."
            ),
            "input": [{"type": "message", "role": "user", "content": content}],
            "stream": True,
            "store": False,
        }
        headers = {
            "Authorization": f"Bearer {creds.access_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "originator": "codex_cli_rs",
            "User-Agent": "codex_cli_rs/0.0.0 (Hermes Agent)",
        }
        if creds.account_id:
            headers["ChatGPT-Account-ID"] = creds.account_id

        logger.info(
            "OpenAI Codex photo estimate attempt model=%s auth=%s",
            self.model,
            creds.source,
        )
        response_start = time.perf_counter()
        try:
            text, last_event = self._stream_completion(headers, payload)
        except httpx.TimeoutException as exc:
            raise OpenAICodexClientError(
                "OpenAI Codex request timed out while estimating the photo.",
                http_status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenAICodexClientError(
                f"OpenAI Codex request failed: {exc}",
                http_status_code=503,
            ) from exc
        finally:
            self.last_response_latency_ms = int(
                (time.perf_counter() - response_start) * 1000
            )

        self.last_raw_response = last_event
        try:
            result = EstimationResult.model_validate_json(_extract_json(text))
        except Exception as exc:
            raise OpenAICodexClientError(
                f"OpenAI Codex response could not be parsed: {exc}",
                http_status_code=502,
            ) from exc

        self.last_used_model = self.model
        self.last_auth_source = creds.source
        logger.info("OpenAI Codex photo estimate succeeded model=%s", self.model)
        return result

    def _stream_completion(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        client = self._http_client
        owns_client = client is None
        if client is None:
            settings = get_settings()
            proxy = (settings.gemini_proxy_url or "").strip() or None
            kwargs: dict[str, Any] = {"timeout": self.timeout, "trust_env": False}
            if proxy:
                kwargs["proxy"] = proxy
            client = httpx.Client(**kwargs)
        try:
            with client.stream(
                "POST",
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    raise _http_error(response.status_code, body)
                text, last_event = _consume_sse(response.iter_lines())
        finally:
            if owns_client:
                client.close()
        return text, last_event

    def _build_prompt(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None,
        products_context: list[dict[str, Any]] | None,
        user_context: str | None,
    ) -> str:
        """Build the text portion of the multimodal user message."""
        manifest = [
            {
                "index": photo.index or position,
                "id": photo.photo_id,
                "filename": photo.filename or photo.path.name,
            }
            for position, photo in enumerate(photos, start=1)
        ]
        context = {
            "patterns": patterns_context or [],
            "products": products_context or [],
        }
        schema = EstimationResult.model_json_schema()
        parts = [
            PHOTO_ESTIMATION_PROMPT_V2,
            "PHOTO MANIFEST JSON:",
            json.dumps(manifest, ensure_ascii=False),
            "Known context JSON:",
            json.dumps(context, ensure_ascii=False),
            "Return a single JSON object matching this schema:",
            json.dumps(schema, ensure_ascii=False),
        ]
        if user_context and user_context.strip():
            parts.extend(["USER CONTEXT:", user_context.strip()])
        return "\n\n".join(parts)


def _consume_sse(
    lines: Any,
) -> tuple[str, dict[str, Any] | None]:
    """Accumulate ``response.output_text.delta`` chunks from a Responses SSE stream."""
    parts: list[str] = []
    last_event: dict[str, Any] | None = None
    for raw in lines:
        line = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            if data == "[DONE]":
                break
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        last_event = event
        event_type = event.get("type")
        if event_type == "response.output_text.delta":
            parts.append(event.get("delta") or "")
        elif event_type in FAILED_EVENT_TYPES:
            raise OpenAICodexClientError(
                _event_error_message(event),
                http_status_code=502,
            )
        elif event_type == "response.completed":
            break
    return "".join(parts), last_event


def _event_error_message(event: dict[str, Any]) -> str:
    error = event.get("error")
    if isinstance(error, dict) and error.get("message"):
        return f"OpenAI Codex response failed: {error['message']}"
    response = event.get("response")
    if isinstance(response, dict):
        error = response.get("error")
        if isinstance(error, dict) and error.get("message"):
            return f"OpenAI Codex response failed: {error['message']}"
    return "OpenAI Codex response failed."


def _http_error(status_code: int, body: str) -> OpenAICodexClientError:
    detail = _safe_error_body(body)
    if status_code in {401, 403}:
        return OpenAICodexClientError(
            "OpenAI Codex отклонил сессию Hermes. Обновите авторизацию "
            f"(`hermes auth add openai-codex`). ({detail[:200]})",
            http_status_code=status_code,
        )
    if status_code == 429:
        return OpenAICodexClientError(
            "OpenAI Codex quota or rate limit exceeded. Try again later.",
            http_status_code=429,
        )
    return OpenAICodexClientError(
        f"OpenAI Codex request failed ({status_code}): {detail}",
        http_status_code=status_code if status_code in {400, 404, 503} else 503,
    )


def _data_url(path: Path, content_type: str | None) -> str:
    """Encode a local photo as a data URL for Responses vision input."""
    mime = content_type or mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_json(text: str) -> str:
    """Return the JSON object embedded in a model reply, ignoring fences/prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _safe_error_body(body: str) -> str:
    """Return a short error body for logs/exceptions."""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, str) and detail:
                return detail[:400]
            error = data.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:400]
            if data.get("message"):
                return str(data["message"])[:400]
        return str(data)[:400]
    except Exception:
        return (body or "unknown error")[:400]
