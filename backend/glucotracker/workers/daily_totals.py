"""Daily total recalculation and simple in-process scheduling."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.domain.entities import ItemSourceKind, MealStatus
from glucotracker.infra.db.models import DailyTotal, Meal, utc_now
from glucotracker.infra.db.session import get_session_factory

_pending_days: set[date] = set()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """Return UTC datetime bounds for a date."""
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _as_date(value: date | datetime) -> date:
    """Return a date from a date or datetime."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _accepted_meals_for_day(session: Session, day: date) -> list[Meal]:
    """Return accepted meals for one day."""
    start, end = _day_bounds(day)
    return list(
        session.scalars(
            select(Meal)
            .where(
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= start,
                Meal.eaten_at < end,
            )
            .options(selectinload(Meal.items))
        )
    )


def recalculate_day(
    day: date,
    *,
    session: Session | None = None,
) -> DailyTotal:
    """Sum accepted meals for a day and upsert daily_totals."""
    own_session = session is None
    active_session = session or get_session_factory()()
    try:
        meals = _accepted_meals_for_day(active_session, day)
        item_list = [item for meal in meals for item in meal.items]
        daily_total = active_session.get(DailyTotal, day)
        if daily_total is None:
            daily_total = DailyTotal(date=day)
            active_session.add(daily_total)

        daily_total.kcal = sum(meal.total_kcal for meal in meals)
        daily_total.carbs_g = sum(meal.total_carbs_g for meal in meals)
        daily_total.protein_g = sum(meal.total_protein_g for meal in meals)
        daily_total.fat_g = sum(meal.total_fat_g for meal in meals)
        daily_total.fiber_g = sum(meal.total_fiber_g for meal in meals)
        daily_total.meal_count = len(meals)
        daily_total.estimated_item_count = sum(
            1 for item in item_list if item.source_kind == ItemSourceKind.photo_estimate
        )
        daily_total.exact_item_count = len(item_list) - daily_total.estimated_item_count
        daily_total.updated_at = utc_now()
        if own_session:
            active_session.commit()
        else:
            active_session.flush()
        return daily_total
    finally:
        if own_session:
            active_session.close()


def _iter_dates(from_date: date, to_date: date) -> Iterable[date]:
    """Yield all dates in an inclusive date range."""
    day = from_date
    while day <= to_date:
        yield day
        day += timedelta(days=1)


def recalculate_range(
    from_date: date,
    to_date: date,
    *,
    session: Session | None = None,
) -> list[DailyTotal]:
    """Recalculate an inclusive date range."""
    own_session = session is None
    active_session = session or get_session_factory()()
    try:
        totals = [
            recalculate_day(day, session=active_session)
            for day in _iter_dates(from_date, to_date)
        ]
        if own_session:
            active_session.commit()
        return totals
    finally:
        if own_session:
            active_session.close()


def schedule_recalculate_day(day: date | datetime) -> None:
    """Schedule a day for in-process recalculation."""
    _pending_days.add(_as_date(day))


def schedule_recalculate_days(days: Iterable[date | datetime | None]) -> None:
    """Schedule multiple optional days for recalculation."""
    for day in days:
        if day is not None:
            schedule_recalculate_day(day)


def drain_recalculate_queue(session: Session) -> None:
    """Process scheduled daily total recalculations in the current session."""
    while _pending_days:
        day = min(_pending_days)
        _pending_days.remove(day)
        recalculate_day(day, session=session)


def schedule_and_recalculate(
    session: Session,
    days: Iterable[date | datetime | None],
) -> None:
    """Schedule days and immediately drain the in-process queue."""
    schedule_recalculate_days(days)
    drain_recalculate_queue(session)
