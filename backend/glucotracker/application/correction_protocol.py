"""What a correction has to look like before its fall can be read as ISF.

Two biases sit inside "how far did glucose drop after the dose", and both were
measured on this owner's own history (ml-labs/response-attribution/REPORT.md):

1. **The dose answers the trace.** Most corrections are given while glucose is
   already climbing for a reason the diary does not hold. Whatever drove the
   climb keeps acting after the dose, so the fall understates the insulin.
   Over five months, the 30 minutes before a dose rose by a median 0.4 mmol/L,
   and a distributed-lag fit found an "effect" of the dose *before* it was
   given — which a causal effect cannot have. A correction only counts when
   the trace was level for the hour before it, so that "what would have
   happened without the dose" is the flat line it was already on.

2. **A minimum always lies below the start.** Reading the effect at the lowest
   point of a four-hour window finds a fall even where nothing was given: on
   126 independent quiet windows with no food or insulin, glucose ended where
   it began (median +0.05) while start-minus-minimum read 1.0 mmol/L. That
   placebo fall is measured on the same owner, in the same period, with the
   same rule, and taken off every correction before it is divided by the dose.

Pure functions only: the caller supplies the glucose series and intervention
times. Nothing here reads or writes a record, and nothing produces a dose.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Literal

PreDoseVerdict = Literal["level", "rising", "falling", "missing"]

#: How far back the trace has to be level, and how level. Thirty minutes is
#: checked separately so a climb that only began just before the dose — the
#: commonest case — is not averaged away by a flat first half hour.
PRE_DOSE_LONG = timedelta(minutes=60)
PRE_DOSE_SHORT = timedelta(minutes=30)
MAX_LEVEL_CHANGE_LONG_MMOL_L = 0.6
MAX_LEVEL_CHANGE_SHORT_MMOL_L = 0.4

#: Placebo windows share the correction's measurement window and washouts.
PLACEBO_NADIR_FROM = timedelta(minutes=45)
PLACEBO_NADIR_TO = timedelta(hours=4)
PLACEBO_FOOD_WASHOUT = timedelta(hours=4)
PLACEBO_INSULIN_WASHOUT = timedelta(hours=5)
#: Windows are spaced so none shares a stretch of trace with another; adjacent
#: hours of one quiet evening are one observation, not four.
PLACEBO_SPACING = timedelta(hours=4)
PLACEBO_POINT_TOLERANCE = timedelta(minutes=15)
PLACEBO_EDGE_TOLERANCE = timedelta(minutes=20)
PLACEBO_MAX_GAP = timedelta(minutes=30)
PLACEBO_MIN_START_MMOL_L = 4.0
PLACEBO_MAX_START_MMOL_L = 15.0
#: Below this many windows the placebo is noise and is not subtracted.
MIN_PLACEBO_WINDOWS = 8


@dataclass(frozen=True)
class NadirPlacebo:
    """The fall the nadir rule reads where no insulin was given."""

    fall_mmol_l: float | None
    window_count: int


def pre_dose_verdict(
    *,
    glucose_start: float | None,
    glucose_minus_30: float | None,
    glucose_minus_60: float | None,
) -> PreDoseVerdict:
    """Say whether the hour before the dose was level enough to compare with."""
    if glucose_start is None or glucose_minus_30 is None or glucose_minus_60 is None:
        return "missing"
    long_change = glucose_start - glucose_minus_60
    short_change = glucose_start - glucose_minus_30
    if (
        long_change > MAX_LEVEL_CHANGE_LONG_MMOL_L
        or short_change > MAX_LEVEL_CHANGE_SHORT_MMOL_L
    ):
        return "rising"
    if (
        long_change < -MAX_LEVEL_CHANGE_LONG_MMOL_L
        or short_change < -MAX_LEVEL_CHANGE_SHORT_MMOL_L
    ):
        return "falling"
    return "level"


def nadir_placebo(
    series: Sequence[tuple[datetime, float]],
    *,
    meal_times: Sequence[datetime],
    insulin_times: Sequence[datetime],
) -> NadirPlacebo:
    """Median start-minus-minimum over quiet, non-overlapping windows.

    ``series`` must be sorted by time; the event lists need not be.
    """
    if not series:
        return NadirPlacebo(fall_mmol_l=None, window_count=0)
    times = [timestamp for timestamp, _ in series]
    meals = sorted(meal_times)
    doses = sorted(insulin_times)
    first = times[0].replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    falls: list[float] = []
    anchor = first
    while anchor + PLACEBO_NADIR_TO <= times[-1]:
        fall = _quiet_window_fall(series, times, anchor, meals, doses)
        if fall is None:
            anchor += timedelta(hours=1)
            continue
        falls.append(fall)
        anchor += PLACEBO_SPACING
    if len(falls) < MIN_PLACEBO_WINDOWS:
        return NadirPlacebo(fall_mmol_l=None, window_count=len(falls))
    return NadirPlacebo(fall_mmol_l=median(falls), window_count=len(falls))


def _quiet_window_fall(
    series: Sequence[tuple[datetime, float]],
    times: list[datetime],
    anchor: datetime,
    meals: list[datetime],
    doses: list[datetime],
) -> float | None:
    end = anchor + PLACEBO_NADIR_TO
    if _any_between(meals, anchor - PLACEBO_FOOD_WASHOUT, end) or _any_between(
        doses, anchor - PLACEBO_INSULIN_WASHOUT, end
    ):
        return None
    start = _nearest(series, times, anchor)
    if start is None or not (
        PLACEBO_MIN_START_MMOL_L <= start <= PLACEBO_MAX_START_MMOL_L
    ):
        return None
    lo = bisect_left(times, anchor + PLACEBO_NADIR_FROM)
    hi = bisect_left(times, end + timedelta(seconds=1))
    # A window with most of its trace missing would read its minimum from
    # whichever few readings survived, so it has to be covered end to end.
    window_times = times[lo:hi]
    if (
        not window_times
        or window_times[0] - (anchor + PLACEBO_NADIR_FROM) > PLACEBO_EDGE_TOLERANCE
        or end - window_times[-1] > PLACEBO_EDGE_TOLERANCE
        or any(
            later - earlier > PLACEBO_MAX_GAP
            for earlier, later in zip(window_times, window_times[1:], strict=False)
        )
    ):
        return None
    return start - min(value for _, value in series[lo:hi])


def _any_between(sorted_times: list[datetime], start: datetime, end: datetime) -> bool:
    index = bisect_left(sorted_times, start)
    return index < len(sorted_times) and sorted_times[index] <= end


def _nearest(
    series: Sequence[tuple[datetime, float]],
    times: list[datetime],
    target: datetime,
) -> float | None:
    index = bisect_left(times, target)
    best: tuple[timedelta, float] | None = None
    for candidate in (index - 1, index):
        if 0 <= candidate < len(series):
            gap = abs(times[candidate] - target)
            if gap <= PLACEBO_POINT_TOLERANCE and (best is None or gap < best[0]):
                best = (gap, series[candidate][1])
    return best[1] if best is not None else None
