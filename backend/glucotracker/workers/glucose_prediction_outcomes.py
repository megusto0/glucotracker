"""Periodic evaluator for prospective glucose forecasts."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from glucotracker.application.glucose_prediction_audit import (
    GlucosePredictionAuditService,
)
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import User
from glucotracker.infra.db.session import get_session_factory

logger = logging.getLogger(__name__)

PREDICTION_OUTCOME_INTERVAL_SECONDS = 5 * 60


class GlucosePredictionOutcomeWorker:
    """Evaluate mature forecast points independently for every gluco user."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def run_forever(self) -> None:
        """Run immediately and then every five minutes until cancelled."""
        while True:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception:
                logger.exception("Glucose prediction outcome evaluation failed")
            await asyncio.sleep(PREDICTION_OUTCOME_INTERVAL_SECONDS)

    def run_once(self) -> int:
        """Evaluate due points and return the number finalized."""
        with self._session_factory() as session:
            user_ids = list(
                session.scalars(select(User.id).where(User.role == UserRole.gluco))
            )

        finalized = 0
        for user_id in user_ids:
            with self._session_factory() as session:
                try:
                    result = GlucosePredictionAuditService(
                        session,
                        user_id,
                    ).evaluate_due()
                    session.commit()
                    finalized += (
                        result.evaluated + result.missing + result.intervened
                    )
                except Exception:
                    session.rollback()
                    logger.exception(
                        "Prediction outcome evaluation failed for user %s",
                        user_id,
                    )
        if finalized:
            logger.info("Finalized %d glucose prediction points", finalized)
        return finalized
