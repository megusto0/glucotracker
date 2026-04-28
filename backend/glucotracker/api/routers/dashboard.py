"""Dashboard read endpoints backed by accepted meals and daily totals."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import (
    DashboardDataQualityResponse,
    DashboardDayResponse,
    DashboardHeatmapCell,
    DashboardHeatmapResponse,
    DashboardNutrientTotal,
    DashboardRangeResponse,
    DashboardRangeSummary,
    DashboardSourceBreakdownResponse,
    DashboardSourceBreakdownRow,
    DashboardTodayResponse,
    DashboardTopPatternResponse,
    LowConfidenceItemResponse,
)
from glucotracker.domain.entities import ItemSourceKind, MealStatus
from glucotracker.infra.db.models import (
    DailyTotal,
    Meal,
    MealItem,
    NutrientDefinition,
    Pattern,
)
from glucotracker.infra.db.nutrients import ensure_nutrient_definitions
from glucotracker.workers.daily_totals import recalculate_day, recalculate_range

router = APIRouter(
    tags=["dashboard"],
    dependencies=[Depends(verify_token)],
)

LOW_CONFIDENCE_THRESHOLD = 0.60


def _today() -> date_type:
    """Return the backend dashboard date."""
    return datetime.now(UTC).date()


def _day_bounds(day: date_type) -> tuple[datetime, datetime]:
    """Return UTC datetime bounds for a date."""
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _range_bounds(
    from_date: date_type,
    to_date: date_type,
) -> tuple[datetime, datetime]:
    """Return UTC datetime bounds for an inclusive date range."""
    start = datetime.combine(from_date, time.min, tzinfo=UTC)
    end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC)
    return start, end


def _iter_dates(from_date: date_type, to_date: date_type) -> list[date_type]:
    """Return dates in an inclusive range."""
    days = []
    day = from_date
    while day <= to_date:
        days.append(day)
        day += timedelta(days=1)
    return days


def _daily_row(session: SessionDep, day: date_type) -> DailyTotal:
    """Return recalculated daily total for a date."""
    return recalculate_day(day, session=session)


def _nutrient_totals_for_items(
    session: SessionDep,
    items: list[MealItem],
) -> list[DashboardNutrientTotal]:
    """Return optional nutrient totals, skipping unknown null amounts."""
    ensure_nutrient_definitions(session)
    session.flush()
    definitions = list(
        session.scalars(
            select(NutrientDefinition).order_by(NutrientDefinition.code.asc())
        )
    )
    totals: dict[str, float] = defaultdict(float)
    known_counts: dict[str, int] = defaultdict(int)
    total_item_count = len(items)
    for item in items:
        for nutrient in item.nutrients:
            if nutrient.amount is None:
                continue
            totals[nutrient.nutrient_code] += nutrient.amount
            known_counts[nutrient.nutrient_code] += 1

    return [
        DashboardNutrientTotal(
            nutrient_code=definition.code,
            display_name=definition.display_name,
            unit=definition.unit,
            amount=totals.get(definition.code)
            if known_counts.get(definition.code, 0)
            else None,
            known_item_count=known_counts.get(definition.code, 0),
            total_item_count=total_item_count,
            coverage=(
                known_counts.get(definition.code, 0) / total_item_count
                if total_item_count
                else 0.0
            ),
        )
        for definition in definitions
    ]


def _day_response(session: SessionDep, row: DailyTotal) -> DashboardDayResponse:
    """Convert DailyTotal to dashboard response row."""
    items = _accepted_items_between(session, row.date, row.date)
    return DashboardDayResponse(
        date=row.date,
        kcal=row.kcal,
        carbs_g=row.carbs_g,
        protein_g=row.protein_g,
        fat_g=row.fat_g,
        fiber_g=row.fiber_g,
        meal_count=row.meal_count,
        nutrients=_nutrient_totals_for_items(session, items),
    )


def _accepted_meals_between(
    session: SessionDep,
    from_date: date_type,
    to_date: date_type,
) -> list[Meal]:
    """Return accepted meals in an inclusive date range."""
    start, end = _range_bounds(from_date, to_date)
    return list(
        session.scalars(
            select(Meal)
            .where(
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= start,
                Meal.eaten_at < end,
            )
            .options(selectinload(Meal.items).selectinload(MealItem.nutrients))
            .order_by(Meal.eaten_at.asc())
        )
    )


def _accepted_items_between(
    session: SessionDep,
    from_date: date_type,
    to_date: date_type,
) -> list[MealItem]:
    """Return accepted meal items in an inclusive date range."""
    return [
        item
        for meal in _accepted_meals_between(session, from_date, to_date)
        for item in meal.items
    ]


def _average(values: list[float], divisor: int) -> float:
    """Return a stable average."""
    if divisor <= 0:
        return 0.0
    return sum(values) / divisor


def _average_logged_days(rows: list[object], field: str) -> float:
    """Return an average over days that have accepted meal data."""
    values = [
        float(getattr(row, field))
        for row in rows
        if int(row.meal_count) > 0
    ]
    return _average(values, len(values))


def _last_meal(session: SessionDep) -> Meal | None:
    """Return latest accepted meal."""
    return session.scalar(
        select(Meal)
        .where(Meal.status == MealStatus.accepted)
        .order_by(Meal.eaten_at.desc())
        .limit(1)
    )


@router.get(
    "/dashboard/today",
    response_model=DashboardTodayResponse,
    operation_id="getDashboardToday",
)
def dashboard_today(session: SessionDep) -> DashboardTodayResponse:
    """Return today's dashboard summary."""
    today = _today()
    recalculate_range(today - timedelta(days=13), today, session=session)
    session.flush()

    row = _daily_row(session, today)
    week_days = _iter_dates(today - timedelta(days=6), today)
    prev_week_days = _iter_dates(today - timedelta(days=13), today - timedelta(days=7))
    week_rows = [
        session.get(DailyTotal, day) or _daily_row(session, day) for day in week_days
    ]
    prev_rows = [
        session.get(DailyTotal, day) or _daily_row(session, day)
        for day in prev_week_days
    ]
    last_meal = _last_meal(session)
    last_meal_at = last_meal.eaten_at if last_meal is not None else None
    hours_since = None
    if last_meal_at is not None:
        comparable = last_meal_at
        if comparable.tzinfo is None:
            comparable = comparable.replace(tzinfo=UTC)
        hours_since = (datetime.now(UTC) - comparable).total_seconds() / 3600

    return DashboardTodayResponse(
        date=today,
        kcal=row.kcal,
        carbs_g=row.carbs_g,
        protein_g=row.protein_g,
        fat_g=row.fat_g,
        fiber_g=row.fiber_g,
        meal_count=row.meal_count,
        last_meal_at=last_meal_at,
        hours_since_last_meal=hours_since,
        week_avg_carbs=_average_logged_days(week_rows, "carbs_g"),
        week_avg_kcal=_average_logged_days(week_rows, "kcal"),
        prev_week_avg_carbs=_average_logged_days(prev_rows, "carbs_g"),
        prev_week_avg_kcal=_average_logged_days(prev_rows, "kcal"),
        nutrients=_nutrient_totals_for_items(
            session,
            _accepted_items_between(session, today, today),
        ),
    )


