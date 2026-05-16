"""Best-effort background import for local Nightscout glucose cache."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from glucotracker.application.nightscout_context import (
    NightscoutContextImportService,
)
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import (
    NightscoutGlucoseEntry,
    NightscoutImportState,
    NightscoutSettings,
    User,
    utc_now,
)
from glucotracker.infra.nightscout.client import NightscoutClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NightscoutImportCandidate:
    """Configured gluco user eligible for background glucose import."""

    user_id: UUID
    url: str
    api_secret: str
    latest_glucose_at: datetime | None


class NightscoutBackgroundImporter:
    """Poll Nightscout periodically and persist glucose rows locally."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        interval_seconds: int | None = None,
        lookback_hours: int | None = None,
        overlap_minutes: int | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        settings = get_settings()
        self.session_factory = session_factory
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else settings.nightscout_background_import_interval_seconds
        )
        self.lookback = timedelta(
            hours=lookback_hours
            if lookback_hours is not None
            else settings.nightscout_background_import_lookback_hours
        )
        self.overlap = timedelta(
            minutes=overlap_minutes
            if overlap_minutes is not None
            else settings.nightscout_background_import_overlap_minutes
        )
        self._now = now or (lambda: datetime.now(get_settings().local_zoneinfo))

    async def run_forever(self) -> None:
        """Run imports every configured interval until cancelled."""
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Background Nightscout glucose import loop failed")
            await asyncio.sleep(self.interval_seconds)

    async def run_once(self) -> int:
        """Import recent glucose rows once for every configured gluco user."""
        candidates = self._candidates()
        imported_total = 0
        for candidate in candidates:
            try:
                imported_total += await self._import_candidate(candidate)
            except Exception:
                logger.exception(
                    "Background Nightscout glucose import failed for user %s",
                    candidate.user_id,
                )
        return imported_total

    def _candidates(self) -> list[NightscoutImportCandidate]:
        env = get_settings()
        with self.session_factory() as session:
            rows = session.execute(
                select(User.id, NightscoutSettings)
                .outerjoin(
                    NightscoutSettings,
                    NightscoutSettings.owner_id == User.id,
                )
                .where(User.role == UserRole.gluco)
            ).all()
            candidates: list[NightscoutImportCandidate] = []
            for user_id, settings_row in rows:
                url = (settings_row.url if settings_row is not None else None) or (
                    env.nightscout_url
                )
                api_secret = (
                    settings_row.api_secret if settings_row is not None else None
                ) or env.nightscout_api_secret
                enabled = (
                    settings_row.enabled
                    if settings_row is not None
                    else bool(url and api_secret)
                )
                sync_glucose = (
                    settings_row.sync_glucose if settings_row is not None else True
                )
                if not enabled or not sync_glucose or not url or not api_secret:
                    continue

                latest_glucose_at = session.scalar(
                    select(func.max(NightscoutGlucoseEntry.timestamp)).where(
                        NightscoutGlucoseEntry.owner_id == user_id
                    )
                )
                candidates.append(
                    NightscoutImportCandidate(
                        user_id=user_id,
                        url=url,
                        api_secret=api_secret,
                        latest_glucose_at=latest_glucose_at,
                    )
                )
            return candidates

    async def _import_candidate(self, candidate: NightscoutImportCandidate) -> int:
        from_datetime, to_datetime = self._range(candidate.latest_glucose_at)
        client = NightscoutClient(
            base_url=candidate.url,
            api_secret=candidate.api_secret,
        )
        try:
            glucose_rows = await client.fetch_glucose_entries(
                from_datetime,
                to_datetime,
            )
        except Exception as exc:
            self._record_error(candidate.user_id, exc)
            raise
        sensor_event_rows = []
        if hasattr(client, "fetch_sensor_events"):
            try:
                sensor_event_rows = await client.fetch_sensor_events(
                    from_datetime,
                    to_datetime,
                )
            except Exception:
                sensor_event_rows = []

        with self.session_factory() as session:
            response = NightscoutContextImportService(
                session,
                candidate.user_id,
                client,
            ).import_fetched(
                from_datetime,
                to_datetime,
                glucose_rows=glucose_rows,
                insulin_rows=[],
                sensor_event_rows=sensor_event_rows,
            )
            return response.glucose_imported

    def _range(self, latest_glucose_at: datetime | None) -> tuple[datetime, datetime]:
        now = self._now()
        floor = now - self.lookback
        if latest_glucose_at is None:
            return floor, now

        latest = _as_local_aware(latest_glucose_at)
        start = max(floor, min(latest - self.overlap, now))
        return start, now

    def _record_error(self, user_id: UUID, exc: Exception) -> None:
        with self.session_factory() as session:
            state = session.scalar(
                select(NightscoutImportState).where(
                    NightscoutImportState.owner_id == user_id
                )
            )
            if state is None:
                state = NightscoutImportState(owner_id=user_id)
                session.add(state)
                session.flush()
            state.last_error = str(exc) or "Nightscout background import failed"
            state.updated_at = utc_now()
            session.commit()


def _as_local_aware(value: datetime) -> datetime:
    local_zone = get_settings().local_zoneinfo
    if value.tzinfo is None:
        return value.replace(tzinfo=local_zone)
    return value.astimezone(local_zone)
