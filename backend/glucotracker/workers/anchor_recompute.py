"""Background task that recomputes day-anchors nightly for all users."""

from __future__ import annotations

import asyncio
import logging

from glucotracker.application.categorization.window import (
    recompute_anchors_for_all_users,
)
from glucotracker.infra.db.session import get_session_factory

logger = logging.getLogger(__name__)

ANCHOR_RECOMPUTE_INTERVAL_SECONDS = 3600


class AnchorRecomputeWorker:
    """Periodically recompute day anchors for all users."""

    def __init__(self) -> None:
        self._session_factory = get_session_factory()

    async def run_forever(self) -> None:
        """Run indefinitely, recomputing anchors each interval."""
        logger.info("Anchor recompute worker started")
        while True:
            await asyncio.sleep(ANCHOR_RECOMPUTE_INTERVAL_SECONDS)
            try:
                self._recompute()
            except Exception:
                logger.exception("Anchor recompute worker failed")

    def _recompute(self) -> None:
        session = self._session_factory()
        try:
            recompute_anchors_for_all_users(session)
        finally:
            session.close()
