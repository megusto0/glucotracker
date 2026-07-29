"""Use cases for scanned CGM sensor Data Matrix codes."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    SensorCodeCreate,
    SensorCodePatch,
    SensorCodeResponse,
)
from glucotracker.domain.sensor_codes import (
    SensorCodeParseError,
    parse_sensor_data_matrix,
)
from glucotracker.infra.db.models import utc_now
from glucotracker.infra.db.repositories.sensor_codes import SensorCodeRepository


class SensorCodeService:
    """Coordinate parsing and owner-scoped persistence for sensor scans."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.repository = SensorCodeRepository(session, user_id)

    def list_codes(self) -> list[SensorCodeResponse]:
        return [
            SensorCodeResponse.model_validate(row)
            for row in self.repository.list_codes()
        ]

    def create(self, payload: SensorCodeCreate) -> SensorCodeResponse:
        try:
            parsed = parse_sensor_data_matrix(payload.raw_payload)
        except SensorCodeParseError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        row = self.repository.save_code(
            parsed,
            scanned_at=payload.scanned_at or utc_now(),
            sensor_session_id=payload.sensor_session_id,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor session not found.",
            )
        self.session.commit()
        self.session.refresh(row)
        return SensorCodeResponse.model_validate(row)

    def patch(self, code_id: UUID, payload: SensorCodePatch) -> SensorCodeResponse:
        if "sensor_session_id" not in payload.model_fields_set:
            row = self.repository.get_code(code_id)
        else:
            row = self.repository.attach(code_id, payload.sensor_session_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor code or sensor session not found.",
            )
        self.session.commit()
        self.session.refresh(row)
        return SensorCodeResponse.model_validate(row)
