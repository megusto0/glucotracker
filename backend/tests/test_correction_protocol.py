"""Correction protocol: the level-start gate and the nadir placebo."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from glucotracker.application.correction_protocol import (
    MIN_PLACEBO_WINDOWS,
    nadir_placebo,
    pre_dose_verdict,
)


@pytest.mark.parametrize(
    ("minus_60", "minus_30", "start", "expected"),
    [
        (9.0, 9.0, 9.0, "level"),
        (8.5, 8.8, 9.0, "level"),
        # A climb that only began in the last half hour is still a climb.
        (9.0, 8.5, 9.0, "rising"),
        (8.0, 8.7, 9.0, "rising"),
        (10.0, 9.3, 9.0, "falling"),
        (None, 9.0, 9.0, "missing"),
        (9.0, None, 9.0, "missing"),
    ],
)
def test_pre_dose_verdict(minus_60, minus_30, start, expected) -> None:
    assert (
        pre_dose_verdict(
            glucose_start=start,
            glucose_minus_30=minus_30,
            glucose_minus_60=minus_60,
        )
        == expected
    )


def _quiet_days(count: int, dip: float) -> list[tuple[datetime, float]]:
    """One flat 7.0 trace per day, 09:00–14:30, with one reading ``dip`` lower
    at 12:00 — inside the single quiet window anchored at 10:00."""
    series: list[tuple[datetime, float]] = []
    for day in range(count):
        start = datetime(2026, 7, 1 + day, 9)
        for step in range(0, 66 + 1):
            at = start + timedelta(minutes=5 * step)
            value = 7.0 - dip if step == 36 else 7.0
            series.append((at, value))
    return series


def test_placebo_is_the_fall_the_nadir_rule_reads_without_insulin() -> None:
    placebo = nadir_placebo(
        _quiet_days(MIN_PLACEBO_WINDOWS, dip=0.8),
        meal_times=[],
        insulin_times=[],
    )
    assert placebo.window_count == MIN_PLACEBO_WINDOWS
    assert placebo.fall_mmol_l == pytest.approx(0.8)


def test_windows_near_food_or_insulin_are_not_quiet() -> None:
    series = _quiet_days(MIN_PLACEBO_WINDOWS, dip=0.8)
    meal_times = [datetime(2026, 7, 1 + day, 8) for day in range(2)]
    insulin_times = [datetime(2026, 7, 3, 11)]
    placebo = nadir_placebo(
        series,
        meal_times=meal_times,
        insulin_times=insulin_times,
    )
    # Three days lost; five windows are too few to subtract anything.
    assert placebo.window_count == MIN_PLACEBO_WINDOWS - 3
    assert placebo.fall_mmol_l is None


def test_empty_series_has_no_placebo() -> None:
    placebo = nadir_placebo([], meal_times=[], insulin_times=[])
    assert placebo.fall_mmol_l is None
    assert placebo.window_count == 0
