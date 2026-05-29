"""Visibility rules for CGM readings.

Raw CGM rows are immutable and remain stored, but rows inside sensor sessions
marked as excluded must not be surfaced in app views or analytics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import exists, not_, select
from sqlalchemy.orm import Session

from glucotracker.application.time import local_wall_time
from glucotracker.infra.db.models import NightscoutGlucoseEntry, SensorSession


def visible_glucose_filter(user_id: UUID) -> Any:
    """Return a SQL filter that excludes CGM inside corrupt sensor sessions."""
    return not_(_excluded_glucose_exists(user_id))


def is_glucose_timestamp_visible(
    session: Session,
    user_id: UUID,
    timestamp: datetime,
) -> bool:
    """Return whether a non-DB CGM timestamp is outside excluded sensor sessions."""
    value = local_wall_time(timestamp)
    rows = session.scalars(
        select(SensorSession).where(
            SensorSession.owner_id == user_id,
            SensorSession.excluded_from_analytics.is_(True),
        )
    )
    return not any(
        local_wall_time(row.started_at)
        <= value
        <= local_wall_time(row.ended_at or value)
        for row in rows
    )


def _excluded_glucose_exists(user_id: UUID) -> Any:
    return exists(
        select(1).where(
            SensorSession.owner_id == user_id,
            SensorSession.excluded_from_analytics.is_(True),
            SensorSession.started_at <= NightscoutGlucoseEntry.timestamp,
            (SensorSession.ended_at.is_(None))
            | (SensorSession.ended_at >= NightscoutGlucoseEntry.timestamp),
        )
    )
