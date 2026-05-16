"""Report endpoints."""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
from glucotracker.api.schemas import EndocrinologistReportResponse
from glucotracker.application.endocrinologist_report import (
    EndocrinologistReportService,
    ReportGlucoseMode,
)

router = APIRouter(tags=["reports"])


@router.get(
    "/reports/endocrinologist",
    response_model=EndocrinologistReportResponse,
    operation_id="getEndocrinologistReport",
    dependencies=[Depends(require_feature("glucose"))],
)
def get_endocrinologist_report(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_date: Annotated[date_type, Query(alias="from")],
    to_date: Annotated[date_type, Query(alias="to")],
    glucose_mode: Annotated[
        ReportGlucoseMode,
        Query(description="Glucose series used for report metrics."),
    ] = "raw",
) -> EndocrinologistReportResponse:
    """Return one-page endocrinologist report data."""
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range start must be before or equal to end.",
        )
    return EndocrinologistReportResponse.model_validate(
        EndocrinologistReportService(session, current_user.id).build(
            from_date,
            to_date,
            glucose_mode,
        )
    )
