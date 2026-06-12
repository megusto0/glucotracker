"""Background task that materializes meal/insulin episode snapshots."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from glucotracker.application.insulin_links import InsulinLinkDayService
from glucotracker.application.time import local_now
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import User
from glucotracker.infra.db.session import get_session_factory

logger = logging.getLogger(__name__)

EPISODE_SNAPSHOT_INTERVAL_SECONDS = 3600
# Today plus a settle window: meals and Nightscout insulin for "yesterday"
# keep arriving for a while after midnight.
EPISODE_SNAPSHOT_LOOKBACK_DAYS = 2


class EpisodeSnapshotWorker:
    """Hourly recompute of episode snapshots for recent days, all gluco users.

    Keeps ``meal_insulin_episode_snapshots`` filled without manual review so
    the owner-scoped DB export always contains meal+insulin groupings.
    """

    def __init__(self) -> None:
        self._session_factory = get_session_factory()

    async def run_forever(self) -> None:
        """Run indefinitely, materializing snapshots each interval."""
        logger.info("Episode snapshot worker started")
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Episode snapshot worker failed")
            await asyncio.sleep(EPISODE_SNAPSHOT_INTERVAL_SECONDS)

    def run_once(self) -> int:
        """Materialize snapshots once; return the number of user-days touched."""
        session = self._session_factory()
        touched = 0
        try:
            user_ids = list(
                session.scalars(
                    select(User.id).where(User.role == UserRole.gluco)
                )
            )
            today = local_now().date()
            days = [
                today - timedelta(days=offset)
                for offset in range(EPISODE_SNAPSHOT_LOOKBACK_DAYS)
            ]
            for user_id in user_ids:
                service = InsulinLinkDayService(session, user_id)
                for day in days:
                    try:
                        service.materialize_day(day)
                        touched += 1
                    except Exception:
                        session.rollback()
                        logger.exception(
                            "Episode snapshot failed for user %s day %s",
                            user_id,
                            day,
                        )
        finally:
            session.close()
        return touched
