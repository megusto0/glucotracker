"""Append-only evidence for recommendations and the user's subsequent bolus."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.api.schemas import (
    InsulinRecommendationRequest,
    InsulinRecommendationResponse,
)
from glucotracker.application.dose_shadow import shadow_meal_estimate
from glucotracker.application.glucose_dashboard import (
    MODEL_VERSION as CGM_MODEL_VERSION,
)
from glucotracker.application.grouping import GROUPING_VERSION
from glucotracker.application.insulin_recommendation import (
    TOTAL_METHOD_VERSION,
    InsulinCalculation,
)
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.infra.db.models import (
    InsulinRecommendationAction,
    InsulinRecommendationRun,
    Meal,
    NightscoutInsulinEvent,
)
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.repositories.twin import TwinRepository


class InsulinRecommendationAuditService:
    """Persist what the backend generated, including inputs that may later change."""

    def __init__(self, session: Session, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def record(
        self,
        *,
        run_id: UUID,
        created_at: datetime,
        request: InsulinRecommendationRequest,
        response: InsulinRecommendationResponse,
        calculation: InsulinCalculation,
        duration_ms: int,
        client_user_agent: str | None = None,
    ) -> InsulinRecommendationRun:
        """Commit the snapshot before returning the recommendation to the client."""
        meals = list(
            self.session.scalars(
                select(Meal)
                .options(selectinload(Meal.items))
                .where(
                    Meal.owner_id == self.owner_id,
                    Meal.id.in_(calculation.meal.meal_ids),
                )
                .order_by(Meal.eaten_at, Meal.id)
            )
        )
        if len(meals) != len(calculation.meal.meal_ids):
            raise ValueError("Recommendation meals changed before audit storage")
        meal_at = min(meal.eaten_at for meal in meals)
        calculation_at = (
            _local_wall_time(request.calculation_at)
            if request.calculation_at is not None
            else meal_at
        )
        params = TwinRepository(self.session, self.owner_id).get_or_create_params(
            persist=False
        )
        on_board = OnBoardRepository(self.session, self.owner_id)
        iob_fit = on_board.get_active_fit("iob", "rapid")
        cob_fits = on_board.list_active_fits("cob")
        food_from = calculation_at - timedelta(
            minutes=max(params.carb_duration_minutes, 420)
        )
        insulin_from = utc_instant_from_local_wall(
            calculation_at - timedelta(minutes=max(params.dia_minutes, 480))
        )
        insulin_to = utc_instant_from_local_wall(calculation_at)
        prior_meals = list(
            self.session.scalars(
                select(Meal)
                .where(
                    Meal.owner_id == self.owner_id,
                    Meal.eaten_at >= food_from,
                    Meal.eaten_at <= calculation_at,
                )
                .order_by(Meal.eaten_at, Meal.id)
            )
        )
        prior_insulin = list(
            self.session.scalars(
                select(NightscoutInsulinEvent)
                .where(
                    NightscoutInsulinEvent.owner_id == self.owner_id,
                    NightscoutInsulinEvent.timestamp >= insulin_from,
                    NightscoutInsulinEvent.timestamp <= insulin_to,
                )
                .order_by(NightscoutInsulinEvent.timestamp, NightscoutInsulinEvent.id)
            )
        )
        input_snapshot = {
            "schema_version": 1,
            "client_user_agent": client_user_agent[:200] if client_user_agent else None,
            "meal_inputs": [_meal_input(meal) for meal in meals],
            "therapy_params": {
                "id": params.id,
                "icr_morning": params.icr_morning,
                "icr_day": params.icr_day,
                "icr_evening": params.icr_evening,
                "morning_start_minutes": params.morning_start_minutes,
                "day_start_minutes": params.day_start_minutes,
                "evening_start_minutes": params.evening_start_minutes,
                "isf": params.isf,
                "dia_minutes": params.dia_minutes,
                "carb_duration_minutes": params.carb_duration_minutes,
                "insulin_therapy": params.insulin_therapy,
                "last_fit_method": params.last_fit_method,
                "last_fit_at": params.last_fit_at,
            },
            "active_iob_fit": _fit_input(iob_fit),
            "active_cob_fits": [_fit_input(fit) for fit in cob_fits],
            "correction_cgm_sensor_id": calculation.correction.sensor_session_id,
            "correction_cgm_points": [
                point.model_dump(mode="json")
                for point in calculation.correction.cgm_points
            ],
            "correction_trend_projection": (
                asdict(calculation.correction.trend_projection)
                if calculation.correction.trend_projection is not None
                else None
            ),
            "prior_meals": [
                {
                    "id": meal.id,
                    "eaten_at": meal.eaten_at,
                    "carbs_g": meal.total_carbs_g,
                    "kcal": meal.total_kcal,
                    "fat_g": meal.total_fat_g,
                    "protein_g": meal.total_protein_g,
                }
                for meal in prior_meals
            ],
            "prior_insulin": [
                {
                    "id": event.id,
                    "timestamp": event.timestamp,
                    "insulin_units": event.insulin_units,
                    "event_type": event.event_type,
                    "insulin_type": event.insulin_type,
                    "entered_by": event.entered_by,
                    "source_key": event.source_key,
                }
                for event in prior_insulin
            ],
            # Recorded, never applied: the frozen alternative the next weeks
            # of outcomes will judge (application/dose_shadow.py).
            "shadow_meal_estimate": _shadow_input(calculation, meals),
            "versions": {
                "meal_method": calculation.meal.method_version,
                "total_method": TOTAL_METHOD_VERSION,
                "episode_grouping": GROUPING_VERSION,
                "cgm_display": CGM_MODEL_VERSION,
            },
        }
        row = InsulinRecommendationRun(
            id=run_id,
            owner_id=self.owner_id,
            created_at=created_at,
            meal_at=meal_at,
            calculation_at=calculation_at,
            meal_key="|".join(sorted(str(item) for item in response.meal_ids)),
            method_version=response.method_version,
            status=response.status,
            total_recommended_units=response.total_recommended_units,
            duration_ms=max(0, duration_ms),
            request_json=request.model_dump(mode="json"),
            input_json=jsonable_encoder(input_snapshot),
            response_json=response.model_dump(mode="json"),
        )
        self.session.add(row)
        self.session.commit()
        return row

    def list_recent(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[InsulinRecommendationRun]:
        return list(
            self.session.scalars(
                select(InsulinRecommendationRun)
                .where(InsulinRecommendationRun.owner_id == self.owner_id)
                .order_by(
                    InsulinRecommendationRun.created_at.desc(),
                    InsulinRecommendationRun.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )

    def get(self, run_id: UUID) -> InsulinRecommendationRun | None:
        return self.session.scalar(
            select(InsulinRecommendationRun).where(
                InsulinRecommendationRun.id == run_id,
                InsulinRecommendationRun.owner_id == self.owner_id,
            )
        )

    def actions(self, run_id: UUID) -> list[InsulinRecommendationAction]:
        return list(
            self.session.scalars(
                select(InsulinRecommendationAction)
                .where(
                    InsulinRecommendationAction.owner_id == self.owner_id,
                    InsulinRecommendationAction.recommendation_run_id == run_id,
                )
                .order_by(
                    InsulinRecommendationAction.created_at,
                    InsulinRecommendationAction.id,
                )
            )
        )


def _shadow_input(
    calculation: InsulinCalculation,
    meals: list[Meal],
) -> dict[str, Any] | None:
    shadow = shadow_meal_estimate(
        production_meal_units=calculation.meal.recommended_units,
        carbs_g=sum(float(meal.total_carbs_g or 0) for meal in meals),
        fat_g=sum(float(meal.total_fat_g or 0) for meal in meals),
        trend_mmol_l_per_min=calculation.correction.trend_mmol_l_per_min,
        after_sleep=calculation.meal.icr_after_sleep,
    )
    return asdict(shadow) if shadow is not None else None


def _meal_input(meal: Meal) -> dict[str, Any]:
    return {
        "id": meal.id,
        "eaten_at": meal.eaten_at,
        "updated_at": meal.updated_at,
        "title": meal.title,
        "source": meal.source.value,
        "carbs_g": meal.total_carbs_g,
        "kcal": meal.total_kcal,
        "protein_g": meal.total_protein_g,
        "fat_g": meal.total_fat_g,
        "fiber_g": meal.total_fiber_g,
        "confidence": meal.confidence,
        "model_used": meal.model_used,
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "grams": item.grams,
                "carbs_g": item.carbs_g,
                "kcal": item.kcal,
                "protein_g": item.protein_g,
                "fat_g": item.fat_g,
                "fiber_g": item.fiber_g,
                "source_kind": item.source_kind.value,
                "confidence": item.confidence,
            }
            for item in meal.items
        ],
    }


def _fit_input(fit: Any) -> dict[str, Any] | None:
    if fit is None:
        return None
    return {
        "id": fit.id,
        "kind": fit.kind,
        "scope_key": fit.scope_key,
        "model_version": fit.model_version,
        "confidence": fit.confidence,
        "params": fit.params_json,
        "fitted_at": fit.fitted_at,
    }
