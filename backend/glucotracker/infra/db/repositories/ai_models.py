"""Owner-scoped model preferences and photo-estimation audit reads."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, load_only

from glucotracker.infra.db.models import AIModelRouting, AIRun, Meal


class RoutingConflict(ValueError):
    pass


class AIModelsRepository:
    def __init__(self, session: Session, user_id: UUID):
        if user_id is None:
            raise ValueError("AIModelsRepository requires user_id")
        self.session = session
        self.user_id = user_id

    def routing(self) -> AIModelRouting | None:
        return self.session.scalar(
            select(AIModelRouting).where(AIModelRouting.owner_id == self.user_id)
        )

    def save(self, models: list[dict], revision: int) -> None:
        if revision == 0:
            if self.routing() is not None:
                raise RoutingConflict()
            self.session.add(
                AIModelRouting(owner_id=self.user_id, revision=1, models_json=models)
            )
            self.session.flush()
            return
        result = self.session.execute(
            update(AIModelRouting)
            .where(
                AIModelRouting.owner_id == self.user_id,
                AIModelRouting.revision == revision,
            )
            .values(models_json=models, revision=revision + 1)
        )
        if result.rowcount != 1:
            raise RoutingConflict()

    def runs(self, since: datetime, limit: int = 5001) -> list[AIRun]:
        return list(
            self.session.scalars(
                select(AIRun)
                .options(
                    load_only(
                        AIRun.id,
                        AIRun.model,
                        AIRun.model_requested,
                        AIRun.model_used,
                        AIRun.provider,
                        AIRun.request_type,
                        AIRun.fallback_used,
                        AIRun.status,
                        AIRun.created_at,
                        AIRun.request_summary,
                        AIRun.error_history_json,
                    )
                )
                .join(Meal, Meal.id == AIRun.meal_id)
                .where(Meal.owner_id == self.user_id, AIRun.created_at >= since)
                .order_by(AIRun.created_at.desc(), AIRun.id.desc())
                .limit(limit)
            )
        )
