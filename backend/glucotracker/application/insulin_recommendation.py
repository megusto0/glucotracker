"""Explainable meal and glucose-correction estimates for manual review.

The meal component comes from comparable personal episodes.  The optional
correction reconstructs glucose, trend, personal ISF, and prior IOB at the
meal time.  It never creates an insulin record, and it withholds a total when
the context is incomplete, low, or falling quickly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite, log
from statistics import median
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    GlucoseDashboardInsulinEvent,
    GlucoseDashboardPoint,
)
from glucotracker.application.episodes import EpisodeComponent, EpisodeQueryService
from glucotracker.application.glucose_dashboard import (
    GlucoseDashboardService,
    _local_wall_from_utc,
    _remaining_on_board,
)
from glucotracker.application.on_board.classification import (
    is_rapid_insulin_event,
    normalized_text,
)
from glucotracker.application.twin.kernels import PersonalizedInsulinKernel
from glucotracker.infra.db.models import Meal
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.repositories.twin import TwinRepository

HISTORY_WINDOW = timedelta(days=180)
MAX_MATCHES = 8
MIN_MATCHES = 3
METHOD_VERSION = "historical-episode-median-v1"
CORRECTION_LOOKBACK = timedelta(minutes=20)
CORRECTION_PROJECTION_MINUTES = 15
MAX_PROJECTED_CHANGE_MMOL_L = 2.0
MAX_CGM_AGE = timedelta(minutes=15)
MIN_TREND_SPAN_MINUTES = 5
FAST_FALL_MMOL_L_PER_MIN = -1 / 18.0182
LOW_GLUCOSE_MMOL_L = 3.9


@dataclass(frozen=True)
class HistoricalDoseMatch:
    """One prior food/insulin episode scaled to the target carbohydrates."""

    occurred_at: datetime
    meal_ids: list[UUID]
    carbs_g: float
    insulin_units: float
    scaled_units: float
    similarity: float


@dataclass(frozen=True)
class HistoricalDoseEstimate:
    """Backend result before API serialization."""

    status: Literal["ready", "insufficient_history", "meal_without_carbs"]
    meal_ids: list[UUID]
    target_carbs_g: float
    target_kcal: float
    recommended_units: float | None
    range_low_units: float | None
    range_high_units: float | None
    confidence: Literal["none", "low", "medium", "high"]
    matches: list[HistoricalDoseMatch]
    method_version: str = METHOD_VERSION


CorrectionStatus = Literal[
    "ready",
    "not_needed",
    "target_required",
    "isf_unavailable",
    "glucose_unavailable",
    "trend_unavailable",
    "low_or_falling",
]


@dataclass(frozen=True)
class CorrectionEstimate:
    """Correction component reconstructed at the selected meal time."""

    status: CorrectionStatus
    units: float | None = None
    target_mmol_l: float | None = None
    glucose_mmol_l: float | None = None
    projected_glucose_mmol_l: float | None = None
    trend_mmol_l_per_min: float | None = None
    isf_mmol_l_per_unit: float | None = None
    iob_units: float | None = None


@dataclass(frozen=True)
class InsulinCalculation:
    """Meal estimate, correction context, and a total when both are safe."""

    meal: HistoricalDoseEstimate
    correction: CorrectionEstimate
    total_recommended_units: float | None
    total_range_low_units: float | None
    total_range_high_units: float | None


class HistoricalInsulinRecommendationService:
    """Calculate a historical meal reference and optional correction."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.repository = OnBoardRepository(session, user_id)
        self.episodes = EpisodeQueryService(session, user_id)

    def estimate(
        self,
        meal_ids: list[UUID],
        correction_target_mmol_l: float | None = None,
    ) -> InsulinCalculation | None:
        """Return None when any requested meal is absent or not accepted."""
        unique_ids = list(dict.fromkeys(meal_ids))
        meals = self.repository.list_accepted_meals_by_ids(unique_ids)
        if len(meals) != len(unique_ids):
            return None

        meal_estimate = self._meal_estimate(unique_ids, meals)
        correction = self._correction_estimate(
            meals,
            correction_target_mmol_l,
        )
        correction_is_usable = correction.status in {"ready", "not_needed"}
        correction_units = correction.units if correction_is_usable else None
        total = (
            _round_dose(meal_estimate.recommended_units + correction_units)
            if meal_estimate.recommended_units is not None
            and correction_units is not None
            else None
        )
        total_low = (
            _round_dose(meal_estimate.range_low_units + correction_units)
            if meal_estimate.range_low_units is not None
            and correction_units is not None
            else None
        )
        total_high = (
            _round_dose(meal_estimate.range_high_units + correction_units)
            if meal_estimate.range_high_units is not None
            and correction_units is not None
            else None
        )
        return InsulinCalculation(
            meal=meal_estimate,
            correction=correction,
            total_recommended_units=total,
            total_range_low_units=total_low,
            total_range_high_units=total_high,
        )

    def _meal_estimate(
        self,
        unique_ids: list[UUID],
        meals: list[Meal],
    ) -> HistoricalDoseEstimate:
        """Return the historical meal-only component."""
        target_carbs = sum(float(meal.total_carbs_g or 0) for meal in meals)
        target_kcal = sum(float(meal.total_kcal or 0) for meal in meals)
        if target_carbs <= 0:
            return HistoricalDoseEstimate(
                status="meal_without_carbs",
                meal_ids=unique_ids,
                target_carbs_g=round(target_carbs, 1),
                target_kcal=round(target_kcal, 1),
                recommended_units=None,
                range_low_units=None,
                range_high_units=None,
                confidence="none",
                matches=[],
            )

        target_at = min(meal.eaten_at for meal in meals)
        components = self.episodes.components(
            target_at - HISTORY_WINDOW,
            target_at,
        )
        candidates = [
            candidate
            for component in components
            if (
                candidate := _match_from_component(
                    component,
                    target_at=target_at,
                    target_carbs=target_carbs,
                    target_kcal=target_kcal,
                    excluded_meal_ids=set(unique_ids),
                )
            )
            is not None
        ]
        matches = sorted(
            candidates,
            key=lambda candidate: (-candidate.similarity, candidate.occurred_at),
        )[:MAX_MATCHES]
        if len(matches) < MIN_MATCHES:
            return HistoricalDoseEstimate(
                status="insufficient_history",
                meal_ids=unique_ids,
                target_carbs_g=round(target_carbs, 1),
                target_kcal=round(target_kcal, 1),
                recommended_units=None,
                range_low_units=None,
                range_high_units=None,
                confidence="none",
                matches=matches,
            )

        scaled = sorted(match.scaled_units for match in matches)
        recommendation = _round_dose(median(scaled))
        low = _round_dose(_percentile(scaled, 0.25))
        high = _round_dose(_percentile(scaled, 0.75))
        spread = (high - low) / recommendation if recommendation > 0 else 1.0
        confidence: Literal["low", "medium", "high"] = (
            "high"
            if len(matches) >= 7 and spread <= 0.35
            else "medium"
            if len(matches) >= 5 and spread <= 0.6
            else "low"
        )
        return HistoricalDoseEstimate(
            status="ready",
            meal_ids=unique_ids,
            target_carbs_g=round(target_carbs, 1),
            target_kcal=round(target_kcal, 1),
            recommended_units=recommendation,
            range_low_units=low,
            range_high_units=high,
            confidence=confidence,
            matches=matches,
        )

    def _correction_estimate(
        self,
        meals: list[Meal],
        target_mmol_l: float | None,
    ) -> CorrectionEstimate:
        """Reconstruct a correction at meal time without counting its own bolus."""
        if target_mmol_l is None:
            return CorrectionEstimate(status="target_required")

        twin_params = TwinRepository(
            self.repository.session,
            self.repository.user_id,
        ).get_or_create_params(persist=False)
        isf = float(twin_params.isf or 0)
        if not isfinite(isf) or isf <= 0:
            return CorrectionEstimate(
                status="isf_unavailable",
                target_mmol_l=target_mmol_l,
            )

        meal_at = min(meal.eaten_at for meal in meals)
        dashboard = GlucoseDashboardService(
            self.repository.session,
            self.repository.user_id,
        ).dashboard(
            meal_at - CORRECTION_LOOKBACK,
            meal_at,
            "normalized",
        )
        points = dashboard.points
        if not points:
            return CorrectionEstimate(
                status="glucose_unavailable",
                target_mmol_l=target_mmol_l,
                isf_mmol_l_per_unit=isf,
            )
        latest = points[-1]
        if (
            meal_at - latest.timestamp > MAX_CGM_AGE
            or "compression_suspected" in latest.flags
            or "jump_suspected" in latest.flags
        ):
            return CorrectionEstimate(
                status="glucose_unavailable",
                target_mmol_l=target_mmol_l,
                glucose_mmol_l=latest.display_value,
                isf_mmol_l_per_unit=isf,
            )

        trend = _trend_mmol_l_per_min(points)
        if trend is None:
            return CorrectionEstimate(
                status="trend_unavailable",
                target_mmol_l=target_mmol_l,
                glucose_mmol_l=latest.display_value,
                isf_mmol_l_per_unit=isf,
            )

        projected_change = max(
            -MAX_PROJECTED_CHANGE_MMOL_L,
            min(
                MAX_PROJECTED_CHANGE_MMOL_L,
                trend * CORRECTION_PROJECTION_MINUTES,
            ),
        )
        projected = latest.display_value + projected_change
        iob_units = self._prior_iob_units(
            meals,
            as_of=meal_at,
            dia_minutes=twin_params.dia_minutes,
        )
        context = {
            "target_mmol_l": round(target_mmol_l, 1),
            "glucose_mmol_l": round(latest.display_value, 1),
            "projected_glucose_mmol_l": round(projected, 1),
            "trend_mmol_l_per_min": round(trend, 3),
            "isf_mmol_l_per_unit": round(isf, 2),
            "iob_units": round(iob_units, 2),
        }
        if (
            latest.display_value < LOW_GLUCOSE_MMOL_L
            or projected < LOW_GLUCOSE_MMOL_L
            or trend <= FAST_FALL_MMOL_L_PER_MIN
        ):
            return CorrectionEstimate(status="low_or_falling", **context)

        gross_units = (projected - target_mmol_l) / isf
        net_units = gross_units - iob_units
        if net_units <= 0:
            return CorrectionEstimate(status="not_needed", units=0.0, **context)
        return CorrectionEstimate(
            status="ready",
            units=_round_dose(min(net_units, 100)),
            **context,
        )

    def _prior_iob_units(
        self,
        meals: list[Meal],
        *,
        as_of: datetime,
        dia_minutes: int,
    ) -> float:
        """Return active rapid insulin, excluding insulin linked to this meal."""
        meal_ids = {meal.id for meal in meals}
        components = self.episodes.components(
            as_of - timedelta(hours=2),
            as_of + timedelta(hours=2),
        )
        excluded_insulin_ids = {
            event.id
            for component in components
            if meal_ids.intersection(meal.id for meal in component.meals)
            for event in component.insulin
        }
        on_board_fit = self.repository.get_active_fit("iob", "rapid")
        kernel: PersonalizedInsulinKernel | None = None
        if on_board_fit is not None:
            try:
                kernel = PersonalizedInsulinKernel.from_mapping(
                    on_board_fit.params_json
                )
            except ValueError:
                kernel = None
        horizon = max(dia_minutes, 8 * 60 if kernel is not None else dia_minutes)
        rows = self.repository.list_training_insulin(
            as_of - timedelta(minutes=horizon),
            as_of,
        )
        events = [
            GlucoseDashboardInsulinEvent(
                timestamp=_local_wall_from_utc(row.timestamp),
                insulin_units=row.insulin_units,
                event_type=row.event_type,
                insulin_type=row.insulin_type,
                notes=row.notes,
            )
            for row in rows
            if row.id not in excluded_insulin_ids
            and is_rapid_insulin_event(
                insulin_type=row.insulin_type,
                event_type=row.event_type,
            )
        ]
        units, _ = _remaining_on_board(
            events,
            as_of=as_of,
            duration_minutes=dia_minutes,
            amount=lambda event: event.insulin_units,
            decay="insulin_pd",
            insulin_kernel=kernel,
        )
        return units