@router.get(
    "/dashboard/range",
    response_model=DashboardRangeResponse,
    operation_id="getDashboardRange",
)
def dashboard_range(
    session: SessionDep,
    from_date: Annotated[date_type, Query(alias="from")],
    to_date: Annotated[date_type, Query(alias="to")],
) -> DashboardRangeResponse:
    """Return daily dashboard rows and summary for an inclusive range."""
    rows = recalculate_range(from_date, to_date, session=session)
    days = [_day_response(session, row) for row in rows]
    range_items = _accepted_items_between(session, from_date, to_date)
    summary = DashboardRangeSummary(
        avg_kcal=_average_logged_days(days, "kcal"),
        avg_carbs_g=_average_logged_days(days, "carbs_g"),
        avg_protein_g=_average_logged_days(days, "protein_g"),
        avg_fat_g=_average_logged_days(days, "fat_g"),
        avg_fiber_g=_average_logged_days(days, "fiber_g"),
        total_meals=sum(day.meal_count for day in days),
        total_kcal=sum(day.kcal for day in days),
        total_carbs_g=sum(day.carbs_g for day in days),
        total_protein_g=sum(day.protein_g for day in days),
        total_fat_g=sum(day.fat_g for day in days),
        total_fiber_g=sum(day.fiber_g for day in days),
        nutrients=_nutrient_totals_for_items(session, range_items),
    )
    return DashboardRangeResponse(days=days, summary=summary)


