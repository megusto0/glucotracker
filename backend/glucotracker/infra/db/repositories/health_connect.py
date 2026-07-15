"""Owner-scoped persistence for raw Health Connect records."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import HealthConnectRecord


class HealthConnectRepository:
    """Persist Health Connect records without allowing unscoped access."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        if not isinstance(user_id, UUID):
            raise ValueError("HealthConnectRepository requires a user_id")
        self.session = session
        self.user_id = user_id

    def sync(
        self,
        records: Iterable[dict[str, Any]],
        deleted_record_ids: Iterable[str],
    ) -> tuple[int, int]:
        """Upsert current records and hard-delete Health Connect tombstones."""
        record_list = list(records)
        incoming_ids = {str(item["record_id"]) for item in record_list}
        existing_by_id: dict[str, HealthConnectRecord] = {}
        if incoming_ids:
            rows = self.session.scalars(
                select(HealthConnectRecord).where(
                    HealthConnectRecord.owner_id == self.user_id,
                    HealthConnectRecord.record_id.in_(incoming_ids),
                )
            )
            existing_by_id = {row.record_id: row for row in rows}

        for values in record_list:
            record_id = str(values["record_id"])
            row = existing_by_id.get(record_id)
            if row is None:
                row = HealthConnectRecord(owner_id=self.user_id, record_id=record_id)
                self.session.add(row)
            for field, value in values.items():
                if field != "record_id":
                    setattr(row, field, value)

        deleted_ids = {str(record_id) for record_id in deleted_record_ids}
        deleted = 0
        if deleted_ids:
            result = self.session.execute(
                delete(HealthConnectRecord).where(
                    HealthConnectRecord.owner_id == self.user_id,
                    HealthConnectRecord.record_id.in_(deleted_ids),
                )
            )
            deleted = int(result.rowcount or 0)
        self.session.flush()
        return len(record_list), deleted

    def list_records(self) -> list[HealthConnectRecord]:
        """Return only records owned by the repository user."""
        return list(
            self.session.scalars(
                select(HealthConnectRecord)
                .where(HealthConnectRecord.owner_id == self.user_id)
                .order_by(HealthConnectRecord.start_time, HealthConnectRecord.record_id)
            )
        )

    def count_by_type(self) -> dict[str, int]:
        """Return a compact inventory without exposing raw health payloads."""
        counts: dict[str, int] = {}
        for row in self.list_records():
            counts[row.record_type] = counts.get(row.record_type, 0) + 1
        return counts


def normalize_health_connect_record(
    *,
    record_id: str,
    record_type: str,
    client_record_id: str | None,
    client_record_version: int,
    data_origin: str | None,
    recording_method: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    last_modified_time: datetime | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build the only accepted repository mutation shape."""
    return {
        "record_id": record_id,
        "record_type": record_type,
        "client_record_id": client_record_id,
        "client_record_version": client_record_version,
        "data_origin": data_origin,
        "recording_method": recording_method,
        "start_time": start_time,
        "end_time": end_time,
        "last_modified_time": last_modified_time,
        "payload": payload,
    }
