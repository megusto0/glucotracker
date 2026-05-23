"""Pure digital twin estimator tests."""

from __future__ import annotations

from datetime import datetime

from glucotracker.application.twin.estimator import (
    BGAnchor,
    CarbEvent,
    EstimatorParams,
    InsulinEvent,
    estimate_curve,
)
from glucotracker.application.twin.kernels import carb_effect, icr_at


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
    points = estimate_curve(
        bg_anchors=[BGAnchor(datetime(2026, 4, 28, 8, 0), 8.0)],
        carbs=[],
        insulin=[InsulinEvent(datetime(2026, 4, 28, 8, 0), 4.0)],
        params=_params(),
        start=datetime(2026, 4, 28, 9, 7, 30),
        end=datetime(2026, 4, 28, 9, 7, 30),
    )

    assert abs(points[0].mmol - 0.0) < 0.001


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
