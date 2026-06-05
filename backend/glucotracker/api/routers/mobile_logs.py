"""Mobile diagnostic log ingestion endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from glucotracker.api.dependencies import CurrentUserDep
from glucotracker.config import get_settings

router = APIRouter(prefix="/mobile", tags=["mobile"])


class MobilePhotoEstimateLogEvent(BaseModel):
    """One Android-side photo estimation pipeline diagnostic event."""

    event_id: str = Field(min_length=1, max_length=80)
    trace_id: str = Field(min_length=1, max_length=80)
    outbox_id: str | None = Field(default=None, max_length=80)
    idempotency_key: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, max_length=32)
    event_type: str = Field(min_length=1, max_length=64)
    event_at: datetime
    captured_at: datetime | None = None
    server_meal_id: UUID | None = None
    estimate_status: str | None = Field(default=None, max_length=32)
    attempt: int | None = Field(default=None, ge=0, le=100)
    total_elapsed_ms: int | None = Field(default=None, ge=0)
    queued_delay_ms: int | None = Field(default=None, ge=0)
    upload_duration_ms: int | None = Field(default=None, ge=0)
    retry_delay_ms: int | None = Field(default=None, ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=1000)
    app_flavor: str | None = Field(default=None, max_length=32)
    app_version: str | None = Field(default=None, max_length=32)
    android_sdk: int | None = Field(default=None, ge=1)
    device_model: str | None = Field(default=None, max_length=120)
    detail: dict[str, Any] = Field(default_factory=dict)


class MobilePhotoEstimateLogRequest(BaseModel):
    """Batch of mobile photo-estimation diagnostic events."""

    events: list[MobilePhotoEstimateLogEvent] = Field(min_length=1, max_length=100)
    client_sent_at: datetime | None = None


class MobilePhotoEstimateLogResponse(BaseModel):
    """Server-side log ingest acknowledgement."""

    accepted_count: int


@router.post(
    "/photo-estimate-logs",
    response_model=MobilePhotoEstimateLogResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="submitMobilePhotoEstimateLogs",
)
def submit_mobile_photo_estimate_logs(
    payload: MobilePhotoEstimateLogRequest,
    current_user: CurrentUserDep,
) -> MobilePhotoEstimateLogResponse:
    """Append Android photo-estimation diagnostics to a server JSONL log file."""
    received_at = datetime.now(UTC)
    log_dir = get_settings().activity_log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "mobile-photo-estimate.jsonl"

    with log_path.open("a", encoding="utf-8") as log_file:
        for event in payload.events:
            row = {
                "received_at": received_at.isoformat(),
                "user_id": str(current_user.id),
                "user_role": current_user.role.value,
                "client_sent_at": (
                    payload.client_sent_at.isoformat()
                    if payload.client_sent_at is not None
                    else None
                ),
                **event.model_dump(mode="json"),
                "detail": _safe_detail(event.detail),
            }
            log_file.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                + "\n"
            )

    return MobilePhotoEstimateLogResponse(accepted_count=len(payload.events))


def _safe_detail(value: Any) -> Any:
    """Redact accidental local file/photo identifiers before writing diagnostics."""
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized = key.lower()
            if any(token in normalized for token in ("path", "file", "photo", "image")):
                safe[key] = "[redacted]"
            else:
                safe[key] = _safe_detail(item)
        return safe
    if isinstance(value, list):
        return [_safe_detail(item) for item in value[:50]]
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _truncate(str(value))


def _truncate(value: str, limit: int = 1000) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."
