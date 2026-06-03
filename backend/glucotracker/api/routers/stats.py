"""Stats insight endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from glucotracker.api.dependencies import CurrentUserDep, ReadSessionDep
from glucotracker.api.schemas import StatsInsightsResponse, StatsOverviewResponse
from glucotracker.application.stats_insights import (
    InsightPeriod,
    InsightSlot,
    generate_insights,
    generate_overview,
)

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get(
    "/insights",
    response_model=StatsInsightsResponse,
    operation_id="getStatsInsights",
)
def stats_insights(
    session: ReadSessionDep,
    current_user: CurrentUserDep,
    period: InsightPeriod = "14d",
    slot: InsightSlot = "stats",
) -> StatsInsightsResponse:
    """Return deterministic, server-rendered food pattern observations."""
    return StatsInsightsResponse(
        insights=generate_insights(
            session,
            current_user.id,
            period,
            slot,
            current_user.role,
        )
    )


@router.get(
    "/overview",
    response_model=StatsOverviewResponse,
    operation_id="getStatsOverview",
)
def stats_overview(
    session: ReadSessionDep,
    current_user: CurrentUserDep,
    period: InsightPeriod = "30d",
) -> StatsOverviewResponse:
    """Return structured deterministic nutrition stats for mobile rendering."""
    return StatsOverviewResponse.model_validate(
        generate_overview(session, current_user.id, period, current_user.role),
        from_attributes=True,
    )
