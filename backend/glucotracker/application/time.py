"""Local wall-clock time helpers for user-entered records."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo

from glucotracker.config import get_settings


def local_timezone() -> tzinfo:
    """Return the configured or host-local application timezone."""
    return get_settings().local_zoneinfo


def local_now() -> datetime:
    """Return the current local wall-clock time without tzinfo."""
    return datetime.now(local_timezone()).replace(tzinfo=None)


def local_wall_time(value: datetime) -> datetime:
    """Return a local wall-clock datetime, preserving naive values unchanged."""
    if value.tzinfo is None:
        return value
    return value.astimezone(local_timezone()).replace(tzinfo=None)


def utc_instant_from_local_wall(value: datetime) -> datetime:
    """Return the UTC instant represented by a local wall-clock datetime."""
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    return value.replace(tzinfo=local_timezone()).astimezone(UTC)


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Return local wall-clock datetime bounds for an app-local date."""
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)
