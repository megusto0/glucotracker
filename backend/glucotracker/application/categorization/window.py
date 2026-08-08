"""Day-anchor computation for adaptive meal-window categorization."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.body_states import BodyStateInterval, BodyStateService
from glucotracker.application.time import local_now, local_wall_time
from glucotracker.domain.entities import AnchorBasis, MealStatus
from glucotracker.infra.db.models import DayAnchorHistory, Meal, NonTypicalPeriod, User

logger = logging.getLogger(__name__)

WEIGHTS_7D: list[float] = [1.0, 0.85, 0.72, 0.61, 0.52, 0.44, 0.38]
SHIFT_DETECTION_DAYS: int = 3
SHIFT_THRESHOLD_MINUTES: int = 120
WEEKEND_SPLIT_THRESHOLD_MINUTES: int = 90
WEEKEND_SPLIT_MIN_WEEKS: int = 4
MIN_QUALIFYING_DAYS: int = 7
TYPICAL_MORNING_START_MINUTES: int = 4 * 60
TYPICAL_MORNING_END_MINUTES: int = 11 * 60

#: How far back to look for nights when anchoring the day on real sleep.
SLEEP_LOOKBACK_DAYS: int = 10
#: Nights needed before sleep is trusted over the first-meal estimate. Below
#: this the anchor would flip between the two as watch data comes and goes.
MIN_SLEEP_NIGHTS: int = 5
#: A nap is not the end of a night. Naps end in the afternoon and would drag
#: the anchor hours late, so only a real night counts as waking up.
MIN_NIGHT_SLEEP = timedelta(hours=3)


def anchor_is_typical_morning(anchor_minutes: int | None) -> bool:
    """Return True when the day anchor lands in a conventional morning slot.

    Time-of-day wording («утром», «вечерние») is only truthful for such
    anchors; shifted anchors need anchor-relative labels instead.
    """
    if anchor_minutes is None:
        return True
    return (
        TYPICAL_MORNING_START_MINUTES <= anchor_minutes <= TYPICAL_MORNING_END_MINUTES
    )


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """Return the weighted median of values."""
    if not values or not weights:
        return 0.0

    n = min(len(values), len(weights))
    recent_values = values[-n:]
    recent_weights = weights[:n][::-1]

    indexed = sorted(
        zip(recent_values, recent_weights, strict=False), key=lambda x: x[0]
    )
    total_weight = sum(w for _, w in indexed)
    half_weight = total_weight / 2
    cumulative = 0.0

    for v, w in indexed:
        cumulative += w
        if cumulative >= half_weight:
            return v

    return indexed[-1][0] if indexed else 0.0


def _first_meal_of_day(meals_for_date: list[Meal]) -> Meal | None:
    """Return the first meal after a >=6-hour eating gap."""
    if not meals_for_date:
        return None

    sorted_meals = sorted(meals_for_date, key=lambda m: m.eaten_at)
    for i, meal in enumerate(sorted_meals):
        prev = sorted_meals[i - 1] if i > 0 else None
        if prev is None:
            return meal
        gap = (meal.eaten_at - prev.eaten_at).total_seconds()
        if gap >= 6 * 3600:
            return meal
    return sorted_meals[0]


def _fetch_first_meals_of_day(
    session: Session,
    user_id: UUID,
    lookback_days: int = 28,
) -> list[Meal]:
    """Fetch all accepted meals within the lookback window, grouped by day."""
    cutoff = local_wall_time(datetime.now()) - timedelta(days=lookback_days)
    meals = list(
        session.scalars(
            select(Meal)
            .where(
                Meal.owner_id == user_id,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= cutoff,
            )
            .order_by(Meal.eaten_at)
        )
    )

    by_date: defaultdict[date, list[Meal]] = defaultdict(list)
    for meal in meals:
        meal_local_date = local_wall_time(meal.eaten_at).date()
        by_date[meal_local_date].append(meal)

    first_meals: list[Meal] = []
    for day in sorted(by_date):
        first = _first_meal_of_day(by_date[day])
        if first is not None:
            first_meals.append(first)

    return first_meals


def _exclude_non_typical_periods(
    session: Session,
    user_id: UUID,
    first_meals: list[Meal],
) -> list[Meal]:
    """Filter out meals whose date falls within a non-typical period."""
    periods = list(
        session.scalars(
            select(NonTypicalPeriod).where(
                NonTypicalPeriod.user_id == user_id,
            )
        )
    )
    if not periods:
        return first_meals

    excluded_dates: set[date] = set()
    for period in periods:
        day = period.start_date
        while day <= period.end_date:
            excluded_dates.add(day)
            day += timedelta(days=1)

    return [
        m
        for m in first_meals
        if local_wall_time(m.eaten_at).date() not in excluded_dates
    ]


def _minutes_from_midnight(dt: datetime) -> float:
    """Return minutes since midnight in local time."""
    local = local_wall_time(dt)
    return local.hour * 60 + local.minute


@dataclass(frozen=True)
class SleepRhythm:
    """The nights behind the anchor, so a screen can show what it read."""

    start_minutes: int
    end_minutes: int
    nights: int


def sleep_rhythm(session: Session, user_id: UUID) -> SleepRhythm | None:
    """Typical sleep window over the recent nights, or None if too few."""
    nights = _nights(session, user_id)
    if len(nights) < MIN_SLEEP_NIGHTS:
        return None
    # The wider lookup tolerates an occasional night that the watch missed,
    # but the rhythm itself and the evidence count both describe the same last
    # seven recorded nights. Previously the times used seven while the API
    # reported every night found in the ten-day lookup.
    recent_nights = nights[-len(WEIGHTS_7D) :]
    starts = [_minutes_from_midnight(night.start_at) for night in recent_nights]
    ends = [_minutes_from_midnight(night.end_at) for night in recent_nights]
    # Bedtime straddles midnight, so it is averaged on the far side of the
    # clock and brought back. Waking does not, and is taken as it comes.
    shifted = [start + 24 * 60 if start < 12 * 60 else start for start in starts]
    start = int(round(_weighted_median(shifted, WEIGHTS_7D))) % (24 * 60)
    return SleepRhythm(
        start_minutes=start,
        end_minutes=int(round(_weighted_median(ends, WEIGHTS_7D))),
        nights=len(recent_nights),
    )


def _nights(session: Session, user_id: UUID) -> list[BodyStateInterval]:
    """One sleep per calendar day: the longest night ending that day."""
    now = local_now()
    intervals = BodyStateService(session, user_id).intervals(
        now - timedelta(days=SLEEP_LOOKBACK_DAYS),
        now,
    )
    # Taking the latest instead would pick an afternoon nap over the morning it
    # began, dragging the day's start hours late.
    longest_by_date: dict[date, BodyStateInterval] = {}
    for interval in intervals:
        if interval.kind != "sleep":
            continue
        if timedelta(minutes=interval.total_minutes) < MIN_NIGHT_SLEEP:
            continue
        day = interval.end_at.date()
        current = longest_by_date.get(day)
        if current is None or interval.total_minutes > current.total_minutes:
            longest_by_date[day] = interval
    return [longest_by_date[day] for day in sorted(longest_by_date)]


def _wake_minutes(session: Session, user_id: UUID) -> list[float]:
    """When the user actually got up, one value per night, oldest first.

    The first meal is only a proxy for the start of a day, and a poor one on
    any day breakfast is skipped or late: waking at 06:00 and first eating at
    11:00 moved the whole rhythm five hours. Sleep says it directly. Recorded
    sessions are used where the watch has synced them and heart rate fills in
    the rest, which is the same pair `BodyStateService` already reconciles.
    """
    return [_minutes_from_midnight(night.end_at) for night in _nights(session, user_id)]


def compute_user_anchors(
    session: Session,
    user_id: UUID,
) -> tuple[int | None, int | None, AnchorBasis]:
    """Compute weekday and weekend anchors for a user.

    Returns (weekday_anchor_minutes, weekend_anchor_minutes, basis).
    None values mean "use absolute fallback".
    """
    override = session.scalar(
        select(User.day_anchor_user_override_minutes).where(
            User.id == user_id,
        )
    )
    if override is not None:
        return (override, None, AnchorBasis.user_override)

    # Real waking beats guessing it from the first plate. Falls through to the
    # meal estimate whenever there are too few nights to be steady, so a user
    # with no watch — and the food flavor, which has no sleep at all — keeps
    # exactly the behaviour they had.
    wake_minutes = _wake_minutes(session, user_id)
    if len(wake_minutes) >= MIN_SLEEP_NIGHTS:
        anchor = _weighted_median(wake_minutes[-7:], WEIGHTS_7D)
        return (int(round(anchor)), None, AnchorBasis.sleep_7d)

    first_meals = _fetch_first_meals_of_day(session, user_id, lookback_days=28)
    first_meals = _exclude_non_typical_periods(session, user_id, first_meals)

    qualifying_dates = {local_wall_time(m.eaten_at).date() for m in first_meals}
    if len(qualifying_dates) < MIN_QUALIFYING_DAYS:
        return (None, None, AnchorBasis.absolute_fallback)

    minutes_list = [_minutes_from_midnight(m.eaten_at) for m in first_meals]

    recent_3 = minutes_list[-SHIFT_DETECTION_DAYS:]
    weighted_7d = (
        _weighted_median(minutes_list[-7:], WEIGHTS_7D)
        if len(minutes_list) >= 7
        else 0.0
    )

    if (
        len(recent_3) >= SHIFT_DETECTION_DAYS
        and len(minutes_list) >= 7
        and all(abs(m - weighted_7d) >= SHIFT_THRESHOLD_MINUTES for m in recent_3)
    ):
        anchor = median(recent_3)
        _record_shift(session, user_id)
        return (int(round(anchor)), None, AnchorBasis.shift_3d)

    weekday_minutes = [
        _minutes_from_midnight(m.eaten_at)
        for m in first_meals[-28:]
        if local_wall_time(m.eaten_at).weekday() < 5
    ]
    weekend_minutes = [
        _minutes_from_midnight(m.eaten_at)
        for m in first_meals[-28:]
        if local_wall_time(m.eaten_at).weekday() >= 5
    ]

    dates = sorted(qualifying_dates)
    weeks_covered = 0
    if len(dates) >= 2:
        weeks_covered = (dates[-1] - dates[0]).days // 7

    weekday_anchor = (
        _weighted_median(weekday_minutes[-7:], WEIGHTS_7D)
        if len(weekday_minutes) >= MIN_QUALIFYING_DAYS
        else None
    )
    weekend_anchor = (
        _weighted_median(weekend_minutes[-7:], WEIGHTS_7D)
        if len(weekend_minutes) >= 2
        else None
    )

    if (
        weekday_anchor is not None
        and weekend_anchor is not None
        and weeks_covered >= WEEKEND_SPLIT_MIN_WEEKS
        and abs(weekday_anchor - weekend_anchor) >= WEEKEND_SPLIT_THRESHOLD_MINUTES
    ):
        return (
            int(round(weekday_anchor)),
            int(round(weekend_anchor)),
            AnchorBasis.weighted_7d,
        )

    anchor = _weighted_median(minutes_list[-7:], WEIGHTS_7D)
    return (int(round(anchor)), None, AnchorBasis.weighted_7d)


def _record_shift(session: Session, user_id: UUID) -> None:
    """Record a regime-shift detection event."""
    from datetime import UTC
    from datetime import datetime as dt

    user = session.scalar(select(User).where(User.id == user_id))
    if user is not None:
        user.day_anchor_last_shift_at = dt.now(UTC)
        session.flush()


def write_anchors_to_user(
    session: Session,
    user_id: UUID,
    weekday: int | None,
    weekend: int | None,
    basis: AnchorBasis,
) -> None:
    """Persist computed anchors to the user record."""
    user = session.scalar(select(User).where(User.id == user_id))
    if user is None:
        return

    previous = (
        user.day_anchor_weekday_minutes,
        user.day_anchor_weekend_minutes,
        user.day_anchor_basis,
    )

    user.day_anchor_weekday_minutes = weekday
    user.day_anchor_weekend_minutes = weekend
    user.day_anchor_basis = basis.value
    if previous != (weekday, weekend, basis.value):
        _append_anchor_history(session, user_id, weekday, weekend, basis.value)
    logger.info(
        "User %s anchors updated: weekday=%s weekend=%s basis=%s",
        user_id,
        weekday,
        weekend,
        basis.value,
    )
    session.flush()


def _append_anchor_history(
    session: Session,
    user_id: UUID,
    weekday: int | None,
    weekend: int | None,
    basis: str,
) -> None:
    """Append or replace today's effective anchor-history row."""
    today = local_now().date()
    open_row = session.scalar(
        select(DayAnchorHistory)
        .where(
            DayAnchorHistory.user_id == user_id,
            DayAnchorHistory.effective_to.is_(None),
        )
        .order_by(DayAnchorHistory.effective_from.desc())
        .limit(1)
    )
    if open_row is not None and open_row.effective_from == today:
        open_row.anchor_weekday_minutes = weekday
        open_row.anchor_weekend_minutes = weekend
        open_row.basis = basis
        session.flush()
        return
    if open_row is not None:
        open_row.effective_to = today - timedelta(days=1)
    session.add(
        DayAnchorHistory(
            user_id=user_id,
            effective_from=today,
            effective_to=None,
            anchor_weekday_minutes=weekday,
            anchor_weekend_minutes=weekend,
            basis=basis,
        )
    )
    session.flush()


def recompute_and_persist_anchors(
    session: Session,
    user_id: UUID,
) -> None:
    """Compute and persist day anchors for a single user."""
    weekday, weekend, basis = compute_user_anchors(session, user_id)
    write_anchors_to_user(session, user_id, weekday, weekend, basis)


def recompute_anchors_for_all_users(session: Session) -> None:
    """Nightly job: recompute day anchors for all users."""
    users = list(session.scalars(select(User.id)))
    for user_id in users:
        try:
            recompute_and_persist_anchors(session, user_id)
        except Exception:
            logger.exception("Failed to recompute anchors for user %s", user_id)
    session.commit()


def get_anchor_for_meal(
    user: User,
    eaten_at: datetime,
) -> int | None:
    """Return the effective anchor in minutes for a specific meal date.

    Handles weekday/weekend split based on eaten_at's weekday.
    """
    override = user.day_anchor_user_override_minutes
    if override is not None:
        return override

    if eaten_at.weekday() >= 5 and user.day_anchor_weekend_minutes is not None:
        return user.day_anchor_weekend_minutes
    return user.day_anchor_weekday_minutes
