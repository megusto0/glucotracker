"""Calibrated CGM series shared by every model that learns from glucose.

Raw CGM carries a per-sensor bias of one to several mmol/L. The dashboard already
corrects it for display, but each fitter used to read the raw column directly, so
absolute-level thresholds (hypo/hyper bands, target distances) were evaluated on a
scale that does not match what the user — or the insulin math — sees.

This module exposes one owner-scoped series in the normalized space, calibrated
**per sensor session** rather than by whichever sensor happens to be newest, and
annotated with the local bias confidence so callers can down-weight windows where
normalization is guesswork.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.glucose_dashboard import (
    Confidence,
    GlucoseDashboardService,
    RawPoint,
    _correction_for_age,
    _local_wall_from_utc,
    _local_wall_time,
    estimate_bias_at,
)
from glucotracker.application.glucose_visibility import visible_glucose_filter
from glucotracker.infra.db.models import NightscoutGlucoseEntry, SensorSession

# Bias confidence ranked so callers can compare against a minimum requirement.
BIAS_CONFIDENCE_ORDER: dict[Confidence, int] = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


@dataclass(frozen=True)
class NormalizedGlucoseSample:
    """One CGM reading with its calibrated value and calibration provenance."""

    timestamp: datetime
    raw_mmol_l: float
    normalized_mmol_l: float
    bias_mmol_l: float
    bias_confidence: Confidence
    sensor_session_id: UUID | None
    sensor_age_days: float | None

    @property
    def is_normalized(self) -> bool:
        """Return whether a real calibration produced this value."""
        return self.bias_confidence != "none"


class GlucoseNormalizationService:
    """Build the calibrated CGM series used for training and evaluation."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def series(
        self,
        from_at: datetime,
        to_at: datetime,
    ) -> list[NormalizedGlucoseSample]:
        """Return calibrated samples for a UTC range, oldest first.

        Every sensor session overlapping the range is calibrated on its own
        fingersticks; a reading outside any known session keeps its raw value
        and reports ``none`` confidence rather than borrowing another sensor's
        bias.
        """
        rows = self.session.scalars(
            select(NightscoutGlucoseEntry)
            .where(
                NightscoutGlucoseEntry.owner_id == self.user_id,
                NightscoutGlucoseEntry.timestamp >= _as_utc(from_at),
                NightscoutGlucoseEntry.timestamp <= _as_utc(to_at),
                visible_glucose_filter(self.user_id),
            )
            .order_by(NightscoutGlucoseEntry.timestamp.asc())
        ).all()
        deduped: dict[datetime, float] = {}
        for row in rows:
            deduped[_as_utc(row.timestamp)] = float(row.value_mmol_l)
        if not deduped:
            return []

        ordered = sorted(deduped.items())
        sensors = self._sensors_covering(ordered[0][0], ordered[-1][0])
        calibrations = {
            sensor.id: self._calibration_for(sensor) for sensor in sensors
        }
        starts = [_local_wall_time(sensor.started_at) for sensor in sensors]

        samples: list[NormalizedGlucoseSample] = []
        for timestamp, raw_value in ordered:
            local = _local_wall_from_utc(timestamp)
            sensor = _sensor_at(sensors, starts, local)
            bias = 0.0
            confidence: Confidence = "none"
            age_days: float | None = None
            if sensor is not None:
                sensor_start = _local_wall_time(sensor.started_at)
                age_days = max((local - sensor_start).total_seconds(), 0.0) / 86400
                calibration = calibrations.get(sensor.id)
                if calibration is not None and calibration.can_normalize:
                    estimate = estimate_bias_at(
                        local,
                        calibration.valid_points,
                        sensor_start,
                    )
                    if estimate is not None:
                        bias = estimate.bias
                        confidence = estimate.confidence
                    else:
                        bias = _correction_for_age(calibration.params, age_days)
                        confidence = "low"
            samples.append(
                NormalizedGlucoseSample(
                    timestamp=timestamp,
                    raw_mmol_l=raw_value,
                    normalized_mmol_l=round(raw_value + bias, 3),
                    bias_mmol_l=round(bias, 4),
                    bias_confidence=confidence,
                    sensor_session_id=sensor.id if sensor is not None else None,
                    sensor_age_days=age_days,
                )
            )
        return samples

    def _sensors_covering(
        self,
        from_at: datetime,
        to_at: datetime,
    ) -> list[SensorSession]:
        """Return sessions overlapping the range, oldest first."""
        local_from = _local_wall_from_utc(from_at)
        local_to = _local_wall_from_utc(to_at)
        rows = self.session.scalars(
            select(SensorSession)
            .where(
                SensorSession.owner_id == self.user_id,
                SensorSession.started_at <= local_to,
                (SensorSession.ended_at.is_(None))
                | (SensorSession.ended_at >= local_from),
            )
            .order_by(SensorSession.started_at.asc())
        ).all()
        return list(rows)

    def _calibration_for(self, sensor: SensorSession):
        """Calibrate one sensor session on its own fingersticks."""
        dashboard = GlucoseDashboardService(self.session, self.user_id)
        sensor_raw = dashboard._raw_points(
            sensor.started_at,
            sensor.ended_at or _local_wall_time(datetime.now(UTC)),
        )
        fingersticks = dashboard._fingerstick_rows(
            sensor.started_at,
            sensor.ended_at,
        )
        return dashboard._calibration(sensor, sensor_raw, fingersticks)


def normalized_raw_points(
    samples: list[NormalizedGlucoseSample],
) -> list[RawPoint]:
    """Adapt calibrated samples to the dashboard's local-wall point shape."""
    return [
        RawPoint(_local_wall_from_utc(sample.timestamp), sample.normalized_mmol_l)
        for sample in samples
    ]


def _sensor_at(
    sensors: list[SensorSession],
    starts: list[datetime],
    local: datetime,
) -> SensorSession | None:
    """Return the session containing a local wall timestamp, if any."""
    index = bisect_right(starts, local) - 1
    if index < 0:
        return None
    sensor = sensors[index]
    ended_at = sensor.ended_at
    if ended_at is not None and _local_wall_time(ended_at) < local:
        return None
    return sensor


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
