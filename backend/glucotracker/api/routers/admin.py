"""Admin maintenance endpoints."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
from glucotracker.api.schemas import (
    AdminPostprandialResponse,
    AdminRecalculateResponse,
)
from glucotracker.application.daily_totals import DailyTotalsService
from glucotracker.application.postprandial.worker import recompute_postprandial

router = APIRouter(tags=["admin"])


@router.post(
    "/admin/recalculate",
    response_model=AdminRecalculateResponse,
    operation_id="adminRecalculateDailyTotals",
)
def admin_recalculate_daily_totals(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_date: Annotated[date_type, Query(alias="from")],
    to_date: Annotated[date_type, Query(alias="to")],
) -> AdminRecalculateResponse:
    """Backfill daily totals for an inclusive date range."""
    totals = DailyTotalsService(session, current_user.id).recalculate_range(
        from_date,
        to_date,
    )
    session.commit()
    return AdminRecalculateResponse(
        from_date=from_date,
        to_date=to_date,
        days_recalculated=len(totals),
    )


@router.post(
    "/admin/postprandial/recompute",
    response_model=AdminPostprandialResponse,
    operation_id="adminRecomputePostprandial",
    dependencies=[Depends(require_feature("glucose"))],
)
def admin_recompute_postprandial(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_date: Annotated[date_type | None, Query(alias="from")] = None,
    to_date: Annotated[date_type | None, Query(alias="to")] = None,
) -> AdminPostprandialResponse:
    """Recompute postprandial analysis for meals in a date range."""
    from sqlalchemy import select

    from glucotracker.domain.entities import MealStatus
    from glucotracker.infra.db.models import Meal

    stmt = select(Meal.id).where(
        Meal.owner_id == current_user.id,
        Meal.status == MealStatus.accepted,
    )
    if from_date is not None:
        from_start = datetime(from_date.year, from_date.month, from_date.day)
        stmt = stmt.where(Meal.eaten_at >= from_start)
    if to_date is not None:
        to_end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59)
        stmt = stmt.where(Meal.eaten_at <= to_end)

    meal_ids = [row[0] for row in session.execute(stmt).fetchall()]

    analyzed = 0
    for mid in meal_ids:
        if recompute_postprandial(mid, session=session):
            analyzed += 1

    session.commit()
    return AdminPostprandialResponse(
        meals_total=len(meal_ids),
        meals_analyzed=analyzed,
    )
