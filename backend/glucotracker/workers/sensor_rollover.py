"""Background task that rolls over sensor sessions after their expected life."""

from __future__ import annotations

import asyncio
import logging

from glucotracker.application.sensor_lifecycle import (
    rollover_expired_sensor_sessions,
)
from glucotracker.infra.db.session import get_session_factory

logger = logging.getLogger(__name__)

SENSOR_ROLLOVER_INTERVAL_SECONDS = 3600


class SensorRolloverWorker:
    """Hourly finish of sensor sessions that outlived their expected life."""

    def __init__(self) -> None:
        self._session_factory = get_session_factory()

    async def run_forever(self) -> None:
        """Run indefinitely, rolling over expired sessions each interval."""
        logger.info("Sensor rollover worker started")
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Sensor rollover worker failed")
            await asyncio.sleep(SENSOR_ROLLOVER_INTERVAL_SECONDS)

    def run_once(self) -> int:
        """Finish expired sessions once; return the number rolled over."""
        session = self._session_factory()
        try:
            rolled = rollover_expired_sensor_sessions(session)
            if rolled:
                logger.info("Rolled over %d expired sensor session(s)", rolled)
            return rolled
        finally:
            session.close()
