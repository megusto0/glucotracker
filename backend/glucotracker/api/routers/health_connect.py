"""Raw Health Connect ingestion for the glucose-enabled mobile app."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
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
