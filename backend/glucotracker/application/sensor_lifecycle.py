"""Sensor lifecycle helpers driven by explicit Nightscout/user events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.config import get_settings
from glucotracker.infra.db.models import (
    NightscoutGlucoseEntry,
    SensorSession,
    utc_now,
)
from glucotracker.infra.db.repositories.sensor_codes import (
    CGM_STREAM_GAP,
    SensorCodeRepository,
)

SENSOR_ROLLOVER_NOTE = "Автоматически завершён: истёк срок сенсора."

SensorLifecycleKind = Literal["start", "stop"]

_SENSOR_STOP_MARKERS = (
    "sensor stop",
    "sensor stopped",
    "sensor end",
    "sensor ended",
    "sensor expire",
    "sensor expired",
    "sensor removed",
)
_SENSOR_START_MARKERS = (
    "sensor start",
    "sensor started",
    "sensor change",
    "sensor changed",
    "sensor replace",
    "sensor replaced",
    "new sensor",
)


@dataclass(frozen=True)
class SensorLifecycleEvent:
    """Normalized sensor lifecycle event from an external source."""

    kind: SensorLifecycleKind
    timestamp: datetime
    label: str


def apply_sensor_lifecycle_events(
    session: Session,
    user_id: UUID,
    rows: list[dict[str, Any]],
) -> int:
    """Close user-owned sensor sessions from explicit Nightscout sensor events."""
    events = sorted(
        (event for row in rows if (event := _sensor_event(row)) is not None),
        key=lambda event: event.timestamp,
    )
    closed = 0
    for event in events:
        sensor = _sensor_to_close(session, user_id, event)
        if sensor is None:
            continue
        if _close_sensor(sensor, event.timestamp, event.label):
            closed += 1
    return closed


def close_previous_open_sensors(
    session: Session,
    user_id: UUID,
    new_started_at: datetime,
) -> int:
    """Close older open sessions when the user creates a newer sensor session."""
    local_started_at = _local_wall_time(new_started_at)
    rows = session.scalars(
        select(SensorSession).where(
            SensorSession.owner_id == user_id,
            SensorSession.ended_at.is_(None),
            SensorSession.started_at < local_started_at,
        )
    ).all()
    closed = 0
    for sensor in rows:
        if _close_sensor(sensor, local_started_at, "новый сенсор"):
            closed += 1
    return closed


def rollover_expired_sensor_sessions(
    session: Session,
    *,
    user_id: UUID | None = None,
) -> int:
    """Finish sensor sessions past their expected life at the sensor's last point.

    Guarantees that no open session survives longer than ``expected_life_days``:
    the expired session is closed on the last CGM point of its own stream and a
    fresh session is started on the first point of the following stream.
    """
    now = utc_now()
    statement = select(SensorSession).where(SensorSession.ended_at.is_(None))
    if user_id is not None:
        statement = statement.where(SensorSession.owner_id == user_id)
    rolled = 0
    for sensor in session.scalars(statement).all():
        if _rollover_expired_sensor(session, sensor, now):
            rolled += 1
    if rolled:
        session.commit()
    return rolled


def _rollover_expired_sensor(
    session: Session,
    sensor: SensorSession,
    now: datetime,
) -> bool:
    started_at = _as_utc(sensor.started_at)
    life_days = float(sensor.expected_life_days or 15)
    cutoff = started_at + timedelta(days=life_days)
    if cutoff > now:
        return False

    boundary = _stream_boundary(session, sensor, started_at, now, cutoff)
    if boundary is None:
        return False
    old_last, new_first = boundary

    sensor.ended_at = old_last
    sensor.updated_at = utc_now()
    if SENSOR_ROLLOVER_NOTE not in (sensor.notes or ""):
        sensor.notes = (
            f"{sensor.notes}\n{SENSOR_ROLLOVER_NOTE}".strip()
            if sensor.notes
            else SENSOR_ROLLOVER_NOTE
        )
    # Flush the finished session before the auto-start query reads open rows,
    # so the new stream is not mistaken for a continuation of the old one.
    session.flush()

    if new_first is not None:
        SensorCodeRepository(session, sensor.owner_id).start_sensor_at(new_first)
        session.flush()
    return True


def _stream_boundary(
    session: Session,
    sensor: SensorSession,
    started_at: datetime,
    now: datetime,
    cutoff: datetime,
) -> tuple[datetime, datetime | None] | None:
    """Return the last point of the expired stream and the next stream's first."""
    rows = session.scalars(
        select(NightscoutGlucoseEntry.timestamp)
        .where(
            NightscoutGlucoseEntry.owner_id == sensor.owner_id,
            NightscoutGlucoseEntry.timestamp >= started_at,
            NightscoutGlucoseEntry.timestamp <= now,
        )
        .order_by(NightscoutGlucoseEntry.timestamp.asc())
    ).all()
    times = [_as_utc(value) for value in rows]
    if not times:
        return None

    # The sensor ends on the last point before the first stream gap that starts
    # after its expected life. Earlier outages belong to the same sensor.
    for older, newer in zip(times, times[1:], strict=False):
        if older >= cutoff and newer - older > CGM_STREAM_GAP:
            return older, newer

    if times[-1] <= cutoff:
        # The stream stopped at/before the expected end; wait for the next one.
        return times[-1], None

    before = [value for value in times if value <= cutoff]
    after = [value for value in times if value > cutoff]
    if before and after:
        return before[-1], after[0]
    return None


