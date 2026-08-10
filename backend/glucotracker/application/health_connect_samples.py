"""Reading embedded Health Connect samples at the right instant.

Two conventions reach the database. Older Android builds wrote each sample's
``time`` as the true UTC instant while the row's ``start_time`` column arrived
shifted by the local offset; newer builds write the sample as local wall clock
tagged with a misleading ``Z`` and the column carries the corrected instant.
Neither can be trusted on its own, so when the payload declares a zone offset
the candidate closest to the row's own span wins. That keeps every reader on
the same timeline whichever client wrote the row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from glucotracker.infra.db.models import HealthConnectRecord
from glucotracker.infra.db.repositories.health_connect import (
    HealthConnectRepository,
)

MIN_PLAUSIBLE_BPM = 25.0
MAX_PLAUSIBLE_BPM = 240.0
# Health Connect metadata can be shifted by a whole UTC offset, so records are
# read with a margin around the window and every sample is filtered by its own
# resolved instant.
METADATA_MARGIN = timedelta(days=1)


def as_utc(value: datetime | None) -> datetime | None:
    """Return an aware UTC datetime for a stored column value."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def payload_zone_offset(payload: dict[str, Any]) -> timedelta | None:
    """Return the wall-clock offset Health Connect attached to a payload."""
    raw = payload.get("startZoneOffset") or payload.get("endZoneOffset")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(f"2026-01-01T00:00:00{raw}").utcoffset()
    except ValueError:
        return None


def _parse_instant(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _distance_to_row(candidate: datetime, row: HealthConnectRecord) -> timedelta:
    start = as_utc(row.start_time)
    end = as_utc(row.end_time) or start
    if start is None:
        return timedelta(0)
    if end is not None and start <= candidate <= end:
        return timedelta(0)
    if end is not None and candidate > end:
        return candidate - end
    return start - candidate


def resolve_instant(
    raw: Any,
    row: HealthConnectRecord,
    *,
    fallback_to_end: bool = False,
) -> datetime | None:
    """Return the true UTC instant a payload-embedded time refers to.

    Real rows carry the sample or session time as the true UTC instant tagged
    with "Z", while the row's own ``start_time``/``end_time`` columns are that
    same wall clock shifted by the declared zone offset, stored as if UTC.
    Both readings are scored against the row's own span and the closer one
    wins, so whichever writer convention produced the row ends up on the same
    timeline. When the payload carries no time, the matching column is the
    fallback.
    """
    naive = _parse_instant(raw)
    if naive is None:
        column = row.end_time if fallback_to_end else row.start_time
        return as_utc(column)
    offset = payload_zone_offset(row.payload or {})
    if offset is None or as_utc(row.start_time) is None:
        return naive
    shifted = naive - offset
    return (
        shifted
        if _distance_to_row(shifted, row) < _distance_to_row(naive, row)
        else naive
    )


def resolve_sample_instant(
    sample: dict[str, Any],
    row: HealthConnectRecord,
) -> datetime | None:
    """Return the instant a single embedded sample was actually recorded."""
    if not isinstance(sample, dict):
        return None
    return resolve_instant(sample.get("time"), row)


def heart_rate_samples(
    session: Session,
    user_id,
    from_utc: datetime,
    to_utc: datetime,
) -> list[tuple[datetime, float]]:
    """Return owner-scoped heart-rate samples inside a UTC range, in order.

    Duplicate instants collapse to one reading, which is how repeated syncs of
    the same wearable minute reach the database.
    """
    records = HealthConnectRepository(
        session,
        user_id,
    ).list_records_by_type_and_time(
        "HeartRateRecord",
        from_utc - METADATA_MARGIN,
        to_utc + METADATA_MARGIN,
    )
    by_instant: dict[datetime, float] = {}
    for record in records:
        samples = record.payload.get("samples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            instant = resolve_sample_instant(sample, record)
            bpm = _finite_number(sample.get("beatsPerMinute"))
            if (
                instant is None
                or bpm is None
                or bpm < MIN_PLAUSIBLE_BPM
                or bpm > MAX_PLAUSIBLE_BPM
                or instant < from_utc
                or instant >= to_utc
            ):
                continue
            by_instant[instant] = bpm
    return sorted(by_instant.items())


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number
