"""Owner-scoped persistence for prospective glucose forecast evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from glucotracker.application.glucose_visibility import visible_glucose_filter
from glucotracker.application.time import (
    local_wall_time,
)
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    GlucosePredictionPointAudit,
    GlucosePredictionRun,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)


@dataclass(frozen=True)
class ForecastPointSnapshot:
    """Canonical raw forecast values known at prediction time."""

    target_timestamp: datetime
    horizon_minutes: int
    predicted_value_mmol_l: float
    ci_low_mmol_l: float
    ci_high_mmol_l: float
    confidence: float
    predicted_band: str


class GlucosePredictionAuditRepository:
    """Require a user id for every forecast and outcome operation."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        if user_id is None:
            raise ValueError("GlucosePredictionAuditRepository requires user_id.")
        self.session = session
        self.user_id = user_id

    def add_forecast(
        self,
        *,
        generated_at: datetime,
        anchor_timestamp: datetime,
        anchor_value_mmol_l: float,
        model_version: str,
        algorithm: str,
        horizon_minutes: int,
        step_minutes: int,
        model_json: dict[str, object],
        inputs_json: dict[str, object],
        notes_json: list[str],
        points: list[ForecastPointSnapshot],
    ) -> tuple[GlucosePredictionRun, bool]:
        """Append one immutable run, or return the existing polling duplicate."""
        existing = self.session.scalar(
            select(GlucosePredictionRun).where(
                GlucosePredictionRun.owner_id == self.user_id,
                GlucosePredictionRun.anchor_timestamp == anchor_timestamp,
                GlucosePredictionRun.model_version == model_version,
                GlucosePredictionRun.horizon_minutes == horizon_minutes,
                GlucosePredictionRun.step_minutes == step_minutes,
            )
        )
        if existing is not None:
            return existing, False

        run = GlucosePredictionRun(
            owner_id=self.user_id,
            generated_at=generated_at,
            anchor_timestamp=anchor_timestamp,
            anchor_value_mmol_l=anchor_value_mmol_l,
            model_version=model_version,
            algorithm=algorithm,
            horizon_minutes=horizon_minutes,
            step_minutes=step_minutes,
            model_json=model_json,
            inputs_json=inputs_json,
            notes_json=notes_json,
        )
        run.points = [
            GlucosePredictionPointAudit(
                owner_id=self.user_id,
                target_timestamp=point.target_timestamp,
                horizon_minutes=point.horizon_minutes,
                predicted_value_mmol_l=point.predicted_value_mmol_l,
                ci_low_mmol_l=point.ci_low_mmol_l,
                ci_high_mmol_l=point.ci_high_mmol_l,
                confidence=point.confidence,
                predicted_band=point.predicted_band,
            )
            for point in points
        ]
        self.session.add(run)
        self.session.flush()
        return run, True

    def list_due_points(
        self,
        eligible_before: datetime,
        *,
        limit: int,
    ) -> list[GlucosePredictionPointAudit]:
        """Return this user's pending points whose sync grace has elapsed."""
        return list(
            self.session.scalars(
                select(GlucosePredictionPointAudit)
                .where(
                    GlucosePredictionPointAudit.owner_id == self.user_id,
                    GlucosePredictionPointAudit.evaluation_status == "pending",
                    GlucosePredictionPointAudit.target_timestamp <= eligible_before,
                )
                .options(joinedload(GlucosePredictionPointAudit.run))
                .order_by(GlucosePredictionPointAudit.target_timestamp.asc())
                .limit(limit)
            )
        )

    def closest_actual(
        self,
        target_timestamp: datetime,
        *,
        tolerance: timedelta,
    ) -> NightscoutGlucoseEntry | None:
        """Return the nearest visible raw CGM reading in the target window."""
        candidates = list(
            self.session.scalars(
                select(NightscoutGlucoseEntry)
                .where(
                    NightscoutGlucoseEntry.owner_id == self.user_id,
                    NightscoutGlucoseEntry.timestamp
                    >= target_timestamp - tolerance,
                    NightscoutGlucoseEntry.timestamp
                    <= target_timestamp + tolerance,
                    visible_glucose_filter(self.user_id),
                )
                .order_by(NightscoutGlucoseEntry.timestamp.asc())
            )
        )
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda row: abs(
                (_as_utc(row.timestamp) - _as_utc(target_timestamp)).total_seconds()
            ),
        )

    def has_intervention(
        self,
        anchor_timestamp: datetime,
        target_timestamp: datetime,
    ) -> bool:
        """Return whether new food or insulin was recorded after the anchor."""
        local_anchor = local_wall_time(anchor_timestamp)
        local_target = local_wall_time(target_timestamp)
        food = self.session.scalar(
            select(Meal.id)
            .where(
                Meal.owner_id == self.user_id,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at > local_anchor,
                Meal.eaten_at <= local_target,
            )
            .limit(1)
        )
        if food is not None:
            return True
        insulin = self.session.scalar(
            select(NightscoutInsulinEvent.id)
            .where(
                NightscoutInsulinEvent.owner_id == self.user_id,
                NightscoutInsulinEvent.timestamp > anchor_timestamp,
                NightscoutInsulinEvent.timestamp <= target_timestamp,
                NightscoutInsulinEvent.insulin_units.is_not(None),
                NightscoutInsulinEvent.insulin_units > 0,
            )
            .limit(1)
        )
        return insulin is not None

    def count_runs(self) -> int:
        """Return the number of immutable runs visible to this owner."""
        return len(
            self.session.scalars(
                select(GlucosePredictionRun.id).where(
                    GlucosePredictionRun.owner_id == self.user_id
                )
            ).all()
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
