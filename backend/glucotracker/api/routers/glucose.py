"""Glucose dashboard, sensor, and fingerstick endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
from glucotracker.api.schemas import (
    CgmCalibrationModelResponse,
    DayEpisodeInsulinResponse,
    DayEpisodeResponse,
    DayEpisodesResponse,
    FingerstickReadingCreate,
    FingerstickReadingPatch,
    FingerstickReadingResponse,
    GlucoseDashboardResponse,
    GlucosePredictionResponse,
    GlucoseTirDailyResponse,
    GlucoseTirDayResponse,
    SensorQualityResponse,
    SensorSessionCreate,
    SensorSessionPatch,
    SensorSessionResponse,
)
from glucotracker.application.episodes import (
    EpisodeQueryService,
    anchor_meal_id,
)
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.glucose_prediction import GlucosePredictionService
from glucotracker.application.glucose_prediction_audit import (
    GlucosePredictionAuditService,
)
from glucotracker.application.stats_insights import (
    InsightPeriod,
    generate_glucose_tir_daily,
)

router = APIRouter(
    tags=["glucose"],
    dependencies=[Depends(require_feature("glucose"))],
)


@router.get(
    "/glucose/dashboard",
    response_model=GlucoseDashboardResponse,
    operation_id="getGlucoseDashboard",
)
async def get_glucose_dashboard(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
    mode: Literal["raw", "smoothed", "normalized"] = "raw",
) -> GlucoseDashboardResponse:
    """Return display-only glucose dashboard data from the local cache."""
    return GlucoseDashboardService(session, current_user.id).dashboard(
        from_datetime,
        to_datetime,
        mode,
    )


@router.get(
    "/glucose/prediction",
    response_model=GlucosePredictionResponse,
    operation_id="getGlucosePrediction",
)
def get_glucose_prediction(
    session: SessionDep,
    current_user: CurrentUserDep,
    mode: Literal["raw", "normalized"] = "normalized",
    horizon_minutes: Annotated[int, Query(ge=5, le=90)] = 90,
    step_minutes: Annotated[int, Query(ge=5, le=30)] = 5,
) -> GlucosePredictionResponse:
    """Return a validated personal forecast for informational display only."""
    prediction = GlucosePredictionService(session, current_user.id).predict(
        mode=mode,
        horizon_minutes=horizon_minutes,
        step_minutes=step_minutes,
    )
    GlucosePredictionAuditService(session, current_user.id).record(prediction)
    session.commit()
    return prediction


@router.get(
    "/glucose/episodes",
    response_model=DayEpisodesResponse,
    operation_id="getGlucoseEpisodes",
)
def get_glucose_episodes(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> DayEpisodesResponse:
    """Return grouped meal/insulin episodes for the range (attribution only)."""
    components = EpisodeQueryService(session, current_user.id).components(
        from_datetime,
        to_datetime,
    )
    episodes: list[DayEpisodeResponse] = []
    for component in components:
        # Raw UTC timestamps, same as /nightscout/insulin — clients convert.
        insulin = [
            DayEpisodeInsulinResponse(
                id=event.id,
                timestamp=event.timestamp,
                insulin_units=event.insulin_units,
                kind="food" if component.meals else "correction",
                anchor_meal_id=anchor_meal_id(event, component),
                editable=(
                    event.source_key.startswith("manual_insulin:")
                    and event.entered_by == "glucotracker"
                    and bool(event.nightscout_id)
                ),
            )
            for event in component.insulin
        ]
        kind = (
            "food"
            if component.meals and component.insulin
            else "food_only"
            if component.meals
            else "correction"
        )
        episodes.append(
            DayEpisodeResponse(
                key="|".join(
                    sorted(
                        [f"m:{meal.id}" for meal in component.meals]
                        + [f"i:{event.id}" for event in component.insulin]
                    )
                ),
                kind=kind,
                start_at=component.start_at,
                end_at=component.end_at,
                meal_ids=[meal.id for meal in component.meals],
                insulin=insulin,
                total_carbs_g=round(
                    sum(meal.total_carbs_g for meal in component.meals), 1
                ),
                total_kcal=round(sum(meal.total_kcal for meal in component.meals), 1),
                total_insulin_units=round(
                    sum(event.insulin_units or 0 for event in component.insulin), 2
                ),
            )
        )
    return DayEpisodesResponse(
        from_datetime=from_datetime,
        to_datetime=to_datetime,
        episodes=episodes,
    )


@router.get(
    "/glucose/tir-daily",
    response_model=GlucoseTirDailyResponse,
    operation_id="getGlucoseTirDaily",
)
def get_glucose_tir_daily(
    session: SessionDep,
    current_user: CurrentUserDep,
    period: InsightPeriod = "30d",
) -> GlucoseTirDailyResponse:
    """Return per-day TIR band shares for the period (descriptive only)."""
    return GlucoseTirDailyResponse(
        period=period,
        days=[
            GlucoseTirDayResponse.model_validate(day, from_attributes=True)
            for day in generate_glucose_tir_daily(session, current_user.id, period)
        ],
    )


@router.post(
    "/fingersticks",
    response_model=FingerstickReadingResponse,
    status_code=201,
    operation_id="createFingerstick",
)
def create_fingerstick(
    payload: FingerstickReadingCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> FingerstickReadingResponse:
    """Create a manual capillary glucose reading."""
    return GlucoseDashboardService(session, current_user.id).create_fingerstick(payload)


@router.get(
    "/fingersticks",
    response_model=list[FingerstickReadingResponse],
    operation_id="listFingersticks",
)
def list_fingersticks(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime | None, Query(alias="from")] = None,
    to_datetime: Annotated[datetime | None, Query(alias="to")] = None,
) -> list[FingerstickReadingResponse]:
    """List manual capillary glucose readings."""
    return GlucoseDashboardService(session, current_user.id).list_fingersticks(
        from_datetime,
        to_datetime,
    )


@router.patch(
    "/fingersticks/{fingerstick_id}",
    response_model=FingerstickReadingResponse,
    operation_id="patchFingerstick",
)
def patch_fingerstick(
    fingerstick_id: UUID,
    payload: FingerstickReadingPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> FingerstickReadingResponse:
    """Patch a manual capillary glucose reading."""
    return GlucoseDashboardService(session, current_user.id).patch_fingerstick(
        fingerstick_id,
        payload,
    )


@router.delete(
    "/fingersticks/{fingerstick_id}",
    status_code=204,
    operation_id="deleteFingerstick",
)
def delete_fingerstick(
    fingerstick_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> None:
    """Delete a manual capillary glucose reading."""
    GlucoseDashboardService(session, current_user.id).delete_fingerstick(fingerstick_id)


@router.get(
    "/sensors",
    response_model=list[SensorSessionResponse],
    operation_id="listSensors",
)
def list_sensors(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> list[SensorSessionResponse]:
    """List sensor sessions."""
    return GlucoseDashboardService(session, current_user.id).list_sensors()


@router.post(
    "/sensors",
    response_model=SensorSessionResponse,
    status_code=201,
    operation_id="createSensor",
)
def create_sensor(
    payload: SensorSessionCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorSessionResponse:
    """Create a sensor session."""
    return GlucoseDashboardService(session, current_user.id).create_sensor(payload)


@router.patch(
    "/sensors/{sensor_id}",
    response_model=SensorSessionResponse,
    operation_id="patchSensor",
)
def patch_sensor(
    sensor_id: UUID,
    payload: SensorSessionPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorSessionResponse:
    """Patch a sensor session."""
    return GlucoseDashboardService(session, current_user.id).patch_sensor(
        sensor_id,
        payload,
    )


@router.get(
    "/sensors/{sensor_id}/quality",
    response_model=SensorQualityResponse,
    operation_id="getSensorQuality",
)
def get_sensor_quality(
    sensor_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorQualityResponse:
    """Return computed display-only quality metrics for one sensor."""
    return GlucoseDashboardService(session, current_user.id).sensor_quality(sensor_id)


@router.post(
    "/sensors/{sensor_id}/recalculate-calibration",
    response_model=CgmCalibrationModelResponse,
    operation_id="recalculateSensorCalibration",
)
def recalculate_sensor_calibration(
    sensor_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> CgmCalibrationModelResponse:
    """Recompute and store a display-only calibration model."""
    return GlucoseDashboardService(session, current_user.id).recalculate_calibration(
        sensor_id
    )
