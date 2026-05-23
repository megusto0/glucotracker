"""Digital twin research-mode endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
from glucotracker.api.schemas import (
    TwinCurveResponse,
    TwinFitLogEntry,
    TwinParamsPatch,
    TwinParamsRead,
)
from glucotracker.application.twin.service import TwinService

router = APIRouter(
    tags=["twin"],
    dependencies=[Depends(require_feature("glucose"))],
)


@router.get(
    "/twin/params",
    response_model=TwinParamsRead,
    operation_id="getTwinParams",
)
def get_twin_params(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> TwinParamsRead:
    """Return current digital twin parameters for the user."""
    return TwinService(session, current_user.id).get_params()


@router.patch(
    "/twin/params",
    response_model=TwinParamsRead,
    operation_id="patchTwinParams",
)
def patch_twin_params(
    payload: TwinParamsPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> TwinParamsRead:
    """Apply a manual digital twin parameter override."""
    return TwinService(session, current_user.id).patch_params(payload)


@router.post(
    "/twin/params/reset",
    response_model=TwinParamsRead,
    operation_id="resetTwinParams",
)
def reset_twin_params(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> TwinParamsRead:
    """Reset fitted digital twin parameters to defaults."""
    return TwinService(session, current_user.id).reset_params()


@router.get(
    "/twin/fit/history",
    response_model=list[TwinFitLogEntry],
    operation_id="getTwinFitHistory",
)
def get_twin_fit_history(
    session: SessionDep,
    current_user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[TwinFitLogEntry]:
    """Return newest digital twin fit/manual-change history rows."""
    return TwinService(session, current_user.id).fit_history(limit)


@router.get(
    "/twin/curve",
    response_model=TwinCurveResponse,
    operation_id="getTwinCurve",
)
def get_twin_curve(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
    step_minutes: Annotated[int, Query(ge=1, le=60)] = 5,
) -> TwinCurveResponse:
    """Return display-only digital twin reconstruction and forecast points."""
    return TwinService(session, current_user.id).curve(
        from_datetime,
        to_datetime,
        step_minutes=step_minutes,
    )
