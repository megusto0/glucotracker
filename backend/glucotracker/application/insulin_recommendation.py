"""Explainable meal and glucose-correction estimates for manual review.

v2 meal component:
  - comparable personal episodes with deferred-bolus reattribution
  - outcome weights from +2h normalized CGM
  - optional ICR blend when twin ICR is configured
  - low/falling pre-meal gate withholds the actionable total

Correction uses normalized CGM, personal ISF, trend, and prior IOB. A default
target is applied when the client omits one. Nothing here creates an insulin
record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import isfinite, log
from statistics import median
from typing import Literal
from uuid import UUID, uuid4

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
from glucotracker.application.glucose_trend_projection import (
    GlucoseTrendProjectionService,
)
from glucotracker.application.nightscout_context import (
    INSULIN_WINDOW_AFTER,
    _local_wall_time,
)
from glucotracker.application.on_board.classification import (
    is_rapid_insulin_event,
    normalized_text,
)
from glucotracker.application.time import (
    utc_instant_from_local_wall as _utc_instant_from_local_wall,
)
from glucotracker.application.twin.kernels import PersonalizedInsulinKernel
from glucotracker.infra.db.models import Meal, NightscoutInsulinEvent, TwinParams
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.repositories.twin import TwinRepository

HISTORY_WINDOW = timedelta(days=180)
MAX_MATCHES = 8
MIN_MATCHES = 3
METHOD_VERSION = "historical-episode-median-v2"
CORRECTION_LOOKBACK = timedelta(minutes=20)
CORRECTION_PROJECTION_MINUTES = 15
MAX_PROJECTED_CHANGE_MMOL_L = 2.0
MAX_CGM_AGE = timedelta(minutes=15)
MIN_TREND_SPAN_MINUTES = 5
# How far ahead a fall is followed before deciding it is dangerous. A rate on
# its own says nothing: -4 mmol/L per hour from 8.8 lands at 5.8, while the same
# rate from 5.5 lands at 2.5. Only the second is a reason to withhold a dose.
FAST_FALL_LOOKAHEAD_MINUTES = 45
LOW_GLUCOSE_MMOL_L = 3.9
TIR_HIGH_MMOL_L = 10.0
VERY_LOW_MMOL_L = 3.0
VERY_HIGH_MMOL_L = 13.0
DEFAULT_CORRECTION_TARGET_MMOL_L = 6.0
# Conservative fallback from the owner's isolated-correction replay audit.
# It remains explicitly labelled ``default``; a trusted manual/personal fit
# still takes precedence.
DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT = 2.8
AUTO_FIT_ISF_MIN_MMOL_L_PER_UNIT = 0.2
AUTO_FIT_ISF_MAX_MMOL_L_PER_UNIT = 8.0
AUTO_FIT_ICR_MIN_G_PER_UNIT = 3.0
AUTO_FIT_ICR_MAX_G_PER_UNIT = 40.0
FIT_BOUNDARY_TOLERANCE = 1e-6

# Deferred coverage: insulin after the standard auto-link window.
DEFERRED_AFTER = INSULIN_WINDOW_AFTER  # 90 minutes
DEFERRED_UNTIL = timedelta(hours=3)
MIN_CARBS_FOR_DEFERRED_G = 15.0
OUTCOME_HORIZON = timedelta(hours=2)
OUTCOME_SAMPLE_WINDOW = timedelta(minutes=20)
# The first plate after a long break needs more insulin per gram: measured over
# 75 days, episodes following a gap of this length implied 7.1 g/U against 8.7
# for the rest. The clock cannot stand in for it — those episodes ran from 06:00
# to 20:00 with a median at 14:00, so the configured morning window caught
# almost none of them, and by hour the morning and day slots are indistinguishable
# (7.7 against 7.9) while only the evening separates.
FIRST_MEAL_GAP = timedelta(hours=7)
FIRST_MEAL_ICR_FACTOR = 7.1 / 8.7
# Floor of the comfortable +2 h landing zone. Finishing between this and the
# hypo threshold is a near miss, so the episode's dose is corrected downward
# rather than being copied as if it had gone well.
OUTCOME_COMFORT_LOW_MMOL_L = 5.0
# Cap on how far one episode's outcome may move its own dose, either way.
MAX_OUTCOME_RESIDUAL_FRACTION = 0.25


@dataclass(frozen=True)
class HistoricalDoseMatch:
    """One prior food/insulin episode scaled to the target carbohydrates."""

    occurred_at: datetime
    meal_ids: list[UUID]
    carbs_g: float
    insulin_units: float
    scaled_units: float
    similarity: float
    deferred_insulin_units: float = 0.0
    outcome_weight: float = 1.0
    glucose_plus_2h_mmol: float | None = None


@dataclass(frozen=True)
class HistoricalDoseEstimate:
    """Backend result before API serialization."""

    status: Literal[
        "ready",
        "insufficient_history",
        "meal_without_carbs",
        "low_or_falling",
    ]
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
IsfSource = Literal["manual", "fitted", "default"]
ProjectionSource = Literal["linear_trend", "forecast"]


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
    isf_source: IsfSource | None = None
    iob_units: float | None = None
    projection_source: ProjectionSource = "linear_trend"
    projection_horizon_minutes: int = CORRECTION_PROJECTION_MINUTES
    projection_calibration_factor: float | None = None


@dataclass(frozen=True)
class InsulinCalculation:
    """Meal estimate, correction context, and a total when both are safe."""

    meal: HistoricalDoseEstimate
    correction: CorrectionEstimate
    total_recommended_units: float | None
    total_range_low_units: float | None
    total_range_high_units: float | None


@dataclass
class _FoodCoverage:
    """Training label for one food episode after deferred reattribution."""

    meals: list[Meal]
    occurred_at: datetime
    carbs_g: float
    kcal: float
    linked_units: float
    deferred_units: float
    event_ids: set[UUID] = field(default_factory=set)

    @property
    def units(self) -> float:
        return self.linked_units + self.deferred_units


@dataclass(frozen=True)
class _InsulinRef:
    event: NightscoutInsulinEvent
    at: datetime
    units: float


class HistoricalInsulinRecommendationService:
    """Calculate a historical meal reference and optional correction."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.repository = OnBoardRepository(session, user_id)
        self.episodes = EpisodeQueryService(session, user_id)
        self._normalized_outcome_cache: dict[datetime, float | None] = {}
        self._preloaded_components: list[EpisodeComponent] | None = None
        self._preloaded_from: datetime | None = None
        self._preloaded_to: datetime | None = None

    def preload_history(self, from_at: datetime, to_at: datetime) -> None:
        """Load one shared history window for several same-day estimates."""
        self._preloaded_from = from_at - HISTORY_WINDOW
        self._preloaded_to = to_at + DEFERRED_UNTIL
        self._preloaded_components = self.episodes.components(
            self._preloaded_from,
            self._preloaded_to,
        )

    def correction_at(
        self,
        at: datetime,
        target_mmol_l: float,
        *,
        excluded_insulin_ids: set[UUID] | None = None,
    ) -> CorrectionEstimate:
        """Reconstruct a standalone correction immediately before its event."""
        before_event = at - timedelta(microseconds=1)
        placeholder = Meal(id=uuid4(), eaten_at=before_event)
        return self._correction_estimate(
            [placeholder],
            target_mmol_l,
            twin_params=TwinRepository(
                self.repository.session,
                self.repository.user_id,
            ).get_or_create_params(persist=False),
            excluded_insulin_ids=excluded_insulin_ids,
        )

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

        twin_params = TwinRepository(
            self.repository.session,
            self.repository.user_id,
        ).get_or_create_params(persist=False)

        effective_target = (
            correction_target_mmol_l
            if correction_target_mmol_l is not None
            else DEFAULT_CORRECTION_TARGET_MMOL_L
        )
        correction = self._correction_estimate(
            meals,
            effective_target,
            twin_params=twin_params,
        )
        meal_estimate = self._meal_estimate(
            unique_ids,
            meals,
            twin_params=twin_params,
        )

        # Safety: no insulin amount is actionable when pre-meal glucose is
        # low/falling. Keep only the historical matches for auditability; even
        # a meal-only number is too easy to misread as a recommendation.
        if correction.status == "low_or_falling":
            meal_estimate = HistoricalDoseEstimate(
                status="low_or_falling",
                meal_ids=meal_estimate.meal_ids,
                target_carbs_g=meal_estimate.target_carbs_g,
                target_kcal=meal_estimate.target_kcal,
                recommended_units=None,
                range_low_units=None,
                range_high_units=None,
                confidence=meal_estimate.confidence,
                matches=meal_estimate.matches,
                method_version=meal_estimate.method_version,
            )
            return InsulinCalculation(
                meal=meal_estimate,
                correction=correction,
                total_recommended_units=None,
                total_range_low_units=None,
                total_range_high_units=None,
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
        *,
        twin_params: TwinParams,
    ) -> HistoricalDoseEstimate:
        """Return the historical meal-only component (v2)."""
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
        # Extend end so deferred boluses after late history meals are visible.
        if (
            self._preloaded_components is not None
            and self._preloaded_from is not None
            and self._preloaded_to is not None
            and self._preloaded_from <= target_at - HISTORY_WINDOW
            and self._preloaded_to >= target_at + DEFERRED_UNTIL
        ):
            components = [
                component
                for component in self._preloaded_components
                if component.end_at >= target_at - HISTORY_WINDOW
                and component.start_at < target_at + DEFERRED_UNTIL
            ]
        else:
            components = self.episodes.components(
                target_at - HISTORY_WINDOW,
                target_at + DEFERRED_UNTIL,
            )
        coverages = _build_food_coverages(
            components,
            excluded_meal_ids=set(unique_ids),
            history_end=target_at,
        )
        base_candidates: list[HistoricalDoseMatch] = []
        for coverage in coverages:
            match = _match_from_coverage(
                coverage,
                target_at=target_at,
                target_carbs=target_carbs,
                target_kcal=target_kcal,
                glucose_plus_2h=None,
            )
            if match is not None:
                base_candidates.append(match)

        # Normalize only a bounded similarity shortlist. This keeps the
        # 180-day read practical and, unlike one long dashboard request,
        # applies the sensor/calibration model active for each episode.
        shortlist = sorted(
            base_candidates,
            key=lambda candidate: (-candidate.similarity, candidate.occurred_at),
        )[: MAX_MATCHES * 3]
        candidates = [
            outcome_match
            for match in shortlist
            if (
                outcome_match := self._with_normalized_outcome(
                    match,
                    isf=(
                        _trusted_isf(twin_params)
                        or DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT
                    ),
                    target_carbs=target_carbs,
                )
            )
            is not None
        ]

        matches = sorted(
            candidates,
            key=lambda candidate: (
                -(candidate.similarity * candidate.outcome_weight),
                candidate.occurred_at,
            ),
        )[:MAX_MATCHES]

        icr_dose = _icr_dose(
            target_carbs,
            target_at,
            twin_params,
            hours_since_previous_meal=_hours_since_previous_meal(
                components,
                target_at,
                excluded_meal_ids=set(unique_ids),
            ),
        )

        if len(matches) < MIN_MATCHES:
            if icr_dose is not None:
                return HistoricalDoseEstimate(
                    status="ready",
                    meal_ids=unique_ids,
                    target_carbs_g=round(target_carbs, 1),
                    target_kcal=round(target_kcal, 1),
                    recommended_units=_round_dose(icr_dose),
                    range_low_units=_round_dose(icr_dose * 0.85),
                    range_high_units=_round_dose(icr_dose * 1.15),
                    confidence="low",
                    matches=matches,
                )
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

        scaled = [match.scaled_units for match in matches]
        weights = [match.outcome_weight for match in matches]
        history_median = _round_dose(_weighted_median(scaled, weights))
        low = _round_dose(_weighted_percentile(scaled, weights, 0.25))
        high = _round_dose(_weighted_percentile(scaled, weights, 0.75))

        recommendation = history_median
        if icr_dose is not None:
            # More history and tighter spread → trust personal matches more.
            spread = (high - low) / history_median if history_median > 0 else 1.0
            history_weight = min(1.0, len(matches) / 8.0) * (
                0.85 if spread <= 0.35 else 0.7 if spread <= 0.6 else 0.55
            )
            recommendation = _round_dose(
                history_weight * history_median + (1.0 - history_weight) * icr_dose
            )
            low = _round_dose(min(low, recommendation, icr_dose))
            high = _round_dose(max(high, recommendation, icr_dose))

        spread = (
            (high - low) / recommendation
            if recommendation and recommendation > 0
            else 1.0
        )
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
        *,
        twin_params: TwinParams | None = None,
        excluded_insulin_ids: set[UUID] | None = None,
    ) -> CorrectionEstimate:
        """Reconstruct a correction at meal time without counting its own bolus."""
        if target_mmol_l is None:
            return CorrectionEstimate(status="target_required")

        if twin_params is None:
            twin_params = TwinRepository(
                self.repository.session,
                self.repository.user_id,
            ).get_or_create_params(persist=False)
        trusted_isf = _trusted_isf(twin_params)
        isf = trusted_isf or DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT
        isf_source: IsfSource = (
            "default"
            if trusted_isf is None
            else "manual"
            if twin_params.last_fit_method == "manual"
            else "fitted"
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
                isf_source=isf_source,
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
                isf_source=isf_source,
            )

        trend = _trend_mmol_l_per_min(points)
        if trend is None:
            return CorrectionEstimate(
                status="trend_unavailable",
                target_mmol_l=target_mmol_l,
                glucose_mmol_l=latest.display_value,
                isf_mmol_l_per_unit=isf,
                isf_source=isf_source,
            )

        projected_change = max(
            -MAX_PROJECTED_CHANGE_MMOL_L,
            min(
                MAX_PROJECTED_CHANGE_MMOL_L,
                trend * CORRECTION_PROJECTION_MINUTES,
            ),
        )
        projected = latest.display_value + projected_change
        projection_source: ProjectionSource = "linear_trend"
        projection_horizon_minutes = CORRECTION_PROJECTION_MINUTES

        # A straight line through the last 20 minutes cannot tell a rise that is
        # about to stall from one that is still accelerating. The prospective
        # forecast models the same "no new food or insulin" counterfactual the
        # correction is asking about, so prefer it when one is fresh enough.
        trend_projection = GlucoseTrendProjectionService(
            self.repository.session,
            self.repository.user_id,
        ).project(_utc_instant_from_local_wall(meal_at))
        if trend_projection.is_usable:
            assert trend_projection.projected_mmol_l is not None
            forecast_move = trend_projection.move_mmol_l or 0.0
            projected = latest.display_value + forecast_move
            projection_source = "forecast"
            projection_horizon_minutes = trend_projection.horizon_minutes

        iob_units = self._prior_iob_units(
            meals,
            as_of=meal_at,
            dia_minutes=twin_params.dia_minutes,
            additionally_excluded_ids=excluded_insulin_ids,
        )
        context = {
            "target_mmol_l": round(target_mmol_l, 1),
            "glucose_mmol_l": round(latest.display_value, 1),
            "projected_glucose_mmol_l": round(projected, 1),
            "trend_mmol_l_per_min": round(trend, 3),
            "isf_mmol_l_per_unit": round(isf, 2),
            "isf_source": isf_source,
            "iob_units": round(iob_units, 2),
            "projection_source": projection_source,
            "projection_horizon_minutes": projection_horizon_minutes,
            "projection_calibration_factor": (
                trend_projection.calibration_factor
                if projection_source == "forecast"
                else None
            ),
        }
        # Triggering on rate alone hid the entire calculation - meal dose
        # included - at 8.8 mmol/L falling 4.0/h with 76 g about to be eaten,
        # where the food outweighs the trend several times over. Follow the fall
        # far enough to see where it actually lands instead. The trend is
        # already reflected in ``projected``, so the correction shrinks with it
        # without needing a second, blunter guard.
        fall_landing = (
            projected
            if projection_source == "forecast"
            else latest.display_value + trend * FAST_FALL_LOOKAHEAD_MINUTES
        )
        if (
            latest.display_value < LOW_GLUCOSE_MMOL_L
            or projected < LOW_GLUCOSE_MMOL_L
            or fall_landing < LOW_GLUCOSE_MMOL_L
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

    def _with_normalized_outcome(
        self,
        match: HistoricalDoseMatch,
        *,
        isf: float | None,
        target_carbs: float,
    ) -> HistoricalDoseMatch | None:
        """Apply the episode's own sensor normalization and +2 h outcome."""
        target = match.occurred_at + OUTCOME_HORIZON
        if target not in self._normalized_outcome_cache:
            glucose: float | None = None
            try:
                dashboard = GlucoseDashboardService(
                    self.repository.session,
                    self.repository.user_id,
                ).dashboard(
                    target - OUTCOME_SAMPLE_WINDOW,
                    target + OUTCOME_SAMPLE_WINDOW,
                    "normalized",
                )
                if dashboard.points:
                    point = min(
                        dashboard.points,
                        key=lambda candidate: abs(candidate.timestamp - target),
                    )
                    if abs(point.timestamp - target) <= OUTCOME_SAMPLE_WINDOW and not {
                        "compression_suspected",
                        "jump_suspected",
                    }.intersection(point.flags):
                        glucose = float(point.display_value)
            except Exception:
                glucose = None
            self._normalized_outcome_cache[target] = glucose
        glucose = self._normalized_outcome_cache[target]
        if glucose is None:
            return match
        # A very low outcome carries no usable ratio: the episode was rescued
        # with carbs, so its dose teaches nothing except "less than this".
        if glucose < VERY_LOW_MMOL_L:
            return None
        # Otherwise correct the historical dose toward the amount that would
        # have landed in range. This has to be signed: an episode that finished
        # just above the low threshold is a near miss, not an exemplar, and an
        # upward-only residual made the estimator drift high over time.
        residual_units = 0.0
        if isf is not None and isfinite(isf) and isf > 0:
            carb_scale = target_carbs / match.carbs_g
            if glucose > TIR_HIGH_MMOL_L:
                excess = glucose - TIR_HIGH_MMOL_L
            elif glucose < OUTCOME_COMFORT_LOW_MMOL_L:
                excess = glucose - OUTCOME_COMFORT_LOW_MMOL_L
            else:
                excess = 0.0
            residual_units = max(
                -match.scaled_units * MAX_OUTCOME_RESIDUAL_FRACTION,
                min(
                    (excess / isf) * carb_scale,
                    match.scaled_units * MAX_OUTCOME_RESIDUAL_FRACTION,
                ),
            )
        return HistoricalDoseMatch(
            occurred_at=match.occurred_at,
            meal_ids=match.meal_ids,
            carbs_g=match.carbs_g,
            insulin_units=match.insulin_units,
            scaled_units=_round_dose(match.scaled_units + residual_units),
            similarity=match.similarity,
            deferred_insulin_units=match.deferred_insulin_units,
            outcome_weight=_outcome_weight(glucose),
            glucose_plus_2h_mmol=round(glucose, 1),
        )

    def _prior_iob_units(
        self,
        meals: list[Meal],
        *,
        as_of: datetime,
        dia_minutes: int,
        additionally_excluded_ids: set[UUID] | None = None,
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
        excluded_insulin_ids.update(additionally_excluded_ids or set())
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


def _build_food_coverages(
    components: list[EpisodeComponent],
    *,
    excluded_meal_ids: set[UUID],
    history_end: datetime,
) -> list[_FoodCoverage]:
    """Build per-food training doses with deferred bolus reattribution."""
    food_components = [
        component
        for component in components
        if component.meals
        and not any(meal.id in excluded_meal_ids for meal in component.meals)
        and min(meal.eaten_at for meal in component.meals) < history_end
    ]
    food_components.sort(key=lambda component: component.start_at)

    coverages: list[_FoodCoverage] = []
    for component in food_components:
        meals = sorted(component.meals, key=lambda meal: meal.eaten_at)
        carbs = sum(float(meal.total_carbs_g or 0) for meal in meals)
        kcal = sum(float(meal.total_kcal or 0) for meal in meals)
        linked_events = _strong_meal_boluses(component)
        linked_units = sum(float(event.insulin_units or 0) for event in linked_events)
        coverages.append(
            _FoodCoverage(
                meals=meals,
                occurred_at=meals[0].eaten_at,
                carbs_g=carbs,
                kcal=kcal,
                linked_units=linked_units,
                deferred_units=0.0,
                event_ids={event.id for event in linked_events},
            )
        )

    # All rapid insulin with local timestamps (food-linked and free).
    insulin_refs: list[_InsulinRef] = []
    seen_ids: set[UUID] = set()
    for component in components:
        for event in component.insulin:
            if event.id in seen_ids:
                continue
            if not is_rapid_insulin_event(
                insulin_type=event.insulin_type,
                event_type=event.event_type,
            ):
                continue
            units = float(event.insulin_units or 0)
            if units <= 0:
                continue
            seen_ids.add(event.id)
            insulin_refs.append(
                _InsulinRef(
                    event=event,
                    at=_local_wall_time(event.timestamp),
                    units=units,
                )
            )
    insulin_refs.sort(key=lambda item: item.at)

    # Map event -> coverage index for currently linked meal boluses.
    owner: dict[UUID, int] = {}
    for index, coverage in enumerate(coverages):
        for event_id in coverage.event_ids:
            owner[event_id] = index

    # Attach deferred coverage to earlier food.
    #
    # This used to run only for episodes with no linked bolus at all, so a meal
    # that got a bolus at the plate and a follow-up an hour later was labelled
    # with the first dose alone. Measured over 75 days: 62 of 201 food episodes
    # had both, and 232 U of the 709 involved — a third — never reached the
    # training label. The estimator then learned the under-dosed first bolus,
    # recommended it, and the follow-up it provoked was discarded again.
    #
    # Stealing a bolus already attributed to a later meal still requires the
    # episode to be uncovered: unowned insulin is evidence about this meal,
    # another meal's bolus is not.
    for index, coverage in enumerate(coverages):
        if coverage.carbs_g < MIN_CARBS_FOR_DEFERRED_G:
            continue
        under_covered = coverage.linked_units <= 0

        meal_at = coverage.occurred_at
        window_start = meal_at + DEFERRED_AFTER
        window_end = meal_at + DEFERRED_UNTIL
        next_meal_at = (
            coverages[index + 1].occurred_at if index + 1 < len(coverages) else None
        )

        stealable = insulin_refs if under_covered else []
        for ref in stealable:
            if "correction" in normalized_text(ref.event.event_type):
                continue
            if ref.at <= window_start or ref.at > window_end:
                continue
            # Prefer not to pull boluses that clearly belong deep inside a later meal.
            if next_meal_at is not None and ref.at > next_meal_at + timedelta(
                minutes=30
            ):
                continue

            current_owner = owner.get(ref.event.id)
            if current_owner is not None and current_owner <= index:
                continue
            if current_owner is not None and current_owner > index:
                # Steal from later meal episode for training only.
                later = coverages[current_owner]
                if ref.event.id in later.event_ids:
                    # Was counted as linked on later — move to deferred on this.
                    if later.linked_units >= ref.units:
                        later.linked_units = max(0.0, later.linked_units - ref.units)
                    else:
                        later.deferred_units = max(
                            0.0, later.deferred_units - ref.units
                        )
                    later.event_ids.discard(ref.event.id)

            coverage.deferred_units += ref.units
            coverage.event_ids.add(ref.event.id)
            owner[ref.event.id] = index

        # Free (unassigned) rapid insulin in the deferred window.
        for ref in insulin_refs:
            if ref.event.id in owner:
                continue
            if "correction" in normalized_text(ref.event.event_type):
                # A labelled correction may coincide with delayed digestion,
                # but treating it as meal coverage pollutes the learned ICR.
                continue
            if ref.at <= window_start or ref.at > window_end:
                continue
            if next_meal_at is not None and ref.at > next_meal_at + timedelta(
                minutes=30
            ):
                continue
            coverage.deferred_units += ref.units
            coverage.event_ids.add(ref.event.id)
            owner[ref.event.id] = index

    return coverages


def _strong_meal_boluses(
    component: EpisodeComponent,
) -> list[NightscoutInsulinEvent]:
    strong_event_ids = {
        pair.insulin_event_id
        for pair in component.pairs
        if pair.source == "manual" or (pair.confidence or 0) >= 0.75
    }
    return [
        event
        for event in component.insulin
        if event.id in strong_event_ids
        and is_rapid_insulin_event(
            insulin_type=event.insulin_type,
            event_type=event.event_type,
        )
        and "correction" not in normalized_text(event.event_type)
    ]


def _match_from_coverage(
    coverage: _FoodCoverage,
    *,
    target_at: datetime,
    target_carbs: float,
    target_kcal: float,
    glucose_plus_2h: float | None,
) -> HistoricalDoseMatch | None:
    units = coverage.units
    carbs = coverage.carbs_g
    if carbs <= 0 or units <= 0:
        return None
    carb_scale = target_carbs / carbs
    if not 0.35 <= carb_scale <= 2.85:
        return None
    scaled_units = units * carb_scale
    if not 0 < scaled_units <= 100:
        return None

    occurred_at = coverage.occurred_at
    carb_distance = abs(log(carbs / target_carbs))
    target_minutes = target_at.hour * 60 + target_at.minute
    occurred_minutes = occurred_at.hour * 60 + occurred_at.minute
    raw_minutes = abs(target_minutes - occurred_minutes)
    daypart_distance = min(raw_minutes, 1440 - raw_minutes) / 720
    kcal = coverage.kcal
    target_density = target_kcal / target_carbs if target_kcal > 0 else 0
    candidate_density = kcal / carbs if kcal > 0 else 0
    density_distance = (
        min(abs(log(candidate_density / target_density)), 2.0)
        if target_density > 0 and candidate_density > 0
        else 0.5
    )
    distance = carb_distance * 0.65 + daypart_distance * 0.25 + density_distance * 0.1

    weight = _outcome_weight(glucose_plus_2h)

    return HistoricalDoseMatch(
        occurred_at=occurred_at,
        meal_ids=[meal.id for meal in coverage.meals],
        carbs_g=round(carbs, 1),
        insulin_units=round(units, 2),
        scaled_units=_round_dose(scaled_units),
        similarity=round(1 / (1 + distance), 3),
        deferred_insulin_units=round(coverage.deferred_units, 2),
        outcome_weight=round(weight, 3),
        glucose_plus_2h_mmol=(
            round(glucose_plus_2h, 1) if glucose_plus_2h is not None else None
        ),
    )


def _outcome_weight(glucose_plus_2h: float | None) -> float:
    """Prefer historical episodes that landed in range at +2h."""
    if glucose_plus_2h is None:
        return 0.6
    if LOW_GLUCOSE_MMOL_L <= glucose_plus_2h <= TIR_HIGH_MMOL_L:
        return 1.0
    if glucose_plus_2h < VERY_LOW_MMOL_L or glucose_plus_2h > VERY_HIGH_MMOL_L:
        return 0.15
    return 0.4


def _hours_since_previous_meal(
    components: list[EpisodeComponent],
    target_at: datetime,
    *,
    excluded_meal_ids: set[UUID],
) -> float | None:
    """Hours from the last real meal to this one, or None when unknown."""
    previous = [
        meal.eaten_at
        for component in components
        for meal in component.meals
        if meal.id not in excluded_meal_ids
        and meal.eaten_at < target_at
        and float(meal.total_carbs_g or 0) >= 10.0
    ]
    if not previous:
        return None
    return (target_at - max(previous)).total_seconds() / 3600.0


def _icr_dose(
    carbs: float,
    meal_at: datetime,
    twin_params: TwinParams,
    *,
    hours_since_previous_meal: float | None = None,
) -> float | None:
    icr = _icr_for_time(meal_at, twin_params)
    if icr is None or icr <= 0 or not isfinite(icr):
        return None
    if (
        twin_params.last_fit_method != "manual"
        and (
            icr <= AUTO_FIT_ICR_MIN_G_PER_UNIT + FIT_BOUNDARY_TOLERANCE
            or icr >= AUTO_FIT_ICR_MAX_G_PER_UNIT - FIT_BOUNDARY_TOLERANCE
        )
    ):
        # A constrained fit landing exactly on a bound is not a trustworthy
        # personal ratio. Keep history usable, but do not blend/fallback to it.
        return None
    if (
        hours_since_previous_meal is not None
        and hours_since_previous_meal >= FIRST_MEAL_GAP.total_seconds() / 3600.0
    ):
        icr *= FIRST_MEAL_ICR_FACTOR
    dose = carbs / icr
    if not 0 < dose <= 100:
        return None
    return dose


def _icr_for_time(meal_at: datetime, twin_params: TwinParams) -> float | None:
    """Return the daypart ICR: morning / day / evening (overnight → evening)."""
    minutes = meal_at.hour * 60 + meal_at.minute
    morning = twin_params.morning_start_minutes
    day = twin_params.day_start_minutes
    evening = twin_params.evening_start_minutes
    if morning <= minutes < day:
        return twin_params.icr_morning
    if day <= minutes < evening:
        return twin_params.icr_day
    return twin_params.icr_evening


def _trusted_isf(twin_params: TwinParams) -> float | None:
    """Return ISF unless an automated constrained fit hit either boundary."""
    raw_isf = twin_params.isf
    if raw_isf is None:
        return None
    isf = float(raw_isf)
    if not isfinite(isf) or isf <= 0:
        return None
    if (
        twin_params.last_fit_method != "manual"
        and (
            isf <= AUTO_FIT_ISF_MIN_MMOL_L_PER_UNIT + FIT_BOUNDARY_TOLERANCE
            or isf >= AUTO_FIT_ISF_MAX_MMOL_L_PER_UNIT - FIT_BOUNDARY_TOLERANCE
        )
    ):
        return None
    return isf


def _weighted_median(values: list[float], weights: list[float]) -> float:
    return _weighted_percentile(values, weights, 0.5)


def _weighted_percentile(
    values: list[float],
    weights: list[float],
    quantile: float,
) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if len(values) == 1:
        return values[0]
    # Uniform weights: keep the interpolated percentile used by v1.
    if max(weights) - min(weights) < 1e-9:
        return _percentile(sorted(values), quantile)
    pairs = sorted(zip(values, weights, strict=True), key=lambda item: item[0])
    total = sum(max(weight, 0.0) for _, weight in pairs)
    if total <= 0:
        return median(values)
    threshold = total * quantile
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += max(weight, 0.0)
        if cumulative >= threshold:
            return value
    return pairs[-1][0]


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
