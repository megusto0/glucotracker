"""Daily total recalculation and simple in-process scheduling."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.application.time import local_day_bounds, local_wall_time
from glucotracker.domain.entities import ItemSourceKind, MealStatus
from glucotracker.infra.db.models import DailyTotal, Meal, utc_now
from glucotracker.infra.db.session import get_session_factory

_pending_days: set[tuple[UUID, date]] = set()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """Return local wall-clock datetime bounds for a date."""
    return local_day_bounds(day)


def _as_date(value: date | datetime) -> date:
    """Return a date from a date or datetime."""
    if isinstance(value, datetime):
        return local_wall_time(value).date()
    return value


def _accepted_meals_for_day(session: Session, user_id: UUID, day: date) -> list[Meal]:
    """Return accepted meals for one day."""
    start, end = _day_bounds(day)
    return list(
        session.scalars(
            select(Meal)
            .where(
                Meal.status == MealStatus.accepted,
                Meal.owner_id == user_id,
                Meal.eaten_at >= start,
                Meal.eaten_at < end,
            )
            .options(selectinload(Meal.items))
        )
    )


def recalculate_day(
    day: date,
    *,
    user_id: UUID,
    session: Session | None = None,
) -> DailyTotal:
    """Sum accepted meals for a day and upsert daily_totals."""
    own_session = session is None
    active_session = session or get_session_factory()()
    try:
        meals = _accepted_meals_for_day(active_session, user_id, day)
        item_list = [item for meal in meals for item in meal.items]
        daily_total = active_session.scalar(
            select(DailyTotal).where(
                DailyTotal.owner_id == user_id,
                DailyTotal.date == day,
            )
        )
        if daily_total is None:
            daily_total = DailyTotal(owner_id=user_id, date=day)
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
    user_id: UUID,
    session: Session | None = None,
) -> list[DailyTotal]:
    """Recalculate an inclusive date range."""
    own_session = session is None
    active_session = session or get_session_factory()()
    try:
        totals = [
            recalculate_day(day, user_id=user_id, session=active_session)
            for day in _iter_dates(from_date, to_date)
        ]
        if own_session:
            active_session.commit()
        return totals
    finally:
        if own_session:
            active_session.close()


def schedule_recalculate_day(user_id: UUID, day: date | datetime) -> None:
    """Schedule a day for in-process recalculation."""
    _pending_days.add((user_id, _as_date(day)))


def schedule_recalculate_days(
    user_id: UUID,
    days: Iterable[date | datetime | None],
) -> None:
    """Schedule multiple optional days for recalculation."""
    for day in days:
        if day is not None:
            schedule_recalculate_day(user_id, day)


def drain_recalculate_queue(session: Session) -> None:
    """Process scheduled daily total recalculations in the current session."""
    while _pending_days:
        user_id, day = min(_pending_days)
        _pending_days.remove((user_id, day))
        recalculate_day(day, user_id=user_id, session=session)


def schedule_and_recalculate(
    session: Session,
    user_id: UUID,
    days: Iterable[date | datetime | None],
) -> None:
    """Schedule days and immediately drain the in-process queue."""
    schedule_recalculate_days(user_id, days)
    drain_recalculate_queue(session)
