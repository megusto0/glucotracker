"""Explainable meal and glucose-correction estimates for manual review.

v2 meal component:
  - comparable personal episodes with deferred-bolus reattribution
  - outcome weights from +2h normalized CGM
  - optional ICR blend when twin ICR is configured
  - low/falling glucose caps the actionable total at zero

Correction uses normalized CGM, personal ISF, trend, and prior IOB. A default
target is applied when the client omits one. Nothing here creates an insulin
record.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import isfinite, log
from statistics import median
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import func, select
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
from glucotracker.application.grouping import GROUPING_VERSION
from glucotracker.application.health_connect_samples import resolve_instant
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
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    HealthConnectRecord,
    InsulinRecommendationCache,
    Meal,
    NightscoutInsulinEvent,
    TwinParams,
)
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.repositories.twin import TwinRepository

HISTORY_WINDOW = timedelta(days=180)
MAX_MATCHES = 8
MIN_MATCHES = 3
METHOD_VERSION = "historical-episode-median-v3"
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
# A gap alone cannot stand in for waking. Meals are sometimes not logged, and a
# missing log looks exactly like a long gap — far more often than sleep actually
# occurs. That failure points the wrong way, since it would raise the dose. The
# factor therefore requires a recorded sleep session inside the gap, and simply
# does not apply when sleep is not being recorded at all.
FIRST_MEAL_GAP = timedelta(hours=7)
MIN_SLEEP_FOR_FIRST_MEAL = timedelta(hours=3)
SLEEP_TO_FIRST_MEAL_WINDOW = timedelta(hours=6)
FIRST_MEAL_ICR_FACTOR = 7.1 / 8.7
# When Health Connect records no sleep session, the nightly low-HR trough is
# the fallback wake signal. HR percentile within the lookback window, the run
# breaks on a gap this long (a missed sample is not an awakening), and the
# trough must end inside SLEEP_TO_FIRST_MEAL_WINDOW before the meal just like
# a recorded session.
HR_SLEEP_PERCENTILE = 0.30
HR_SLEEP_RUN_GAP = timedelta(minutes=10)
HR_SLEEP_RECOVERY_WINDOW = timedelta(hours=2)
HR_SLEEP_LOOKBACK = timedelta(hours=24)
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


Daypart = Literal["morning", "day", "evening"]


@dataclass(frozen=True)
class IcrBasis:
    """The configured ratio behind the ICR half of a meal estimate."""

    daypart: Daypart
    configured_g_per_unit: float
    #: After the first-meal-after-sleep tightening, when it applied.
    effective_g_per_unit: float
    after_sleep: bool
    dose_units: float


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
    # How the meal number was arrived at, so a client can show its working
    # rather than a bare figure. The recommendation is a weighted blend of the
    # personal history median and the configured ratio; either side can be
    # absent, and which one dominated is the first thing worth reading.
    icr_daypart: Daypart | None = None
    icr_g_per_unit: float | None = None
    icr_configured_g_per_unit: float | None = None
    icr_after_sleep: bool = False
    icr_dose_units: float | None = None
    history_median_units: float | None = None
    history_weight: float | None = None

    @property
    def implied_icr_g_per_unit(self) -> float | None:
        """Grams per unit the meal recommendation actually works out to."""
        if not self.recommended_units or self.target_carbs_g <= 0:
            return None
        return round(self.target_carbs_g / self.recommended_units, 1)


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
    """Signed glucose adjustment and free IOB at one calculation instant."""

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
    # Carbohydrate still absorbing from *earlier* meals, and the insulin on
    # board beyond what that carbohydrate needs.
    prior_cob_g: float | None = None
    excess_iob_units: float | None = None
    calculated_at: datetime | None = None


@dataclass(frozen=True)
class InsulinCalculation:
    """Meal estimate, correction context, and a total when both are safe."""

    meal: HistoricalDoseEstimate
    correction: CorrectionEstimate
    total_recommended_units: float | None
    total_range_low_units: float | None
    total_range_high_units: float | None
    #: Whether the food half was served from store. The correction never is.
    meal_from_cache: bool = False
    meal_computed_at: datetime | None = None


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

    def is_first_after_sleep(self, meal_ids: list[UUID]) -> bool:
        """Return the exact first-after-sleep fact used by the ICR estimate.

        Diary episode projections use this method for their visual marker, so
        the icon and the recommendation cannot drift into two client-visible
        definitions. The previous-meal lookup is owner-scoped and deliberately
        excludes the current sitting.
        """
        unique_ids = list(dict.fromkeys(meal_ids))
        meals = self.repository.list_accepted_meals_by_ids(unique_ids)
        if len(meals) != len(unique_ids) or not meals:
            return False
        target_at = min(meal.eaten_at for meal in meals)
        previous_at = self.repository.session.scalar(
            select(Meal.eaten_at)
            .where(
                Meal.owner_id == self.repository.user_id,
                Meal.status == MealStatus.accepted,
                Meal.id.not_in(unique_ids),
                Meal.eaten_at < target_at,
                Meal.total_carbs_g >= 10.0,
            )
            .order_by(Meal.eaten_at.desc())
            .limit(1)
        )
        hours_since_previous = (
            (target_at - previous_at).total_seconds() / 3600.0
            if previous_at is not None
            else None
        )
        return self._is_first_meal_after_sleep(
            target_at,
            hours_since_previous_meal=hours_since_previous,
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
            as_of=before_event,
        )

    def estimate(
        self,
        meal_ids: list[UUID],
        correction_target_mmol_l: float | None = None,
        calculation_at: datetime | None = None,
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
        # The correction is always live. It reads glucose and insulin on board
        # at this moment, so a stored one is worse than none.
        correction = self._correction_estimate(
            meals,
            effective_target,
            twin_params=twin_params,
            as_of=calculation_at,
            separate_iob=True,
        )
        # The food half costs a 180-day pass over episode history and does not
        # change minute to minute, so it is stored and reused.
        meal_estimate, meal_cached = self._cached_meal_estimate(
            unique_ids,
            meals,
            twin_params=twin_params,
        )

        correction_is_usable = correction.status in {
            "ready",
            "not_needed",
            "low_or_falling",
        }
        correction_units = correction.units if correction_is_usable else None
        free_iob_units = correction.excess_iob_units or 0.0

        def _total(base: float | None) -> float | None:
            if base is None or correction_units is None:
                return None
            # A projected low always has a numeric answer: zero now. Otherwise
            # the calculation is transparent and signed: food + glucose
            # adjustment - only the IOB left after earlier COB is covered.
            if correction.status == "low_or_falling":
                return 0.0
            return _round_dose(max(0.0, base + correction_units - free_iob_units))

        total = _total(meal_estimate.recommended_units)
        total_low = _total(meal_estimate.range_low_units)
        total_high = _total(meal_estimate.range_high_units)
        return InsulinCalculation(
            meal=meal_estimate,
            correction=correction,
            total_recommended_units=total,
            total_range_low_units=total_low,
            total_range_high_units=total_high,
            meal_from_cache=meal_cached is not None,
            meal_computed_at=meal_cached,
        )

    def _cached_meal_estimate(
        self,
        unique_ids: list[UUID],
        meals: list[Meal],
        *,
        twin_params: TwinParams,
    ) -> tuple[HistoricalDoseEstimate, datetime | None]:
        """Serve the stored food estimate when nothing behind it has moved.

        Scoped to the sitting and the therapy parameters. The matcher also
        reads six months of prior episodes; folding that into the fingerprint
        would invalidate every stored estimate the moment one meal is logged,
        which is the opposite of a cache. A model-version bump is what pulls
        new history in — the same trade-off the review cache documents.
        """
        session = self.repository.session
        meal_key = "|".join(sorted(str(meal_id) for meal_id in unique_ids))
        target_at = min(meal.eaten_at for meal in meals)
        fingerprint = _meal_fingerprint(
            meals,
            twin_params,
            first_meal_context=self._first_meal_context_fingerprint(target_at),
        )
        row = session.scalar(
            select(InsulinRecommendationCache).where(
                InsulinRecommendationCache.owner_id == self.repository.user_id,
                InsulinRecommendationCache.meal_key == meal_key,
                InsulinRecommendationCache.method_version == METHOD_VERSION,
            )
        )
        if row is not None and row.input_fingerprint == fingerprint:
            stored = _estimate_from_json(row.result_json)
            if stored is not None:
                computed_at = row.computed_at
                if computed_at.tzinfo is None:
                    computed_at = computed_at.replace(tzinfo=UTC)
                return stored, computed_at

        estimate = self._meal_estimate(
            unique_ids,
            meals,
            twin_params=twin_params,
        )
        payload = _estimate_to_json(estimate)
        if row is None:
            session.add(
                InsulinRecommendationCache(
                    owner_id=self.repository.user_id,
                    meal_key=meal_key,
                    method_version=METHOD_VERSION,
                    input_fingerprint=fingerprint,
                    result_json=payload,
                )
            )
        else:
            row.input_fingerprint = fingerprint
            row.result_json = payload
            row.computed_at = datetime.now(UTC)
        session.commit()
        return estimate, None

    def _first_meal_context_fingerprint(self, target_at: datetime) -> str:
        """Fingerprint late sleep/HR evidence used by the food estimate.

        Health Connect often uploads a completed sleep session after the meal
        recommendation was first opened. The first-after-sleep factor belongs
        to the food half, so that late evidence must invalidate its persisted
        cache even though the target meal itself did not change.
        """
        target_utc = _utc_instant_from_local_wall(target_at)
        rows = self.repository.session.execute(
            select(
                HealthConnectRecord.record_type,
                func.count(HealthConnectRecord.id),
                func.max(HealthConnectRecord.updated_at),
            )
            .where(
                HealthConnectRecord.owner_id == self.repository.user_id,
                HealthConnectRecord.record_type.in_(
                    ("SleepSessionRecord", "HeartRateRecord")
                ),
                HealthConnectRecord.start_time >= target_utc - HR_SLEEP_LOOKBACK,
                HealthConnectRecord.start_time <= target_utc,
            )
            .group_by(HealthConnectRecord.record_type)
            .order_by(HealthConnectRecord.record_type)
        ).all()
        return "|".join(
            f"{kind}:{count}:{updated_at}" for kind, count, updated_at in rows
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

        after_sleep = self._is_first_meal_after_sleep(
            target_at,
            hours_since_previous_meal=_hours_since_previous_meal(
                components,
                target_at,
                excluded_meal_ids=set(unique_ids),
            ),
        )
        icr_dose = _icr_dose(
            target_carbs,
            target_at,
            twin_params,
            after_sleep=after_sleep,
        )

        icr_fields = _icr_fields(icr_dose)

        # The first-after-sleep ratio is a distinct, measured context. Generic
        # similar meals are not filtered to that same context, so blending them
        # here makes the displayed equation stop being true (for example,
        # 77 g / 7.6 g/U was shown beside a 7.2 U result). Use the adjusted ICR
        # directly; keep matches in the response as context, with zero weight.
        if after_sleep and icr_dose is not None:
            return HistoricalDoseEstimate(
                status="ready",
                meal_ids=unique_ids,
                target_carbs_g=round(target_carbs, 1),
                target_kcal=round(target_kcal, 1),
                recommended_units=_round_dose(icr_dose.dose_units),
                range_low_units=_round_dose(icr_dose.dose_units * 0.85),
                range_high_units=_round_dose(icr_dose.dose_units * 1.15),
                confidence="low",
                matches=matches,
                history_weight=0.0,
                **icr_fields,
            )

        if len(matches) < MIN_MATCHES:
            if icr_dose is not None:
                return HistoricalDoseEstimate(
                    status="ready",
                    meal_ids=unique_ids,
                    target_carbs_g=round(target_carbs, 1),
                    target_kcal=round(target_kcal, 1),
                    recommended_units=_round_dose(icr_dose.dose_units),
                    range_low_units=_round_dose(icr_dose.dose_units * 0.85),
                    range_high_units=_round_dose(icr_dose.dose_units * 1.15),
                    confidence="low",
                    matches=matches,
                    history_weight=0.0,
                    **icr_fields,
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
        history_weight = 1.0
        if icr_dose is not None:
            # More history and tighter spread → trust personal matches more.
            spread = (high - low) / history_median if history_median > 0 else 1.0
            history_weight = min(1.0, len(matches) / 8.0) * (
                0.85 if spread <= 0.35 else 0.7 if spread <= 0.6 else 0.55
            )
            recommendation = _round_dose(
                history_weight * history_median
                + (1.0 - history_weight) * icr_dose.dose_units
            )
            low = _round_dose(min(low, recommendation, icr_dose.dose_units))
            high = _round_dose(max(high, recommendation, icr_dose.dose_units))

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
            history_median_units=history_median,
            history_weight=round(history_weight, 2),
            **icr_fields,
        )

    def _is_first_meal_after_sleep(
        self,
        target_at: datetime,
        *,
        hours_since_previous_meal: float | None,
    ) -> bool:
        """Return whether a recorded sleep separates this meal from the last.

        Both conditions must hold: a long enough gap, and a sleep session that
        actually ended inside it. Without sleep records the daily low-HR trough
        stands in for the session when it too ended inside the window. Without
        either, this is always False, which leaves the daypart ratio untouched.
        """
        if hours_since_previous_meal is None:
            return False
        if hours_since_previous_meal < FIRST_MEAL_GAP.total_seconds() / 3600.0:
            return False
        target_utc = _utc_instant_from_local_wall(target_at)
        rows = self.repository.session.scalars(
            select(HealthConnectRecord).where(
                HealthConnectRecord.owner_id == self.repository.user_id,
                HealthConnectRecord.record_type == "SleepSessionRecord",
                HealthConnectRecord.start_time >= target_utc - timedelta(hours=48),
                HealthConnectRecord.start_time <= target_utc + timedelta(hours=24),
            )
        ).all()
        for row in rows:
            payload = row.payload or {}
            start = resolve_instant(payload.get("startTime"), row)
            end = resolve_instant(
                payload.get("endTime"),
                row,
                fallback_to_end=True,
            )
            if start is None or end is None or end <= start:
                continue
            if end - start < MIN_SLEEP_FOR_FIRST_MEAL:
                continue
            if timedelta(0) <= target_utc - end <= SLEEP_TO_FIRST_MEAL_WINDOW:
                return True
        return self._hr_wake_ended_within_window(target_utc)

    def _hr_wake_ended_within_window(self, target_utc: datetime) -> bool:
        """Return whether the low-HR trough ended inside the first-meal window.

        Falls back to heart-rate data only when no sleep session qualified
        above. A trough is a sustained run of samples at or below the 30th
        percentile of the lookback window; it must last at least
        MIN_SLEEP_FOR_FIRST_MEAL and end no more than SLEEP_TO_FIRST_MEAL_WINDOW
        before the meal.
        """
        rows = self.repository.session.scalars(
            select(HealthConnectRecord).where(
                HealthConnectRecord.owner_id == self.repository.user_id,
                HealthConnectRecord.record_type == "HeartRateRecord",
                HealthConnectRecord.start_time >= target_utc - HR_SLEEP_LOOKBACK,
                HealthConnectRecord.start_time <= target_utc + timedelta(hours=24),
            )
        ).all()
        samples: list[tuple[datetime, int]] = []
        for row in rows:
            for sample in (row.payload or {}).get("samples", []):
                sample_at = _hr_sample_instant(sample, row)
                raw_bpm = sample.get("beatsPerMinute")
                if sample_at is None or not isinstance(raw_bpm, (int, float)):
                    continue
                samples.append((sample_at, int(raw_bpm)))
        if len(samples) < 2:
            return False
        return _hr_trough_ended_within_window(samples, target_utc)

    def _correction_estimate(
        self,
        meals: list[Meal],
        target_mmol_l: float | None,
        *,
        twin_params: TwinParams | None = None,
        excluded_insulin_ids: set[UUID] | None = None,
        as_of: datetime | None = None,
        separate_iob: bool = False,
    ) -> CorrectionEstimate:
        """Calculate a signed correction without counting this meal's bolus."""
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
        calculation_at = (
            _local_wall_time(as_of) if as_of is not None and as_of.tzinfo else as_of
        ) or meal_at
        dashboard = GlucoseDashboardService(
            self.repository.session,
            self.repository.user_id,
        ).dashboard(
            calculation_at - CORRECTION_LOOKBACK,
            calculation_at,
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
            calculation_at - latest.timestamp > MAX_CGM_AGE
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
        ).project(_utc_instant_from_local_wall(calculation_at))
        if trend_projection.is_usable:
            assert trend_projection.projected_mmol_l is not None
            forecast_move = trend_projection.move_mmol_l or 0.0
            projected = latest.display_value + forecast_move
            projection_source = "forecast"
            projection_horizon_minutes = trend_projection.horizon_minutes

        iob_units = self._prior_iob_units(
            meals,
            as_of=calculation_at,
            dia_minutes=twin_params.dia_minutes,
            additionally_excluded_ids=excluded_insulin_ids,
        )
        # Insulin already working is not free to cover a new plate: most of it
        # is committed to carbohydrate that is still absorbing. Only the
        # surplus over that commitment should reduce the next dose.
        own_carbs = sum(float(meal.total_carbs_g or 0) for meal in meals)
        prior_cob = max(0.0, float(dashboard.summary.cob_g) - own_carbs)
        _, icr_now = _icr_for_time(calculation_at, twin_params)
        committed = prior_cob / icr_now if icr_now and icr_now > 0 else 0.0
        excess_iob = max(0.0, iob_units - committed)
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
            "prior_cob_g": round(prior_cob, 1),
            "excess_iob_units": round(excess_iob, 2),
            "calculated_at": calculation_at,
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
            gross_units = (projected - target_mmol_l) / isf
            if not separate_iob:
                return CorrectionEstimate(status="low_or_falling", **context)
            return CorrectionEstimate(
                status="low_or_falling",
                units=_round_dose(max(-100.0, gross_units)),
                **context,
            )

        gross_units = (projected - target_mmol_l) / isf
        if not separate_iob:
            net_units = gross_units - excess_iob
            if net_units <= 0:
                return CorrectionEstimate(status="not_needed", units=0.0, **context)
            return CorrectionEstimate(
                status="ready",
                units=_round_dose(min(net_units, 100.0)),
                **context,
            )
        # Keep the glucose adjustment signed. Free IOB is a separate term in
        # the meal total so the client can show exactly why the dose shrank.
        if abs(gross_units) < 0.05:
            return CorrectionEstimate(status="not_needed", units=0.0, **context)
        return CorrectionEstimate(
            status="ready",
            units=_round_dose(max(-100.0, min(gross_units, 100.0))),
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


def _hr_sample_instant(
    sample: dict[str, Any],
    row: HealthConnectRecord,
) -> datetime | None:
    """Return the true UTC instant of a heart-rate sample.

    Sample times arrive as the true UTC instant tagged with "Z"; the row's own
    start_time is the same wall clock shifted by the recorded zone offset.
    Resolve against the row span exactly as the health-connect reader does,
    falling back to the row's start_time when no embedded time exists.
    """
    return resolve_instant(sample.get("time"), row)


def _hr_trough_ended_within_window(
    samples: list[tuple[datetime, int]],
    target_utc: datetime,
) -> bool:
    """Return whether a sustained low-HR trough ended just before the meal.

    The trough threshold is the 30th percentile of the window so it adapts to
    the wearer rather than a fixed bpm. A run is a span of samples at or below
    the threshold; a single above-threshold minute does not end it, but a rise
    sustained past HR_SLEEP_RUN_GAP or a gap between low samples that long does.
    Any qualifying run must last at least MIN_SLEEP_FOR_FIRST_MEAL and end no
    more than SLEEP_TO_FIRST_MEAL_WINDOW before the meal, and the trough must
    actually be followed by heart rate rising above the threshold within
    HR_SLEEP_RECOVERY_WINDOW — otherwise a monotone or too-short window would
    let the percentile swallow every sample and read as a trough.
    """
    ordered = sorted(samples)
    thresholds = sorted(bpm for _, bpm in ordered)
    threshold = float(
        thresholds[min(len(thresholds) - 1, int(HR_SLEEP_PERCENTILE * len(thresholds)))]
    )
    runs: list[tuple[datetime, datetime]] = []
    run_start: datetime | None = None
    last_low_time: datetime | None = None
    for sample_at, bpm in ordered:
        if bpm <= threshold:
            if run_start is None:
                run_start = sample_at
            elif (
                last_low_time is not None
                and sample_at - last_low_time > HR_SLEEP_RUN_GAP
            ):
                runs.append((run_start, last_low_time))
                run_start = sample_at
            last_low_time = sample_at
        elif (
            run_start is not None
            and last_low_time is not None
            and sample_at - last_low_time > HR_SLEEP_RUN_GAP
        ):
            runs.append((run_start, last_low_time))
            run_start = None
            last_low_time = None
    if run_start is not None and last_low_time is not None:
        runs.append((run_start, last_low_time))
    for run_start, run_end in runs:
        if run_end - run_start < MIN_SLEEP_FOR_FIRST_MEAL:
            continue
        if not (timedelta(0) <= target_utc - run_end <= SLEEP_TO_FIRST_MEAL_WINDOW):
            continue
        if not any(
            bpm > threshold
            for sample_at, bpm in ordered
            if timedelta(0) < sample_at - run_end <= HR_SLEEP_RECOVERY_WINDOW
        ):
            continue
        return True
    return False


def _meal_fingerprint(
    meals: list[Meal],
    twin_params: TwinParams,
    *,
    first_meal_context: str = "",
) -> str:
    """Summarise the sitting and the parameters the food estimate came from."""
    # The parameters themselves, not their updated_at: an unpersisted default
    # row is rebuilt with a fresh timestamp on every request, and an unrelated
    # twin edit should not throw away a still-valid estimate.
    parts = [
        METHOD_VERSION,
        GROUPING_VERSION,
        str(twin_params.icr_morning),
        str(twin_params.icr_day),
        str(twin_params.icr_evening),
        str(twin_params.morning_start_minutes),
        str(twin_params.day_start_minutes),
        str(twin_params.evening_start_minutes),
        str(_trusted_isf(twin_params)),
        str(twin_params.last_fit_method),
        first_meal_context,
    ]
    for meal in sorted(meals, key=lambda item: item.id):
        parts.append(
            f"{meal.id}:{meal.updated_at}:{meal.eaten_at}:"
            f"{meal.total_carbs_g}:{meal.total_kcal}"
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _estimate_to_json(estimate: HistoricalDoseEstimate) -> dict[str, Any]:
    return {
        **vars(estimate),
        "meal_ids": [str(meal_id) for meal_id in estimate.meal_ids],
        "matches": [
            {
                **vars(match),
                "occurred_at": match.occurred_at.isoformat(),
                "meal_ids": [str(meal_id) for meal_id in match.meal_ids],
            }
            for match in estimate.matches
        ],
    }


def _estimate_from_json(payload: dict[str, Any]) -> HistoricalDoseEstimate | None:
    """Rebuild a stored estimate, treating any shape surprise as a miss."""
    try:
        return HistoricalDoseEstimate(
            **{
                **payload,
                "meal_ids": [UUID(str(item)) for item in payload["meal_ids"]],
                "matches": [
                    HistoricalDoseMatch(
                        **{
                            **match,
                            "occurred_at": datetime.fromisoformat(
                                str(match["occurred_at"])
                            ),
                            "meal_ids": [UUID(str(item)) for item in match["meal_ids"]],
                        }
                    )
                    for match in payload.get("matches", [])
                ],
            }
        )
    except (KeyError, TypeError, ValueError):
        return None


def _icr_fields(basis: IcrBasis | None) -> dict[str, Any]:
    """Spread an ICR basis over the estimate fields that report it."""
    if basis is None:
        return {}
    return {
        "icr_daypart": basis.daypart,
        "icr_g_per_unit": basis.effective_g_per_unit,
        "icr_configured_g_per_unit": basis.configured_g_per_unit,
        "icr_after_sleep": basis.after_sleep,
        "icr_dose_units": _round_dose(basis.dose_units),
    }


def _icr_dose(
    carbs: float,
    meal_at: datetime,
    twin_params: TwinParams,
    *,
    after_sleep: bool = False,
) -> IcrBasis | None:
    daypart, icr = _icr_for_time(meal_at, twin_params)
    if icr is None or icr <= 0 or not isfinite(icr):
        return None
    if twin_params.last_fit_method != "manual" and (
        icr <= AUTO_FIT_ICR_MIN_G_PER_UNIT + FIT_BOUNDARY_TOLERANCE
        or icr >= AUTO_FIT_ICR_MAX_G_PER_UNIT - FIT_BOUNDARY_TOLERANCE
    ):
        # A constrained fit landing exactly on a bound is not a trustworthy
        # personal ratio. Keep history usable, but do not blend/fallback to it.
        return None
    effective = icr * FIRST_MEAL_ICR_FACTOR if after_sleep else icr
    dose = carbs / effective
    if not 0 < dose <= 100:
        return None
    return IcrBasis(
        daypart=daypart,
        configured_g_per_unit=round(icr, 2),
        effective_g_per_unit=round(effective, 2),
        after_sleep=after_sleep,
        dose_units=dose,
    )


def _icr_for_time(
    meal_at: datetime,
    twin_params: TwinParams,
) -> tuple[Daypart, float | None]:
    """Return the daypart ICR: morning / day / evening (overnight → evening)."""
    minutes = meal_at.hour * 60 + meal_at.minute
    morning = twin_params.morning_start_minutes
    day = twin_params.day_start_minutes
    evening = twin_params.evening_start_minutes
    if morning <= minutes < day:
        return "morning", twin_params.icr_morning
    if day <= minutes < evening:
        return "day", twin_params.icr_day
    return "evening", twin_params.icr_evening


def _trusted_isf(twin_params: TwinParams) -> float | None:
    """Return ISF unless an automated constrained fit hit either boundary."""
    raw_isf = twin_params.isf
    if raw_isf is None:
        return None
    isf = float(raw_isf)
    if not isfinite(isf) or isf <= 0:
        return None
    if twin_params.last_fit_method != "manual" and (
        isf <= AUTO_FIT_ISF_MIN_MMOL_L_PER_UNIT + FIT_BOUNDARY_TOLERANCE
        or isf >= AUTO_FIT_ISF_MAX_MMOL_L_PER_UNIT - FIT_BOUNDARY_TOLERANCE
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
