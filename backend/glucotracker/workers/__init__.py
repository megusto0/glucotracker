"""Background maintenance worker entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from glucotracker.application.nightscout_background import NightscoutBackgroundImporter
from glucotracker.application.postprandial.worker import PostprandialSweeper
from glucotracker.config import get_settings
from glucotracker.infra.db.session import get_session_factory
from glucotracker.infra.storage import photo_store
from glucotracker.workers.anchor_recompute import AnchorRecomputeWorker
from glucotracker.workers.episode_snapshots import EpisodeSnapshotWorker
from glucotracker.workers.on_board_fit import OnBoardFitWorker

logger = logging.getLogger(__name__)
PHOTO_TOMBSTONE_RETENTION_DAYS = 30
PHOTO_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


class PhotoTombstoneCleanupWorker:
    """Permanently delete tombstoned photo files after the retention window."""

    async def run_forever(self) -> None:
        """Run cleanup daily until cancelled."""
        logger.info("Photo tombstone cleanup worker started")
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Photo tombstone cleanup failed")
            await asyncio.sleep(PHOTO_CLEANUP_INTERVAL_SECONDS)

    def run_once(self) -> int:
        """Delete old tombstones once and return the number removed."""
        cutoff = datetime.now(UTC) - timedelta(days=PHOTO_TOMBSTONE_RETENTION_DAYS)
        deleted = photo_store.purge_deleted_older_than(cutoff)
        if deleted:
            logger.info("Purged %d tombstoned photo files", deleted)
        return deleted


async def run_workers() -> None:
    """Run all single-host maintenance workers in one process."""
    settings = get_settings()
    settings.validated_jwt_secret()

    tasks: list[asyncio.Task[None]] = [
        asyncio.create_task(AnchorRecomputeWorker().run_forever()),
        asyncio.create_task(PostprandialSweeper().run_forever()),
        asyncio.create_task(PhotoTombstoneCleanupWorker().run_forever()),
        asyncio.create_task(EpisodeSnapshotWorker().run_forever()),
        # Personalized IOB/COB timing (only runs in web when RUN_BACKGROUND_TASKS_IN_WEB).
        asyncio.create_task(OnBoardFitWorker().run_forever()),
    ]
    if settings.nightscout_background_import_enabled:
        tasks.append(
            asyncio.create_task(
                NightscoutBackgroundImporter(get_session_factory()).run_forever()
            )
        )

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


def main() -> None:
    """CLI entry point for `python -m glucotracker.workers`."""
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(run_workers())


if __name__ == "__main__":
    main()
