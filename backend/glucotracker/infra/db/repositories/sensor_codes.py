"""Owner-scoped persistence for scanned CGM sensor codes and auto-start."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.domain.sensor_codes import ParsedSensorCode
from glucotracker.infra.db.models import (
    NightscoutGlucoseEntry,
    SensorCode,
    SensorSession,
    utc_now,
)

CGM_STREAM_GAP = timedelta(minutes=20)
CGM_STREAM_LOOKBACK = timedelta(days=16)


class SensorCodeRepository:
    """Persist sensor scans without allowing unscoped access."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        if not isinstance(user_id, UUID):
            raise ValueError("SensorCodeRepository requires a user_id")
        self.session = session
        self.user_id = user_id

    def list_codes(self) -> list[SensorCode]:
        """Return this user's sensor scans, newest first."""
        return list(
            self.session.scalars(
                select(SensorCode)
                .where(SensorCode.owner_id == self.user_id)
                .order_by(SensorCode.scanned_at.desc(), SensorCode.created_at.desc())
            )
        )

    def get_code(self, code_id: UUID) -> SensorCode | None:
        """Return one scan only when it belongs to this user."""
        return self.session.scalar(
            select(SensorCode).where(
                SensorCode.id == code_id,
                SensorCode.owner_id == self.user_id,
            )
        )

    def get_sensor(self, sensor_id: UUID) -> SensorSession | None:
        """Return one sensor session only when it belongs to this user."""
        return self.session.scalar(
            select(SensorSession).where(
                SensorSession.id == sensor_id,
                SensorSession.owner_id == self.user_id,
            )
        )

    def save_code(
        self,
        parsed: ParsedSensorCode,
        *,
        scanned_at: datetime,
        sensor_session_id: UUID | None,
    ) -> SensorCode | None:
        """Idempotently save a scan and optionally attach it to an owned sensor."""
        if sensor_session_id is not None and self.get_sensor(sensor_session_id) is None:
            return None
        row = self.session.scalar(
            select(SensorCode).where(
                SensorCode.owner_id == self.user_id,
                SensorCode.gtin == parsed.gtin,
                SensorCode.serial_number == parsed.serial_number,
            )
        )
        if row is None:
            row = SensorCode(
                owner_id=self.user_id,
                raw_payload=parsed.raw_payload,
                gtin=parsed.gtin,
                manufactured_on=parsed.manufactured_on,
                expires_on=parsed.expires_on,
                lot_number=parsed.lot_number,
                serial_number=parsed.serial_number,
                scanned_at=scanned_at,
            )
            self.session.add(row)
        else:
            row.raw_payload = parsed.raw_payload
            row.manufactured_on = parsed.manufactured_on
            row.expires_on = parsed.expires_on
            row.lot_number = parsed.lot_number
            row.scanned_at = scanned_at
            row.updated_at = utc_now()
        if sensor_session_id is not None:
            self._detach_other_code(sensor_session_id, except_code_id=row.id)
            row.sensor_session_id = sensor_session_id
        self.session.flush()
        return row

    def attach(
        self,
        code_id: UUID,
        sensor_session_id: UUID | None,
    ) -> SensorCode | None:
        """Attach, move, or detach a scan, enforcing ownership on both sides."""
        row = self.get_code(code_id)
        if row is None:
            return None
        if sensor_session_id is not None:
            if self.get_sensor(sensor_session_id) is None:
                return None
            self._detach_other_code(sensor_session_id, except_code_id=row.id)
        row.sensor_session_id = sensor_session_id
        row.updated_at = utc_now()
        self.session.flush()
        return row

    def ensure_sensor_for_new_glucose(
        self,
        reading_at: datetime,
    ) -> SensorSession | None:
        """Auto-start a sensor at the first point of the current CGM stream."""
        active = self.session.scalar(
            select(SensorSession)
            .where(
                SensorSession.owner_id == self.user_id,
                SensorSession.ended_at.is_(None),
            )
            .order_by(SensorSession.started_at.desc())
            .limit(1)
        )
        if active is not None:
            return None

        stream_started_at = self._current_stream_start(reading_at)
        latest_finished_at = self.session.scalar(
            select(SensorSession.ended_at)
            .where(
                SensorSession.owner_id == self.user_id,
                SensorSession.ended_at.is_not(None),
            )
            .order_by(SensorSession.ended_at.desc())
            .limit(1)
        )
        if latest_finished_at is not None and stream_started_at <= _as_utc(
            latest_finished_at
        ):
            # A manually finished sensor may still emit a few more readings.
            # Wait for an actual CGM stream boundary before starting another.
            return None

        code = self.session.scalar(
            select(SensorCode)
            .where(
                SensorCode.owner_id == self.user_id,
                SensorCode.sensor_session_id.is_(None),
            )
            .order_by(SensorCode.scanned_at.desc(), SensorCode.created_at.desc())
            .limit(1)
        )
        label = f"Сенсор · {code.serial_number[-6:]}" if code is not None else "Сенсор"
        sensor = SensorSession(
            owner_id=self.user_id,
            source="auto_cgm",
            label=label,
            started_at=stream_started_at,
            expected_life_days=15,
            notes="Автоматически начат по первой точке нового потока CGM.",
        )
        self.session.add(sensor)
        self.session.flush()
        if code is not None:
            code.sensor_session_id = sensor.id
            code.updated_at = utc_now()
        self.session.flush()
        return sensor

    def latest_glucose_timestamp(self) -> datetime | None:
        """Return this user's latest cached CGM instant."""
        return self.session.scalar(
            select(NightscoutGlucoseEntry.timestamp)
            .where(NightscoutGlucoseEntry.owner_id == self.user_id)
            .order_by(NightscoutGlucoseEntry.timestamp.desc())
            .limit(1)
        )

    def _current_stream_start(self, reading_at: datetime) -> datetime:
        """Walk backwards to the first CGM point before the latest long gap."""
        reading_utc = _as_utc(reading_at)
        timestamps = self.session.scalars(
            select(NightscoutGlucoseEntry.timestamp)
            .where(
                NightscoutGlucoseEntry.owner_id == self.user_id,
                NightscoutGlucoseEntry.timestamp <= reading_utc,
                NightscoutGlucoseEntry.timestamp >= reading_utc - CGM_STREAM_LOOKBACK,
            )
            .order_by(NightscoutGlucoseEntry.timestamp.desc())
        ).all()
        if not timestamps:
            return reading_utc

        stream_start = _as_utc(timestamps[0])
        newer = stream_start
        for raw_older in timestamps[1:]:
            older = _as_utc(raw_older)
            if newer - older > CGM_STREAM_GAP:
                break
            stream_start = older
            newer = older
        return stream_start

    def _detach_other_code(
        self,
        sensor_session_id: UUID,
        *,
        except_code_id: UUID | None,
    ) -> None:
        rows = self.session.scalars(
            select(SensorCode).where(
                SensorCode.owner_id == self.user_id,
                SensorCode.sensor_session_id == sensor_session_id,
            )
        ).all()
        for row in rows:
            if row.id != except_code_id:
                row.sensor_session_id = None
                row.updated_at = utc_now()


def _as_utc(value: datetime) -> datetime:
    """Preserve the CGM instant instead of reinterpreting local wall time."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
