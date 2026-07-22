"""Gemini client wrapper for structured photo nutrition estimation."""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from glucotracker.config import get_settings
from glucotracker.infra.gemini.quota_cooldown import GeminiQuotaCooldownStore
from glucotracker.infra.gemini.schemas import EstimationResult, GeminiScenario

logger = logging.getLogger(__name__)

PHOTO_ESTIMATION_PROMPT_VERSION = "PHOTO_ESTIMATION_PROMPT_V2"
PHOTO_ESTIMATION_PROMPT_V2 = """\
You are a nutrition estimator for a personal food diary. The user is a
type-1 diabetic who logs meals to track macros, but this is NOT used for
insulin dosing. Do not recommend insulin, bolus, correction or treatment.

Input: one or more photos of one meal/snack. The user may attach multiple
photos. Each photo is identified in the PHOTO MANIFEST below and the image
parts are supplied in the same order.

The request may include USER CONTEXT supplied by the user, such as known
component weights, eaten quantity, or corrections like "100 г варёного риса".
Use this as user-provided evidence. Do not ignore visible photo evidence. If it
gives a known weight/count for a visible component, apply that component context
in your extraction and explain it in evidence or assumptions. Do not treat user
context as medical advice and do not use it to recommend insulin or treatment.

For each distinct visible item:
1. Identify the item, brand if recognizable.
2. Choose scenario:
   - LABEL_FULL: nutrition facts and net weight/volume visible.
   - LABEL_PARTIAL: nutrition facts visible but net weight/volume not visible.
   - PLATED: prepared food without label.
   - BARCODE: barcode visible.
   - SPLIT_LABEL_IDENTICAL_ITEMS: label facts are split across clearly matching
     identical packages/photos.
   - UNKNOWN: unclear.
3. For labels, extract facts exactly. Do not do final arithmetic unless asked.
   Put Russian visible text into visible_label_facts, and normalized per-100g
   values into nutrition_per_100g when a per-100g label is visible. If visible
   fiber, sodium, caffeine, sugar, potassium, iron, calcium, or magnesium facts
   are present, put them in optional_nutrients with per-100g, per-100ml, or
   per-serving values and units. The backend performs final arithmetic.
4. For missing weight/volume, provide an assumption and reason.
5. For plated food, estimate grams and macros as low/mid/high. Do not visually
   guess sodium or caffeine. Fiber may be included only from a known food
   database or context match and must be marked as estimated.
   For PLATED items, grams_mid and macro mid values MUST describe the total
   visible/eaten amount represented by the item. If four bread crisps are
   visible and together weigh about 40g, return grams_mid=40 and
   values_basis="total_visible"; do not return one-crisp values at top level.
   Only if the top-level values intentionally describe one unit, set
   values_basis="per_unit" so the backend can multiply by count_detected.
   Also return component_estimates with component-level raw macros:
   carbs_g_mid, protein_g_mid, fat_g_mid, fiber_g_mid, kcal_mid. Identify
   reusable known components separately: tortilla / лаваш, bread / булка /
   хлеб, rice, pasta, potato, sweet drink, candy/bar, cereal/granola, bakery
   products, and other visible branded/standard components. Mark those
   components with component_type="carb_base" or component_type="known_component"
   and should_use_database_if_available=true. Estimate count, rough grams, and
   raw component macros, but do not invent precise branded/package values.
6. If reference object exists, use it for scale.
7. Return confidence 0..1 and one-sentence confidence reason.
8. Put evidence as short user-readable strings in the evidence list. Prefer
   Russian wording when the visible label is Russian.
9. For every item, set source_photo_ids and source_photo_indices. Set
   primary_photo_id to the best single source photo for that item.

Output contract:
Every food item you return must include enough nutrition for the backend to
save it. For each item, one of these must be true:
- nutrition_per_100g has non-null carbs_g, protein_g, fat_g, and kcal, and a
  visible, assumed, net, or total weight is present.
- top-level grams_mid, carbs_g_mid, protein_g_mid, fat_g_mid, and kcal_mid are
  all non-null for the total visible/eaten amount.
If an exact nutrition label is incomplete or unreadable but the packaged food
is identifiable, estimate typical values for that exact product/category and
use the second option. This also applies when only some facts are readable, for
example weight and protein but not carbohydrates, fat, or kcal.

Mandatory packaged-food fallback:
- Preserve every readable label value in visible_label_facts.
- Use the visible package weight/volume for grams_mid when available; otherwise
  estimate the package size.
- Fill ALL of grams_mid, carbs_g_mid, protein_g_mid, fat_g_mid, fiber_g_mid, and
  kcal_mid with numeric values for the total package/visible amount. Never leave
  any of these fields null. Fiber may be 0 only when a low-fiber estimate is
  plausible; other missing fields must be realistic category estimates, not
  placeholder zeroes.
- Keep readable facts consistent with the estimates. Estimate only the missing
  facts from the identified product or closest food category.
- Add a Russian assumption stating exactly which values were estimated and
  lower confidence to 0.55..0.75.

Before returning JSON, validate every packaged-food item. If the complete
nutrition_per_100g option is not usable, the six top-level numeric fields above
MUST all be present. Repair any null packaged-food macro before returning. It is
forbidden to return a packaged food item with only name/weight or partial macros.
A useful approximate macro estimate is better than an unsavable null-macro item.

Do not merge unrelated photos:
If multiple photos show different food/drink items, return separate
EstimatedItem objects. Do not merge a drink and a wrap into one item. Only
combine evidence across photos when the photos clearly show the same packaged
product or identical packages.

For one coherent wrap/lavash/sandwich on one photo, return one EstimatedItem
with component_estimates rather than separate final items for tortilla, chicken,
tomatoes, sauce, etc. Component breakdown belongs inside the item. If a model
reasoning step sees tortilla/lavash/bread/rice/pasta/potato, put that component
in component_estimates and mark it as a known component candidate so the backend
can use the user's saved component values for carbs, protein, fat, fiber, kcal,
and optional nutrients. If there is a reference object like a pen, use it only
for rough scale; do not let it inflate portion size aggressively.

Component types:
- carb_base: tortilla/lavash/bread/rice/pasta/potato/sweet drink/candy/cereal/bakery.
- protein: chicken/meat/fish/egg/tofu.
- vegetable: vegetables/greens.
- sauce: sauces/dressings.
- fat_source: visible oil/butter/cheese/nuts/avocado when primarily fat.
- known_component: any component that looks like a saved product/pattern should
  be used if available.
- unknown: unclear component.

Do not double count component macros. The EstimatedItem mid totals should be the
sum of the visible components. Component mid macros should represent each
component only, so the backend can replace one component's raw values with saved
database values.

Russian output:
Return user-facing names in Russian. Use display_name_ru for UI. Do not return
English names like "Chicken and Vegetable Wrap" unless no Russian
identification is possible. Prefer names such as "Лаваш с курицей", "Ролл с
курицей", "Напиток", "Шоколадный батончик", "Бисквит-сэндвич".

Russian labels:
- углеводы = carbs
- белки = protein
- жиры = fat
- клетчатка / пищевые волокна = fiber
- сахара = sugar
- соль = salt
- натрий = sodium
- кофеин = caffeine
- энергетическая ценность = kcal / energy
- масса нетто = net weight
- пищевая ценность на 100 г = nutrition per 100g

Split label evidence:
If multiple identical packaged items are visible and nutrition values are
visible on one package while net weight is visible on another package, combine
those visible facts only when the packages clearly appear identical. In that
case keep scenario LABEL_FULL, set evidence_is_split_across_identical_items to
true, return count_detected, count_confidence, net_weight_per_unit_g,
total_weight_g if directly derivable from visible count, nutrition_per_100g,
and evidence explaining which facts were read from which package. Do not do
final macro totals; the backend will calculate totals.

Count:
If multiple identical packages are visible, return count_detected. If the count
is uncertain, lower count_confidence and add an assumption. Do not assume eaten
count is more than the visible count.

Whole fruit on scales:
If an unpeeled fruit such as an orange, mandarin, banana, or similar whole
fruit is visible on a scale, treat the visible scale weight as gross weight
including peel unless the user context says it is peeled/edible weight. Explain
that the weight includes peel and lower confidence if edible yield is uncertain.
Do not report high confidence for edible macros when only gross unpeeled weight
is known.

Confidence rubric:
  >0.85: LABEL_FULL or strong product/pattern match.
  0.60..0.85: LABEL_PARTIAL with plausible size assumption, or clear plated item.
  <0.60: mixed plated food, unclear photo, no reference, ambiguous item.

Be conservative. Prefer uncertainty over fake precision.
"""