def _match_from_component(
    component: EpisodeComponent,
    *,
    target_at: datetime,
    target_carbs: float,
    target_kcal: float,
    excluded_meal_ids: set[UUID],
) -> HistoricalDoseMatch | None:
    meals = component.meals
    if (
        not meals
        or not component.insulin
        or any(meal.id in excluded_meal_ids for meal in meals)
    ):
        return None
    strong_event_ids = {
        pair.insulin_event_id
        for pair in component.pairs
        if pair.source == "manual" or (pair.confidence or 0) >= 0.75
    }
    insulin = [
        event
        for event in component.insulin
        if event.id in strong_event_ids
        and is_rapid_insulin_event(
            insulin_type=event.insulin_type,
            event_type=event.event_type,
        )
        and "correction" not in normalized_text(event.event_type)
    ]
    if not insulin:
        return None
    carbs = sum(float(meal.total_carbs_g or 0) for meal in meals)
    units = sum(float(getattr(event, "insulin_units", 0) or 0) for event in insulin)
    if carbs <= 0 or units <= 0:
        return None
    carb_scale = target_carbs / carbs
    # Very different episode sizes are poor analogues and can amplify noise.
    if not 0.35 <= carb_scale <= 2.85:
        return None
    scaled_units = units * carb_scale
    if not 0 < scaled_units <= 100:
        return None

    occurred_at = min(meal.eaten_at for meal in meals)
    carb_distance = abs(log(carbs / target_carbs))
    target_minutes = target_at.hour * 60 + target_at.minute
    occurred_minutes = occurred_at.hour * 60 + occurred_at.minute
    raw_minutes = abs(target_minutes - occurred_minutes)
    daypart_distance = min(raw_minutes, 1440 - raw_minutes) / 720
    kcal = sum(float(meal.total_kcal or 0) for meal in meals)
    target_density = target_kcal / target_carbs if target_kcal > 0 else 0
    candidate_density = kcal / carbs if kcal > 0 else 0
    density_distance = (
        min(abs(log(candidate_density / target_density)), 2.0)
        if target_density > 0 and candidate_density > 0
        else 0.5
    )
    distance = carb_distance * 0.65 + daypart_distance * 0.25 + density_distance * 0.1
    return HistoricalDoseMatch(
        occurred_at=occurred_at,
        meal_ids=[meal.id for meal in meals],
        carbs_g=round(carbs, 1),
        insulin_units=round(units, 2),
        scaled_units=_round_dose(scaled_units),
        similarity=round(1 / (1 + distance), 3),
    )


def _percentile(values: list[float], quantile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = position - lower_index
    return values[lower_index] + (values[upper_index] - values[lower_index]) * fraction


def _round_dose(value: float) -> float:
    return round(value * 10) / 10


def _trend_mmol_l_per_min(
    points: list[GlucoseDashboardPoint],
) -> float | None:
    """Return a simple recent slope when at least five minutes are observed."""
    if len(points) < 2:
        return None
    latest = points[-1]
    candidates = [
        point
        for point in points[:-1]
        if latest.timestamp - point.timestamp <= CORRECTION_LOOKBACK
    ]
    if not candidates:
        return None
    first = candidates[0]
    elapsed_minutes = (latest.timestamp - first.timestamp).total_seconds() / 60
    if elapsed_minutes < MIN_TREND_SPAN_MINUTES:
        return None
    return (latest.display_value - first.display_value) / elapsed_minutes