@router.get(
    "/dashboard/heatmap",
    response_model=DashboardHeatmapResponse,
    operation_id="getDashboardHeatmap",
)
def dashboard_heatmap(
    session: SessionDep,
    weeks: int = Query(default=4, ge=1, le=52),
) -> DashboardHeatmapResponse:
    """Aggregate accepted meals by weekday and hour."""
    today = _today()
    meals = _accepted_meals_between(
        session,
        today - timedelta(days=weeks * 7 - 1),
        today,
    )
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for meal in meals:
        buckets[(meal.eaten_at.weekday(), meal.eaten_at.hour)].append(
            meal.total_carbs_g
        )
    cells = [
        DashboardHeatmapCell(
            day_of_week=day_of_week,
            hour=hour,
            avg_carbs_g=sum(carbs_values) / len(carbs_values),
            meal_count=len(carbs_values),
        )
        for (day_of_week, hour), carbs_values in sorted(buckets.items())
    ]
    return DashboardHeatmapResponse(cells=cells)


@router.get(
    "/dashboard/top_patterns",
    response_model=list[DashboardTopPatternResponse],
    operation_id="getDashboardTopPatterns",
)
def dashboard_top_patterns(
    session: SessionDep,
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[DashboardTopPatternResponse]:
    """Return most frequently used patterns in accepted meals."""
    today = _today()
    items = _accepted_items_between(session, today - timedelta(days=days - 1), today)
    counts: dict[Pattern, int] = {}
    for item in items:
        if item.pattern is not None:
            counts[item.pattern] = counts.get(item.pattern, 0) + 1
    sorted_counts = sorted(
        counts.items(),
        key=lambda row: (-row[1], row[0].display_name.casefold()),
    )
    return [
        DashboardTopPatternResponse(
            pattern_id=pattern.id,
            token=f"{pattern.prefix}:{pattern.key}",
            display_name=pattern.display_name,
            count=count,
        )
        for pattern, count in sorted_counts[:limit]
    ]


@router.get(
    "/dashboard/source_breakdown",
    response_model=DashboardSourceBreakdownResponse,
    operation_id="getDashboardSourceBreakdown",
)
def dashboard_source_breakdown(
    session: SessionDep,
    days: int = Query(default=7, ge=1, le=365),
) -> DashboardSourceBreakdownResponse:
    """Count accepted meal items by source kind."""
    today = _today()
    items = _accepted_items_between(session, today - timedelta(days=days - 1), today)
    counts: dict[ItemSourceKind, int] = defaultdict(int)
    for item in items:
        counts[item.source_kind] += 1
    return DashboardSourceBreakdownResponse(
        days=days,
        items=[
            DashboardSourceBreakdownRow(source_kind=source_kind, count=count)
            for source_kind, count in sorted(
                counts.items(),
                key=lambda row: row[0].value,
            )
        ],
    )


@router.get(
    "/dashboard/data_quality",
    response_model=DashboardDataQualityResponse,
    operation_id="getDashboardDataQuality",
)
def dashboard_data_quality(
    session: SessionDep,
    days: int = Query(default=7, ge=1, le=365),
) -> DashboardDataQualityResponse:
    """Return item source and confidence quality metrics."""
    today = _today()
    items = _accepted_items_between(session, today - timedelta(days=days - 1), today)
    low_confidence_items = [
        LowConfidenceItemResponse(
            meal_id=item.meal_id,
            item_id=item.id,
            name=item.name,
            confidence=item.confidence,
            reason=item.confidence_reason,
        )
        for item in items
        if item.confidence is not None and item.confidence < LOW_CONFIDENCE_THRESHOLD
    ]
    return DashboardDataQualityResponse(
        exact_label_count=sum(
            1
            for item in items
            if item.calculation_method == "label_visible_weight_backend_calc"
        ),
        assumed_label_count=sum(
            1
            for item in items
            if item.calculation_method == "label_assumed_weight_backend_calc"
        ),
        restaurant_db_count=sum(
            1 for item in items if item.source_kind == ItemSourceKind.restaurant_db
        ),
        product_db_count=sum(
            1 for item in items if item.source_kind == ItemSourceKind.product_db
        ),
        pattern_count=sum(
            1 for item in items if item.source_kind == ItemSourceKind.pattern
        ),
        visual_estimate_count=sum(
            1 for item in items if item.source_kind == ItemSourceKind.photo_estimate
        ),
        manual_count=sum(
            1 for item in items if item.source_kind == ItemSourceKind.manual
        ),
        low_confidence_count=len(low_confidence_items),
        total_item_count=len(items),
        low_confidence_items=low_confidence_items,
    )
