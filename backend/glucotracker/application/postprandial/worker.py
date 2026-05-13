"""Deferred postprandial sweeper — runs every 5 minutes.

Selects meals where eaten_at + 300 min has elapsed and
postprandial_response is still NULL, then computes and
persists the analysis.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from glucotracker.application.postprandial.analyzer import (
    compute_postprandial_response,
)
from glucotracker.application.postprandial.thresholds import (
    DEFERRED_WORKER_DELAY_MINUTES,
)
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import Meal
from glucotracker.infra.db.session import get_session_factory

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 300
MAX_MEALS_PER_RUN = 100


class PostprandialSweeper:
    """Background worker that sweeps eligible meals every 5 minutes."""

    def __init__(self) -> None:
        self._session_factory = get_session_factory()

    async def run_forever(self) -> None:
        """Run indefinitely, sweeping every SWEEP_INTERVAL_SECONDS."""
        logger.info("Postprandial sweeper started")
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            try:
                self._sweep()
            except Exception:
                logger.exception("Postprandial sweeper failed")

    def _sweep(self) -> None:
        session = self._session_factory()
        try:
            cutoff = datetime.now() - timedelta(
                minutes=DEFERRED_WORKER_DELAY_MINUTES
            )
            meal_ids = list(
                session.execute(
                    select(Meal.id)
                    .where(
                        Meal.status == MealStatus.accepted,
                        Meal.postprandial_response.is_(None),
                        Meal.eaten_at <= cutoff,
                    )
                    .limit(MAX_MEALS_PER_RUN)
                )
                .scalars()
                .all()
            )

            if not meal_ids:
                return

            analyzed = 0
            for mid in meal_ids:
                try:
                    recompute_postprandial(mid, session=session)
                    analyzed += 1
                except Exception:
                    logger.exception(
                        "Failed to compute postprandial for meal %s", mid
                    )

            if analyzed:
                logger.info(
                    "Postprandial sweeper: analyzed %d meals", analyzed
                )
        finally:
            session.close()


def recompute_postprandial(
    meal_id: UUID,
    *,
    session: object | None = None,
) -> bool:
    """Compute and persist postprandial response for a single meal.

    Idempotent — can be called on already-analyzed meals.
    Returns True if analysis was performed.
    """
    own_session = session is None
    active_session = (
        session if session is not None else get_session_factory()()
    )
    try:
        meal = active_session.scalar(
            select(Meal)
            .where(Meal.id == meal_id)
            .options(selectinload(Meal.items))
        )
        if meal is None:
            logger.warning("recompute_postprandial: meal %s not found", meal_id)
            return False

        response = compute_postprandial_response(active_session, meal)
        if response is None:
            return False

        from datetime import UTC
        from datetime import datetime as dt

        meal.postprandial_response = response
        meal.postprandial_computed_at = dt.now(UTC)

        if own_session:
            active_session.commit()
        else:
            active_session.flush()

        return True
    finally:
        if own_session:
            active_session.close()
