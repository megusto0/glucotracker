"""Generate owner-scoped forecast snapshots outside API request handling."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from glucotracker.application.glucose_prediction_audit import (
    GlucosePredictionAuditService,
)
from glucotracker.application.glucose_prediction_runtime import selected_predictor
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import User
from glucotracker.infra.db.repositories.glucose_prediction_audit import (
    GlucosePredictionAuditRepository,
)
from glucotracker.infra.db.session import get_session_factory

logger = logging.getLogger(__name__)


class GlucosePredictionWorker:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self.factory = session_factory or get_session_factory()

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception:
                logger.exception("Forecast worker pass failed")
            await asyncio.sleep(60)

    def run_once(self, *, now: datetime | None = None) -> int:
        at = now or datetime.now(UTC)
        prediction = selected_predictor()
        with self.factory() as session:
            users = list(
                session.scalars(select(User.id).where(User.role == UserRole.gluco))
            )
        created = 0
        for owner in users:
            with self.factory() as session:
                try:
                    repository = GlucosePredictionAuditRepository(session, owner)
                    newest = repository.latest_glucose_at(
                        since=at - timedelta(minutes=15),
                        before=at,
                    )
                    if newest is None:
                        continue
                    latest = GlucosePredictionAuditRepository(
                        session, owner
                    ).latest_forecast(
                        model_version=prediction.MODEL_VERSION,
                        since=at - timedelta(minutes=15),
                        before=at,
                    )
                    if latest is not None and latest.anchor_timestamp == newest:
                        continue
                    predictor = prediction.GlucosePredictionService(session, owner)
                    # V8 is live-only; historical cutoffs belong to the v9 replay.
                    kwargs = (
                        {"as_of": at}
                        if prediction.MODEL_VERSION.endswith("_v9")
                        else {}
                    )
                    response = predictor.predict(**kwargs)
                    made = GlucosePredictionAuditService(session, owner).record(
                        response,
                        provenance=getattr(predictor, "input_provenance", {}),
                    )
                    session.commit()
                    created += int(made)
                except Exception:
                    session.rollback()
                    logger.exception("Forecast generation failed for user %s", owner)
        return created
