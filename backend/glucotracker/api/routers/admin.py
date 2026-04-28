"""Admin maintenance endpoints."""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import AdminRecalculateResponse
from glucotracker.workers.daily_totals import recalculate_range

router = APIRouter(
    tags=["admin"],
    dependencies=[Depends(verify_token)],
)


@router.post(
    "/admin/recalculate",
    response_model=AdminRecalculateResponse,
    operation_id="adminRecalculateDailyTotals",
)
def admin_recalculate_daily_totals(
    session: SessionDep,
    from_date: Annotated[date_type, Query(alias="from")],
    to_date: Annotated[date_type, Query(alias="to")],
) -> AdminRecalculateResponse:
    """Backfill daily totals for an inclusive date range."""
    totals = recalculate_range(from_date, to_date, session=session)
    session.commit()
    return AdminRecalculateResponse(
        from_date=from_date,
        to_date=to_date,
        days_recalculated=len(totals),
    )
