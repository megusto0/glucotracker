"""Pure digital twin curve estimator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from glucotracker.application.twin.kernels import (
    carb_effect,
    icr_at,
    insulin_effect,
)

PointMode = Literal["interpolation", "forecast", "boundary"]
AnchorSource = Literal["fingerstick", "cgm"]


@dataclass(frozen=True)
class CarbEvent:
    """Carbohydrate event used by the estimator."""

    timestamp: datetime
    grams: float


@dataclass(frozen=True)
class InsulinEvent:
    """Insulin event used by the estimator."""

    timestamp: datetime
    units: float


@dataclass(frozen=True)
class BGAnchor:
    """Known glucose anchor point."""

    timestamp: datetime
    mmol: float
    source: AnchorSource = "fingerstick"


@dataclass(frozen=True)
class EstimatorParams:
    """Parameter set for one curve estimation pass."""

    icr_morning: float
    icr_day: float
    icr_evening: float
    isf: float
    baseline_drift_per_hour: float = 0.0
    morning_start_minutes: int = 360
    day_start_minutes: int = 660
    evening_start_minutes: int = 1080
    dia_minutes: int = 270
    carb_duration_minutes: int = 180


@dataclass(frozen=True)
class EstimatePoint:
    """One estimated curve point with uncertainty band metadata."""

    timestamp: datetime
    mmol: float
    ci_low: float
    ci_high: float
    confidence: float
    mode: PointMode


def estimate_curve(
    *,
    bg_anchors: list[BGAnchor],
    carbs: list[CarbEvent],
    insulin: list[InsulinEvent],
    params: EstimatorParams,
    start: datetime,
    end: datetime,
    step_minutes: int = 5,
) -> list[EstimatePoint]:
    """Estimate a glucose curve over a regular time grid."""
    if not bg_anchors or end < start or step_minutes <= 0:
        return []

    anchors = sorted(bg_anchors, key=lambda item: item.timestamp)
    carb_events = sorted(carbs, key=lambda item: item.timestamp)
    insulin_events = sorted(insulin, key=lambda item: item.timestamp)
    result: list[EstimatePoint] = []
    step = timedelta(minutes=step_minutes)
    current = start
    while current <= end:
        result.append(
            _estimate_point(
                current,
                anchors=anchors,
                carbs=carb_events,
                insulin=insulin_events,
                params=params,
            )
        )
        current += step
    return result


def _estimate_point(
    ts: datetime,
    *,
    anchors: list[BGAnchor],
    carbs: list[CarbEvent],
    insulin: list[InsulinEvent],
    params: EstimatorParams,
) -> EstimatePoint:
    first = anchors[0]
    if ts < first.timestamp:
        dt_min = (first.timestamp - ts).total_seconds() / 60
        ci_half = min(3.0, 3.0 * dt_min / 60)
        return _point(ts, first.mmol, ci_half, 0.0, "boundary")

    next_anchor = next((anchor for anchor in anchors if anchor.timestamp >= ts), None)
    prev_candidates = [anchor for anchor in anchors if anchor.timestamp <= ts]
    prev_anchor = prev_candidates[-1] if prev_candidates else first

    if next_anchor is not None and next_anchor.timestamp != prev_anchor.timestamp:
        raw = _raw_projection(ts, prev_anchor, carbs, insulin, params)
        next_raw = _raw_projection(
            next_anchor.timestamp,
            prev_anchor,
            carbs,
            insulin,
            params,
        )
        residual = next_anchor.mmol - next_raw
        span = (next_anchor.timestamp - prev_anchor.timestamp).total_seconds()
        ratio = (ts - prev_anchor.timestamp).total_seconds() / span
        value = raw + residual * ratio
        dt_to_nearest = min(
            (ts - prev_anchor.timestamp).total_seconds(),
            (next_anchor.timestamp - ts).total_seconds(),
        ) / 60
        ci_half = min(2.0, 2.0 * dt_to_nearest / 180)
        confidence = max(0.0, 1.0 - dt_to_nearest / 180)
        return _point(ts, value, ci_half, confidence, "interpolation")

    raw = _raw_projection(ts, prev_anchor, carbs, insulin, params)
    dt_since = (ts - prev_anchor.timestamp).total_seconds() / 60
    ci_half = min(3.0, 3.0 * dt_since / 180)
    confidence = max(0.0, 1.0 - dt_since / 180)
    return _point(ts, raw, ci_half, confidence, "forecast")


def _raw_projection(
    ts: datetime,
    anchor: BGAnchor,
    carbs: list[CarbEvent],
    insulin: list[InsulinEvent],
    params: EstimatorParams,
) -> float:
    hours_since = (ts - anchor.timestamp).total_seconds() / 3600
    value = anchor.mmol + params.baseline_drift_per_hour * hours_since
    value += sum(
        carb_effect(
            (ts - event.timestamp).total_seconds() / 60,
            event.grams,
            icr_at(ts, params),
            params.carb_duration_minutes,
        )
        for event in carbs
        if anchor.timestamp <= event.timestamp <= ts
    )
    value -= sum(
        insulin_effect(
            (ts - event.timestamp).total_seconds() / 60,
            event.units,
            params.isf,
            params.dia_minutes,
        )
        for event in insulin
        if anchor.timestamp <= event.timestamp <= ts
    )
    return value


def _point(
    timestamp: datetime,
    value: float,
    ci_half: float,
    confidence: float,
    mode: PointMode,
) -> EstimatePoint:
    return EstimatePoint(
        timestamp=timestamp,
        mmol=round(value, 3),
        ci_low=round(value - ci_half, 3),
        ci_high=round(value + ci_half, 3),
        confidence=round(max(0.0, min(confidence, 1.0)), 3),
        mode=mode,
    )
