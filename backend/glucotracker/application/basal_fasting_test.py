"""Deliberately fasted stretches, and what the trace did during them.

The autotune table waits for a quiet hour to happen by itself: an evening only
becomes eligible when four hours passed without food, so the stretches whose
drift matters most are the ones it observes least. This is the active
alternative — a segment the owner chose to fast through, which yields in one
evening the clean observation a month of waiting could not.

Nothing stores a drift. A run records only what the owner did — when it began,
when it stopped, and why — and the outcome is recomputed from CGM whenever it
is read, so a stored number can never drift away from the trace behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.time import local_now, utc_instant_from_local_wall
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    BasalFastingTest,
    Meal,
    NightscoutInsulinEvent,
)

RunStatus = Literal["running", "completed", "aborted"]

# A run needs enough of a stretch to say anything; below this the drift is noise
# with a start button in front of it.
MIN_MEASURABLE_HOURS = 1.0


@dataclass(frozen=True)
class BasalFastingTestOutcome:
    """What the trace did across a finished run, and whether it counts."""

    measured_hours: float
    drift_mmol_l_per_hour: float | None
    start_glucose_mmol_l: float | None
    end_glucose_mmol_l: float | None
    #: A run is only evidence if the fast actually held. Food or a bolus inside
    #: it does not invalidate the record — it invalidates the measurement, and
    #: saying which is the difference between a log and a result.
    fast_held: bool
    intervention_count: int


@dataclass(frozen=True)
class BasalFastingTestRun:
    """One recorded run, with its outcome derived on read."""

    id: UUID
    started_at: datetime
    ended_at: datetime | None
    window_start_hour: int
    window_end_hour: int
    planned_hours: int
    status: RunStatus
    abort_reason: str | None
    outcome: BasalFastingTestOutcome | None


class BasalFastingTestService:
    """Start, stop and read back fasted stretches for one owner."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def start(
        self,
        *,
        window_start_hour: int,
        window_end_hour: int,
        planned_hours: int,
        at: datetime | None = None,
    ) -> BasalFastingTestRun:
        """Begin a run, closing any earlier one still marked running.

        Two runs at once cannot both be true, and the stale one is always the
        older: a run left open is a run someone walked away from.
        """
        started_at = at or local_now()
        for stale in self._open_runs():
            stale.status = "aborted"
            stale.abort_reason = "superseded"
            stale.ended_at = started_at
        row = BasalFastingTest(
            owner_id=self.user_id,
            started_at=started_at,
            window_start_hour=window_start_hour,
            window_end_hour=window_end_hour,
            planned_hours=planned_hours,
            status="running",
        )
        self.session.add(row)
        self.session.flush()
        return self._to_run(row)

    def stop(
        self,
        run_id: UUID,
        *,
        status: Literal["completed", "aborted"],
        abort_reason: str | None = None,
        at: datetime | None = None,
    ) -> BasalFastingTestRun | None:
        row = self.session.scalar(
            select(BasalFastingTest).where(
                BasalFastingTest.id == run_id,
                BasalFastingTest.owner_id == self.user_id,
            )
        )
        if row is None:
            return None
        row.ended_at = at or local_now()
        row.status = status
        row.abort_reason = abort_reason
        self.session.flush()
        return self._to_run(row)

    def active(self) -> BasalFastingTestRun | None:
        rows = self._open_runs()
        return self._to_run(rows[0]) if rows else None

    def history(self, limit: int = 20) -> list[BasalFastingTestRun]:
        rows = self.session.scalars(
            select(BasalFastingTest)
            .where(BasalFastingTest.owner_id == self.user_id)
            .order_by(BasalFastingTest.started_at.desc())
            .limit(limit)
        ).all()
        return [self._to_run(row) for row in rows]

    def _open_runs(self) -> list[BasalFastingTest]:
        return list(
            self.session.scalars(
                select(BasalFastingTest)
                .where(
                    BasalFastingTest.owner_id == self.user_id,
                    BasalFastingTest.status == "running",
                )
                .order_by(BasalFastingTest.started_at.desc())
            )
        )

    def _to_run(self, row: BasalFastingTest) -> BasalFastingTestRun:
        return BasalFastingTestRun(
            id=row.id,
            started_at=row.started_at,
            ended_at=row.ended_at,
            window_start_hour=row.window_start_hour,
            window_end_hour=row.window_end_hour,
            planned_hours=row.planned_hours,
            status=row.status,  # type: ignore[arg-type]
            abort_reason=row.abort_reason,
            outcome=(
                self._outcome(row.started_at, row.ended_at)
                if row.ended_at is not None
                else None
            ),
        )

    def _outcome(
        self,
        started_at: datetime,
        ended_at: datetime,
    ) -> BasalFastingTestOutcome | None:
        hours = (ended_at - started_at).total_seconds() / 3600
        interventions = self._interventions(started_at, ended_at)
        if hours < MIN_MEASURABLE_HOURS:
            return BasalFastingTestOutcome(
                measured_hours=round(hours, 2),
                drift_mmol_l_per_hour=None,
                start_glucose_mmol_l=None,
                end_glucose_mmol_l=None,
                fast_held=not interventions,
                intervention_count=interventions,
            )
        points = (
            GlucoseDashboardService(self.session, self.user_id)
            .dashboard(started_at, ended_at, "normalized")
            .points
        )
        # Normalized only, no raw fallback: the whole point of the segment is an
        # absolute drift, and this owner's raw stream carries a per-session
        # offset that would be read as one.
        values = [
            (point.timestamp, float(point.normalized_value))
            for point in points
            if point.normalized_value is not None
        ]
        if len(values) < 2:
            return BasalFastingTestOutcome(
                measured_hours=round(hours, 2),
                drift_mmol_l_per_hour=None,
                start_glucose_mmol_l=None,
                end_glucose_mmol_l=None,
                fast_held=not interventions,
                intervention_count=interventions,
            )
        values.sort()
        first_at, first_value = values[0]
        last_at, last_value = values[-1]
        span = (last_at - first_at).total_seconds() / 3600
        drift = (last_value - first_value) / span if span > 0 else None
        return BasalFastingTestOutcome(
            measured_hours=round(span, 2),
            drift_mmol_l_per_hour=round(drift, 2) if drift is not None else None,
            start_glucose_mmol_l=round(first_value, 1),
            end_glucose_mmol_l=round(last_value, 1),
            fast_held=not interventions,
            intervention_count=interventions,
        )

    def _interventions(self, started_at: datetime, ended_at: datetime) -> int:
        """Meals and boluses inside the run — what would break the fast."""
        meals = self.session.scalars(
            select(Meal).where(
                Meal.owner_id == self.user_id,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= started_at,
                Meal.eaten_at <= ended_at,
            )
        ).all()
        insulin = self.session.scalars(
            select(NightscoutInsulinEvent).where(
                NightscoutInsulinEvent.owner_id == self.user_id,
                NightscoutInsulinEvent.timestamp
                >= utc_instant_from_local_wall(started_at),
                NightscoutInsulinEvent.timestamp
                <= utc_instant_from_local_wall(ended_at + timedelta(seconds=1)),
            )
        ).all()
        dosed = [
            event
            for event in insulin
            if event.insulin_units
            and started_at <= _local_wall_time(event.timestamp) <= ended_at
        ]
        return len(meals) + len(dosed)
