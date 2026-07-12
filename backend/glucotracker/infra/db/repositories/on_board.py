"""Owner-scoped persistence and training reads for IOB/COB personalization."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from glucotracker.application.glucose_visibility import visible_glucose_filter
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    Meal,
    MealInsulinEpisodeSnapshot,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    OnBoardModelFit,
    utc_now,
)

OnBoardKind = Literal["iob", "cob"]
OnBoardConfidence = Literal["none", "low", "medium", "high"]
OnBoardFitStatus = Literal["accepted", "rejected", "insufficient_data"]


class OnBoardRepository:
    """Require a user id for every personal fit and source-data operation."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        if user_id is None:
            raise ValueError("OnBoardRepository requires user_id.")
        self.session = session
        self.user_id = user_id

    def get_active_fit(
        self,
        kind: OnBoardKind,
        scope_key: str,
    ) -> OnBoardModelFit | None:
        """Return the newest validated active fit in this user's scope."""
        return self.session.scalar(
            select(OnBoardModelFit)
            .where(
                OnBoardModelFit.owner_id == self.user_id,
                OnBoardModelFit.kind == kind,
                OnBoardModelFit.scope_key == scope_key,
                OnBoardModelFit.active.is_(True),
                OnBoardModelFit.status == "accepted",
            )
            .order_by(
                OnBoardModelFit.fitted_at.desc(),
                OnBoardModelFit.id.desc(),
            )
            .limit(1)
        )

    def list_active_fits(
        self,
        kind: OnBoardKind,
        scope_keys: set[str] | None = None,
    ) -> list[OnBoardModelFit]:
        """Return current validated fits, optionally restricted to known keys."""
        if scope_keys is not None and not scope_keys:
            return []
        statement = select(OnBoardModelFit).where(
            OnBoardModelFit.owner_id == self.user_id,
            OnBoardModelFit.kind == kind,
            OnBoardModelFit.active.is_(True),
            OnBoardModelFit.status == "accepted",
        )
        if scope_keys is not None:
            statement = statement.where(OnBoardModelFit.scope_key.in_(scope_keys))
        return list(
            self.session.scalars(
                statement.order_by(
                    OnBoardModelFit.fitted_at.desc(),
                    OnBoardModelFit.id.desc(),
                )
            )
        )

    def add_fit(
        self,
        *,
        kind: OnBoardKind,
        scope_key: str,
        model_version: str,
        params_json: dict[str, object],
        metrics_json: dict[str, object],
        training_from: datetime | None,
        training_to: datetime | None,
        sample_count: int,
        day_count: int,
        validation_mae_mmol: float | None,
        baseline_mae_mmol: float | None,
        confidence: OnBoardConfidence,
        status: OnBoardFitStatus,
        activate: bool,
    ) -> OnBoardModelFit:
        """Append one result and atomically supersede only the matching fit."""
        should_activate = activate and status == "accepted"
        if should_activate:
            self.session.execute(
                update(OnBoardModelFit)
                .where(
                    OnBoardModelFit.owner_id == self.user_id,
                    OnBoardModelFit.kind == kind,
                    OnBoardModelFit.scope_key == scope_key,
                    OnBoardModelFit.active.is_(True),
                )
                .values(active=False)
            )
        row = OnBoardModelFit(
            owner_id=self.user_id,
            kind=kind,
            scope_key=scope_key,
            model_version=model_version,
            params_json=params_json,
            metrics_json=metrics_json,
            training_from=training_from,
            training_to=training_to,
            sample_count=max(0, sample_count),
            day_count=max(0, day_count),
            validation_mae_mmol=validation_mae_mmol,
            baseline_mae_mmol=baseline_mae_mmol,
            confidence=confidence,
            status=status,
            active=should_activate,
            fitted_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def deactivate_all(self, kind: OnBoardKind | None = None) -> int:
        """Deactivate this user's models without deleting append-only history."""
        statement = update(OnBoardModelFit).where(
            OnBoardModelFit.owner_id == self.user_id,
            OnBoardModelFit.active.is_(True),
        )
        if kind is not None:
            statement = statement.where(OnBoardModelFit.kind == kind)
        result = self.session.execute(statement.values(active=False))
        return int(result.rowcount or 0)

    def deactivate_cob_scopes_except(self, scope_keys: set[str]) -> int:
        """Retire active COB scopes absent from one accepted replacement set."""
        statement = update(OnBoardModelFit).where(
            OnBoardModelFit.owner_id == self.user_id,
            OnBoardModelFit.kind == "cob",
            OnBoardModelFit.active.is_(True),
        )
        if scope_keys:
            statement = statement.where(
                OnBoardModelFit.scope_key.not_in(scope_keys),
            )
        result = self.session.execute(statement.values(active=False))
        return int(result.rowcount or 0)

    def latest_attempt_at(self) -> datetime | None:
        """Return the newest fit attempt timestamp for this user only."""
        return self.session.scalar(
            select(func.max(OnBoardModelFit.fitted_at)).where(
                OnBoardModelFit.owner_id == self.user_id
            )
        )

    def list_training_glucose(
        self,
        from_local: datetime,
        to_local: datetime,
    ) -> list[NightscoutGlucoseEntry]:
        """Return visible raw CGM for a local-wall training range."""
        return list(
            self.session.scalars(
                select(NightscoutGlucoseEntry)
                .where(
                    NightscoutGlucoseEntry.owner_id == self.user_id,
                    NightscoutGlucoseEntry.timestamp
                    >= utc_instant_from_local_wall(from_local),
                    NightscoutGlucoseEntry.timestamp
                    <= utc_instant_from_local_wall(to_local),
                    visible_glucose_filter(self.user_id),
                )
                .order_by(NightscoutGlucoseEntry.timestamp.asc())
            )
        )

    def list_training_meals(
        self,
        from_local: datetime,
        to_local: datetime,
    ) -> list[Meal]:
        """Return accepted meals and their identity features for this user."""
        return list(
            self.session.scalars(
                select(Meal)
                .where(
                    Meal.owner_id == self.user_id,
                    Meal.status == MealStatus.accepted,
                    Meal.eaten_at >= from_local,
                    Meal.eaten_at <= to_local,
                    Meal.total_carbs_g > 0,
                )
                .options(selectinload(Meal.items))
                .order_by(Meal.eaten_at.asc())
            )
        )

    def list_training_insulin(
        self,
        from_local: datetime,
        to_local: datetime,
    ) -> list[NightscoutInsulinEvent]:
        """Return positive imported insulin events for this user."""
        return list(
            self.session.scalars(
                select(NightscoutInsulinEvent)
                .where(
                    NightscoutInsulinEvent.owner_id == self.user_id,
                    NightscoutInsulinEvent.timestamp
                    >= utc_instant_from_local_wall(from_local),
                    NightscoutInsulinEvent.timestamp
                    <= utc_instant_from_local_wall(to_local),
                    NightscoutInsulinEvent.insulin_units.is_not(None),
                    NightscoutInsulinEvent.insulin_units > 0,
                )
                .order_by(NightscoutInsulinEvent.timestamp.asc())
            )
        )

    def list_episode_snapshots(
        self,
        from_date: date,
        to_date: date,
    ) -> list[MealInsulinEpisodeSnapshot]:
        """Return attribution/review snapshots without using their sparse CGM."""
        return list(
            self.session.scalars(
                select(MealInsulinEpisodeSnapshot)
                .where(
                    MealInsulinEpisodeSnapshot.owner_id == self.user_id,
                    MealInsulinEpisodeSnapshot.date >= from_date,
                    MealInsulinEpisodeSnapshot.date <= to_date,
                )
                .order_by(
                    MealInsulinEpisodeSnapshot.date.asc(),
                    MealInsulinEpisodeSnapshot.sequence.asc(),
                )
            )
        )
