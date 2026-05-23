"""Scoped persistence for the digital twin feature."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import TwinFitLog, TwinParams, utc_now


class TwinRepository:
    """Repository that requires and applies a current user scope."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        if user_id is None:
            raise ValueError("TwinRepository requires user_id.")
        self.session = session
        self.user_id = user_id

    def get_params(self) -> TwinParams | None:
        """Return this user's params row when it already exists."""
        return self.session.scalar(
            select(TwinParams).where(TwinParams.owner_id == self.user_id)
        )

    def get_or_create_params(self, *, persist: bool = True) -> TwinParams:
        """Return this user's params row, creating default values if missing."""
        row = self.get_params()
        if row is not None:
            return row

        row = self._new_default_params()
        if not persist:
            return row

        self.session.add(row)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            row = self.get_params()
            if row is None:
                raise
        return row

    def _new_default_params(self) -> TwinParams:
        now = utc_now()
        return TwinParams(
            id=uuid4(),
            owner_id=self.user_id,
            morning_start_minutes=360,
            day_start_minutes=660,
            evening_start_minutes=1080,
            dia_minutes=270,
            carb_duration_minutes=180,
            baseline_drift_per_hour=0.0,
            created_at=now,
            updated_at=now,
        )

    def list_fit_logs(self, limit: int = 20) -> list[TwinFitLog]:
        """Return this user's fit log rows, newest first."""
        bounded_limit = max(1, min(limit, 100))
        return list(
            self.session.scalars(
                select(TwinFitLog)
                .where(TwinFitLog.owner_id == self.user_id)
                .order_by(TwinFitLog.fit_at.desc(), TwinFitLog.id.desc())
                .limit(bounded_limit)
            )
        )

    def add_fit_log(
        self,
        *,
        params_snapshot: dict[str, object],
        method: str,
        converged: bool | None = None,
        data_from: datetime | None = None,
        data_to: datetime | None = None,
        fit_at: datetime | None = None,
        holdout_mae_mmol: float | None = None,
        holdout_window_count: int | None = None,
        iterations: int | None = None,
        notes: str | None = None,
        train_mae_mmol: float | None = None,
        train_window_count: int | None = None,
    ) -> TwinFitLog:
        """Append one fit/history row in the current user's scope."""
        row = TwinFitLog(
            owner_id=self.user_id,
            fit_at=fit_at or utc_now(),
            data_from=data_from,
            data_to=data_to,
            params_snapshot=params_snapshot,
            train_window_count=train_window_count,
            holdout_window_count=holdout_window_count,
            train_mae_mmol=train_mae_mmol,
            holdout_mae_mmol=holdout_mae_mmol,
            method=method,
            converged=converged,
            iterations=iterations,
            notes=notes,
        )
        self.session.add(row)
        self.session.flush()
        return row
