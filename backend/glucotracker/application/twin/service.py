"""Application service for the digital twin API."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    TwinCurveAnchor,
    TwinCurveFoodEvent,
    TwinCurveInsulinEvent,
    TwinCurvePoint,
    TwinCurveResponse,
    TwinFitLogEntry,
    TwinParamsPatch,
    TwinParamsRead,
)
from glucotracker.application.twin.estimator import (
    BGAnchor,
    CarbEvent,
    EstimatorParams,
    InsulinEvent,
    estimate_curve,
)
from glucotracker.config import get_settings
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    FingerstickReading,
    Meal,
    NightscoutInsulinEvent,
    TwinParams,
    utc_now,
)
from glucotracker.infra.db.repositories.twin import TwinRepository

STALE_AFTER_DAYS = 30


class TwinService:
    """Coordinate digital twin params and curve rendering."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.repository = TwinRepository(session, user_id)

    def get_params(self) -> TwinParamsRead:
        """Return the current user's twin parameters."""
        row = self.repository.get_or_create_params()
        self.session.commit()
        self.session.refresh(row)
        return _params_read(row)

    def patch_params(self, payload: TwinParamsPatch) -> TwinParamsRead:
        """Apply a manual twin parameter override and append a history row."""
        row = self.repository.get_or_create_params()
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(row, field, value)
        _validate_slot_order(row)
        now = utc_now()
        row.updated_at = now
        row.last_fit_at = now
        row.last_fit_method = "manual"
        row.last_fit_converged = True
        self.repository.add_fit_log(
            params_snapshot=_params_snapshot(row),
            method="manual",
            converged=True,
            fit_at=now,
            notes="Ручное изменение параметров.",
        )
        self.session.commit()
        self.session.refresh(row)
        return _params_read(row)

    def reset_params(self) -> TwinParamsRead:
        """Reset fitted values to defaults without deleting history."""
        row = self.repository.get_or_create_params()
        row.icr_morning = None
        row.icr_day = None
        row.icr_evening = None
        row.morning_start_minutes = 360
        row.day_start_minutes = 660
        row.evening_start_minutes = 1080
        row.isf = None
        row.dia_minutes = 270
        row.carb_duration_minutes = 180
        row.baseline_drift_per_hour = 0.0
        row.last_fit_at = None
        row.last_fit_data_from = None
        row.last_fit_data_to = None
        row.last_fit_train_window_count = None
        row.last_fit_holdout_window_count = None
        row.last_fit_train_mae_mmol = None
        row.last_fit_holdout_mae_mmol = None
        row.last_fit_method = "reset"
        row.last_fit_converged = None
        row.updated_at = utc_now()
        self.repository.add_fit_log(
            params_snapshot=_params_snapshot(row),
            method="reset",
            converged=None,
            notes="Сброс параметров цифрового двойника.",
        )
        self.session.commit()
        self.session.refresh(row)
        return _params_read(row)

    def fit_history(self, limit: int = 20) -> list[TwinFitLogEntry]:
        """Return this user's newest fit/history rows."""
        rows = self.repository.list_fit_logs(limit)
        return [TwinFitLogEntry.model_validate(row) for row in rows]

    def curve(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        *,
        step_minutes: int = 5,
    ) -> TwinCurveResponse:
        """Return a display-only reconstruction/forecast curve."""
        local_from = _local_wall_time(from_datetime)
        local_to = _local_wall_time(to_datetime)
        row = self.repository.get_or_create_params(persist=False)
        params = _params_read(row)
        notes = [
            "Цифровой двойник является исследовательской моделью, а не CGM-измерением.",
        ]
        if local_to < local_from:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="to must be greater than or equal to from.",
            )

        anchors = self._anchors(local_from, local_to)
        visible_food = self._food_events(local_from, local_to)
        visible_insulin = self._insulin_events(local_from, local_to)
        if not params.is_fitted:
            notes.append("Параметры ещё не подогнаны.")
            return TwinCurveResponse(
                from_datetime=from_datetime,
                to_datetime=to_datetime,
                points=[],
                anchors=[_anchor_response(anchor) for anchor in anchors],
                food_events=visible_food,
                insulin_events=visible_insulin,
                params=params,
                notes=notes,
            )
        if not anchors:
            notes.append("Нет измерений из пальца для якорей двойника.")
            return TwinCurveResponse(
                from_datetime=from_datetime,
                to_datetime=to_datetime,
                points=[],
                anchors=[],
                food_events=visible_food,
                insulin_events=visible_insulin,
                params=params,
                notes=notes,
            )

        estimator_params = _estimator_params(row)
        lookback_from = min(
            anchors[0].timestamp,
            local_from - timedelta(
                minutes=max(row.dia_minutes, row.carb_duration_minutes)
            ),
        )
        curve_points = estimate_curve(
            bg_anchors=anchors,
            carbs=[
                CarbEvent(timestamp=event.timestamp, grams=event.carbs_g)
                for event in self._food_events(lookback_from, local_to)
            ],
            insulin=[
                InsulinEvent(timestamp=event.timestamp, units=event.insulin_units)
                for event in self._insulin_events(lookback_from, local_to)
            ],
            params=estimator_params,
            start=local_from,
            end=local_to,
            step_minutes=step_minutes,
        )
        return TwinCurveResponse(
            from_datetime=from_datetime,
            to_datetime=to_datetime,
            points=[
                TwinCurvePoint(
                    timestamp=point.timestamp,
                    mmol=point.mmol,
                    ci_low=point.ci_low,
                    ci_high=point.ci_high,
                    confidence=point.confidence,
                    mode=point.mode,
                )
                for point in curve_points
            ],
            anchors=[_anchor_response(anchor) for anchor in anchors],
            food_events=visible_food,
            insulin_events=visible_insulin,
            params=params,
            notes=notes,
        )

    def _anchors(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[BGAnchor]:
        prior = self.session.scalar(
            select(FingerstickReading)
            .where(
                FingerstickReading.owner_id == self.user_id,
                FingerstickReading.measured_at < from_datetime,
            )
            .order_by(FingerstickReading.measured_at.desc())
            .limit(1)
        )
        rows = list(
            self.session.scalars(
                select(FingerstickReading)
                .where(
                    FingerstickReading.owner_id == self.user_id,
                    FingerstickReading.measured_at >= from_datetime,
                    FingerstickReading.measured_at <= to_datetime,
                )
                .order_by(FingerstickReading.measured_at.asc())
            )
        )
        if prior is not None:
            rows.insert(0, prior)
        return [
            BGAnchor(
                timestamp=_local_wall_time(row.measured_at),
                mmol=row.glucose_mmol_l,
                source="fingerstick",
            )
            for row in rows
        ]

    def _food_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[TwinCurveFoodEvent]:
        rows = self.session.scalars(
            select(Meal)
            .where(
                Meal.owner_id == self.user_id,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= from_datetime,
                Meal.eaten_at <= to_datetime,
                Meal.total_carbs_g > 0,
            )
            .order_by(Meal.eaten_at.asc())
        ).all()
        return [
            TwinCurveFoodEvent(
                timestamp=row.eaten_at,
                title=row.title or "Приём пищи",
                carbs_g=row.total_carbs_g,
                kcal=row.total_kcal,
            )
            for row in rows
        ]

    def _insulin_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[TwinCurveInsulinEvent]:
        rows = self.session.scalars(
            select(NightscoutInsulinEvent)
            .where(
                NightscoutInsulinEvent.owner_id == self.user_id,
                NightscoutInsulinEvent.timestamp >= from_datetime,
                NightscoutInsulinEvent.timestamp <= to_datetime,
                NightscoutInsulinEvent.insulin_units.is_not(None),
            )
            .order_by(NightscoutInsulinEvent.timestamp.asc())
        ).all()
        return [
            TwinCurveInsulinEvent(
                timestamp=_local_wall_time(row.timestamp),
                insulin_units=float(row.insulin_units or 0),
                event_type=row.event_type,
                notes=row.notes,
            )
            for row in rows
            if row.insulin_units is not None and row.insulin_units > 0
        ]


def _params_read(row: TwinParams) -> TwinParamsRead:
    is_fitted = all(
        value is not None
        for value in [row.icr_morning, row.icr_day, row.icr_evening, row.isf]
    )
    hint: str
    if not is_fitted:
        hint = "not_fitted"
    elif row.last_fit_at and _as_utc(row.last_fit_at) < utc_now() - timedelta(
        days=STALE_AFTER_DAYS
    ):
        hint = "stale"
    else:
        hint = "ready"
    return TwinParamsRead(
        id=row.id,
        icr_morning=row.icr_morning,
        icr_day=row.icr_day,
        icr_evening=row.icr_evening,
        morning_start_minutes=row.morning_start_minutes,
        day_start_minutes=row.day_start_minutes,
        evening_start_minutes=row.evening_start_minutes,
        isf=row.isf,
        dia_minutes=row.dia_minutes,
        carb_duration_minutes=row.carb_duration_minutes,
        baseline_drift_per_hour=row.baseline_drift_per_hour,
        last_fit_at=row.last_fit_at,
        last_fit_data_from=row.last_fit_data_from,
        last_fit_data_to=row.last_fit_data_to,
        last_fit_train_window_count=row.last_fit_train_window_count,
        last_fit_holdout_window_count=row.last_fit_holdout_window_count,
        last_fit_train_mae_mmol=row.last_fit_train_mae_mmol,
        last_fit_holdout_mae_mmol=row.last_fit_holdout_mae_mmol,
        last_fit_method=row.last_fit_method,
        last_fit_converged=row.last_fit_converged,
        updated_at=row.updated_at,
        is_fitted=is_fitted,
        hint=hint,  # type: ignore[arg-type]
    )


def _params_snapshot(row: TwinParams) -> dict[str, object]:
    return {
        "icr_morning": row.icr_morning,
        "icr_day": row.icr_day,
        "icr_evening": row.icr_evening,
        "isf": row.isf,
        "baseline_drift_per_hour": row.baseline_drift_per_hour,
        "morning_start_minutes": row.morning_start_minutes,
        "day_start_minutes": row.day_start_minutes,
        "evening_start_minutes": row.evening_start_minutes,
        "dia_minutes": row.dia_minutes,
        "carb_duration_minutes": row.carb_duration_minutes,
    }


def _estimator_params(row: TwinParams) -> EstimatorParams:
    if (
        row.icr_morning is None
        or row.icr_day is None
        or row.icr_evening is None
        or row.isf is None
    ):
        raise ValueError("Twin params are not fitted.")
    return EstimatorParams(
        icr_morning=row.icr_morning,
        icr_day=row.icr_day,
        icr_evening=row.icr_evening,
        isf=row.isf,
        baseline_drift_per_hour=row.baseline_drift_per_hour,
        morning_start_minutes=row.morning_start_minutes,
        day_start_minutes=row.day_start_minutes,
        evening_start_minutes=row.evening_start_minutes,
        dia_minutes=row.dia_minutes,
        carb_duration_minutes=row.carb_duration_minutes,
    )


def _validate_slot_order(row: TwinParams) -> None:
    if not (
        row.morning_start_minutes < row.day_start_minutes < row.evening_start_minutes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "morning_start_minutes must be less than day_start_minutes and "
                "day_start_minutes must be less than evening_start_minutes"
            ),
        )


def _anchor_response(anchor: BGAnchor) -> TwinCurveAnchor:
    return TwinCurveAnchor(
        timestamp=anchor.timestamp,
        mmol=anchor.mmol,
        source=anchor.source,
    )


def _local_wall_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(get_settings().local_zoneinfo).replace(tzinfo=None)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value
