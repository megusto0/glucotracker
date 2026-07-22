"""Prospective glucose forecast recording and delayed outcome evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.api.schemas import GlucosePredictionResponse
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.infra.db.repositories.glucose_prediction_audit import (
    ForecastPointSnapshot,
    GlucosePredictionAuditRepository,
)

OUTCOME_SYNC_GRACE = timedelta(minutes=10)
OUTCOME_MATCH_TOLERANCE = timedelta(minutes=8)
OUTCOME_MAX_WAIT = timedelta(hours=24)
MAX_POINTS_PER_EVALUATION = 500
DIRECTION_DEADZONE_MMOL_L = 0.2


@dataclass(frozen=True)
class EvaluationResult:
    """Counts from one bounded evaluator pass."""

    evaluated: int = 0
    missing: int = 0
    intervened: int = 0
    still_pending: int = 0


class GlucosePredictionAuditService:
    """Record forecasts exactly once and attach later raw CGM outcomes."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.repository = GlucosePredictionAuditRepository(session, user_id)

    def record(self, prediction: GlucosePredictionResponse) -> bool:
        """Persist a successful canonical raw forecast, deduplicating polling."""
        if (
            prediction.anchor_timestamp is None
            or prediction.raw_anchor_value is None
            or not prediction.points
        ):
            return False

        _, created = self.repository.add_forecast(
            generated_at=_as_utc(prediction.generated_at),
            anchor_timestamp=_wall_to_utc(prediction.anchor_timestamp),
            anchor_value_mmol_l=prediction.raw_anchor_value,
            model_version=prediction.model.version,
            algorithm=prediction.model.algorithm,
            horizon_minutes=prediction.horizon_minutes,
            step_minutes=prediction.step_minutes,
            model_json=prediction.model.model_dump(mode="json"),
            inputs_json=prediction.inputs.model_dump(mode="json"),
            notes_json=list(prediction.notes),
            points=[
                ForecastPointSnapshot(
                    target_timestamp=_wall_to_utc(point.timestamp),
                    horizon_minutes=point.horizon_minutes,
                    predicted_value_mmol_l=point.raw_value,
                    ci_low_mmol_l=point.raw_ci_low,
                    ci_high_mmol_l=point.raw_ci_high,
                    confidence=point.confidence,
                    predicted_band=_glucose_band(point.raw_value),
                )
                for point in prediction.points
            ],
        )
        return created

    def evaluate_due(self, *, now: datetime | None = None) -> EvaluationResult:
        """Evaluate due points without using CGM data unavailable at forecast time."""
        checked_at = _as_utc(now or datetime.now(UTC))
        points = self.repository.list_due_points(
            checked_at - OUTCOME_SYNC_GRACE,
            limit=MAX_POINTS_PER_EVALUATION,
        )
        evaluated = 0
        missing = 0
        intervened = 0
        still_pending = 0
        for point in points:
            target = _as_utc(point.target_timestamp)
            actual = self.repository.closest_actual(
                target,
                tolerance=OUTCOME_MATCH_TOLERANCE,
            )
            point.last_checked_at = checked_at
            is_no_input_scenario = (
                point.run.model_json.get("forecast_assumption")
                == "no_new_food_or_insulin"
            )
            if is_no_input_scenario and self.repository.has_intervention(
                _as_utc(point.run.anchor_timestamp),
                target,
            ):
                point.intervention_detected = True
                point.evaluation_status = "intervened"
                point.evaluated_at = checked_at
                if actual is not None:
                    point.actual_glucose_entry_id = actual.id
                    point.actual_timestamp = _as_utc(actual.timestamp)
                    point.actual_value_mmol_l = float(actual.value_mmol_l)
                intervened += 1
                continue
            if actual is None:
                if checked_at >= target + OUTCOME_MAX_WAIT:
                    point.evaluation_status = "missing"
                    point.evaluated_at = checked_at
                    missing += 1
                else:
                    still_pending += 1
                continue

            actual_value = float(actual.value_mmol_l)
            predicted_value = float(point.predicted_value_mmol_l)
            anchor_value = float(point.run.anchor_value_mmol_l)
            signed_error = predicted_value - actual_value
            point.actual_glucose_entry_id = actual.id
            point.actual_timestamp = _as_utc(actual.timestamp)
            point.actual_value_mmol_l = actual_value
            point.signed_error_mmol_l = signed_error
            point.absolute_error_mmol_l = abs(signed_error)
            point.baseline_absolute_error_mmol_l = abs(anchor_value - actual_value)
            point.direction_correct = _direction(predicted_value - anchor_value) == (
                _direction(actual_value - anchor_value)
            )
            point.within_interval = (
                point.ci_low_mmol_l <= actual_value <= point.ci_high_mmol_l
            )
            point.evaluation_status = "evaluated"
            point.evaluated_at = checked_at
            evaluated += 1

        return EvaluationResult(
            evaluated=evaluated,
            missing=missing,
            intervened=intervened,
            still_pending=still_pending,
        )


def _wall_to_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    return utc_instant_from_local_wall(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _direction(delta: float) -> int:
    if delta > DIRECTION_DEADZONE_MMOL_L:
        return 1
    if delta < -DIRECTION_DEADZONE_MMOL_L:
        return -1
    return 0


def _glucose_band(value: float) -> str:
    if value < 3.9:
        return "low"
    if value > 10:
        return "high"
    return "in_range"
