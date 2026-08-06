"""Automatic therapy intent classification for grouped food/insulin episodes.

Episode linkage answers "which records belong together."  This module adds a
separate, read-only interpretation layer: meal, snack, carbohydrate rescue,
insulin correction, or mixed treatment.  It never rewrites meal/insulin links
and never creates treatment records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from glucotracker.api.schemas import GlucoseDashboardPoint
from glucotracker.application.episodes import EpisodeComponent
from glucotracker.application.grouping import INSULIN_COVERAGE_WINDOW
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import normalized_text

TherapyClass = Literal[
    "meal",
    "snack",
    "carb_correction",
    "insulin_correction",
    "mixed",
    "unresolved",
]
TherapyConfidence = Literal["low", "medium", "high"]

LOW_GLUCOSE_MMOL_L = 3.9
LEVEL_TWO_LOW_MMOL_L = 3.0
SNACK_MAX_CARBS_G = 30.0
DEFAULT_RESCUE_CARBS_G = 15.0
POINT_TOLERANCE = timedelta(minutes=15)
TREND_LOOKBACK = timedelta(minutes=20)
OUTCOME_HORIZON = timedelta(hours=2)
PEAK_HORIZON = timedelta(minutes=150)
SNACK_ROLES = {"snack", "drink", "dessert"}
# A bolus this soon after the plate is still part of dosing it; past the far
# edge the meal is no longer plausibly the cause of what is being chased.
CATCH_UP_AFTER = timedelta(minutes=20)
CATCH_UP_UNTIL = timedelta(hours=3)
# +0.3 mmol/L per 15 min. Comfortably above the noise a flat trace shows, and
# well under the +1.80/h these boluses were measured to sit on.
CATCH_UP_RISING_PER_MINUTE = 0.02
# How long "there is no bolus here" has to wait before it means anything.
# Equal to the window in which a later bolus still attaches to the sitting, so
# the classifier never draws a conclusion from insulin that may still arrive.
SETTLING_WINDOW = INSULIN_COVERAGE_WINDOW


@dataclass(frozen=True)
class EpisodeTherapy:
    """Read-only therapy interpretation returned with one episode."""

    classification: TherapyClass
    confidence: TherapyConfidence
    reasons: list[str]
    suggested_carbs_g: float | None = None
    suggestion_source: Literal["ada_default"] | None = None
    glucose_at_start_raw: float | None = None
    glucose_at_start_normalized: float | None = None
    glucose_plus_2h_raw: float | None = None
    glucose_plus_2h_normalized: float | None = None
    peak_post_event_raw: float | None = None
    peak_post_event_normalized: float | None = None


def classify_episode_therapy(
    component: EpisodeComponent,
    points: list[GlucoseDashboardPoint],
    now: datetime | None = None,
) -> EpisodeTherapy:
    """Classify one component from calibrated glucose, once it has settled.

    [now] is app-local wall time, the same convention as `component.start_at`.
    It defaults to the real clock, so every past episode is settled and only a
    sitting still in progress is held back.
    """
    start_at = component.start_at
    at_start = _nearest(points, start_at)
    plus_2h = _nearest(points, start_at + OUTCOME_HORIZON)
    post_points = [
        point
        for point in points
        if start_at <= point.timestamp <= start_at + PEAK_HORIZON
    ]

    raw_at = _raw(at_start)
    normalized_at = _normalized(at_start)
    raw_plus_2h = _raw(plus_2h)
    normalized_plus_2h = _normalized(plus_2h)
    raw_peak = max((_raw(point) for point in post_points), default=None)
    normalized_peak = max(
        (_normalized(point) for point in post_points),
        default=None,
    )
    normalized_trend = _trend(points, start_at, normalized=True)

    # Classification reads the calibrated value alone. This used to take
    # min(raw, normalized) as a safety floor, which is right for an alarm and
    # wrong for a judgement: this owner's raw stream sits 1.0-2.8 mmol/L below
    # true glucose, so an ordinary 5.5 arrived as a raw 3.5 and the plate that
    # followed was filed as a rescue. `_normalized` already falls back to raw
    # for a session with no calibration, which is the only place raw should
    # still decide anything. Both raw figures are still reported.
    safety_glucose = normalized_at
    low_at_start = (
        safety_glucose is not None and safety_glucose < LOW_GLUCOSE_MMOL_L
    )
    # Same reason. A constant offset would cancel out of a slope, but the
    # calibration is affine, so the calibrated trend is the one to read.
    falling = (
        normalized_trend is not None and normalized_trend <= -(1 / 18.0182)
    )
    # "No bolus" is only evidence once a bolus would no longer be linked here.
    # Inside the window the user may still be photographing the plate and has
    # simply not dosed yet — and a half-entered lunch is exactly what "food, no
    # insulin, small carbs, drifting down" looks like.
    settled = (
        start_at + SETTLING_WINDOW
        <= (now if now is not None else _local_wall_time(datetime.now(UTC)))
    )

    total_carbs = sum(float(meal.total_carbs_g or 0) for meal in component.meals)
    roles = {
        normalized_text(
            str((meal.derived_categories or {}).get("meal_role") or "")
        )
        for meal in component.meals
    }
    roles.discard("")
    explicit_corrections = [
        event
        for event in component.insulin
        if "correction" in normalized_text(event.event_type)
    ]
    food_boluses = [
        event for event in component.insulin if event not in explicit_corrections
    ]

    classification: TherapyClass
    confidence: TherapyConfidence
    reasons: list[str]
    suggested_carbs: float | None = None
    suggestion_source: Literal["ada_default"] | None = None

    # Being below range before eating is its own evidence and stands whenever
    # it happens. Drifting down is not: it only becomes a rescue because no
    # bolus followed, so it has to wait until that is settled.
    small_falling_food_only = (
        bool(component.meals)
        and not component.insulin
        and settled
        and falling
        and 0 < total_carbs <= SNACK_MAX_CARBS_G
    )

    if component.meals and not component.insulin and (
        low_at_start or small_falling_food_only
    ):
        classification = "carb_correction"
        confidence = (
            "high"
            if (
                safety_glucose is not None
                and safety_glucose < LEVEL_TWO_LOW_MMOL_L
            )
            or (
                small_falling_food_only
                and total_carbs <= DEFAULT_RESCUE_CARBS_G
            )
            else "medium"
        )
        reasons = []
        if low_at_start and safety_glucose is not None:
            reasons.append(f"глюкоза перед едой {safety_glucose:.1f} ммоль/л")
        elif small_falling_food_only:
            reasons.append("глюкоза быстро снижалась перед едой")
        reasons.append("рядом нет пищевого болюса")
        if small_falling_food_only:
            reasons.append(f"небольшой приём: {total_carbs:.0f} г")
        if raw_at is not None and normalized_at is not None:
            reasons.append(
                f"raw {raw_at:.1f}, нормализованная {normalized_at:.1f}"
            )
        if falling:
            reasons.append("глюкоза снижалась")
        suggested_carbs = DEFAULT_RESCUE_CARBS_G
        suggestion_source = "ada_default"
    elif component.meals and explicit_corrections:
        classification = "mixed"
        confidence = "high" if food_boluses else "medium"
        reasons = ["еда и отдельная коррекция инсулином в одном эпизоде"]
    elif component.meals:
        is_role_snack = (
            bool(roles)
            and roles.issubset(SNACK_ROLES)
            and total_carbs <= SNACK_MAX_CARBS_G
        )
        if is_role_snack or (not roles and total_carbs <= SNACK_MAX_CARBS_G):
            classification = "snack"
            confidence = "high" if is_role_snack else "medium"
            reasons = (
                [f"роль продукта: {', '.join(sorted(roles))}"]
                if is_role_snack
                else [f"небольшой отдельный приём: {total_carbs:.0f} г"]
            )
        else:
            classification = "meal"
            confidence = "high" if food_boluses or roles else "medium"
            reasons = (
                [f"углеводы приёма: {total_carbs:.0f} г"]
                if roles.issubset(SNACK_ROLES)
                and total_carbs > SNACK_MAX_CARBS_G
                else [f"роль приёма: {', '.join(sorted(roles))}"]
                if roles
                else [f"углеводы приёма: {total_carbs:.0f} г"]
            )
    elif component.insulin:
        classification = "insulin_correction"
        confidence = "high" if explicit_corrections else "medium"
        reasons = [
            "инсулин без еды",
            (
                "событие помечено как коррекция"
                if explicit_corrections
                else "рядом нет записи о еде"
            ),
        ]
    else:
        classification = "unresolved"
        confidence = "low"
        reasons = ["недостаточно контекста"]

    return EpisodeTherapy(
        classification=classification,
        confidence=confidence,
        reasons=reasons,
        suggested_carbs_g=suggested_carbs,
        suggestion_source=suggestion_source,
        glucose_at_start_raw=_rounded(raw_at),
        glucose_at_start_normalized=_rounded(normalized_at),
        glucose_plus_2h_raw=_rounded(raw_plus_2h),
        glucose_plus_2h_normalized=_rounded(normalized_plus_2h),
        peak_post_event_raw=_rounded(raw_peak),
        peak_post_event_normalized=_rounded(normalized_peak),
    )


def _nearest(
    points: list[GlucoseDashboardPoint],
    target: datetime,
) -> GlucoseDashboardPoint | None:
    if not points:
        return None
    nearest = min(points, key=lambda point: abs(point.timestamp - target))
    return nearest if abs(nearest.timestamp - target) <= POINT_TOLERANCE else None


def catch_up_event_ids(
    component: EpisodeComponent,
    points: list[GlucoseDashboardPoint],
) -> set[UUID]:
    """Boluses given to chase a rise the meal was already causing.

    Not meal insulin and not a correction. It answers a rise that has already
    started, so it is given knowing something the dose at the plate could not:
    that the first bolus did not hold. Counting it as ordinary meal coverage
    makes the food look like it needed more insulin, when what it needed was
    the same insulin earlier — and a recommendation that quotes the inflated
    total up front is a different, riskier act than 8 U now and 4 U if it
    climbs.

    Measured over 75 days for this owner: boluses at the plate sit on a
    −0.40 mmol/L per hour trend, later ones on +1.80 with 86% rising. The two
    acts separate on what glucose was doing, so that is the test used here.
    A bolus given while glucose is flat or falling stays an ordinary one.
    """
    if not component.meals:
        return set()
    sitting_at = min(meal.eaten_at for meal in component.meals)
    catch_ups: set[UUID] = set()
    for event in component.insulin:
        at = _local_wall_time(event.timestamp)
        if not (
            sitting_at + CATCH_UP_AFTER <= at <= sitting_at + CATCH_UP_UNTIL
        ):
            continue
        # A later plate makes the rise ambiguous; that insulin belongs to it.
        if any(
            sitting_at < meal.eaten_at <= at for meal in component.meals
        ):
            continue
        rising = [
            trend
            for trend in (
                _trend(points, at, normalized=True),
                _trend(points, at, normalized=False),
            )
            if trend is not None
        ]
        if rising and max(rising) >= CATCH_UP_RISING_PER_MINUTE:
            catch_ups.add(event.id)
    return catch_ups


def _trend(
    points: list[GlucoseDashboardPoint],
    target: datetime,
    *,
    normalized: bool,
) -> float | None:
    recent = [
        point
        for point in points
        if target - TREND_LOOKBACK <= point.timestamp <= target
    ]
    if len(recent) < 2:
        return None
    first = recent[0]
    last = recent[-1]
    minutes = (last.timestamp - first.timestamp).total_seconds() / 60
    if minutes < 5:
        return None
    value = _normalized if normalized else _raw
    first_value = value(first)
    last_value = value(last)
    if first_value is None or last_value is None:
        return None
    return (last_value - first_value) / minutes


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
