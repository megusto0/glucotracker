"""Application service for daily total recalculation orchestration."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.infra.db.models import DailyTotal
from glucotracker.workers.daily_totals import (
    recalculate_range,
    schedule_and_recalculate,
)


class DailyTotalsService:
    """Coordinate synchronous daily total recalculation for API workflows."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def schedule_for_meal_times(self, meal_times: list[datetime | None]) -> None:
        """Recalculate affected meal days immediately."""
        schedule_and_recalculate(self.session, self.user_id, meal_times)

    def recalculate_range(self, from_date: date, to_date: date) -> list[DailyTotal]:
        """Backfill daily totals for an inclusive date range."""
        return recalculate_range(
            from_date,
            to_date,
            user_id=self.user_id,
            session=self.session,
        )
