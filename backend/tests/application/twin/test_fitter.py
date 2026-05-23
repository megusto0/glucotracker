"""Pure digital twin fitter tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from glucotracker.application.twin.estimator import (
    BGAnchor,
    CarbEvent,
    EstimatorParams,
    InsulinEvent,
    estimate_curve,
)
from glucotracker.application.twin.fitter import CGMPoint, fit_twin_params


def _true_params() -> EstimatorParams:
    return EstimatorParams(
        icr_morning=11.5,
        icr_day=12.5,
        icr_evening=13.0,
        isf=2.1,
        baseline_drift_per_hour=0.05,
    )


def _synthetic_history(days: int = 10) -> tuple[
    list[CGMPoint],
    list[CarbEvent],
    list[InsulinEvent],
]:
    cgm: list[CGMPoint] = []
    carbs: list[CarbEvent] = []
    insulin: list[InsulinEvent] = []
    params = _true_params()
    first_day = datetime(2026, 4, 1)
    for day_idx in range(days):
        day = first_day + timedelta(days=day_idx)
        for hour, grams, units in [(6, 34.5, 1.0), (11, 50.0, 1.5), (18, 52.0, 1.8)]:
            start = day.replace(hour=hour)
            meal = CarbEvent(start + timedelta(minutes=15), grams)
            bolus = InsulinEvent(start + timedelta(minutes=15), units)
            carbs.append(meal)
            insulin.append(bolus)
            points = estimate_curve(
                bg_anchors=[BGAnchor(start, 6.0, source="cgm")],
                carbs=[meal],
                insulin=[bolus],
                params=params,
                start=start,
                end=start + timedelta(minutes=180),
                step_minutes=5,
            )
            cgm.extend(CGMPoint(point.timestamp, point.mmol) for point in points)
    return cgm, carbs, insulin


def test_synthetic_recovery_uses_train_and_holdout_windows() -> None:
    cgm, carbs, insulin = _synthetic_history()

    result = fit_twin_params(
        cgm=cgm,
        carbs=carbs,
        insulin=insulin,
        existing_params=None,
        dia_minutes=270,
        carb_duration_minutes=180,
        morning_start_minutes=360,
        day_start_minutes=660,
        evening_start_minutes=1080,
        stride_min=300,
    )

    assert result.method == "least_squares"
    assert result.converged is True
    assert abs(result.icr_morning - 11.5) < 0.2
    assert abs(result.icr_day - 12.5) < 0.2
    assert abs(result.icr_evening - 13.0) < 0.2
    assert abs(result.isf - 2.1) < 0.2
    assert result.holdout_mae_mmol < 0.05


def test_insufficient_cgm_returns_fallback() -> None:
    result = fit_twin_params(
        cgm=[CGMPoint(datetime(2026, 4, 1, 8, 0), 6.0)],
        carbs=[],
        insulin=[],
        existing_params=None,
        dia_minutes=270,
        carb_duration_minutes=180,
        morning_start_minutes=360,
        day_start_minutes=660,
        evening_start_minutes=1080,
    )

    assert result.method == "fallback_to_defaults"
    assert result.converged is False


def test_train_and_holdout_dates_are_disjoint() -> None:
    cgm, carbs, insulin = _synthetic_history()

    result = fit_twin_params(
        cgm=cgm,
        carbs=carbs,
        insulin=insulin,
        existing_params=None,
        dia_minutes=270,
        carb_duration_minutes=180,
        morning_start_minutes=360,
        day_start_minutes=660,
        evening_start_minutes=1080,
        stride_min=300,
    )

    assert set(result.per_window_train_dates).isdisjoint(
        set(result.per_window_holdout_dates)
    )


def test_bounds_are_respected() -> None:
    cgm, carbs, insulin = _synthetic_history()

    result = fit_twin_params(
        cgm=cgm,
        carbs=carbs,
        insulin=insulin,
        existing_params=EstimatorParams(
            icr_morning=40,
            icr_day=40,
            icr_evening=40,
            isf=8,
        ),
        dia_minutes=270,
        carb_duration_minutes=180,
        morning_start_minutes=360,
        day_start_minutes=660,
        evening_start_minutes=1080,
        stride_min=300,
    )

    assert result.icr_morning >= 3
    assert result.icr_day >= 3
    assert result.icr_evening >= 3
    assert 0.2 <= result.isf <= 8
    assert -1 <= result.baseline_drift_per_hour <= 1
