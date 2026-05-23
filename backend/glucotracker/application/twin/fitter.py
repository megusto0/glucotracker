"""Pure digital twin parameter fitter."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from glucotracker.application.twin.estimator import (
    BGAnchor,
    CarbEvent,
    EstimatePoint,
    EstimatorParams,
    InsulinEvent,
    estimate_curve,
)
from glucotracker.application.twin.kernels import carb_effect, insulin_effect

FitMethod = Literal["least_squares", "fallback_to_defaults"]

ICR_MIN = 3.0
ICR_MAX = 40.0
ISF_MIN = 0.2
ISF_MAX = 8.0
DRIFT_MIN = -1.0
DRIFT_MAX = 1.0


@dataclass(frozen=True)
class CGMPoint:
    """One historical CGM point used by the fitter."""

    timestamp: datetime
    mmol: float


@dataclass(frozen=True)
class FitResult:
    """Digital twin parameter fitting result."""

    icr_morning: float
    icr_day: float
    icr_evening: float
    isf: float
    baseline_drift_per_hour: float
    train_mae_mmol: float
    holdout_mae_mmol: float
    train_window_count: int
    holdout_window_count: int
    method: FitMethod
    converged: bool
    iterations: int
    per_window_train_mae: list[float]
    per_window_holdout_mae: list[float]
    per_window_train_dates: list[date]
    per_window_holdout_dates: list[date]


@dataclass(frozen=True)
class _FitWindow:
    cgm: list[CGMPoint]
    start: datetime
    end: datetime

    @property
    def date(self) -> date:
        return self.start.date()


def fit_twin_params(
    *,
    cgm: list[CGMPoint],
    carbs: list[CarbEvent],
    insulin: list[InsulinEvent],
    existing_params: EstimatorParams | None,
    dia_minutes: int,
    carb_duration_minutes: int,
    morning_start_minutes: int,
    day_start_minutes: int,
    evening_start_minutes: int,
    train_split: float = 0.8,
    window_min: int = 180,
    stride_min: int = 60,
) -> FitResult:
    """Fit free digital twin parameters from historical CGM windows."""
    fallback = _fallback_result(
        existing_params,
        dia_minutes=dia_minutes,
        carb_duration_minutes=carb_duration_minutes,
        morning_start_minutes=morning_start_minutes,
        day_start_minutes=day_start_minutes,
        evening_start_minutes=evening_start_minutes,
    )
    windows = _build_windows(cgm, window_min=window_min, stride_min=stride_min)
    train_windows, holdout_windows = _split_windows(windows, train_split=train_split)
    if len(train_windows) < 5 or len(holdout_windows) < 2:
        return fallback

    rows: list[tuple[list[float], float, float]] = []
    for window in train_windows:
        rows.extend(
            _window_rows(
                window,
                carbs=carbs,
                insulin=insulin,
                dia_minutes=dia_minutes,
                carb_duration_minutes=carb_duration_minutes,
                morning_start_minutes=morning_start_minutes,
                day_start_minutes=day_start_minutes,
                evening_start_minutes=evening_start_minutes,
            )
        )
    if len(rows) < 5:
        return fallback

    solution = _solve_weighted_least_squares(rows)
    if solution is None:
        return fallback

    params = _params_from_solution(
        solution,
        dia_minutes=dia_minutes,
        carb_duration_minutes=carb_duration_minutes,
        morning_start_minutes=morning_start_minutes,
        day_start_minutes=day_start_minutes,
        evening_start_minutes=evening_start_minutes,
    )
    train_mae = [
        _window_mae(window, params, carbs, insulin) for window in train_windows
    ]
    holdout_mae = [
        _window_mae(window, params, carbs, insulin) for window in holdout_windows
    ]
    train_mae = [value for value in train_mae if value is not None]
    holdout_mae = [value for value in holdout_mae if value is not None]
    if not train_mae or not holdout_mae:
        return fallback

    return FitResult(
        icr_morning=round(params.icr_morning, 4),
        icr_day=round(params.icr_day, 4),
        icr_evening=round(params.icr_evening, 4),
        isf=round(params.isf, 4),
        baseline_drift_per_hour=round(params.baseline_drift_per_hour, 5),
        train_mae_mmol=round(_mean(train_mae), 4),
        holdout_mae_mmol=round(_mean(holdout_mae), 4),
        train_window_count=len(train_mae),
        holdout_window_count=len(holdout_mae),
        method="least_squares",
        converged=True,
        iterations=1 if existing_params is not None else 2,
        per_window_train_mae=[round(value, 4) for value in train_mae],
        per_window_holdout_mae=[round(value, 4) for value in holdout_mae],
        per_window_train_dates=[window.date for window in train_windows],
        per_window_holdout_dates=[window.date for window in holdout_windows],
    )


def _build_windows(
    cgm: list[CGMPoint],
    *,
    window_min: int,
    stride_min: int,
) -> list[_FitWindow]:
    points = sorted(cgm, key=lambda point: point.timestamp)
    windows: list[_FitWindow] = []
    if not points or window_min <= 0 or stride_min <= 0:
        return windows

    start_idx = 0
    while start_idx < len(points):
        start = points[start_idx].timestamp
        end = start + timedelta(minutes=window_min)
        window_points = [
            point for point in points[start_idx:] if start <= point.timestamp <= end
        ]
        if len(window_points) >= 30:
            windows.append(_FitWindow(cgm=window_points, start=start, end=end))

        next_start = start + timedelta(minutes=stride_min)
        next_idx = next(
            (idx for idx, point in enumerate(points) if point.timestamp >= next_start),
            len(points),
        )
        if next_idx <= start_idx:
            next_idx = start_idx + 1
        start_idx = next_idx
    return windows


def _split_windows(
    windows: list[_FitWindow],
    *,
    train_split: float,
) -> tuple[list[_FitWindow], list[_FitWindow]]:
    if not windows:
        return [], []
    dates = sorted({window.date for window in windows})
    holdout_date_count = math.floor((1.0 - train_split) * len(dates) + 1e-9)
    if holdout_date_count <= 0 and len(dates) > 1:
        holdout_date_count = 1
    holdout_dates = set(dates[-holdout_date_count:]) if holdout_date_count else set()
    train = [window for window in windows if window.date not in holdout_dates]
    holdout = [window for window in windows if window.date in holdout_dates]
    return train, holdout


def _window_rows(
    window: _FitWindow,
    *,
    carbs: list[CarbEvent],
    insulin: list[InsulinEvent],
    dia_minutes: int,
    carb_duration_minutes: int,
    morning_start_minutes: int,
    day_start_minutes: int,
    evening_start_minutes: int,
) -> list[tuple[list[float], float, float]]:
    anchor = window.cgm[0]
    rows: list[tuple[list[float], float, float]] = []
    weight = 1.0 / math.sqrt(max(1, len(window.cgm) - 1))
    for point in window.cgm[1:]:
        features = _features(
            point.timestamp,
            anchor=anchor,
            carbs=carbs,
            insulin=insulin,
            dia_minutes=dia_minutes,
            carb_duration_minutes=carb_duration_minutes,
            morning_start_minutes=morning_start_minutes,
            day_start_minutes=day_start_minutes,
            evening_start_minutes=evening_start_minutes,
        )
        rows.append((features, point.mmol - anchor.mmol, weight))
    return rows


def _features(
    timestamp: datetime,
    *,
    anchor: CGMPoint,
    carbs: list[CarbEvent],
    insulin: list[InsulinEvent],
    dia_minutes: int,
    carb_duration_minutes: int,
    morning_start_minutes: int,
    day_start_minutes: int,
    evening_start_minutes: int,
) -> list[float]:
    carb_total = sum(
        carb_effect(
            (timestamp - event.timestamp).total_seconds() / 60,
            event.grams,
            1.0,
            carb_duration_minutes,
        )
        for event in carbs
        if anchor.timestamp <= event.timestamp <= timestamp
    )
    insulin_total = sum(
        insulin_effect(
            (timestamp - event.timestamp).total_seconds() / 60,
            event.units,
            1.0,
            dia_minutes,
        )
        for event in insulin
        if anchor.timestamp <= event.timestamp <= timestamp
    )
    slot = _slot_index(
        timestamp,
        morning_start_minutes=morning_start_minutes,
        day_start_minutes=day_start_minutes,
        evening_start_minutes=evening_start_minutes,
    )
    carb_features = [0.0, 0.0, 0.0]
    carb_features[slot] = carb_total
    hours_since_anchor = (timestamp - anchor.timestamp).total_seconds() / 3600
    return [
        carb_features[0],
        carb_features[1],
        carb_features[2],
        -insulin_total,
        hours_since_anchor,
    ]


def _slot_index(
    timestamp: datetime,
    *,
    morning_start_minutes: int,
    day_start_minutes: int,
    evening_start_minutes: int,
) -> int:
    minutes = timestamp.hour * 60 + timestamp.minute
    if minutes < day_start_minutes:
        return 0
    if minutes < evening_start_minutes:
        return 1
    return 2


def _solve_weighted_least_squares(
    rows: list[tuple[list[float], float, float]],
) -> list[float] | None:
    size = 5
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    vector = [0.0 for _ in range(size)]
    for features, target, weight in rows:
        weighted = [value * weight for value in features]
        weighted_target = target * weight
        for row_idx in range(size):
            vector[row_idx] += weighted[row_idx] * weighted_target
            for col_idx in range(size):
                matrix[row_idx][col_idx] += weighted[row_idx] * weighted[col_idx]

    for idx in range(size):
        matrix[idx][idx] += 1e-6
    return _gaussian_solve(matrix, vector)


def _gaussian_solve(
    matrix: list[list[float]],
    vector: list[float],
) -> list[float] | None:
    size = len(vector)
    augmented = [row[:] + [vector[idx]] for idx, row in enumerate(matrix)]
    for pivot_idx in range(size):
        pivot_row = max(
            range(pivot_idx, size),
            key=lambda row_idx: abs(augmented[row_idx][pivot_idx]),
        )
        if abs(augmented[pivot_row][pivot_idx]) < 1e-12:
            return None
        augmented[pivot_idx], augmented[pivot_row] = (
            augmented[pivot_row],
            augmented[pivot_idx],
        )
        pivot = augmented[pivot_idx][pivot_idx]
        for col_idx in range(pivot_idx, size + 1):
            augmented[pivot_idx][col_idx] /= pivot
        for row_idx in range(size):
            if row_idx == pivot_idx:
                continue
            factor = augmented[row_idx][pivot_idx]
            for col_idx in range(pivot_idx, size + 1):
                augmented[row_idx][col_idx] -= factor * augmented[pivot_idx][col_idx]
    return [augmented[idx][size] for idx in range(size)]


def _params_from_solution(
    solution: list[float],
    *,
    dia_minutes: int,
    carb_duration_minutes: int,
    morning_start_minutes: int,
    day_start_minutes: int,
    evening_start_minutes: int,
) -> EstimatorParams:
    morning_inverse = _clamp(solution[0], 1.0 / ICR_MAX, 1.0 / ICR_MIN)
    day_inverse = _clamp(solution[1], 1.0 / ICR_MAX, 1.0 / ICR_MIN)
    evening_inverse = _clamp(solution[2], 1.0 / ICR_MAX, 1.0 / ICR_MIN)
    return EstimatorParams(
        icr_morning=1.0 / morning_inverse,
        icr_day=1.0 / day_inverse,
        icr_evening=1.0 / evening_inverse,
        isf=_clamp(solution[3], ISF_MIN, ISF_MAX),
        baseline_drift_per_hour=_clamp(solution[4], DRIFT_MIN, DRIFT_MAX),
        morning_start_minutes=morning_start_minutes,
        day_start_minutes=day_start_minutes,
        evening_start_minutes=evening_start_minutes,
        dia_minutes=dia_minutes,
        carb_duration_minutes=carb_duration_minutes,
    )


def _window_mae(
    window: _FitWindow,
    params: EstimatorParams,
    carbs: list[CarbEvent],
    insulin: list[InsulinEvent],
) -> float | None:
    anchor = window.cgm[0]
    points = estimate_curve(
        bg_anchors=[BGAnchor(anchor.timestamp, anchor.mmol, source="cgm")],
        carbs=[
            event
            for event in carbs
            if anchor.timestamp - timedelta(minutes=params.carb_duration_minutes)
            <= event.timestamp
            <= window.end
        ],
        insulin=[
            event
            for event in insulin
            if anchor.timestamp - timedelta(minutes=params.dia_minutes)
            <= event.timestamp
            <= window.end
        ],
        params=params,
        start=anchor.timestamp,
        end=window.end,
        step_minutes=5,
    )
    residuals: list[float] = []
    for actual in window.cgm[1:]:
        predicted = _nearest_point(points, actual.timestamp, tolerance_min=5)
        if predicted is not None:
            residuals.append(abs(predicted.mmol - actual.mmol))
    return _mean(residuals) if residuals else None


def _nearest_point(
    points: list[EstimatePoint],
    timestamp: datetime,
    *,
    tolerance_min: int,
) -> EstimatePoint | None:
    if not points:
        return None
    nearest = min(points, key=lambda point: abs(point.timestamp - timestamp))
    delta_min = abs((nearest.timestamp - timestamp).total_seconds()) / 60
    return nearest if delta_min <= tolerance_min else None


def _fallback_result(
    existing_params: EstimatorParams | None,
    *,
    dia_minutes: int,
    carb_duration_minutes: int,
    morning_start_minutes: int,
    day_start_minutes: int,
    evening_start_minutes: int,
) -> FitResult:
    params = existing_params or EstimatorParams(
        icr_morning=12.0,
        icr_day=12.0,
        icr_evening=12.0,
        isf=2.0,
        morning_start_minutes=morning_start_minutes,
        day_start_minutes=day_start_minutes,
        evening_start_minutes=evening_start_minutes,
        dia_minutes=dia_minutes,
        carb_duration_minutes=carb_duration_minutes,
    )
    return FitResult(
        icr_morning=params.icr_morning,
        icr_day=params.icr_day,
        icr_evening=params.icr_evening,
        isf=params.isf,
        baseline_drift_per_hour=params.baseline_drift_per_hour,
        train_mae_mmol=0.0,
        holdout_mae_mmol=0.0,
        train_window_count=0,
        holdout_window_count=0,
        method="fallback_to_defaults",
        converged=False,
        iterations=0,
        per_window_train_mae=[],
        per_window_holdout_mae=[],
        per_window_train_dates=[],
        per_window_holdout_dates=[],
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
