"""Pure digital twin estimator tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from glucotracker.application.twin.estimator import (
    BGAnchor,
    CarbEvent,
    EstimatorParams,
    InsulinEvent,
    estimate_curve,
)
from glucotracker.application.twin.kernels import (
    carb_absorption_duration_minutes,
    carb_cob_remaining_fraction,
    carb_effect,
    classify_carb_profile,
    icr_at,
    insulin_activity_shape,
    insulin_cumulative_absorbed,
    insulin_effect,
    insulin_iob_remaining_fraction,
)


def _params() -> EstimatorParams:
    return EstimatorParams(
        icr_morning=12,
        icr_day=12,
        icr_evening=12,
        isf=2,
    )


def test_empty_anchors_returns_empty_list() -> None:
    assert (
        estimate_curve(
            bg_anchors=[],
            carbs=[],
            insulin=[],
            params=_params(),
            start=datetime(2026, 4, 28, 8, 0),
            end=datetime(2026, 4, 28, 9, 0),
        )
        == []
    )


def test_single_anchor_constant_baseline_no_events() -> None:
    points = estimate_curve(
        bg_anchors=[BGAnchor(datetime(2026, 4, 28, 8, 0), 6.0)],
        carbs=[],
        insulin=[],
        params=_params(),
        start=datetime(2026, 4, 28, 8, 0),
        end=datetime(2026, 4, 28, 11, 0),
        step_minutes=180,
    )

    assert [point.mode for point in points] == ["forecast", "forecast"]
    assert [point.mmol for point in points] == [6.0, 6.0]
    assert points[-1].ci_high - points[-1].mmol == 3.0


def test_carb_only_peak_amplitude() -> None:
    points = estimate_curve(
        bg_anchors=[BGAnchor(datetime(2026, 4, 28, 8, 0), 6.0)],
        carbs=[CarbEvent(datetime(2026, 4, 28, 8, 15), 60.0)],
        insulin=[],
        params=_params(),
        start=datetime(2026, 4, 28, 9, 15),
        end=datetime(2026, 4, 28, 9, 15),
    )

    assert points[0].mmol == 11.0


def test_insulin_only_drop_amplitude() -> None:
    # Peak of the biphasic activity curve is early (~30 min); amplitude = units * isf.
    points = estimate_curve(
        bg_anchors=[BGAnchor(datetime(2026, 4, 28, 8, 0), 8.0)],
        carbs=[],
        insulin=[InsulinEvent(datetime(2026, 4, 28, 8, 0), 4.0)],
        params=_params(),
        start=datetime(2026, 4, 28, 8, 30),
        end=datetime(2026, 4, 28, 8, 30),
    )

    assert abs(points[0].mmol - 0.0) < 0.05


def test_interpolation_redistributes_residual() -> None:
    points = estimate_curve(
        bg_anchors=[
            BGAnchor(datetime(2026, 4, 28, 8, 0), 6.0),
            BGAnchor(datetime(2026, 4, 28, 9, 0), 8.0),
        ],
        carbs=[],
        insulin=[],
        params=_params(),
        start=datetime(2026, 4, 28, 8, 30),
        end=datetime(2026, 4, 28, 8, 30),
    )

    assert points[0].mode == "interpolation"
    assert points[0].mmol == 7.0


def test_icr_at_morning_day_evening_boundaries() -> None:
    params = EstimatorParams(
        icr_morning=10,
        icr_day=12,
        icr_evening=14,
        isf=2,
    )

    assert icr_at(datetime(2026, 4, 28, 5, 59), params) == 10
    assert icr_at(datetime(2026, 4, 28, 11, 0), params) == 12
    assert icr_at(datetime(2026, 4, 28, 18, 0), params) == 14


def test_carb_kernel_is_proportional_to_grams() -> None:
    small = carb_effect(60, 30, 12, 180)
    large = carb_effect(60, 60, 12, 180)

    assert large == small * 2


def test_insulin_iob_is_front_loaded_with_long_tail() -> None:
    """Empirical biphasic curve: ~1/3 by 90m, majority by 3h, tail to DIA."""
    dia = 360
    assert insulin_cumulative_absorbed(0, dia) == 0.0
    assert insulin_iob_remaining_fraction(0, dia) == 1.0
    # Front half of the first 90 minutes is still modest (~35% of total action).
    assert 0.30 <= insulin_cumulative_absorbed(90, dia) <= 0.40
    assert 0.55 <= insulin_iob_remaining_fraction(90, dia) <= 0.70
    # About 60% delivered by 3 hours.
    assert 0.55 <= insulin_cumulative_absorbed(180, dia) <= 0.65
    # Long tail still active past 4 hours.
    assert 0.15 <= insulin_iob_remaining_fraction(270, dia) <= 0.30
    assert insulin_iob_remaining_fraction(dia, dia) == 0.0


def test_insulin_activity_peaks_early_and_scales_with_dose() -> None:
    dia = 270
    peak_t = max(range(1, dia), key=lambda t: insulin_activity_shape(float(t), dia))
    assert peak_t <= 90
    assert insulin_activity_shape(float(peak_t), dia) == pytest.approx(1.0, abs=1e-6)
    # Later activity is lower but not zero (tail).
    assert 0.0 < insulin_activity_shape(180, dia) < 0.7
    assert insulin_effect(float(peak_t), 2.0, 3.0, dia) == pytest.approx(6.0, abs=1e-6)
    assert insulin_effect(float(peak_t), 4.0, 3.0, dia) == pytest.approx(12.0, abs=1e-6)


def test_carb_profile_classifies_energy_drink_vs_egg_salad() -> None:
    # Today's energy drink: pure sugar liquid.
    assert (
        classify_carb_profile(carbs_g=53.88, protein_g=0.0, fat_g=0.0, fiber_g=0.0)
        == "fast"
    )
    assert (
        carb_absorption_duration_minutes(
            carbs_g=53.88, protein_g=0.0, fat_g=0.0, fiber_g=0.0
        )
        == 120
    )
    # Egg/veg salad: high protein+fat relative to carbs.
    assert (
        classify_carb_profile(carbs_g=14.5, protein_g=12.5, fat_g=16.2, fiber_g=1.5)
        == "slow"
    )
    assert (
        carb_absorption_duration_minutes(
            carbs_g=14.5, protein_g=12.5, fat_g=16.2, fiber_g=1.5
        )
        == 420
    )


def test_fast_carbs_clear_cob_much_sooner_than_slow() -> None:
    # History-calibrated: pure sugar largely done by 2h; high fat/protein still active.
    fast = carb_cob_remaining_fraction(120, duration_min=120, profile="fast")
    slow = carb_cob_remaining_fraction(120, duration_min=420, profile="slow")
    assert fast == 0.0
    assert 0.5 <= slow <= 0.7
    # Fast delivers most of its load in the first hour.
    assert carb_cob_remaining_fraction(60, duration_min=120, profile="fast") <= 0.35
