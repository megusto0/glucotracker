"""Periodic retrospective IOB/COB timing personalization."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from glucotracker.application.on_board.service import OnBoardFitService
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import User
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.session import get_session_factory

logger = logging.getLogger(__name__)

ON_BOARD_FIT_INTERVAL_SECONDS = 6 * 60 * 60
MIN_REFIT_INTERVAL = timedelta(hours=24)


class OnBoardFitWorker:
    """Fit completed rolling history independently for every gluco user."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def run_forever(self) -> None:
        """Run immediately and then on a bounded background cadence."""
        while True:
            try:
                # Fitting is intentionally CPU-heavy and uses synchronous DB
                # sessions.  Keep both in a worker thread so the FastAPI event
                # loop remains responsive while this background task runs.
                await asyncio.to_thread(self.run_once)
            except Exception:
                logger.exception("On-board fit worker iteration failed")
            await asyncio.sleep(ON_BOARD_FIT_INTERVAL_SECONDS)

    def run_once(self, *, force: bool = False) -> int:
        """Return the number of users for whom a fit attempt was recorded."""
        with self._session_factory() as session:
            user_ids = list(
                session.scalars(select(User.id).where(User.role == UserRole.gluco))
            )

        touched = 0
        for user_id in user_ids:
            with self._session_factory() as session:
                try:
                    repository = OnBoardRepository(session, user_id)
                    latest = repository.latest_attempt_at()
                    if not force and latest is not None:
                        latest_utc = (
                            latest.replace(tzinfo=UTC)
                            if latest.tzinfo is None
                            else latest.astimezone(UTC)
                        )
                        if datetime.now(UTC) - latest_utc < MIN_REFIT_INTERVAL:
                            continue
                    run = OnBoardFitService(session, user_id).fit_recent()
                    session.commit()
                    if run.recorded_fit_count > 0:
                        touched += 1
                except Exception:
                    session.rollback()
                    logger.exception(
                        "On-board fit failed for user %s",
                        user_id,
                    )
        return touched
