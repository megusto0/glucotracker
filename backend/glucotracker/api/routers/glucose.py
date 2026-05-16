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
    FingerstickReadingCreate,
    FingerstickReadingPatch,
    FingerstickReadingResponse,
    GlucoseDashboardResponse,
    SensorQualityResponse,
    SensorSessionCreate,
    SensorSessionPatch,
    SensorSessionResponse,
)
from glucotracker.application.glucose_dashboard import GlucoseDashboardService

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
