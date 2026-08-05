"""Daily retrospective therapy review assembled from episodes and CGM.

The adjusted values are hindsight explanations, never prospective treatment
recommendations. Insulin rows use the observed glucose error divided by ISF.
Carbohydrate-rescue rows use a deliberately explicit coarse conversion so the
UI can show how the actual rescue compared with the later glucose outcome.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import GlucoseDashboardPoint
from glucotracker.application.body_states import BodyStateInterval, BodyStateService
from glucotracker.application.episode_therapy import (
    EpisodeTherapy,
    TherapyClass,
    classify_episode_therapy,
)
from glucotracker.application.episodes import EpisodeComponent, EpisodeQueryService
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.grouping import GROUPING_VERSION
from glucotracker.application.insulin_recommendation import (
    DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT,
    LOW_GLUCOSE_MMOL_L,
    TIR_HIGH_MMOL_L,
    HistoricalInsulinRecommendationService,
    _trusted_isf,
)
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.infra.db.models import (
    HealthConnectRecord,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    TherapyReviewCache,
    TwinParams,
)
from glucotracker.infra.db.repositories.twin import TwinRepository

ReviewUnit = Literal["U", "g"]
AdjustmentStatus = Literal[
    "ready",
    "no_actual",
    "no_outcome",
    "calculation_withheld",
]
BodyContext = Literal["after_sleep", "during_sleep", "near_activity"]
OutcomeQuality = Literal["in_range", "spike", "low", "spike_and_low", "unknown"]

POINT_TOLERANCE = timedelta(minutes=15)
DEFAULT_CARB_ADJUSTMENT_G_PER_MMOL_L = 4.0
# v4: an episode now carries the path it took, not only where it ended, and the
# hindsight adjustment is no longer allowed to contradict that path.
# v3: the day carries its sleep and effort context, and every cached row carries
# a fingerprint of the inputs it was built from.
THERAPY_REVIEW_MODEL_VERSION = (
    f"retrospective-therapy-review-v5+{GROUPING_VERSION}"
)
# An episode is sampled this often across its horizon so the page can draw the
# curve instead of two numbers with a gap between them.
TRAJECTORY_STEP_MINUTES = 10
# A CGM hole longer than this is a hole, not time spent at the last value.
MAX_GAP_FOR_TIME_IN_RANGE = timedelta(minutes=15)
# An episode counts as following sleep when it starts within this long after
# waking, and as sitting near effort when it starts this close to a session.
AFTER_SLEEP_WINDOW = timedelta(hours=6)
NEAR_ACTIVITY_WINDOW = timedelta(hours=3)


@dataclass(frozen=True)
class TherapyReviewItem:
    """One episode rendered as a comparable daily review row."""

    key: str
    title: str
    classification: TherapyClass
    confidence: Literal["low", "medium", "high"]
    start_at: datetime
    horizon_minutes: int
    value_unit: ReviewUnit
    glucose_start_raw: float | None
    glucose_start_normalized: float | None
    glucose_after_raw: float | None
    glucose_after_normalized: float | None
    actual_value: float | None
    calculated_value: float | None
    adjusted_actual_value: float | None
    target_mmol_l: float
    isf_mmol_l_per_unit: float | None
    calculation_status: str
    adjustment_status: AdjustmentStatus
    total_carbs_g: float
    total_insulin_units: float
    notes: list[str] = field(default_factory=list)
    body_context: list[BodyContext] = field(default_factory=list)
    # The path between start and outcome. An endpoint on target says nothing
    # about a 13 mmol/L peak or a 3.5 dip on the way there, and both change what
    # the episode should be read as.
    peak_mmol_l: float | None = None
    peak_after_minutes: int | None = None
    nadir_mmol_l: float | None = None
    nadir_after_minutes: int | None = None
    minutes_above_high: int = 0
    minutes_below_low: int = 0
    outcome_quality: OutcomeQuality = "unknown"
    #: Normalized glucose every TRAJECTORY_STEP_MINUTES across the horizon.
    trajectory: list[float | None] = field(default_factory=list)


@dataclass(frozen=True)
class TherapyReviewDay:
    """Daily collection with the assumptions used by hindsight adjustment."""

    date: date
    target_mmol_l: float
    horizon_minutes: int
    items: list[TherapyReviewItem]
    body_states: list[BodyStateInterval]
    cached: bool
    computed_at: datetime
    model_version: str


class TherapyReviewService:
    """Build a complete local-day therapy review for one owner."""

    def __init__(self, session: Session, user_id) -> None:
        self.session = session
        self.user_id = user_id
        self.episodes = EpisodeQueryService(session, user_id)
        self.recommendations = HistoricalInsulinRecommendationService(
            session,
            user_id,
        )

    def day(
        self,
        day: date,
        *,
        target_mmol_l: float,
        horizon_minutes: int,
        force_recalculate: bool = False,
    ) -> TherapyReviewDay:
        """Serve a saved day when nothing it was built from has changed.

        Every day is cached, today included. A stored row is only served when
        its fingerprint still matches what the day is made of, so a late
        Nightscout import or an edited meal recomputes on its own instead of
        waiting for a model-version bump, and today's page stops recalculating
        several seconds of history on every single request.
        """
        target_tenths = round(target_mmol_l * 10)
        fingerprint = self._fingerprint(day, horizon_minutes)
        cache = self._cached(day, target_tenths, horizon_minutes)
        if (
            cache is not None
            and not force_recalculate
            and cache.input_fingerprint == fingerprint
        ):
            return _day_from_cache(cache)

        review = self._calculate_day(
            day,
            target_mmol_l=target_mmol_l,
            horizon_minutes=horizon_minutes,
        )
        self._save(
            review,
            cache=cache,
            target_tenths=target_tenths,
            horizon_minutes=horizon_minutes,
            fingerprint=fingerprint,
        )
        return review

    def _fingerprint(self, day: date, horizon_minutes: int) -> str:
        """Summarise everything this day's numbers are computed from.

        Deliberately scoped to the day itself plus the therapy parameters. The
        historical matcher also reads six months of prior episodes, but folding
        that in would invalidate every stored day the moment a single new meal
        is logged, which is the opposite of a cache. Pressing refresh remains
        the way to force those in.
        """
        local_from = datetime.combine(day, time.min)
        local_to = local_from + timedelta(days=1)
        glucose_from = utc_instant_from_local_wall(
            local_from - timedelta(minutes=30)
        )
        glucose_to = utc_instant_from_local_wall(
            local_to + timedelta(minutes=horizon_minutes)
        )
        health_from = glucose_from - timedelta(days=1)
        health_to = glucose_to + timedelta(days=1)
        parts = [
            THERAPY_REVIEW_MODEL_VERSION,
            str(
                self.session.execute(
                    select(
                        func.count(Meal.id),
                        func.max(Meal.updated_at),
                        func.sum(Meal.total_carbs_g),
                    ).where(
                        Meal.owner_id == self.user_id,
                        Meal.eaten_at >= local_from,
                        Meal.eaten_at < local_to,
                    )
                ).one()
            ),
            str(
                self.session.execute(
                    select(
                        func.count(NightscoutInsulinEvent.id),
                        func.max(NightscoutInsulinEvent.updated_at),
                        func.sum(NightscoutInsulinEvent.insulin_units),
                    ).where(
                        NightscoutInsulinEvent.owner_id == self.user_id,
                        NightscoutInsulinEvent.timestamp >= glucose_from,
                        NightscoutInsulinEvent.timestamp < glucose_to,
                    )
                ).one()
            ),
            str(
                self.session.execute(
                    select(
                        func.count(NightscoutGlucoseEntry.id),
                        func.max(NightscoutGlucoseEntry.timestamp),
                        func.max(NightscoutGlucoseEntry.updated_at),
                    ).where(
                        NightscoutGlucoseEntry.owner_id == self.user_id,
                        NightscoutGlucoseEntry.timestamp >= glucose_from,
                        NightscoutGlucoseEntry.timestamp < glucose_to,
                    )
                ).one()
            ),
            str(
                self.session.execute(
                    select(
                        func.count(HealthConnectRecord.id),
                        # Server-side, unlike last_modified_time, which the
                        # client leaves unset on some record types.
                        func.max(HealthConnectRecord.updated_at),
                    ).where(
                        HealthConnectRecord.owner_id == self.user_id,
                        HealthConnectRecord.start_time >= health_from,
                        HealthConnectRecord.start_time < health_to,
                    )
                ).one()
            ),
            str(
                self.session.scalar(
                    select(TwinParams.updated_at).where(
                        TwinParams.owner_id == self.user_id
                    )
                )
            ),
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]

    def _calculate_day(
        self,
        day: date,
        *,
        target_mmol_l: float,
        horizon_minutes: int,
    ) -> TherapyReviewDay:
        local_from = datetime.combine(day, time.min)
        local_to = local_from + timedelta(days=1)
        components = self.episodes.components(local_from, local_to)
        points = GlucoseDashboardService(
            self.session,
            self.user_id,
        ).dashboard(
            local_from - timedelta(minutes=30),
            local_to + timedelta(minutes=horizon_minutes),
            "normalized",
        ).points
        self.recommendations.preload_history(local_from, local_to)

        params = TwinRepository(
            self.session,
            self.user_id,
        ).get_or_create_params(persist=False)
        isf = _trusted_isf(params) or DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT
        body_states = BodyStateService(self.session, self.user_id).intervals(
            local_from,
            local_to,
        )

        items = [
            self._item(
                component,
                classify_episode_therapy(component, points),
                points,
                target_mmol_l=target_mmol_l,
                horizon_minutes=horizon_minutes,
                isf=isf,
                body_states=body_states,
            )
            for component in components
        ]
        return TherapyReviewDay(
            date=day,
            target_mmol_l=round(target_mmol_l, 1),
            horizon_minutes=horizon_minutes,
            items=items,
            body_states=body_states,
            cached=False,
            computed_at=datetime.now(UTC),
            model_version=THERAPY_REVIEW_MODEL_VERSION,
        )

    def _cached(
        self,
        day: date,
        target_tenths: int,
        horizon_minutes: int,
    ) -> TherapyReviewCache | None:
        return self.session.scalar(
            select(TherapyReviewCache).where(
                TherapyReviewCache.owner_id == self.user_id,
                TherapyReviewCache.date == day,
                TherapyReviewCache.target_tenths == target_tenths,
                TherapyReviewCache.horizon_minutes == horizon_minutes,
                TherapyReviewCache.model_version
                == THERAPY_REVIEW_MODEL_VERSION,
            )
        )

    def _save(
        self,
        review: TherapyReviewDay,
        *,
        cache: TherapyReviewCache | None,
        target_tenths: int,
        horizon_minutes: int,
        fingerprint: str,
    ) -> None:
        result_json = {
            "items": [_item_to_json(item) for item in review.items],
            "body_states": [_state_to_json(state) for state in review.body_states],
        }
        if cache is None:
            cache = TherapyReviewCache(
                owner_id=self.user_id,
                date=review.date,
                target_tenths=target_tenths,
                horizon_minutes=horizon_minutes,
                model_version=THERAPY_REVIEW_MODEL_VERSION,
                result_json=result_json,
                computed_at=review.computed_at,
                input_fingerprint=fingerprint,
            )
            self.session.add(cache)
        else:
            cache.result_json = result_json
            cache.computed_at = review.computed_at
            cache.input_fingerprint = fingerprint
        self.session.commit()

    def _item(
        self,
        component: EpisodeComponent,
        therapy: EpisodeTherapy,
        points: list[GlucoseDashboardPoint],
        *,
        target_mmol_l: float,
        horizon_minutes: int,
        isf: float,
        body_states: list[BodyStateInterval],
    ) -> TherapyReviewItem:
        start = _nearest(points, component.start_at)
        after = _nearest(
            points,
            component.start_at + timedelta(minutes=horizon_minutes),
        )
        start_raw = _raw(start)
        start_normalized = _normalized(start)
        after_raw = _raw(after)
        after_normalized = _normalized(after)
        outcome = after_normalized
        path = _path(points, component.start_at, horizon_minutes)

        total_carbs = round(
            sum(float(meal.total_carbs_g or 0) for meal in component.meals),
            1,
        )
        total_insulin = round(
            sum(float(event.insulin_units or 0) for event in component.insulin),
            2,
        )
        notes = list(therapy.reasons)

        if therapy.classification == "carb_correction":
            unit: ReviewUnit = "g"
            actual = total_carbs if total_carbs > 0 else None
            calculated = therapy.suggested_carbs_g
            calculation_status = (
                "ready" if calculated is not None else "calculation_withheld"
            )
            adjusted = (
                max(
                    0.0,
                    actual
                    + (target_mmol_l - outcome)
                    * DEFAULT_CARB_ADJUSTMENT_G_PER_MMOL_L,
                )
                if actual is not None and outcome is not None
                else None
            )
            if adjusted is not None:
                adjusted = round(min(adjusted, 100.0), 1)
                notes.append(
                    "ретроспективная поправка углеводов: 4 г на 1 ммоль/л"
                )
                # A rescue that overshot into a spike cannot be told to give
                # more sugar, however the four-hour endpoint reads.
                if path.peak is not None and path.peak > TIR_HIGH_MMOL_L:
                    if adjusted > actual:
                        adjusted = round(actual, 1)
                        notes.append(
                            f"пик {path.peak:.1f} ммоль/л: поправка вверх снята"
                        )
        else:
            unit = "U"
            actual = total_insulin if total_insulin > 0 else None
            calculated: float | None = None
            calculation_status = "calculation_withheld"
            if component.meals:
                calculation = self.recommendations.estimate(
                    [meal.id for meal in component.meals],
                    target_mmol_l,
                )
                if calculation is not None:
                    calculated = calculation.total_recommended_units
                    calculation_status = calculation.meal.status
            elif component.insulin:
                correction = self.recommendations.correction_at(
                    component.start_at,
                    target_mmol_l,
                    excluded_insulin_ids={event.id for event in component.insulin},
                )
                if correction.status in {"ready", "not_needed"}:
                    calculated = correction.units or 0.0
                calculation_status = correction.status

            adjusted = (
                max(0.0, actual + (outcome - target_mmol_l) / isf)
                if actual is not None and outcome is not None
                else None
            )
            if adjusted is not None:
                adjusted = round(min(adjusted, 100.0), 1)
                notes.append(
                    "ретроспективная поправка инсулина по ошибке глюкозы и ISF"
                )
                # The endpoint alone cannot see the path. A dose that put
                # glucose below the hypo threshold on the way is never a dose
                # that needed to be larger, whatever it recovered to by the
                # horizon — and a run above the high band with an on-target
                # ending is a timing question, not a size one.
                if path.nadir is not None and path.nadir < LOW_GLUCOSE_MMOL_L:
                    if adjusted > actual:
                        adjusted = round(actual, 1)
                    notes.append(
                        f"провал до {path.nadir:.1f} ммоль/л: "
                        "поправка вверх снята"
                    )
                elif (
                    path.peak is not None
                    and path.peak > TIR_HIGH_MMOL_L
                    and outcome is not None
                    and LOW_GLUCOSE_MMOL_L <= outcome <= TIR_HIGH_MMOL_L
                ):
                    notes.append(
                        f"пик {path.peak:.1f} ммоль/л при исходе в диапазоне: "
                        "вопрос ко времени укола, а не к дозе"
                    )

        adjustment_status: AdjustmentStatus = (
            "no_actual"
            if actual is None
            else "no_outcome"
            if outcome is None
            else "calculation_withheld"
            if calculated is None
            else "ready"
        )
        return TherapyReviewItem(
            key="|".join(
                sorted(
                    [f"m:{meal.id}" for meal in component.meals]
                    + [f"i:{event.id}" for event in component.insulin]
                )
            ),
            title=_title(component, therapy.classification),
            classification=therapy.classification,
            confidence=therapy.confidence,
            start_at=component.start_at,
            horizon_minutes=horizon_minutes,
            value_unit=unit,
            glucose_start_raw=_rounded(start_raw),
            glucose_start_normalized=_rounded(start_normalized),
            glucose_after_raw=_rounded(after_raw),
            glucose_after_normalized=_rounded(after_normalized),
            actual_value=_rounded(actual),
            calculated_value=_rounded(calculated),
            adjusted_actual_value=_rounded(adjusted),
            target_mmol_l=round(target_mmol_l, 1),
            isf_mmol_l_per_unit=round(isf, 2) if unit == "U" else None,
            calculation_status=calculation_status,
            adjustment_status=adjustment_status,
            total_carbs_g=total_carbs,
            total_insulin_units=total_insulin,
            notes=notes,
            body_context=_body_context(component.start_at, body_states),
            peak_mmol_l=_rounded(path.peak),
            peak_after_minutes=path.peak_after_minutes,
            nadir_mmol_l=_rounded(path.nadir),
            nadir_after_minutes=path.nadir_after_minutes,
            minutes_above_high=path.minutes_above_high,
            minutes_below_low=path.minutes_below_low,
            outcome_quality=path.quality,
            trajectory=path.trajectory,
        )


def _body_context(
    start_at: datetime,
    body_states: list[BodyStateInterval],
) -> list[BodyContext]:
    """Label an episode with the sleep and effort it sat next to.

    Exercise is still invisible to the dose calculation, so a meal that landed
    beside a session has to be readable as such before its numbers are trusted.
    """
    context: list[BodyContext] = []
    for state in body_states:
        if state.kind == "sleep":
            if state.start_at <= start_at <= state.end_at:
                context.append("during_sleep")
            elif timedelta(0) <= start_at - state.end_at <= AFTER_SLEEP_WINDOW:
                context.append("after_sleep")
        elif (
            state.start_at - NEAR_ACTIVITY_WINDOW
            <= start_at
            <= state.end_at + NEAR_ACTIVITY_WINDOW
        ):
            context.append("near_activity")
    return sorted(set(context))


@dataclass(frozen=True)
class _Path:
    """What glucose did between an episode and its horizon."""

    peak: float | None
    peak_after_minutes: int | None
    nadir: float | None
    nadir_after_minutes: int | None
    minutes_above_high: int
    minutes_below_low: int
    quality: OutcomeQuality
    trajectory: list[float | None]


def _path(
    points: list[GlucoseDashboardPoint],
    start_at: datetime,
    horizon_minutes: int,
) -> _Path:
    """Measure the excursion an episode went through, not just where it ended.

    Time above and below is integrated over the gaps between samples rather
    than counted per sample, and a gap longer than
    ``MAX_GAP_FOR_TIME_IN_RANGE`` contributes nothing — a sensor hole is not
    time spent at the last reading.
    """
    end_at = start_at + timedelta(minutes=horizon_minutes)
    inside = [
        (point.timestamp, value)
        for point in points
        if start_at <= point.timestamp <= end_at
        and (value := _normalized(point)) is not None
    ]
    trajectory = [
        _rounded(_normalized(_nearest(points, start_at + timedelta(minutes=offset))))
        for offset in range(0, horizon_minutes + 1, TRAJECTORY_STEP_MINUTES)
    ]
    if not inside:
        return _Path(
            peak=None,
            peak_after_minutes=None,
            nadir=None,
            nadir_after_minutes=None,
            minutes_above_high=0,
            minutes_below_low=0,
            quality="unknown",
            trajectory=trajectory,
        )

    peak_at, peak = max(inside, key=lambda sample: sample[1])
    nadir_at, nadir = min(inside, key=lambda sample: sample[1])
    above = timedelta(0)
    below = timedelta(0)
    for (at, value), (next_at, _) in zip(inside, inside[1:], strict=False):
        span = min(next_at - at, MAX_GAP_FOR_TIME_IN_RANGE)
        if value > TIR_HIGH_MMOL_L:
            above += span
        elif value < LOW_GLUCOSE_MMOL_L:
            below += span

    spiked = peak > TIR_HIGH_MMOL_L
    dipped = nadir < LOW_GLUCOSE_MMOL_L
    quality: OutcomeQuality = (
        "spike_and_low"
        if spiked and dipped
        else "spike"
        if spiked
        else "low"
        if dipped
        else "in_range"
    )
    return _Path(
        peak=peak,
        peak_after_minutes=round((peak_at - start_at).total_seconds() / 60),
        nadir=nadir,
        nadir_after_minutes=round((nadir_at - start_at).total_seconds() / 60),
        minutes_above_high=round(above.total_seconds() / 60),
        minutes_below_low=round(below.total_seconds() / 60),
        quality=quality,
        trajectory=trajectory,
    )


def _nearest(
    points: list[GlucoseDashboardPoint],
    target: datetime,
) -> GlucoseDashboardPoint | None:
    if not points:
        return None
    point = min(points, key=lambda candidate: abs(candidate.timestamp - target))
    return point if abs(point.timestamp - target) <= POINT_TOLERANCE else None


def _raw(point: GlucoseDashboardPoint | None) -> float | None:
    return float(point.raw_value) if point is not None else None


def _normalized(point: GlucoseDashboardPoint | None) -> float | None:
    if point is None:
        return None
    return float(
        point.normalized_value
        if point.normalized_value is not None
        else point.raw_value
    )


def _rounded(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def _title(component: EpisodeComponent, classification: TherapyClass) -> str:
    titles = [meal.title for meal in component.meals if meal.title]
    if titles:
        return " + ".join(titles)
    if classification == "insulin_correction":
        return "Коррекция инсулином"
    if component.insulin:
        return "Инсулин"
    return "Эпизод"


def _item_to_json(item: TherapyReviewItem) -> dict[str, Any]:
    return {
        **vars(item),
        "start_at": item.start_at.isoformat(),
    }


def _state_to_json(state: BodyStateInterval) -> dict[str, Any]:
    return {
        **vars(state),
        "start_at": state.start_at.isoformat(),
        "end_at": state.end_at.isoformat(),
    }


def _day_from_cache(cache: TherapyReviewCache) -> TherapyReviewDay:
    raw_items = cache.result_json.get("items", [])
    items = [
        TherapyReviewItem(
            **{
                **raw,
                "start_at": datetime.fromisoformat(str(raw["start_at"])),
            }
        )
        for raw in raw_items
        if isinstance(raw, dict) and raw.get("start_at")
    ]
    raw_states = cache.result_json.get("body_states", [])
    body_states = [
        BodyStateInterval(
            **{
                **raw,
                "start_at": datetime.fromisoformat(str(raw["start_at"])),
                "end_at": datetime.fromisoformat(str(raw["end_at"])),
            }
        )
        for raw in raw_states
        if isinstance(raw, dict) and raw.get("start_at") and raw.get("end_at")
    ]
    computed_at = cache.computed_at
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=UTC)
    return TherapyReviewDay(
        date=cache.date,
        target_mmol_l=cache.target_tenths / 10,
        horizon_minutes=cache.horizon_minutes,
        items=items,
        body_states=body_states,
        cached=True,
        computed_at=computed_at,
        model_version=cache.model_version,
    )