@dataclass(frozen=True)
class PhotoInput:
    """Photo bytes and MIME type sent to Gemini."""

    path: Path
    content_type: str
    photo_id: str | None = None
    filename: str | None = None
    index: int | None = None


class GeminiClientError(RuntimeError):
    """Raised when Gemini estimation cannot be completed."""

    def __init__(self, message: str, *, http_status_code: int = 503) -> None:
        super().__init__(message)
        self.http_status_code = http_status_code


class GeminiRequestError(GeminiClientError):
    """Gemini SDK request error classified for retry/fallback decisions."""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        code: int | None = None,
        status: str | None = None,
        http_status_code: int = 503,
    ) -> None:
        super().__init__(message, http_status_code=http_status_code)
        self.category = category
        self.code = code
        self.status = status


class GeminiClient:
    """Thin wrapper around the Google GenAI SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        quota_cooldowns: GeminiQuotaCooldownStore | None = None,
    ) -> None:
        settings = get_settings()
        self.settings = settings
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.fallback_api_key = settings.gemini_fallback_api_key
        self.model = model if model is not None else settings.gemini_model
        self.cheap_model = settings.gemini_cheap_model
        self.free_test_model = settings.gemini_free_test_model
        self.fallback_model = settings.gemini_fallback_model
        self.fallback_models = self._parse_fallback_models(
            settings.gemini_fallback_models
        )
        self.max_retries_per_model = settings.gemini_max_retries_per_model
        self.low_confidence_retry_threshold = (
            settings.gemini_low_confidence_retry_threshold
        )
        self.overload_cooldown_hours = settings.gemini_overload_cooldown_hours
        self.quota_cooldowns = quota_cooldowns or GeminiQuotaCooldownStore(
            settings.gemini_quota_cooldown_path,
            cooldown_hours=settings.gemini_quota_cooldown_hours,
        )
        self.last_used_model: str | None = None
        self.last_requested_model: str | None = None
        self.last_fallback_used = False
        self.last_model_attempts: list[str] = []
        self.last_attempts: list[dict[str, Any]] = []
        self.last_error_history: list[dict[str, Any]] = []
        self.last_latency_ms: int | None = None
        self.last_routing_reason: str | None = None
        self.last_provider: str = "gemini"
        self.last_api_key_slot: str = "primary"  # primary | fallback_api

    def estimate_photos(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None = None,
        products_context: list[dict[str, Any]] | None = None,
        scenario_hint: GeminiScenario | None = None,
        model_override: str | None = None,
        user_context: str | None = None,
    ) -> EstimationResult:
        """Estimate visible meal items from photos using structured output."""
        if not self.api_key:
            msg = "GEMINI_API_KEY is not configured"
            raise GeminiClientError(msg)
        if not photos:
            msg = "at least one photo is required for estimation"
            raise GeminiClientError(msg)

        start = time.perf_counter()
        primary_model = (
            model_override
            if model_override is not None and model_override != "default"
            else self._select_primary_model(scenario_hint)
        )
        self._reset_run_metadata(primary_model)
        self.last_routing_reason = (
            "explicit_model_override"
            if model_override is not None and model_override != "default"
            else self._routing_reason(scenario_hint)
        )

        # Pass 1: primary API key + primary model + fallback models.
        # Pass 2 (if configured): GEMINI_FALLBACK_API_KEY with the same model list
        # when the primary key is exhausted (quota) or all models fail.
        key_slots = self._api_key_slots()
        candidate_result: EstimationResult | None = None
        last_error: GeminiRequestError | None = None
        saw_quota = False

        for slot_index, (slot_name, api_key) in enumerate(key_slots):
            self.last_api_key_slot = slot_name
            models = [primary_model, *self._fallback_models(primary_model)]
            # De-dupe while preserving order. Never auto-skip the primary model
            # via _should_skip_model — Pro rejection must raise for that case.
            seen_models: set[str] = set()
            ordered_models: list[str] = []
            for index, model in enumerate(models):
                if model in seen_models:
                    continue
                if self._model_cooldown_active(model):
                    continue
                if index > 0 and self._should_skip_model(model):
                    continue
                seen_models.add(model)
                ordered_models.append(model)

            for model_index, model in enumerate(ordered_models):
                fallback_used = slot_index > 0 or model != primary_model
                try:
                    result = self._run_model_with_retries(
                        model,
                        photos,
                        patterns_context=patterns_context,
                        products_context=products_context,
                        user_context=user_context,
                        fallback_used=fallback_used,
                        api_key=api_key,
                        api_key_slot=slot_name,
                    )
                except GeminiRequestError as exc:
                    last_error = exc
                    if exc.category == "quota":
                        saw_quota = True
                        # Exhausted this model on this key — try next model / key.
                        continue
                    if exc.category == "invalid_request" and self._looks_unsupported(
                        exc
                    ):
                        logger.warning(
                            "Skipping unsupported Gemini model=%s key=%s error=%s",
                            model,
                            slot_name,
                            exc,
                        )
                        continue
                    if exc.category == "invalid_request":
                        self.last_latency_ms = self._elapsed_ms(start)
                        raise self._friendly_client_error(exc) from exc
                    # overload/parse already retried inside _run_model_with_retries
                    continue
                else:
                    if (
                        not self._has_low_confidence(result)
                        or fallback_used
                        or model_index == len(ordered_models) - 1
                    ):
                        if slot_index > 0:
                            result.image_quality_warnings.append(
                                "Основной Gemini API key исчерпан; "
                                "использован GEMINI_FALLBACK_API_KEY."
                            )
                        self.last_latency_ms = self._elapsed_ms(start)
                        return result
                    # Low confidence on first model of primary key — keep and try more.
                    candidate_result = result
                    self.last_routing_reason = "low_confidence_retry"
                    continue

            # If primary key only hit quota, jump to fallback key immediately.
            if (
                slot_index == 0
                and saw_quota
                and len(key_slots) > 1
                and candidate_result is None
            ):
                logger.info(
                    "Primary Gemini API key exhausted (quota); "
                    "switching to GEMINI_FALLBACK_API_KEY"
                )
                self.last_routing_reason = "fallback_api_key_quota"
                continue

        if candidate_result is not None:
            self.last_latency_ms = self._elapsed_ms(start)
            return candidate_result

        # Final fallback: xAI Grok vision (when configured).
        grok_result = self._try_grok_fallback(
            photos,
            patterns_context=patterns_context,
            products_context=products_context,
            user_context=user_context,
            start=start,
        )
        if grok_result is not None:
            return grok_result

        self.last_latency_ms = self._elapsed_ms(start)
        grok_errors = [
            err
            for err in self.last_error_history
            if err.get("provider") == "grok" or err.get("category") == "grok_failed"
        ]
        if grok_errors:
            msg = str(grok_errors[-1].get("message") or "Grok fallback failed")
            raise GeminiClientError(msg)
        if last_error is not None:
            raise self._friendly_client_error(last_error) from last_error
        raise GeminiClientError(
            "Gemini не смог обработать фото. Попробуйте повторить оценку.",
        )

    def _api_key_slots(self) -> list[tuple[str, str]]:
        """Return ordered (slot_name, api_key) pairs for photo estimate."""
        slots: list[tuple[str, str]] = []
        if self.api_key and self.api_key.strip():
            slots.append(("primary", self.api_key.strip()))
        fallback = (self.fallback_api_key or "").strip()
        if fallback and fallback not in {key for _, key in slots}:
            slots.append(("fallback_api", fallback))
        return slots

    def _try_grok_fallback(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None,
        products_context: list[dict[str, Any]] | None,
        user_context: str | None,
        start: float,
    ) -> EstimationResult | None:
        """Attempt Grok vision estimate as the final automatic fallback."""
        settings = self.settings
        if not settings.grok_photo_fallback_enabled:
            return None

        from glucotracker.infra.grok.client import GrokClientError, GrokPhotoClient

        grok = GrokPhotoClient()
        if not grok.configured:
            logger.info(
                "Grok photo fallback skipped: no SuperGrok session "
                "(~/.grok/auth.json / GROK_AUTH_JSON) and no XAI_API_KEY"
            )
            return None
        model = grok.model
        attempt_meta: dict[str, Any] = {
            "model": model,
            "attempt": 1,
            "fallback_used": True,
            "provider": "grok",
        }
        self.last_model_attempts.append(model)
        self.last_attempts.append(attempt_meta)
        self.last_routing_reason = "grok_final_fallback"
        logger.info("Grok final photo-estimate fallback model=%s", model)
        try:
            result = grok.estimate_photos(
                photos,
                patterns_context=patterns_context,
                products_context=products_context,
                user_context=user_context,
            )
        except GrokClientError as exc:
            attempt_meta.update(
                {
                    "status": "error",
                    "error_category": "grok_failed",
                    "message": str(exc),
                    "auth_source": grok.last_auth_source,
                }
            )
            self.last_error_history.append(
                {
                    "model": model,
                    "attempt": 1,
                    "category": "grok_failed",
                    "message": str(exc),
                    "provider": "grok",
                }
            )
            logger.warning("Grok photo fallback failed model=%s error=%s", model, exc)
            return None

        attempt_meta["status"] = "success"
        attempt_meta["auth_source"] = grok.last_auth_source
        self.last_used_model = grok.last_used_model or model
        self.last_fallback_used = True
        self.last_provider = "grok"
        self.last_latency_ms = self._elapsed_ms(start)
        logger.info(
            "Grok photo fallback succeeded model=%s auth=%s",
            self.last_used_model,
            grok.last_auth_source,
        )
        auth_note = (
            "SuperGrok session"
            if grok.last_auth_source == "session"
            else "XAI API key"
        )
        warning = f"Gemini недоступен; использован запасной Grok ({auth_note})."
        if warning not in result.image_quality_warnings:
            result.image_quality_warnings.append(warning)
        return result

    def _run_model_with_retries(
        self,
        model: str,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None,
        products_context: list[dict[str, Any]] | None,
        user_context: str | None,
        fallback_used: bool,
        api_key: str | None = None,
        api_key_slot: str = "primary",
    ) -> EstimationResult:
        """Run one model with bounded retry handling."""
        self._ensure_not_pro_model(model)
        last_error: GeminiRequestError | None = None
        active_key = api_key or self.api_key

        for attempt in range(1, self.max_retries_per_model + 1):
            attempt_meta: dict[str, Any] = {
                "model": model,
                "attempt": attempt,
                "fallback_used": fallback_used,
                "api_key_slot": api_key_slot,
            }
            self.last_model_attempts.append(model)
            self.last_attempts.append(attempt_meta)
            logger.info(
                "Gemini estimate attempt model=%s attempt=%s fallback=%s key=%s",
                model,
                attempt,
                fallback_used,
                api_key_slot,
            )

            try:
                result = self._estimate_with_model(
                    model,
                    photos,
                    patterns_context=patterns_context,
                    products_context=products_context,
                    user_context=user_context,
                    api_key=active_key,
                )
            except GeminiRequestError as exc:
                last_error = exc
                attempt_meta.update(
                    {
                        "status": "error",
                        "error_code": exc.code,
                        "error_status": exc.status,
                        "error_category": exc.category,
                        "message": str(exc),
                    }
                )
                self.last_error_history.append(
                    {
                        "model": model,
                        "attempt": attempt,
                        "code": exc.code,
                        "status": exc.status,
                        "category": exc.category,
                        "message": str(exc),
                        "api_key_slot": api_key_slot,
                    }
                )
                logger.warning(
                    (
                        "Gemini attempt failed model=%s attempt=%s code=%s "
                        "status=%s category=%s key=%s"
                    ),
                    model,
                    attempt,
                    exc.code,
                    exc.status,
                    exc.category,
                    api_key_slot,
                )

                if exc.category in {"quota", "invalid_request"}:
                    if exc.category == "quota":
                        expires_at = self.quota_cooldowns.block(model)
                        logger.warning(
                            "Gemini model quota cooldown opened model=%s until=%s",
                            model,
                            expires_at.isoformat(),
                        )
                    raise exc

                retryable = exc.category in {"overload", "parse"}
                parse_retry_allowed = exc.category == "parse" and attempt < 2
                if retryable and attempt < self.max_retries_per_model:
                    if exc.category != "parse" or parse_retry_allowed:
                        self._sleep(self._retry_delay_seconds(attempt))
                        continue

                if exc.category == "overload":
                    expires_at = self.quota_cooldowns.block(
                        model,
                        duration=timedelta(hours=self.overload_cooldown_hours),
                    )
                    logger.warning(
                        "Gemini model overload cooldown opened model=%s until=%s",
                        model,
                        expires_at.isoformat(),
                    )

                raise exc

            attempt_meta["status"] = "success"
            self.last_used_model = model
            self.last_fallback_used = fallback_used
            self.last_api_key_slot = api_key_slot
            logger.info(
                "Gemini estimate succeeded model=%s attempt=%s fallback=%s key=%s",
                model,
                attempt,
                fallback_used,
                api_key_slot,
            )
            return result

        if last_error is not None:
            raise last_error
        raise GeminiRequestError(
            "Gemini request did not run.",
            category="unknown",
        )

    def _estimate_with_model(
        self,
        model: str,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None = None,
        products_context: list[dict[str, Any]] | None = None,
        user_context: str | None = None,
        api_key: str | None = None,
    ) -> EstimationResult:
        """Estimate visible meal items with a specific non-Pro Gemini model."""
        self._ensure_not_pro_model(model)
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            msg = "google-genai is not installed"
            raise GeminiClientError(msg) from exc

        active_key = (api_key or self.api_key or "").strip()
        if not active_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")

        context = {
            "patterns": patterns_context or [],
            "products": products_context or [],
        }
        manifest = [
            {
                "index": photo.index or position,
                "id": photo.photo_id,
                "filename": photo.filename or photo.path.name,
            }
            for position, photo in enumerate(photos, start=1)
        ]
        contents: list[Any] = [
            PHOTO_ESTIMATION_PROMPT_V2,
            "PHOTO MANIFEST JSON:",
            json.dumps(manifest, ensure_ascii=False),
            "Known context JSON:",
            json.dumps(context, ensure_ascii=False),
        ]
        if user_context and user_context.strip():
            contents.extend(
                [
                    "USER CONTEXT:",
                    user_context.strip(),
                ]
            )
        for photo in photos:
            contents.append(
                types.Part.from_bytes(
                    data=photo.path.read_bytes(),
                    mime_type=photo.content_type,
                )
            )

        client = genai.Client(
            api_key=active_key,
            http_options=self._http_options(),
        )
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": EstimationResult,
                },
            )
        except Exception as exc:
            raise self._classified_request_error(exc) from exc

        try:
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, EstimationResult):
                return parsed
            if parsed is not None:
                return EstimationResult.model_validate(parsed)
            return EstimationResult.model_validate_json(response.text)
        except Exception as exc:
            raise GeminiRequestError(
                f"Gemini response could not be parsed: {exc}",
                category="parse",
            ) from exc

    def _select_primary_model(self, scenario_hint: GeminiScenario | None) -> str:
        """Use the configured main model for every automatic photo estimate."""
        return self.model

    def _fallback_models(self, primary_model: str) -> list[str]:
        """Return configured fallback models in deterministic order."""
        models = [*self.fallback_models]
        if self.fallback_model:
            models.append(self.fallback_model)

        deduped: list[str] = []
        seen = {primary_model}
        for model in models:
            normalized = model.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _parse_fallback_models(self, value: str | None) -> list[str]:
        """Parse comma-separated fallback models from settings."""
        if not value:
            return []
        return [model.strip() for model in value.split(",") if model.strip()]

    def _http_options(self) -> dict[str, Any] | None:
        """Return HTTP options for the Google GenAI SDK."""
        if not self.settings.gemini_proxy_url:
            return None
        client_args = {"proxy": self.settings.gemini_proxy_url}
        return {
            "client_args": client_args,
            "async_client_args": client_args,
        }

    def _reset_run_metadata(self, primary_model: str) -> None:
        """Reset per-run Gemini routing metadata."""
        self.last_used_model = None
        self.last_requested_model = primary_model
        self.last_fallback_used = False
        self.last_model_attempts = []
        self.last_attempts = []
        self.last_error_history = []
        self.last_latency_ms = None
        self.last_routing_reason = None
        self.last_provider = "gemini"
        self.last_api_key_slot = "primary"

    def _should_skip_model(self, model: str) -> bool:
        """Skip known models that should not be routed automatically."""
        if "pro" not in model.lower():
            return False
        logger.warning("Skipping automatic Gemini fallback to Pro model: %s", model)
        self.last_attempts.append(
            {
                "model": model,
                "status": "skipped",
                "reason": "automatic_pro_routing_disabled",
            }
        )
        return True

    def _model_cooldown_active(self, model: str) -> bool:
        """Skip a model while its persistent quota cooldown is active."""
        expires_at = self.quota_cooldowns.active_until(model)
        if expires_at is None:
            return False
        logger.info(
            "Skipping Gemini model in quota cooldown model=%s until=%s",
            model,
            expires_at.isoformat(),
        )
        self.last_attempts.append(
            {
                "model": model,
                "status": "skipped",
                "reason": "model_cooldown",
                "cooldown_until": expires_at.isoformat(),
            }
        )
        return True

    def _retry_delay_seconds(self, attempt: int) -> float:
        """Return bounded exponential backoff with jitter for retries."""
        if attempt <= 1:
            return random.uniform(1, 2)
        return random.uniform(3, 5)

    def _sleep(self, seconds: float) -> None:
        """Sleep between retries. Tests override this method."""
        time.sleep(seconds)

    def _elapsed_ms(self, start: float) -> int:
        """Return elapsed milliseconds from a perf counter start."""
        return int((time.perf_counter() - start) * 1000)

    def _classified_request_error(self, exc: Exception) -> GeminiRequestError:
        """Convert an SDK exception into retry/fallback categories."""
        code = self._error_code(exc)
        status_text = self._error_status(exc)
        message = str(exc)
        haystack = f"{status_text or ''} {message}".upper()

        if code == 503 or "UNAVAILABLE" in haystack or "HIGH DEMAND" in haystack:
            return GeminiRequestError(
                f"Gemini request failed: {message}",
                category="overload",
                code=503 if code is None else code,
                status=status_text or "UNAVAILABLE",
            )
        if (
            code == 429
            or "RESOURCE_EXHAUSTED" in haystack
            or "RATE LIMIT" in haystack
            or "QUOTA" in haystack
        ):
            return GeminiRequestError(
                f"Gemini request failed: {message}",
                category="quota",
                code=429 if code is None else code,
                status=status_text or "RESOURCE_EXHAUSTED",
                http_status_code=429,
            )
        if (
            code == 400
            or "INVALID_ARGUMENT" in haystack
            or "INVALID REQUEST" in haystack
        ):
            return GeminiRequestError(
                f"Gemini request failed: {message}",
                category="invalid_request",
                code=400 if code is None else code,
                status=status_text or "INVALID_ARGUMENT",
                http_status_code=400,
            )
        return GeminiRequestError(
            f"Gemini request failed: {message}",
            category="unknown",
            code=code,
            status=status_text,
        )

    def _error_code(self, exc: Exception) -> int | None:
        """Extract an HTTP/gRPC code from heterogeneous SDK exceptions."""
        for attr in ("code", "status_code"):
            value = getattr(exc, attr, None)
            if callable(value):
                try:
                    value = value()
                except TypeError:
                    value = None
            if value is None:
                continue
            if hasattr(value, "value"):
                value = value.value
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        text = str(exc)
        for candidate in (503, 429, 400):
            if str(candidate) in text:
                return candidate
        return None

    def _error_status(self, exc: Exception) -> str | None:
        """Extract a textual status from an SDK exception."""
        for attr in ("status", "reason"):
            value = getattr(exc, attr, None)
            if value is None:
                continue
            if hasattr(value, "name"):
                return str(value.name)
            return str(value)
        return None

    def _looks_unsupported(self, exc: GeminiRequestError) -> bool:
        """Return whether an invalid request means this model cannot handle the job."""
        message = str(exc).lower()
        return any(
            marker in message
            for marker in (
                "does not support",
                "not support",
                "unsupported",
                "image input",
                "response_schema",
                "structured output",
            )
        )

    def _friendly_client_error(self, exc: GeminiRequestError) -> GeminiClientError:
        """Return a Russian user-facing error for a classified Gemini failure."""
        if exc.category == "overload":
            return GeminiClientError(
                (
                    "Gemini временно перегружен. Фото сохранены, "
                    "попробуйте повторить позже."
                ),
                http_status_code=503,
            )
        if exc.category == "quota":
            return GeminiClientError(
                (
                    "Дневной лимит Gemini исчерпан или превышен. "
                    "Попробуйте позже или выберите другую модель."
                ),
                http_status_code=429,
            )
        if exc.category == "invalid_request":
            return GeminiClientError(
                f"Некорректный запрос Gemini: {exc}",
                http_status_code=400,
            )
        if exc.category == "parse":
            return GeminiClientError(
                (
                    "Gemini вернул ответ в неожиданном формате. "
                    "Попробуйте повторить оценку."
                ),
                http_status_code=503,
            )
        return GeminiClientError(
            "Gemini не смог обработать фото. Попробуйте повторить оценку.",
            http_status_code=503,
        )

    def _routing_reason(self, scenario_hint: GeminiScenario | None) -> str:
        """Return a compact routing reason for audit metadata."""
        if scenario_hint == "LABEL_FULL":
            return "label_full_default"
        if scenario_hint == "LABEL_PARTIAL":
            return "label_partial_default"
        if scenario_hint == "PLATED":
            return "plated_default"
        if scenario_hint is None:
            return "no_scenario_hint_default"
        return "default"

    def _has_low_confidence(self, result: EstimationResult) -> bool:
        """Return whether the result should retry through fallback."""
        if not result.items:
            return True
        lowest_confidence = min(item.confidence for item in result.items)
        return lowest_confidence < self.low_confidence_retry_threshold

    def _ensure_not_pro_model(self, model: str) -> None:
        """Prevent automatic Pro model routing."""
        if "pro" in model.lower():
            msg = "Automatic Gemini routing refuses Pro models."
            raise GeminiClientError(msg)


def get_gemini_client() -> GeminiClient:
    """Dependency factory for the Gemini client."""
    return GeminiClient()
