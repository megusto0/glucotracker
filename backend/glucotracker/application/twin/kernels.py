"""Absorption and action kernels for the digital twin estimator."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from glucotracker.application.twin.estimator import EstimatorParams


def carb_effect(dt_min: float, grams: float, icr: float, duration_min: int) -> float:
    """Return bilinear carbohydrate absorption effect in mmol/L."""
    if dt_min <= 0 or dt_min >= duration_min or grams <= 0 or icr <= 0:
        return 0.0

    first = duration_min / 3
    second = (duration_min * 2) / 3
    if dt_min <= first:
        shape = dt_min / first
    elif dt_min <= second:
        shape = 1.0
    else:
        shape = (duration_min - dt_min) / (duration_min - second)
    return (grams / icr) * max(0.0, min(shape, 1.0))


def insulin_effect(dt_min: float, units: float, isf: float, dia_min: int) -> float:
    """Return bilinear insulin action effect in mmol/L as a positive value."""
    if dt_min <= 0 or dt_min >= dia_min or units <= 0 or isf <= 0:
        return 0.0

    peak_min = min(75.0, dia_min / 4)
    if dt_min <= peak_min:
        shape = dt_min / peak_min
    else:
        shape = (dia_min - dt_min) / (dia_min - peak_min)
    return units * isf * max(0.0, min(shape, 1.0))


def icr_at(ts: datetime, params: EstimatorParams) -> float:
    """Return the active ICR by minutes from local midnight."""
    minutes = ts.hour * 60 + ts.minute
    if minutes < params.day_start_minutes:
        return params.icr_morning
    if minutes < params.evening_start_minutes:
        return params.icr_day
    return params.icr_evening
