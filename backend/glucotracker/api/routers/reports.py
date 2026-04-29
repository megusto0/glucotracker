"""Report endpoints."""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import EndocrinologistReportResponse
from glucotracker.application.endocrinologist_report import (
    EndocrinologistReportService,
)

router = APIRouter(
    tags=["reports"],
    dependencies=[Depends(verify_token)],
)


@router.get(
    "/reports/endocrinologist",
    response_model=EndocrinologistReportResponse,
    operation_id="getEndocrinologistReport",
)
def get_endocrinologist_report(
    session: SessionDep,
    from_date: Annotated[date_type, Query(alias="from")],
    to_date: Annotated[date_type, Query(alias="to")],
) -> EndocrinologistReportResponse:
    """Return one-page endocrinologist report data."""
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range start must be before or equal to end.",
        )
    return EndocrinologistReportResponse.model_validate(
        EndocrinologistReportService(session).build(from_date, to_date)
    )