def is_sensor_lifecycle_treatment(row: dict[str, Any]) -> bool:
    """Return whether a Nightscout treatment looks like a sensor lifecycle event."""
    return _sensor_event(row) is not None


def _sensor_to_close(
    session: Session,
    user_id: UUID,
    event: SensorLifecycleEvent,
) -> SensorSession | None:
    filters = [
        SensorSession.owner_id == user_id,
        SensorSession.ended_at.is_(None),
        SensorSession.started_at <= event.timestamp,
    ]
    if event.kind == "start":
        filters[-1] = SensorSession.started_at < event.timestamp
    return session.scalar(
        select(SensorSession)
        .where(*filters)
        .order_by(SensorSession.started_at.desc())
        .limit(1)
    )


def _close_sensor(
    sensor: SensorSession,
    ended_at: datetime,
    source_label: str,
) -> bool:
    local_ended_at = _local_wall_time(ended_at)
    if local_ended_at < _local_wall_time(sensor.started_at):
        return False
    if sensor.ended_at == local_ended_at:
        return False
    sensor.ended_at = local_ended_at
    sensor.updated_at = utc_now()
    note = f"Автоматически завершён: {source_label}."
    if note not in (sensor.notes or ""):
        sensor.notes = f"{sensor.notes}\n{note}".strip() if sensor.notes else note
    return True


def _sensor_event(row: dict[str, Any]) -> SensorLifecycleEvent | None:
    timestamp = _timestamp_from_row(row)
    if timestamp is None:
        return None
    text = _event_text(row)
    if "sensor" not in text:
        return None
    label = str(row.get("eventType") or row.get("type") or "Nightscout sensor event")
    if any(marker in text for marker in _SENSOR_STOP_MARKERS):
        return SensorLifecycleEvent(kind="stop", timestamp=timestamp, label=label)
    if any(marker in text for marker in _SENSOR_START_MARKERS):
        return SensorLifecycleEvent(kind="start", timestamp=timestamp, label=label)
    return None


def _event_text(row: dict[str, Any]) -> str:
    parts = [
        row.get("eventType"),
        row.get("type"),
        row.get("notes"),
        row.get("reason"),
    ]
    return " ".join(str(part) for part in parts if part).casefold()


def _timestamp_from_row(row: dict[str, Any]) -> datetime | None:
    raw = row.get("dateString") or row.get("created_at") or row.get("createdAt")
    if isinstance(raw, str) and raw:
        try:
            return _local_wall_time(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            return None
    raw_date = row.get("date")
    if isinstance(raw_date, int | float):
        return _local_wall_time(datetime.fromtimestamp(raw_date / 1000, tz=UTC))
    return None


def _local_wall_time(value: datetime) -> datetime:
    """Convert aware timestamps to app-local naive wall time."""
    if value.tzinfo is None:
        return value
    return value.astimezone(get_settings().local_zoneinfo).replace(tzinfo=None)


def _as_utc(value: datetime) -> datetime:
    """Return a stored instant as UTC, treating naive values as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
