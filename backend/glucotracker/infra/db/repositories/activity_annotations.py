"""Owner-scoped activity labels without mutating raw wearable records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import ActivityAnnotation


class ActivityAnnotationRepository:
    """Persist activity labels only when an owner is explicitly supplied."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        if not user_id:
            raise ValueError("ActivityAnnotationRepository requires a user_id")
        self.session = session
        self.user_id = user_id

    def get(self, start_at: datetime, end_at: datetime) -> ActivityAnnotation | None:
        return self.session.scalar(
            select(ActivityAnnotation).where(
                ActivityAnnotation.owner_id == self.user_id,
                ActivityAnnotation.start_at == start_at,
                ActivityAnnotation.end_at == end_at,
            )
        )

    def upsert(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        activity_type: str,
        remember_no_steps_rule: bool,
    ) -> ActivityAnnotation:
        row = self.get(start_at, end_at)
        if row is None:
            row = ActivityAnnotation(
                owner_id=self.user_id,
                start_at=start_at,
                end_at=end_at,
            )
            self.session.add(row)
        row.activity_type = activity_type
        row.remember_no_steps_rule = remember_no_steps_rule
        self.session.flush()
        return row

    def remembered_no_steps_type(self) -> str | None:
        row = self.session.scalar(
            select(ActivityAnnotation)
            .where(
                ActivityAnnotation.owner_id == self.user_id,
                ActivityAnnotation.remember_no_steps_rule.is_(True),
            )
            .order_by(ActivityAnnotation.updated_at.desc())
            .limit(1)
        )
        return row.activity_type if row is not None else None
