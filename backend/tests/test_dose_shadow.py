"""Frozen shadow meal estimate: recorded beside the dose, never applied."""

from __future__ import annotations

from math import log

import pytest

from glucotracker.application.dose_shadow import shadow_meal_estimate


def _shadow(**overrides):
    values = {
        "production_meal_units": 5.0,
        "carbs_g": 50.0,
        "fat_g": 10.0,
        "trend_mmol_l_per_min": 0.0,
        "after_sleep": False,
    }
    return shadow_meal_estimate(**(values | overrides))


def test_residual_follows_the_frozen_coefficients() -> None:
    shadow = _shadow()
    expected = 3.976 - 1.133 * log(50.0) + 3.276 * 0.2
    assert shadow.residual_units == pytest.approx(expected, abs=0.01)
    assert shadow.shadow_meal_units == round(5.0 + expected, 1)
    assert shadow.trend_missing is False


@pytest.mark.parametrize(
    ("overrides", "direction"),
    [
        # Glucose already climbing into the meal: more.
        ({"trend_mmol_l_per_min": 0.04}, 1),
        # Fattier plate at the same carbohydrate: more.
        ({"fat_g": 30.0}, 1),
        # Bigger plate: the per-gram dose shrinks, so the residual falls.
        ({"carbs_g": 100.0, "fat_g": 20.0}, -1),
        # First meal after sleep: the production ratio already over-covers it.
        ({"after_sleep": True}, -1),
    ],
)
def test_each_feature_moves_the_residual_the_measured_way(overrides, direction) -> None:
    base = _shadow().residual_units
    moved = _shadow(**overrides).residual_units
    assert (moved - base) * direction > 0


def test_extrapolation_is_clamped() -> None:
    shadow = _shadow(trend_mmol_l_per_min=1.0, fat_g=500.0, carbs_g=12.0)
    assert shadow.trend_mmol_l_per_30_min == 3.0
    assert shadow.residual_units == 3.0
    low = _shadow(production_meal_units=0.5, carbs_g=180.0, after_sleep=True)
    assert low.shadow_meal_units >= 0.0


def test_missing_trend_is_recorded_not_guessed() -> None:
    shadow = _shadow(trend_mmol_l_per_min=None)
    assert shadow.trend_missing is True
    assert shadow.trend_mmol_l_per_30_min == 0.0


def test_no_production_estimate_means_no_shadow() -> None:
    assert _shadow(production_meal_units=None) is None
    assert _shadow(carbs_g=0.0) is None
