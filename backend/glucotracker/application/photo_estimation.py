"""Application service for Gemini photo-estimation orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    EstimateCreatedDraftResponse,
    EstimateMealRequest,
    EstimateMealResponse,
)
from glucotracker.application.daily_totals import DailyTotalsService
from glucotracker.domain.entities import PhotoReferenceKind
from glucotracker.domain.estimation import normalize_estimation_to_items
from glucotracker.infra.db.models import AIRun, Meal, Photo
from glucotracker.infra.gemini.client import (
    PHOTO_ESTIMATION_PROMPT_VERSION,
    GeminiClient,
    GeminiClientError,
    PhotoInput,
)
from glucotracker.infra.gemini.schemas import EstimationResult


@dataclass(frozen=True)
class PhotoEstimationDependencies:
    """Helper operations used by the photo-estimation application service."""

    get_meal: Callable[[Session, UUID], Meal]
    load_pattern_context: Callable[[Session, list[UUID]], list[dict[str, Any]]]
    load_product_context: Callable[[Session, list[UUID]], list[dict[str, Any]]]
    ordered_photos: Callable[[list[Photo]], list[Photo]]
    photo_inputs: Callable[[list[Photo]], list[PhotoInput]]
    clean_context_note: Callable[[str | None], str | None]
    ai_run_summary: Callable[[GeminiClient], dict[str, Any]]
    photo_reference_kind: Callable[[str], PhotoReferenceKind]
    photo_scenario: Callable[[EstimationResult], Any]
    products_by_barcode: Callable[[Session, EstimationResult], dict[str, Any]]
    load_known_components: Callable[[Session], list[Any]]
    attach_user_context_to_items: Callable[[list[Any], str | None], None]
    set_photo_ids: Callable[[list[Any], list[Photo]], None]
    items_json: Callable[[list[Any]], list[dict[str, Any]]]
    save_suggested_items_as_drafts: Callable[..., list[EstimateCreatedDraftResponse]]
    estimation_response: Callable[..., EstimateMealResponse]


class PhotoEstimationService:
    """Coordinate Gemini calls, AI run storage, normalization, and draft saving."""

    def __init__(
        self,
        session: Session,
        gemini_client: GeminiClient,
        dependencies: PhotoEstimationDependencies,
    ) -> None:
        self.session = session
        self.gemini_client = gemini_client
        self.dependencies = dependencies

    def estimate(
        self,
        *,
        meal_id: UUID,
        payload: EstimateMealRequest,
        save_draft: bool,
    ) -> EstimateMealResponse:
        """Run Gemini estimation and optionally save suggestions as drafts."""
        deps = self.dependencies
        meal = deps.get_meal(self.session, meal_id)
        if not meal.photos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Meal has no photos to estimate.",
            )

        patterns_context = deps.load_pattern_context(
            self.session,
            payload.use_patterns,
        )
        products_context = deps.load_product_context(
            self.session,
            payload.use_products,
        )
        ordered_photos = deps.ordered_photos(meal.photos)
        photo_inputs = deps.photo_inputs(ordered_photos)
        model_override = None if payload.model == "default" else payload.model
        context_note = deps.clean_context_note(payload.context_note)

        try:
            result = self.gemini_client.estimate_photos(
                photo_inputs,
                patterns_context=patterns_context,
                products_context=products_context,
                scenario_hint=payload.scenario_hint,
                model_override=model_override,
                user_context=context_note,
            )
        except GeminiClientError as exc:
            raise HTTPException(
                status_code=getattr(
                    exc,
                    "http_status_code",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                ),
                detail=str(exc),
            ) from exc

        if getattr(self.gemini_client, "last_fallback_used", False) and any(
            error.get("category") == "overload"
            for error in getattr(self.gemini_client, "last_error_history", [])
        ):
            result.image_quality_warnings.append(
                "Основная модель была перегружена, использована запасная модель."
            )

        result_raw = result.model_dump(mode="json")
        ai_summary = deps.ai_run_summary(self.gemini_client)
        ai_run = AIRun(
            meal_id=meal.id,
            model=getattr(self.gemini_client, "last_used_model", None)
            or self.gemini_client.model,
            prompt_version=PHOTO_ESTIMATION_PROMPT_VERSION,
            provider="gemini",
            model_requested=ai_summary["model_requested"],
            model_used=ai_summary["model_used"],
            fallback_used=ai_summary["fallback_used"],
            status="success",
            request_type="initial_estimate" if save_draft else "estimate",
            source_photo_ids=[str(photo.id) for photo in meal.photos],
            error_history_json=ai_summary["error_history"],
            request_summary={
                "photo_ids": [str(photo.id) for photo in meal.photos],
                "use_patterns": [
                    str(pattern_id) for pattern_id in payload.use_patterns
                ],
                "use_products": [
                    str(product_id) for product_id in payload.use_products
                ],
                "requested_model": payload.model,
                "context_note": context_note,
                "scenario_hint": payload.scenario_hint,
                **ai_summary,
            },
            response_raw=result_raw,
        )
        self.session.add(ai_run)

        first_photo = ordered_photos[0]
        first_photo.gemini_response_raw = result_raw
        first_photo.reference_kind = deps.photo_reference_kind(
            result.reference_object_detected
        )
        first_photo.has_reference_object = (
            first_photo.reference_kind != PhotoReferenceKind.none
        )
        first_photo.scenario = deps.photo_scenario(result)

        suggested_items = normalize_estimation_to_items(
            result,
            products_by_barcode=deps.products_by_barcode(self.session, result),
            known_components=deps.load_known_components(self.session),
        )
        deps.attach_user_context_to_items(suggested_items, context_note)
        deps.set_photo_ids(suggested_items, ordered_photos)
        ai_run.normalized_items_json = deps.items_json(suggested_items)

        created_drafts: list[EstimateCreatedDraftResponse] = []
        if save_draft:
            created_drafts = deps.save_suggested_items_as_drafts(
                source_meal=meal,
                suggested_items=suggested_items,
                result=result,
                photos=ordered_photos,
                session=self.session,
            )
            DailyTotalsService(self.session).schedule_for_meal_times([meal.eaten_at])

        self.session.flush()
        response = deps.estimation_response(
            meal,
            suggested_items,
            result,
            ai_run.id,
            source_photos=ordered_photos,
            created_drafts=created_drafts,
        )
        self.session.commit()
        return response
