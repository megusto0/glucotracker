"""Display-only glucose dashboard and sensor quality services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    BiasCurvePoint,
    BiasOverLifetimeData,
    BiasPhaseMarker,
    BiasResidualPoint,
    CgmCalibrationModelResponse,
    FingerstickReadingCreate,
    FingerstickReadingPatch,
    FingerstickReadingResponse,
    GlucoseArtifactInterval,
    GlucoseDashboardFoodEvent,
    GlucoseDashboardInsulinEvent,
    GlucoseDashboardPoint,
    GlucoseDashboardResponse,
    GlucoseDashboardSummary,
    SensorQualityResponse,
    SensorSessionCreate,
    SensorSessionPatch,
    SensorSessionResponse,
    SensorWarmupMetricsResponse,
)
from glucotracker.config import get_settings
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    CgmCalibrationModel,
    FingerstickReading,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    SensorSession,
    utc_now,
)

GlucoseMode = Literal["raw", "smoothed", "normalized"]
Confidence = Literal["none", "low", "medium", "high"]
SensorPhase = Literal["warmup", "stable", "end_of_life"]
CalibrationStrategy = Literal["median_delta", "warmup_blend", "linear", "insufficient"]
CalibrationBasis = Literal[
    "stable_after_48h",
    "warmup_after_12h_fallback",
    "insufficient",
]

MODEL_VERSION = "pointwise_weighted_median_v2"
MAX_OFFSET = 3.0
MAX_DRIFT_PER_DAY = 0.5
INITIAL_WARMUP_HOURS = 2.0
EARLY_WARMUP_HOURS = 12.0
WARMUP_HOURS = 48.0
WARMUP_MEDIAN_WEIGHT = 0.65
WARMUP_LINEAR_WEIGHT = 0.35
STABLE_START_DAYS = WARMUP_HOURS / 24
FALLBACK_START_DAYS = EARLY_WARMUP_HOURS / 24
WARMUP_BIAS_BANDWIDTH_H = 9.0
STABLE_BIAS_BANDWIDTH_H = 36.0
END_OF_LIFE_BIAS_BANDWIDTH_H = 18.0
MIN_BIAS_CONTRIBUTORS = 1
MAX_BIAS_BANDWIDTH_H = 72.0


@dataclass(frozen=True)
class RawPoint:
    """One local raw CGM point."""

    timestamp: datetime
    value: float


@dataclass(frozen=True)
class CalibrationPoint:
    """A valid fingerstick/CGM comparison used for display calibration."""

    measured_at: datetime
    sensor_age_days: float
    raw_cgm: float
    fingerstick: float
    residual: float


@dataclass(frozen=True)
class CalibrationResult:
    """Computed display-only calibration model."""

    params: dict[str, Any]
    metrics: dict[str, Any]
    confidence: Confidence
    valid_points: list[CalibrationPoint]
    notes: list[str]

    @property
    def can_normalize(self) -> bool:
        """Return whether normalized display values can be produced."""
        return bool(self.params.get("can_normalize"))


class GlucoseDashboardService:
    """Coordinate glucose dashboard, fingerstick, and sensor APIs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_sensors(self) -> list[SensorSessionResponse]:
        """Return sensor sessions newest first."""
        rows = self.session.scalars(
            select(SensorSession).order_by(SensorSession.started_at.desc())
        ).all()
        return [SensorSessionResponse.model_validate(row) for row in rows]

    def create_sensor(self, payload: SensorSessionCreate) -> SensorSessionResponse:
        """Create a sensor session."""
        row = SensorSession(**payload.model_dump())
        row.started_at = _local_wall_time(row.started_at)
        if row.ended_at is not None:
            row.ended_at = _local_wall_time(row.ended_at)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return SensorSessionResponse.model_validate(row)

    def patch_sensor(
        self,
        sensor_id: UUID,
        payload: SensorSessionPatch,
    ) -> SensorSessionResponse:
        """Patch a sensor session."""
        row = self._sensor(sensor_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field in {"started_at", "ended_at"} and value is not None:
                value = _local_wall_time(value)
            setattr(row, field, value)
        row.updated_at = utc_now()
        self.session.commit()
        self.session.refresh(row)
        return SensorSessionResponse.model_validate(row)

    def list_fingersticks(
        self,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> list[FingerstickReadingResponse]:
        """Return fingerstick readings for a local time range."""
        filters = []
        if from_datetime is not None:
            filters.append(
                FingerstickReading.measured_at >= _local_wall_time(from_datetime)
            )
        if to_datetime is not None:
            filters.append(
                FingerstickReading.measured_at <= _local_wall_time(to_datetime)
            )
        rows = self.session.scalars(
            select(FingerstickReading)
            .where(*filters)
            .order_by(FingerstickReading.measured_at.asc())
        ).all()
        return [FingerstickReadingResponse.model_validate(row) for row in rows]

    def create_fingerstick(
        self,
        payload: FingerstickReadingCreate,
    ) -> FingerstickReadingResponse:
        """Create a manual capillary glucose reading."""
        row = FingerstickReading(**payload.model_dump())
        row.measured_at = _local_wall_time(row.measured_at)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return FingerstickReadingResponse.model_validate(row)

    def patch_fingerstick(
        self,
        fingerstick_id: UUID,
        payload: FingerstickReadingPatch,
    ) -> FingerstickReadingResponse:
        """Patch a manual capillary glucose reading."""
        row = self._fingerstick(fingerstick_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "measured_at" and value is not None:
                value = _local_wall_time(value)
            setattr(row, field, value)
        self.session.commit()
        self.session.refresh(row)
        return FingerstickReadingResponse.model_validate(row)

    def delete_fingerstick(self, fingerstick_id: UUID) -> None:
        """Delete a manual capillary glucose reading."""
        row = self._fingerstick(fingerstick_id)
        self.session.delete(row)
        self.session.commit()

    def sensor_quality(self, sensor_id: UUID) -> SensorQualityResponse:
        """Return computed quality metrics for one sensor."""
        sensor = self._sensor(sensor_id)
        raw_points = self._raw_points(sensor.started_at, sensor.ended_at or utc_now())
        fingersticks = self._fingerstick_rows(sensor.started_at, sensor.ended_at)
        result = self._calibration(sensor, raw_points, fingersticks)
        return self._quality(sensor, raw_points, fingersticks, result)

    def recalculate_calibration(self, sensor_id: UUID) -> CgmCalibrationModelResponse:
        """Compute and persist a new active display-only calibration model."""
        sensor = self._sensor(sensor_id)
        raw_points = self._raw_points(sensor.started_at, sensor.ended_at or utc_now())
        fingersticks = self._fingerstick_rows(sensor.started_at, sensor.ended_at)
        result = self._calibration(sensor, raw_points, fingersticks)
        for row in sensor.calibration_models:
            row.active = False
        model = CgmCalibrationModel(
            sensor_session_id=sensor.id,
            model_version=MODEL_VERSION,
            params_json=result.params,
            metrics_json=result.metrics,
            confidence=result.confidence,
            active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return CgmCalibrationModelResponse.model_validate(model)

    def dashboard(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        mode: GlucoseMode,
    ) -> GlucoseDashboardResponse:
        """Return a Nightscout-like dashboard with display-only derived series."""
        local_from = _local_wall_time(from_datetime)
        local_to = _local_wall_time(to_datetime)
        raw_points = self._raw_points(local_from, local_to)
        sensors = self._sensors_overlapping(local_from, local_to)
        current_sensor = sensors[0] if sensors else None
        fingerstick_rows = self._fingerstick_rows(local_from, local_to)
        quality = self._empty_quality(None)
        calibration: CalibrationResult | None = None
        notes: list[str] = []

        if current_sensor is not None:
            sensor_raw = self._raw_points(
                current_sensor.started_at,
                current_sensor.ended_at or local_to,
            )
            sensor_fingersticks = self._fingerstick_rows(
                current_sensor.started_at,
                current_sensor.ended_at,
            )
            calibration = self._calibration(
                current_sensor,
                sensor_raw,
                sensor_fingersticks,
            )
            quality = self._quality(
                current_sensor,
                sensor_raw,
                sensor_fingersticks,
                calibration,
            )
            notes.extend(calibration.notes)
        else:
            notes.append("Сенсор не указан для выбранного периода.")

        if mode == "normalized" and not (calibration and calibration.can_normalize):
            notes.append("Недостаточно записей из пальца для нормализации.")

        points = self._display_points(raw_points, calibration, mode)
        artifacts = _artifact_intervals(raw_points, current_sensor)
        summary = self._summary(points, quality)
        bias_data = None
        if current_sensor is not None and calibration is not None:
            bias_data = self._bias_over_lifetime(
                current_sensor, calibration, local_from, local_to,
            )

        return GlucoseDashboardResponse(
            from_datetime=from_datetime,
            to_datetime=to_datetime,
            mode=mode,
            points=points,
            fingersticks=[
                FingerstickReadingResponse.model_validate(row)
                for row in fingerstick_rows
            ],
            food_events=self._food_events(local_from, local_to),
            insulin_events=self._insulin_events(local_from, local_to),
            artifacts=artifacts,
            current_sensor=(
                SensorSessionResponse.model_validate(current_sensor)
                if current_sensor is not None
                else None
            ),
            sensors=[SensorSessionResponse.model_validate(row) for row in sensors],
            quality=quality,
            summary=summary,
            bias_over_lifetime=bias_data,
            notes=_unique(notes),
        )

    def _sensor(self, sensor_id: UUID) -> SensorSession:
        sensor = self.session.get(SensorSession, sensor_id)
        if sensor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor session not found.",
            )
        return sensor

    def _fingerstick(self, fingerstick_id: UUID) -> FingerstickReading:
        row = self.session.get(FingerstickReading, fingerstick_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fingerstick reading not found.",
            )
        return row

    def _raw_points(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[RawPoint]:
        rows = self.session.scalars(
            select(NightscoutGlucoseEntry)
            .where(
                NightscoutGlucoseEntry.timestamp >= _local_wall_time(from_datetime),
                NightscoutGlucoseEntry.timestamp <= _local_wall_time(to_datetime),
            )
            .order_by(NightscoutGlucoseEntry.timestamp.asc())
        ).all()
        return [
            RawPoint(_local_wall_time(row.timestamp), row.value_mmol_l)
            for row in rows
        ]

    def _fingerstick_rows(
        self,
        from_datetime: datetime,
        to_datetime: datetime | None,
    ) -> list[FingerstickReading]:
        filters = [FingerstickReading.measured_at >= _local_wall_time(from_datetime)]
        if to_datetime is not None:
            filters.append(
                FingerstickReading.measured_at <= _local_wall_time(to_datetime)
            )
        rows = self.session.scalars(
            select(FingerstickReading)
            .where(*filters)
            .order_by(FingerstickReading.measured_at.asc())
        ).all()
        return list(rows)

    def _sensors_overlapping(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[SensorSession]:
        return list(
            self.session.scalars(
                select(SensorSession)
                .where(
                    SensorSession.started_at <= to_datetime,
                    (SensorSession.ended_at.is_(None))
                    | (SensorSession.ended_at >= from_datetime),
                )
                .order_by(SensorSession.started_at.desc())
            )
        )

    def _food_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[GlucoseDashboardFoodEvent]:
        rows = self.session.scalars(
            select(Meal)
            .where(
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= from_datetime,
                Meal.eaten_at <= to_datetime,
            )
            .order_by(Meal.eaten_at.asc())
        ).all()
        return [
            GlucoseDashboardFoodEvent(
                timestamp=meal.eaten_at,
                title=meal.title or "Приём пищи",
                carbs_g=meal.total_carbs_g,
                kcal=meal.total_kcal,
            )
            for meal in rows
        ]

    def _insulin_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[GlucoseDashboardInsulinEvent]:
        rows = self.session.scalars(
            select(NightscoutInsulinEvent)
            .where(
                NightscoutInsulinEvent.timestamp >= from_datetime,
                NightscoutInsulinEvent.timestamp <= to_datetime,
            )
            .order_by(NightscoutInsulinEvent.timestamp.asc())
        ).all()
        return [
            GlucoseDashboardInsulinEvent(
                timestamp=row.timestamp,
                insulin_units=row.insulin_units,
                event_type=row.event_type,
                notes=row.notes,
            )
            for row in rows
        ]

    def _calibration(
        self,
        sensor: SensorSession,
        raw_points: list[RawPoint],
        fingersticks: list[FingerstickReading],
    ) -> CalibrationResult:
        matched = _valid_calibration_points(sensor, raw_points, fingersticks)
        warmup_metrics = _warmup_metrics(matched)
        valid, basis = _stable_calibration_points(matched)
        notes: list[str] = []
        if not valid:
            notes.append(
                "Недостаточно записей из пальца после 12 ч для оценки смещения."
            )
            return CalibrationResult(
                params={"can_normalize": False, "b0": 0, "b1": 0},
                metrics=_calibration_metrics(
                    valid,
                    fingersticks,
                    matched_points=matched,
                    calibration_basis=basis,
                    warmup_metrics=warmup_metrics,
                ),
                confidence="none",
                valid_points=valid,
                notes=notes,
            )

        if basis == "warmup_after_12h_fallback":
            notes.append(
                "Стабильных записей после 48 ч мало; оценка смещения построена "
                "по данным после 12 ч информационно."
            )

        residuals = [point.residual for point in valid]
        median_delta = _median(residuals)
        raw_b1 = _robust_slope(valid) if len(valid) >= 3 else 0.0
        b1 = max(min(raw_b1, MAX_DRIFT_PER_DAY), -MAX_DRIFT_PER_DAY)
        capped = False
        if b1 != raw_b1:
            notes.append("Дрейф слишком большой, коррекция ограничена.")
            capped = True
        b0 = _median([point.residual - b1 * point.sensor_age_days for point in valid])
        if abs(b0) > MAX_OFFSET:
            notes.append("Оценка смещения слишком большая, поправка ограничена.")
            b0 = max(min(b0, MAX_OFFSET), -MAX_OFFSET)
            capped = True

        current_age_days = _sensor_age_days(
            sensor,
            raw_points[-1].timestamp if raw_points else _now_local(),
        )
        current_phase = _sensor_phase(current_age_days)
        if len(valid) < 3:
            strategy: CalibrationStrategy = "median_delta"
            b1 = 0.0
            b0 = median_delta
            notes.append(
                "Меньше 3 валидных записей из пальца; используется медиана "
                "расхождения, без оценки дрейфа."
            )
        elif current_phase == "warmup":
            strategy = "warmup_blend"
            notes.append(
                "Сенсор в первые 48 ч; нормализация предварительная и сильнее "
                "опирается на медиану расхождений."
            )
        else:
            strategy = "linear"
        if abs(b0) > MAX_OFFSET:
            notes.append("Оценка смещения слишком большая, поправка ограничена.")
            b0 = max(min(b0, MAX_OFFSET), -MAX_OFFSET)
            capped = True

        fitted_residuals = [
            point.residual - _correction_for_age(
                {
                    "b0": b0,
                    "b1": b1,
                    "median_delta_mmol_l": median_delta,
                    "correction_strategy": strategy,
                },
                point.sensor_age_days,
            )
            for point in valid
        ]
        metrics = _calibration_metrics(
            valid,
            fingersticks,
            matched_points=matched,
            calibration_basis=basis,
            warmup_metrics=warmup_metrics,
        )
        metrics.update(
            {
                "b0_mmol_l": round(b0, 4),
                "b1_raw_mmol_l_per_day": round(raw_b1, 4),
                "b1_capped_mmol_l_per_day": round(b1, 4),
                "calibration_strategy": strategy,
                "correction_now_mmol_l": round(
                    _correction_for_age(
                        {
                            "b0": b0,
                            "b1": b1,
                            "median_delta_mmol_l": median_delta,
                            "correction_strategy": strategy,
                        },
                        current_age_days,
                    ),
                    4,
                ),
                "delta_max_mmol_l": max(residuals),
                "delta_min_mmol_l": min(residuals),
                "median_delta_mmol_l": median_delta,
                "model_residual_mad_mmol_l": _mad(fitted_residuals),
                "raw_residual_median_mmol_l": _median(residuals),
                "capped": capped,
            }
        )
        confidence: Confidence = "low"
        mard = metrics.get("mard_percent")
        if not capped and len(valid) >= 5 and (mard is None or mard <= 15):
            confidence = "high"
        elif not capped and len(valid) >= 3:
            confidence = "medium"
        if basis == "warmup_after_12h_fallback":
            confidence = "low"
        return CalibrationResult(
            params={
                "can_normalize": True,
                "b0": round(b0, 4),
                "b1": round(b1, 4),
                "b1_raw": round(raw_b1, 4),
                "b1_capped": round(b1, 4),
                "correction_strategy": strategy,
                "median_delta_mmol_l": round(median_delta, 4),
                "warmup_linear_weight": WARMUP_LINEAR_WEIGHT,
                "warmup_median_weight": WARMUP_MEDIAN_WEIGHT,
                "sensor_started_at": sensor.started_at.isoformat(),
                "max_offset_mmol_l": MAX_OFFSET,
                "max_drift_mmol_l_per_day": MAX_DRIFT_PER_DAY,
            },
            metrics=metrics,
            confidence=confidence,
            valid_points=valid,
            notes=notes,
        )

    def _quality(
        self,
        sensor: SensorSession,
        raw_points: list[RawPoint],
        fingersticks: list[FingerstickReading],
        calibration: CalibrationResult,
    ) -> SensorQualityResponse:
        metrics = calibration.metrics
        sensor_age_days = round(
            _sensor_age_days(sensor, sensor.ended_at or _now_local()),
            2,
        )
        warmup_metrics = metrics.get("warmup_metrics")
        compression_count = len(
            [
                interval
                for interval in _artifact_intervals(raw_points, sensor)
                if interval.kind == "compression_suspected"
            ]
        )
        missing_pct = _missing_data_pct(raw_points, sensor.started_at, sensor.ended_at)
        noise = _noise_score(raw_points)
        correction_now = _correction_now(sensor, raw_points, calibration)
        quality_score = _quality_score(
            mard=metrics.get("mard_percent"),
            residual_mad=metrics.get("model_residual_mad_mmol_l")
            or metrics.get("mad_mmol_l"),
            missing_pct=missing_pct,
            compression_count=compression_count,
            noise_score=noise,
            confidence=calibration.confidence,
        )
        return SensorQualityResponse(
            sensor=SensorSessionResponse.model_validate(sensor),
            sensor_age_days=sensor_age_days,
            sensor_phase=_sensor_phase(sensor_age_days),
            fingerstick_count=len(fingersticks),
            valid_calibration_points=len(calibration.valid_points),
            matched_calibration_points=metrics.get(
                "matched_calibration_points",
                len(calibration.valid_points),
            ),
            stable_calibration_points=metrics.get("stable_calibration_points", 0),
            warmup_calibration_points=metrics.get("warmup_calibration_points", 0),
            calibration_basis=metrics.get("calibration_basis"),
            warmup_metrics=(
                SensorWarmupMetricsResponse.model_validate(warmup_metrics)
                if warmup_metrics is not None
                else None
            ),
            median_bias_mmol_l=metrics.get("raw_residual_median_mmol_l"),
            median_delta_mmol_l=(
                metrics.get("median_delta_mmol_l")
                if metrics.get("median_delta_mmol_l") is not None
                else metrics.get("raw_residual_median_mmol_l")
            ),
            delta_min_mmol_l=metrics.get("delta_min_mmol_l"),
            delta_max_mmol_l=metrics.get("delta_max_mmol_l"),
            b0_mmol_l=calibration.params.get("b0"),
            b1_raw_mmol_l_per_day=calibration.params.get("b1_raw"),
            b1_capped_mmol_l_per_day=(
                calibration.params.get("b1_capped")
                if calibration.params.get("b1_capped") is not None
                else calibration.params.get("b1")
            ),
            correction_now_mmol_l=correction_now,
            calibration_strategy=calibration.params.get("correction_strategy"),
            mad_mmol_l=metrics.get("mad_mmol_l"),
            mard_percent=metrics.get("mard_percent"),
            drift_mmol_l_per_day=(
                calibration.params.get("b1_capped")
                if calibration.params.get("b1_capped") is not None
                else calibration.params.get("b1")
            ),
            residual_mad_mmol_l=metrics.get("model_residual_mad_mmol_l"),
            missing_data_pct=missing_pct,
            suspected_compression_count=compression_count,
            noise_score=noise,
            quality_score=quality_score,
            confidence=calibration.confidence,
            notes=calibration.notes,
            active_model=self._active_model(sensor),
        )

    def _empty_quality(
        self,
        sensor: SensorSession | None,
    ) -> SensorQualityResponse:
        return SensorQualityResponse(
            sensor=SensorSessionResponse.model_validate(sensor)
            if sensor is not None
            else None,
            sensor_age_days=None,
            sensor_phase=None,
            fingerstick_count=0,
            valid_calibration_points=0,
            matched_calibration_points=0,
            stable_calibration_points=0,
            warmup_calibration_points=0,
            calibration_basis="insufficient",
            warmup_metrics=None,
            suspected_compression_count=0,
            noise_score=0,
            quality_score=0,
            confidence="none",
            notes=[],
        )

    def _active_model(
        self,
        sensor: SensorSession,
    ) -> CgmCalibrationModelResponse | None:
        row = self.session.scalar(
            select(CgmCalibrationModel)
            .where(
                CgmCalibrationModel.sensor_session_id == sensor.id,
                CgmCalibrationModel.active.is_(True),
            )
            .order_by(CgmCalibrationModel.created_at.desc())
        )
        return CgmCalibrationModelResponse.model_validate(row) if row else None

    def _display_points(
        self,
        raw_points: list[RawPoint],
        calibration: CalibrationResult | None,
        mode: GlucoseMode,
    ) -> list[GlucoseDashboardPoint]:
        result: list[GlucoseDashboardPoint] = []
        normalized_values = _normalized_values(raw_points, calibration)
        bias_metadata = _bias_metadata_for_points(raw_points, calibration)
        smoothing_source = [
            value if value is not None else point.value
            for point, value in zip(raw_points, normalized_values, strict=False)
        ]
        smoothed = _smoothed_values(smoothing_source)
        for index, point in enumerate(raw_points):
            smoothed_value = smoothed[index] if index < len(smoothed) else point.value
            normalized = (
                normalized_values[index] if index < len(normalized_values) else None
            )
            correction = normalized - point.value if normalized is not None else None
            display = point.value
            if mode == "smoothed":
                display = smoothed_value
            elif mode == "normalized" and normalized is not None:
                display = normalized
            meta = bias_metadata[index] if index < len(bias_metadata) else {}
            result.append(
                GlucoseDashboardPoint(
                    timestamp=point.timestamp,
                    raw_value=point.value,
                    smoothed_value=round(smoothed_value, 2),
                    normalized_value=normalized,
                    display_value=round(display, 2),
                    correction_mmol_l=round(correction, 2)
                    if correction is not None
                    else None,
                    bias_confidence=meta.get("bias_confidence"),
                    nearest_fingerstick_distance_min=meta.get(
                        "nearest_fingerstick_distance_min",
                    ),
                    contributing_fingerstick_count=meta.get(
                        "contributing_fingerstick_count",
                    ),
                    flags=_flags_for_point(raw_points, index),
                )
            )
        return result

    def _summary(
        self,
        points: list[GlucoseDashboardPoint],
        quality: SensorQualityResponse,
    ) -> GlucoseDashboardSummary:
        current = points[-1] if points else None
        return GlucoseDashboardSummary(
            current_glucose=current.display_value if current else None,
            current_glucose_at=current.timestamp if current else None,
            sensor_age_days=quality.sensor_age_days,
            bias_mmol_l=(
                quality.correction_now_mmol_l
                if quality.correction_now_mmol_l is not None
                else quality.median_bias_mmol_l
            ),
            drift_mmol_l_per_day=quality.drift_mmol_l_per_day,
            calibration_confidence=quality.confidence,
            suspected_compression_count=quality.suspected_compression_count,
        )

    def _bias_over_lifetime(
        self,
        sensor: SensorSession,
        calibration: CalibrationResult,
        view_from: datetime,
        view_to: datetime,
    ) -> BiasOverLifetimeData | None:
        """Build bias-over-lifetime chart data for a sensor."""
        sensor_start = sensor.started_at
        sensor_end = _local_wall_time(sensor.ended_at or utc_now())
        sensor_raw = self._raw_points(sensor_start, sensor_end)
        sensor_fingersticks = self._fingerstick_rows(sensor_start, sensor.ended_at)
        matched = _valid_calibration_points(sensor, sensor_raw, sensor_fingersticks)

        all_fingersticks = self._fingerstick_rows(sensor_start, sensor.ended_at)

        residual_points: list[BiasResidualPoint] = []
        for row in all_fingersticks:
            measured_at = _local_wall_time(row.measured_at)
            age_h = (measured_at - sensor_start).total_seconds() / 3600
            match_result = _cgm_at(sensor_raw, measured_at)
            if match_result is None:
                residual_points.append(
                    BiasResidualPoint(
                        measured_at=measured_at,
                        sensor_age_hours=round(age_h, 1),
                        fingerstick_value=row.glucose_mmol_l,
                        raw_cgm_value=0,
                        residual=0,
                        included=False,
                        exclusion_reason="Нет CGM рядом по времени",
                    )
                )
                continue
            raw_val, max_dist = match_result
            residual = row.glucose_mmol_l - raw_val
            is_matched = any(
                p.measured_at == measured_at and abs(p.residual - residual) < 0.01
                for p in matched
            )
            reason = None
            if not is_matched:
                slope = _local_slope(sensor_raw, measured_at)
                if max_dist > 20:
                    reason = "CGM слишком далеко"
                elif slope is not None and abs(slope) > 0.08:
                    reason = "Глюкоза быстро меняется"
                else:
                    nearest_idx = _nearest_index(sensor_raw, measured_at)
                    if nearest_idx is not None:
                        flags = _flags_for_point(sensor_raw, nearest_idx)
                        if "compression_suspected" in flags:
                            reason = "Артефакт сдавления"
                        elif "jump_suspected" in flags:
                            reason = "Артефакт скачка"
                        else:
                            reason = "Интервал < 10 мин от другого замера"
            residual_points.append(
                BiasResidualPoint(
                    measured_at=measured_at,
                    sensor_age_hours=round(age_h, 1),
                    fingerstick_value=row.glucose_mmol_l,
                    raw_cgm_value=round(raw_val, 1),
                    residual=round(residual, 2),
                    included=is_matched,
                    exclusion_reason=reason,
                )
            )

        range_start = min(sensor_start, view_from)
        range_end = max(sensor_end, view_to)
        total_hours = max((range_end - range_start).total_seconds() / 3600, 1)
        step_hours = max(total_hours / 60, 0.5)
        bias_curve: list[BiasCurvePoint] = []
        t = sensor_start
        while t <= range_end:
            age_h = (t - sensor_start).total_seconds() / 3600
            bias_est = estimate_bias_at(t, matched, sensor_start)
            if bias_est is not None:
                bias_curve.append(
                    BiasCurvePoint(
                        timestamp=t,
                        sensor_age_hours=round(age_h, 1),
                        bias=bias_est.bias,
                        confidence=bias_est.confidence,
                        contributing_fingerstick_count=bias_est.contributing_count,
                        nearest_fingerstick_distance_min=(
                            round(bias_est.nearest_fingerstick_distance_h * 60, 1)
                            if bias_est.nearest_fingerstick_distance_h is not None
                            else None
                        ),
                    )
                )
            t += timedelta(hours=step_hours)

        phase_markers: list[BiasPhaseMarker] = [
            BiasPhaseMarker(sensor_age_hours=0, label="start"),
            BiasPhaseMarker(
                sensor_age_hours=WARMUP_HOURS,
                label=f"stable ({int(WARMUP_HOURS)}ч)",
            ),
        ]
        sensor_life_h = (sensor_end - sensor_start).total_seconds() / 3600
        if sensor_life_h >= 12 * 24:
            phase_markers.append(
                BiasPhaseMarker(
                    sensor_age_hours=12 * 24,
                    label="end_of_life (12д)",
                )
            )

        if not residual_points and not bias_curve:
            return None

        return BiasOverLifetimeData(
            sensor_started_at=sensor_start,
            residuals=residual_points,
            bias_curve=bias_curve,
            phase_markers=phase_markers,
        )


def _valid_calibration_points(
    sensor: SensorSession,
    raw_points: list[RawPoint],
    fingersticks: list[FingerstickReading],
) -> list[CalibrationPoint]:
    valid: list[CalibrationPoint] = []
    last_used: datetime | None = None
    for row in fingersticks:
        measured_at = _local_wall_time(row.measured_at)
        if last_used and measured_at - last_used < timedelta(minutes=10):
            continue
        match = _cgm_at(raw_points, measured_at)
        if match is None:
            continue
        raw_value, max_distance_min = match
        if max_distance_min > 20:
            continue
        slope = _local_slope(raw_points, measured_at)
        if slope is not None and abs(slope) > 0.08:
            continue
        nearest_index = _nearest_index(raw_points, measured_at)
        if nearest_index is not None:
            flags = _flags_for_point(raw_points, nearest_index)
            if "compression_suspected" in flags or "jump_suspected" in flags:
                continue
        valid.append(
            CalibrationPoint(
                measured_at=measured_at,
                sensor_age_days=_sensor_age_days(sensor, measured_at),
                raw_cgm=raw_value,
                fingerstick=row.glucose_mmol_l,
                residual=row.glucose_mmol_l - raw_value,
            )
        )
        last_used = measured_at
    return valid


def _stable_calibration_points(
    points: list[CalibrationPoint],
) -> tuple[list[CalibrationPoint], CalibrationBasis]:
    stable = [
        point for point in points if point.sensor_age_days >= STABLE_START_DAYS
    ]
    if stable:
        return stable, "stable_after_48h"

    fallback = [
        point for point in points if point.sensor_age_days >= FALLBACK_START_DAYS
    ]
    if fallback:
        return fallback, "warmup_after_12h_fallback"

    return [], "insufficient"


def _warmup_metrics(
    points: list[CalibrationPoint],
) -> dict[str, Any]:
    warmup_points = sorted(
        [point for point in points if point.sensor_age_days < STABLE_START_DAYS],
        key=lambda point: point.measured_at,
    )
    initial = [
        point.residual
        for point in warmup_points
        if _sensor_age_hours(point) <= INITIAL_WARMUP_HOURS
    ]
    first_12h_points = [
        point
        for point in warmup_points
        if _sensor_age_hours(point) <= EARLY_WARMUP_HOURS
    ]
    plateau = [
        point.residual
        for point in warmup_points
        if EARLY_WARMUP_HOURS <= _sensor_age_hours(point) < WARMUP_HOURS
    ]
    plateau_residual = _median(plateau) if plateau else None
    instability_score = _warmup_instability_score(first_12h_points, plateau_residual)

    return {
        "initial_residual_mmol_l": _round_optional(
            _median(initial) if initial else None
        ),
        "max_warmup_residual_mmol_l": _round_optional(
            max((abs(point.residual) for point in first_12h_points), default=None)
        ),
        "plateau_residual_mmol_l": _round_optional(plateau_residual),
        "time_to_stabilize_hours": _round_optional(
            _time_to_stabilize_hours(warmup_points, plateau_residual),
            digits=1,
        ),
        "warmup_instability_score": _round_optional(instability_score),
        "residual_sequence_mmol_l": _warmup_residual_sequence(first_12h_points),
    }


def _sensor_age_hours(point: CalibrationPoint) -> float:
    return point.sensor_age_days * 24


def _warmup_instability_score(
    first_12h_points: list[CalibrationPoint],
    plateau_residual: float | None,
) -> float | None:
    if not first_12h_points:
        return None
    if plateau_residual is not None:
        return max(abs(point.residual - plateau_residual) for point in first_12h_points)

    residuals = [point.residual for point in first_12h_points]
    center = _median(residuals)
    return max(abs(residual - center) for residual in residuals)


def _time_to_stabilize_hours(
    warmup_points: list[CalibrationPoint],
    plateau_residual: float | None,
) -> float | None:
    if plateau_residual is None:
        return None
    for point in warmup_points:
        if abs(point.residual - plateau_residual) > 0.8:
            continue
        window_end = point.measured_at + timedelta(hours=3)
        window = [
            candidate
            for candidate in warmup_points
            if point.measured_at <= candidate.measured_at <= window_end
        ]
        if len(window) < 2:
            continue
        span_hours = (window[-1].measured_at - point.measured_at).total_seconds() / 3600
        if span_hours < 3:
            continue
        if all(
            abs(candidate.residual - plateau_residual) <= 0.8
            for candidate in window
        ):
            return _sensor_age_hours(point)
    return None


def _warmup_residual_sequence(points: list[CalibrationPoint]) -> list[float]:
    if not points:
        return []
    if len(points) <= 3:
        return [round(point.residual, 1) for point in points]

    first = points[0]
    peak = max(points, key=lambda point: abs(point.residual))
    last = points[-1]
    sequence: list[CalibrationPoint] = []
    for point in [first, peak, last]:
        if point not in sequence:
            sequence.append(point)
    sequence.sort(key=lambda point: point.measured_at)
    return [round(point.residual, 1) for point in sequence]


def _cgm_at(points: list[RawPoint], target: datetime) -> tuple[float, float] | None:
    if not points:
        return None
    before = [point for point in points if point.timestamp <= target]
    after = [point for point in points if point.timestamp >= target]
    previous = before[-1] if before else None
    next_point = after[0] if after else None
    candidates = [point for point in [previous, next_point] if point is not None]
    if not candidates:
        return None
    max_distance = max(
        abs((point.timestamp - target).total_seconds()) / 60 for point in candidates
    )
    if previous and next_point and previous.timestamp != next_point.timestamp:
        gap = (next_point.timestamp - previous.timestamp).total_seconds() / 60
        if gap > 40:
            return None
        ratio = (target - previous.timestamp).total_seconds() / (
            next_point.timestamp - previous.timestamp
        ).total_seconds()
        value = previous.value + (next_point.value - previous.value) * ratio
        return value, max_distance
    nearest = min(candidates, key=lambda point: abs(point.timestamp - target))
    return nearest.value, max_distance


def _local_slope(points: list[RawPoint], target: datetime) -> float | None:
    before = [
        point
        for point in points
        if target - timedelta(minutes=20) <= point.timestamp <= target
    ]
    after = [
        point
        for point in points
        if target <= point.timestamp <= target + timedelta(minutes=20)
    ]
    if not before or not after:
        return None
    left = before[0]
    right = after[-1]
    minutes = (right.timestamp - left.timestamp).total_seconds() / 60
    if minutes <= 0:
        return None
    return (right.value - left.value) / minutes


@dataclass(frozen=True)
class BiasEstimate:
    """Time-local bias estimate for one CGM point."""

    bias: float
    confidence: Confidence
    nearest_fingerstick_distance_h: float | None
    contributing_count: int


def _bandwidth_for_phase(sensor_age_days: float) -> float:
    """Return bandwidth in hours for the sensor phase."""
    if sensor_age_days < STABLE_START_DAYS:
        return WARMUP_BIAS_BANDWIDTH_H
    if sensor_age_days >= 12:
        return END_OF_LIFE_BIAS_BANDWIDTH_H
    return STABLE_BIAS_BANDWIDTH_H


def estimate_bias_at(
    target: datetime,
    calibration_points: list[CalibrationPoint],
    sensor_start: datetime,
) -> BiasEstimate | None:
    """Estimate time-local CGM bias at a specific timestamp.

    Uses weighted median of nearby fingerstick residuals, with bandwidth
    depending on sensor phase. Returns None when no valid residuals exist
    within range.
    """
    if not calibration_points:
        return None

    target_age_days = max((target - sensor_start).total_seconds(), 0) / 86400
    bandwidth_h = _bandwidth_for_phase(target_age_days)
    bandwidth_s = bandwidth_h * 3600

    weighted: list[tuple[float, float]] = []
    nearest_distance_h: float | None = None
    for point in calibration_points:
        distance_s = abs((point.measured_at - target).total_seconds())
        distance_h = distance_s / 3600
        if nearest_distance_h is None or distance_h < nearest_distance_h:
            nearest_distance_h = distance_h
        if distance_s > bandwidth_s:
            continue
        weight = 1.0 - (distance_s / bandwidth_s)
        weight = weight * weight
        weighted.append((point.residual, weight))

    if not weighted:
        expanded_s = MAX_BIAS_BANDWIDTH_H * 3600
        for point in calibration_points:
            distance_s = abs((point.measured_at - target).total_seconds())
            if distance_s > expanded_s:
                continue
            distance_h = distance_s / 3600
            if nearest_distance_h is None or distance_h < nearest_distance_h:
                nearest_distance_h = distance_h
            weight = 1.0 - (distance_s / expanded_s)
            weight = weight * weight
            weighted.append((point.residual, weight))

    if not weighted:
        return None

    bias = _weighted_median(weighted)
    bias = max(min(bias, MAX_OFFSET), -MAX_OFFSET)

    count = len(weighted)
    if count >= 4 and (nearest_distance_h or 999) <= bandwidth_h * 0.5:
        confidence: Confidence = "high"
    elif count >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    if target_age_days < STABLE_START_DAYS and count < 2:
        confidence = "low"

    return BiasEstimate(
        bias=round(bias, 4),
        confidence=confidence,
        nearest_fingerstick_distance_h=(
            round(nearest_distance_h, 1) if nearest_distance_h is not None else None
        ),
        contributing_count=count,
    )


def _weighted_median(pairs: list[tuple[float, float]]) -> float:
    """Compute weighted median from (value, weight) pairs."""
    if not pairs:
        return 0.0
    sorted_pairs = sorted(pairs, key=lambda p: p[0])
    total = sum(w for _, w in sorted_pairs)
    if total <= 0:
        return _median([v for v, _ in sorted_pairs])
    cumulative = 0.0
    for value, weight in sorted_pairs:
        cumulative += weight
        if cumulative >= total / 2:
            return value
    return sorted_pairs[-1][0]


def _normalized_values(
    points: list[RawPoint],
    calibration: CalibrationResult | None,
) -> list[float | None]:
    if not calibration or not calibration.can_normalize:
        return [None for _ in points]
    sensor_age = calibration.params.get("sensor_started_at")
    sensor_start = (
        _local_wall_time(datetime.fromisoformat(sensor_age))
        if isinstance(sensor_age, str)
        else None
    )
    if sensor_start is None:
        return [None for _ in points]
    cal_points = calibration.valid_points
    values: list[float | None] = []
    for point in points:
        bias_est = estimate_bias_at(point.timestamp, cal_points, sensor_start)
        if bias_est is not None:
            values.append(round(point.value + bias_est.bias, 2))
        else:
            age_days = max((point.timestamp - sensor_start).total_seconds(), 0) / 86400
            correction = _correction_for_age(calibration.params, age_days)
            values.append(round(point.value + correction, 2))
    return values


def _bias_metadata_for_points(
    points: list[RawPoint],
    calibration: CalibrationResult | None,
) -> list[dict[str, Any]]:
    """Return per-point bias metadata for the dashboard response."""
    if not calibration or not calibration.can_normalize:
        return [{} for _ in points]
    sensor_age = calibration.params.get("sensor_started_at")
    sensor_start = (
        _local_wall_time(datetime.fromisoformat(sensor_age))
        if isinstance(sensor_age, str)
        else None
    )
    if sensor_start is None:
        return [{} for _ in points]
    cal_points = calibration.valid_points
    metadata: list[dict[str, Any]] = []
    for point in points:
        bias_est = estimate_bias_at(point.timestamp, cal_points, sensor_start)
        if bias_est is not None:
            metadata.append({
                "bias_confidence": bias_est.confidence,
                "nearest_fingerstick_distance_min": (
                    round(bias_est.nearest_fingerstick_distance_h * 60, 1)
                    if bias_est.nearest_fingerstick_distance_h is not None
                    else None
                ),
                "contributing_fingerstick_count": bias_est.contributing_count,
            })
        else:
            metadata.append({
                "bias_confidence": "none",
                "nearest_fingerstick_distance_min": None,
                "contributing_fingerstick_count": 0,
            })
    return metadata


def _correction_now(
    sensor: SensorSession,
    raw_points: list[RawPoint],
    calibration: CalibrationResult,
) -> float | None:
    if not calibration.can_normalize:
        return None
    at = raw_points[-1].timestamp if raw_points else sensor.ended_at or _now_local()
    age_days = _sensor_age_days(sensor, at)
    return round(_correction_for_age(calibration.params, age_days), 2)


def _correction_for_age(params: dict[str, Any], sensor_age_days: float) -> float:
    strategy = params.get("correction_strategy", "linear")
    median_delta_value = params.get("median_delta_mmol_l")
    if median_delta_value is None:
        median_delta_value = params.get("b0", 0.0)
    median_delta = float(median_delta_value)
    b0 = float(params.get("b0", median_delta))
    b1 = float(params.get("b1_capped", params.get("b1", 0.0)))
    linear = b0 + b1 * sensor_age_days
    if strategy == "median_delta":
        return median_delta
    if strategy == "warmup_blend":
        median_weight = float(params.get("warmup_median_weight", WARMUP_MEDIAN_WEIGHT))
        linear_weight = float(params.get("warmup_linear_weight", WARMUP_LINEAR_WEIGHT))
        return median_weight * median_delta + linear_weight * linear
    return linear


def _smoothed_values(values: list[float]) -> list[float]:
    if len(values) < 3:
        return values
    filtered: list[float] = []
    for index, value in enumerate(values):
        window_values = values[max(index - 2, 0) : min(index + 3, len(values))]
        local_median = _median(window_values)
        local_mad = _mad([value - local_median for value in window_values]) or 0.1
        if abs(value - local_median) > max(2.0, 4 * local_mad):
            filtered.append(local_median)
        else:
            filtered.append(value)

    smoothed = [filtered[0]]
    for value in filtered[1:]:
        smoothed.append(smoothed[-1] * 0.65 + value * 0.35)
    return smoothed


def _artifact_intervals(
    points: list[RawPoint],
    sensor: SensorSession | None,
) -> list[GlucoseArtifactInterval]:
    intervals: list[GlucoseArtifactInterval] = []
    for index, point in enumerate(points):
        flags = _flags_for_point(points, index)
        for flag in flags:
            if flag not in {
                "compression_suspected",
                "jump_suspected",
                "gap",
                "end_of_life_noise",
            }:
                continue
            intervals.append(
                GlucoseArtifactInterval(
                    start_at=point.timestamp - timedelta(minutes=5),
                    end_at=point.timestamp + timedelta(minutes=5),
                    kind=flag,  # type: ignore[arg-type]
                    label=_artifact_label(flag),
                )
            )
    if (
        sensor is not None
        and _sensor_age_days(sensor, sensor.ended_at or _now_local()) >= 12
    ):
        intervals.append(
            GlucoseArtifactInterval(
                start_at=max(sensor.started_at, points[0].timestamp)
                if points
                else sensor.started_at,
                end_at=(
                    points[-1].timestamp
                    if points
                    else sensor.ended_at or _now_local()
                ),
                kind="end_of_life_noise",
                label="Конец срока сенсора: данные требуют осторожности",
            )
        )
    return intervals


def _flags_for_point(points: list[RawPoint], index: int) -> list[str]:
    flags: list[str] = []
    point = points[index]
    previous = points[index - 1] if index > 0 else None
    next_point = points[index + 1] if index < len(points) - 1 else None
    if previous:
        gap = (point.timestamp - previous.timestamp).total_seconds() / 60
        if gap > 20:
            flags.append("gap")
        if abs(point.value - previous.value) >= 4.0:
            flags.append("jump_suspected")
    if previous and next_point:
        recovery_min = (next_point.timestamp - point.timestamp).total_seconds() / 60
        drop = previous.value - point.value
        recovery = next_point.value - point.value
        if point.value < 4.0 and drop >= 1.2 and recovery >= 1.2 and recovery_min <= 60:
            flags.append("compression_suspected")
    return _unique(flags)


def _artifact_label(flag: str) -> str:
    return {
        "compression_suspected": "Вероятный артефакт сдавления",
        "jump_suspected": "Вероятный резкий скачок сенсора",
        "gap": "Разрыв в данных CGM",
        "low_confidence_calibration": "Низкая уверенность нормализации",
        "end_of_life_noise": "Вероятный шум к концу срока сенсора",
    }.get(flag, flag)


def _calibration_metrics(
    valid: list[CalibrationPoint],
    fingersticks: list[FingerstickReading],
    *,
    matched_points: list[CalibrationPoint],
    calibration_basis: CalibrationBasis,
    warmup_metrics: dict[str, Any],
) -> dict[str, Any]:
    residuals = [point.residual for point in valid]
    absolute = [abs(value) for value in residuals]
    mard_values = [
        abs(point.residual) / point.fingerstick * 100
        for point in valid
        if point.fingerstick > 0
    ]
    return {
        "fingerstick_count": len(fingersticks),
        "valid_calibration_points": len(valid),
        "matched_calibration_points": len(matched_points),
        "stable_calibration_points": len(
            [
                point
                for point in matched_points
                if point.sensor_age_days >= STABLE_START_DAYS
            ]
        ),
        "warmup_calibration_points": len(
            [
                point
                for point in matched_points
                if point.sensor_age_days < STABLE_START_DAYS
            ]
        ),
        "calibration_basis": calibration_basis,
        "warmup_metrics": warmup_metrics,
        "mad_mmol_l": _median(absolute) if absolute else None,
        "mard_percent": _median(mard_values) if mard_values else None,
        "raw_residual_median_mmol_l": _median(residuals) if residuals else None,
    }


def _robust_slope(points: list[CalibrationPoint]) -> float:
    slopes: list[float] = []
    for left_index, left in enumerate(points):
        for right in points[left_index + 1 :]:
            delta = right.sensor_age_days - left.sensor_age_days
            if abs(delta) < 0.05:
                continue
            slopes.append((right.residual - left.residual) / delta)
    return _median(slopes) if slopes else 0.0


def _missing_data_pct(
    points: list[RawPoint],
    from_datetime: datetime,
    to_datetime: datetime | None,
) -> float | None:
    end = to_datetime or _now_local()
    minutes = max((end - from_datetime).total_seconds() / 60, 1)
    expected = minutes / 5
    if expected <= 0:
        return None
    return round(max(0, 100 - min(100, (len(points) / expected) * 100)), 1)


def _noise_score(points: list[RawPoint]) -> float:
    if len(points) < 3:
        return 0.0
    diffs = [
        abs(points[index].value - points[index - 1].value)
        for index in range(1, len(points))
    ]
    return round(min(100, (_median(diffs) or 0) * 18), 1)


def _quality_score(
    *,
    mard: float | None,
    residual_mad: float | None,
    missing_pct: float | None,
    compression_count: int,
    noise_score: float,
    confidence: Confidence,
) -> int:
    if confidence == "none":
        return 0
    score = 100.0
    if mard is not None:
        score -= mard * 1.5
    if residual_mad is not None:
        score -= residual_mad * 8
    if missing_pct is not None:
        score -= missing_pct * 0.25
    score -= compression_count * 3
    score -= noise_score * 0.35
    return int(max(0, min(100, round(score))))


def _sensor_age_days(sensor: SensorSession, at: datetime) -> float:
    age_seconds = (
        _local_wall_time(at) - _local_wall_time(sensor.started_at)
    ).total_seconds()
    return max(age_seconds, 0) / 86400


def _sensor_phase(sensor_age_days: float | None) -> SensorPhase | None:
    if sensor_age_days is None:
        return None
    if sensor_age_days < STABLE_START_DAYS:
        return "warmup"
    if sensor_age_days >= 12:
        return "end_of_life"
    return "stable"


def _nearest_index(points: list[RawPoint], target: datetime) -> int | None:
    if not points:
        return None
    return min(
        range(len(points)),
        key=lambda index: abs(points[index].timestamp - target),
    )


def _median(values: list[float]) -> float:
    return float(median(values)) if values else 0.0


def _mad(values: list[float]) -> float | None:
    if not values:
        return None
    center = _median(values)
    return _median([abs(value - center) for value in values])


def _round_optional(value: float | None, *, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _now_local() -> datetime:
    return datetime.now(get_settings().local_zoneinfo).replace(tzinfo=None)


def _local_wall_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(get_settings().local_zoneinfo).replace(tzinfo=None)
