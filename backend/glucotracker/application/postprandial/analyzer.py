"""Postprandial CGM analyzer — computes glucose response per meal.

Pure-Python module. Fully unit-testable with synthetic CGM streams.
No LLM calls. No external services. Deterministic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.glucose_visibility import visible_glucose_filter
from glucotracker.application.postprandial import thresholds as T
from glucotracker.application.time import local_wall_time, utc_instant_from_local_wall
from glucotracker.domain.entities import (
    GlycemicResponse,
    MealStatus,
    PreMealState,
    TasteProfile,
)
from glucotracker.infra.db.models import Meal, NightscoutGlucoseEntry, User

logger = logging.getLogger(__name__)

SAMPLE_MINUTES = [0, 30, 60, 90, 180]
SAMPLE_MINUTES_EXTENDED = [240, 300]
WINDOW_TOTAL_MINUTES = 180
PRE_MEAL_WINDOW_MINUTES = 30
HYP_RECOVERY_MAX_KCAL = 250
HYP_RECOVERY_MIN_CARB_G = T.HYPO_RECOVERY_MIN_CARB_G
HYP_RECOVERY_PRE_LOW_MINUTES = 30


def _cgm_readings(
    session: Session,
    user_id: UUID,
    start: datetime,
    end: datetime,
) -> list[NightscoutGlucoseEntry]:
    utc_start = utc_instant_from_local_wall(local_wall_time(start))
    utc_end = utc_instant_from_local_wall(local_wall_time(end))
    return list(
        session.scalars(
            select(NightscoutGlucoseEntry)
            .where(
                NightscoutGlucoseEntry.owner_id == user_id,
                NightscoutGlucoseEntry.timestamp >= utc_start,
                NightscoutGlucoseEntry.timestamp <= utc_end,
                visible_glucose_filter(user_id),
            )
            .order_by(NightscoutGlucoseEntry.timestamp)
        )
    )


def _reading_time(reading: NightscoutGlucoseEntry) -> datetime:
    """Return a CGM reading timestamp as app-local naive wall-clock time."""
    return local_wall_time(reading.timestamp)


def _interpolate(
    readings: list[NightscoutGlucoseEntry],
    target: datetime,
) -> dict[str, Any] | None:
    """Linearly interpolate glucose at `target` from surrounding readings."""
    if not readings:
        return None

    before: NightscoutGlucoseEntry | None = None
    after: NightscoutGlucoseEntry | None = None
    for r in readings:
        reading_at = _reading_time(r)
        if reading_at <= target:
            before = r
        if reading_at >= target and after is None:
            after = r

    if before is None or after is None:
        return None

    before_at = _reading_time(before)
    after_at = _reading_time(after)
    if before_at == after_at:
        return {"value": round(before.value_mmol_l, 1), "source": "actual"}

    gap_seconds = (after_at - before_at).total_seconds()
    if gap_seconds > T.CGM_GAP_MAX_MINUTES * 60:
        return None

    offset_seconds = (target - before_at).total_seconds()
    fraction = offset_seconds / gap_seconds
    value = before.value_mmol_l + (
        after.value_mmol_l - before.value_mmol_l
    ) * fraction

    return {"value": round(value, 1), "source": "interpolated"}


def _nearest_reading(
    readings: list[NightscoutGlucoseEntry],
    target: datetime,
) -> dict[str, Any] | None:
    """Return the reading nearest to `target`, ±5 min tolerance."""
    if not readings:
        return None
    target = local_wall_time(target)
    nearest = min(
        readings, key=lambda r: abs((_reading_time(r) - target).total_seconds())
    )
    diff = abs((_reading_time(nearest) - target).total_seconds())
    if diff > 5 * 60:
        return None
    return {"value": round(nearest.value_mmol_l, 1), "source": "actual"}


def compute_anchors(
    session: Session,
    meal: Meal,
) -> dict[int, dict[str, Any] | None]:
    """Compute CGM sample anchors at t=0,30,60,90,180 relative to eaten_at."""
    meal_at = local_wall_time(meal.eaten_at)
    start = meal_at
    end = meal_at + timedelta(minutes=WINDOW_TOTAL_MINUTES)
    readings = _cgm_readings(session, meal.owner_id, start, end)

    anchors: dict[int, dict[str, Any] | None] = {}
    for offset in SAMPLE_MINUTES:
        target = meal_at + timedelta(minutes=offset)
        anchor = _nearest_reading(readings, target)
        if anchor is None:
            anchor = _interpolate(readings, target)
        anchors[offset] = anchor

    return anchors


def compute_extended_anchors(
    session: Session,
    meal: Meal,
) -> dict[int, dict[str, Any] | None]:
    """Compute CGM sample anchors at t=240,300 relative to eaten_at."""
    meal_at = local_wall_time(meal.eaten_at)
    start = meal_at + timedelta(minutes=180)
    end = meal_at + timedelta(minutes=T.EXTENDED_WINDOW_MINUTES)
    readings = _cgm_readings(session, meal.owner_id, start, end)

    anchors: dict[int, dict[str, Any] | None] = {}
    for offset in SAMPLE_MINUTES_EXTENDED:
        target = meal_at + timedelta(minutes=offset)
        anchor = _nearest_reading(readings, target)
        if anchor is None:
            anchor = _interpolate(readings, target)
        anchors[offset] = anchor

    return anchors


def compute_pre_meal_state(
    session: Session,
    meal: Meal,
) -> tuple[PreMealState, float | None]:
    """Determine glucose state in the 30 min before the meal."""
    meal_at = local_wall_time(meal.eaten_at)
    window_start = meal_at - timedelta(minutes=PRE_MEAL_WINDOW_MINUTES)
    window_end = meal_at + timedelta(minutes=5)
    readings = _cgm_readings(session, meal.owner_id, window_start, window_end)

    if not readings:
        return PreMealState.unknown, None

    nearest = min(
        readings,
        key=lambda r: abs((_reading_time(r) - meal_at).total_seconds()),
    )
    value = nearest.value_mmol_l

    pre_15_anchor = _interpolate(
        readings, meal_at - timedelta(minutes=15)
    )
    pre_15 = (
        pre_15_anchor["value"] if pre_15_anchor else None
    )

    if value < 4.0:
        return PreMealState.low, pre_15
    if value > 10.0:
        return PreMealState.high, pre_15
    return PreMealState.in_range, pre_15


def _find_peak(
    readings: list[NightscoutGlucoseEntry],
    t0_value: float,
) -> dict[str, Any]:
    """Find the peak glucose value and time in the 180-min window."""
    if not readings:
        return {"value": t0_value, "minutes_from_t0": 0}

    peak = max(readings, key=lambda r: r.value_mmol_l)
    peak_minutes = (
        _reading_time(peak) - _reading_time(readings[0])
    ).total_seconds() / 60
    return {
        "value": round(peak.value_mmol_l, 1),
        "minutes_from_t0": int(round(peak_minutes)),
    }


def _coverage_fraction(
    readings: list[NightscoutGlucoseEntry],
    start: datetime,
    end: datetime,
) -> float:
    """Estimate CGM coverage as fraction of 180-min window with readings."""
    if not readings:
        return 0.0

    window_seconds = (end - start).total_seconds()
    if window_seconds <= 0:
        return 0.0

    covered = 0.0
    for i in range(len(readings)):
        reading_at = _reading_time(readings[i])
        r_start = max(
            reading_at, start
        )
        next_ts = (
            _reading_time(readings[i + 1])
            if i + 1 < len(readings)
            else end
        )
        r_end = min(next_ts, end)

        if i + 1 < len(readings):
            gap = (next_ts - reading_at).total_seconds()
            if gap <= T.CGM_GAP_MAX_MINUTES * 60:
                covered += (r_end - r_start).total_seconds()
        else:
            covered += min(5 * 60, (r_end - r_start).total_seconds())

    return min(1.0, covered / window_seconds)


def _count_peaks(
    readings: list[NightscoutGlucoseEntry],
    prominence: float,
) -> int:
    """Count distinct peaks with given minimum prominence."""
    if len(readings) < 3:
        return 0

    values = [r.value_mmol_l for r in readings]
    peaks = 0
    for i in range(1, len(values) - 1):
        if values[i] > values[i - 1] and values[i] > values[i + 1]:
            left_min = min(values[max(0, i - 3):i])
            right_min = min(values[i + 1:min(len(values), i + 4)])
            if (
                values[i] - left_min >= prominence
                and values[i] - right_min >= prominence
            ):
                peaks += 1
    return peaks


def _sustained_above_threshold(
    readings: list[NightscoutGlucoseEntry],
    threshold: float,
    min_minutes: int,
) -> bool:
    """Check if glucose stays above a threshold for >= min_minutes."""
    if not readings:
        return False

    above_start: datetime | None = None
    for r in readings:
        reading_at = _reading_time(r)
        if r.value_mmol_l > threshold:
            if above_start is None:
                above_start = reading_at
        else:
            if above_start is not None:
                duration = (
                    reading_at - above_start
                ).total_seconds() / 60
                if duration >= min_minutes:
                    return True
                above_start = None

    if above_start is not None:
        duration = (
            _reading_time(readings[-1]) - above_start
        ).total_seconds() / 60
        return duration >= min_minutes

    return False


def classify_response(
    anchors: dict[int, dict[str, Any] | None],
    readings: list[NightscoutGlucoseEntry],
    coverage: float,
) -> GlycemicResponse:
    """Classify glycemic response from anchors and raw CGM stream."""
    if coverage < T.COVERAGE_MIN_FOR_CLASSIFICATION:
        return GlycemicResponse.unknown

    t0 = anchors.get(0)
    t90 = anchors.get(90)
    if t0 is None:
        return GlycemicResponse.unknown

    t0_value = t0["value"]
    peak = _find_peak(readings, t0_value)
    delta_max = peak["value"] - t0_value

    if (
        delta_max < T.GENTLE_MAX_DELTA
        and t90 is not None
        and abs(t90["value"] - t0_value) < T.GENTLE_RETURN_DELTA
    ):
        return GlycemicResponse.gentle

    if (
        delta_max >= T.SPIKE_MIN_DELTA
        or _sustained_above_threshold(
            readings,
            T.SPIKE_SUSTAINED_THRESHOLD,
            T.SPIKE_SUSTAINED_MINUTES,
        )
    ):
        return GlycemicResponse.spike

    peak_count = _count_peaks(readings, T.UNSTABLE_PEAK_PROMINENCE)
    if peak_count >= T.UNSTABLE_MIN_PEAKS:
        return GlycemicResponse.unstable

    values = [r.value_mmol_l for r in readings]
    if len(values) >= 3:
        try:
            cv = stdev(values) / mean(values)
            if cv > T.UNSTABLE_MAX_CV:
                return GlycemicResponse.unstable
        except (ZeroDivisionError, RuntimeError):
            pass

    return GlycemicResponse.moderate


def detect_hypo_recovery(
    meal: Meal,
    pre_meal_state: PreMealState,
) -> bool:
    """Return True if this meal looks like hypoglycemia treatment."""
    if pre_meal_state != PreMealState.low:
        return False

    if meal.total_kcal >= HYP_RECOVERY_MAX_KCAL:
        return False

    if (meal.total_carbs_g or 0.0) < HYP_RECOVERY_MIN_CARB_G:
        return False

    ai_categories = meal.ai_categories or {}
    derived = meal.derived_categories or {}

    taste = ai_categories.get("taste_profile")
    role = derived.get("meal_role")

    if taste not in {TasteProfile.sweet.value, TasteProfile.drink_sweet.value}:
        return False
    if role not in {"snack", "drink"}:
        return False

    return True


def _compute_fat_share(meal: Meal) -> float | None:
    """Return fat calories as a fraction of total kcal.

    Returns None if total_kcal is zero or negative.
    """
    if meal.total_kcal <= 0:
        return None
    fat_cal = meal.total_fat_g * 9.0
    return fat_cal / meal.total_kcal


def _peak_at_or_after_t180(
    readings_0_180: list[NightscoutGlucoseEntry],
    readings_180_300: list[NightscoutGlucoseEntry],
) -> bool:
    """Check if the highest glucose value lies in the extended window."""
    peak_180 = max(
        (r.value_mmol_l for r in readings_0_180), default=0.0
    )
    peak_300 = max(
        (r.value_mmol_l for r in readings_180_300), default=0.0
    )
    return peak_300 > peak_180


def compute_postprandial_response(
    session: Session,
    meal: Meal,
) -> dict[str, Any] | None:
    """Compute the full postprandial response for a meal.

    Returns None if CGM data is completely unavailable for the user.
    """
    user = session.scalar(select(User).where(User.id == meal.owner_id))
    if user is None:
        return None

    anchors = compute_anchors(session, meal)
    pre_meal_state, pre_15 = compute_pre_meal_state(session, meal)

    meal_at = local_wall_time(meal.eaten_at)
    start = meal_at
    end = meal_at + timedelta(minutes=WINDOW_TOTAL_MINUTES)
    readings = _cgm_readings(session, meal.owner_id, start, end)
    coverage = _coverage_fraction(readings, start, end)

    response = classify_response(anchors, readings, coverage)
    is_hypo = detect_hypo_recovery(meal, pre_meal_state)
    is_meal_during_low = pre_meal_state == PreMealState.low

    t0 = anchors.get(0, {}) or {}
    peak = _find_peak(readings, (t0.get("value") or 0.0))
    delta_max = (
        round(peak["value"] - (t0.get("value") or peak["value"]), 1)
        if t0
        else 0.0
    )

    quality_flags: list[str] = []
    if (
        T.COVERAGE_MIN_FOR_CLASSIFICATION
        <= coverage
        < T.COVERAGE_DOWNWEIGHT_THRESHOLD
    ):
        quality_flags.append("low_coverage")

    ext_anchors = compute_extended_anchors(session, meal)
    ext_start = meal_at + timedelta(minutes=180)
    ext_end = meal_at + timedelta(minutes=T.EXTENDED_WINDOW_MINUTES)
    ext_readings = _cgm_readings(session, meal.owner_id, ext_start, ext_end)
    ext_coverage = _coverage_fraction(ext_readings, ext_start, ext_end)

    fat_share = _compute_fat_share(meal)
    delayed_peak_likely = False
    if fat_share is not None and fat_share > T.DELAYED_PEAK_FAT_SHARE:
        if _peak_at_or_after_t180(readings, ext_readings):
            if ext_coverage >= T.DELAYED_PEAK_MIN_EXTENDED_COVERAGE:
                delayed_peak_likely = True

    from datetime import UTC

    all_anchors: dict[str, Any] = {str(k): v for k, v in anchors.items()}
    for k, v in ext_anchors.items():
        all_anchors[str(k)] = v

    return {
        "anchors": all_anchors,
        "peak": peak,
        "delta_max": delta_max,
        "pre_meal_state": pre_meal_state.value,
        "pre_meal_glucose_at_minus_15": pre_15,
        "glycemic_response": response.value,
        "is_hypo_recovery": is_hypo,
        "is_meal_during_low": is_meal_during_low,
        "delayed_peak_likely": delayed_peak_likely,
        "coverage_180min": round(coverage, 3),
        "extended_coverage_300min": round(ext_coverage, 3),
        "quality_flags": quality_flags,
        "computed_at": datetime.now(UTC).isoformat(),
    }


def aggregate_by_product(
    session: Session,
    user_id: UUID,
    product_name: str,
    days: int = 30,
    exclude_delayed_peaks: bool = True,
) -> dict[str, Any] | None:
    """Aggregate postprandial responses for meals containing a product.

    Args:
        exclude_delayed_peaks: If True, skip meals flagged with
            delayed_peak_likely (their 180-min delta is understated).
    """
    cutoff = datetime.now() - timedelta(days=days)
    meals = list(
        session.scalars(
            select(Meal)
            .where(
                Meal.owner_id == user_id,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= cutoff,
                Meal.postprandial_response.isnot(None),
            )
        )
    )

    matching: list[dict[str, Any]] = []
    for meal in meals:
        if not meal.items:
            continue
        item_names = {item.name.casefold() for item in meal.items}
        if product_name.casefold() in item_names:
            pr = meal.postprandial_response
            if pr and pr.get("delta_max") is not None:
                if (
                    exclude_delayed_peaks
                    and pr.get("delayed_peak_likely")
                ):
                    continue
                matching.append(pr)

    if len(matching) < 3:
        return None

    deltas = [r["delta_max"] for r in matching]
    try:
        dev = stdev(deltas) if len(deltas) >= 2 else 0.0
    except RuntimeError:
        dev = 0.0

    return {
        "samples": len(matching),
        "mean_delta_max": round(mean(deltas), 2),
        "stdev_delta_max": round(dev, 2),
        "predictable": dev < 1.0,
    }
