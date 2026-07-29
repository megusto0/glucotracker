"""Raw Health Connect ingestion for the glucose-enabled mobile app."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from glucotracker.api.dependencies import CurrentUserDep, ReadSessionDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
from glucotracker.application.time import (
    local_wall_time,
    utc_instant_from_local_wall,
)
from glucotracker.infra.db.repositories.health_connect import (
    HealthConnectRepository,
    normalize_health_connect_record,
)

router = APIRouter(
    prefix="/health-connect",
    tags=["health-connect"],
    dependencies=[Depends(require_feature("glucose"))],
)


class HealthConnectRecordUpload(BaseModel):
    record_id: str = Field(min_length=1, max_length=255)
    record_type: str = Field(min_length=1, max_length=100)
    client_record_id: str | None = Field(default=None, max_length=255)
    client_record_version: int = Field(
        default=0,
        ge=0,
        json_schema_extra={"format": "int64"},
    )
    data_origin: str | None = Field(default=None, max_length=255)
    recording_method: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    last_modified_time: datetime | None = None
    payload: dict[str, Any]


class HealthConnectSyncRequest(BaseModel):
    records: list[HealthConnectRecordUpload] = Field(
        default_factory=list,
        max_length=500,
    )
    deleted_record_ids: list[str] = Field(default_factory=list, max_length=1000)


class HealthConnectSyncResponse(BaseModel):
    received: int
    upserted: int
    deleted: int


class HeartRateBinResponse(BaseModel):
    timestamp: datetime
    bpm: float
    sample_count: int


class HeartRateSeriesResponse(BaseModel):
    from_datetime: datetime
    to_datetime: datetime
    bin_minutes: int
    points: list[HeartRateBinResponse]


@router.post(
    "/records:sync",
    response_model=HealthConnectSyncResponse,
    operation_id="syncHealthConnectRecords",
)
def sync_health_connect_records(
    payload: HealthConnectSyncRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> HealthConnectSyncResponse:
    """Idempotently mirror raw records and deletions from Health Connect."""
    repository = HealthConnectRepository(session, current_user.id)
    normalized = [
        normalize_health_connect_record(**record.model_dump())
        for record in payload.records
    ]
    upserted, deleted = repository.sync(normalized, payload.deleted_record_ids)
    session.commit()
    return HealthConnectSyncResponse(
        received=len(payload.records) + len(payload.deleted_record_ids),
        upserted=upserted,
        deleted=deleted,
    )


@router.get(
    "/heart-rate",
    response_model=HeartRateSeriesResponse,
    operation_id="getHeartRateSeries",
)
def get_heart_rate_series(
    session: ReadSessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
    bin_minutes: Annotated[int, Query(ge=5, le=60)] = 10,
) -> HeartRateSeriesResponse:
    """Return median heart-rate samples in compact display bins."""
    from_utc = utc_instant_from_local_wall(from_datetime)
    to_utc = utc_instant_from_local_wall(to_datetime)
    if to_utc <= from_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'to' must be after 'from'.",
        )
    if to_utc - from_utc > timedelta(days=7):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Heart-rate range cannot exceed 7 days.",
        )

    # Health Connect metadata from the current Android client can be shifted by
    # the local UTC offset. Query a safe margin, then trust each sample's
    # embedded instant and strictly filter it to the requested range.
    metadata_margin = timedelta(days=1)
    records = HealthConnectRepository(
        session,
        current_user.id,
    ).list_records_by_type_and_time(
        "HeartRateRecord",
        from_utc - metadata_margin,
        to_utc + metadata_margin,
    )

    samples_by_time: dict[datetime, float] = {}
    for record in records:
        raw_samples = record.payload.get("samples")
        if not isinstance(raw_samples, list):
            continue
        for sample in raw_samples:
            if not isinstance(sample, dict):
                continue
            timestamp = _payload_timestamp(sample.get("time"))
            bpm = _finite_number(sample.get("beatsPerMinute"))
            if (
                timestamp is None
                or bpm is None
                or bpm < 25
                or bpm > 240
                or timestamp < from_utc
                or timestamp >= to_utc
            ):
                continue
            samples_by_time[timestamp] = bpm

    bin_seconds = bin_minutes * 60
    values_by_bin: dict[datetime, list[float]] = defaultdict(list)
    for timestamp, bpm in samples_by_time.items():
        bucket_epoch = int(timestamp.timestamp()) // bin_seconds * bin_seconds
        bucket = datetime.fromtimestamp(bucket_epoch, tz=UTC)
        values_by_bin[bucket].append(bpm)

    points = [
        HeartRateBinResponse(
            timestamp=local_wall_time(timestamp),
            bpm=round(float(median(values)), 1),
            sample_count=len(values),
        )
        for timestamp, values in sorted(values_by_bin.items())
    ]
    return HeartRateSeriesResponse(
        from_datetime=local_wall_time(from_utc),
        to_datetime=local_wall_time(to_utc),
        bin_minutes=bin_minutes,
        points=points,
    )


def _payload_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number
