"""Deterministic ADR-009 observation generation for food stats."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from statistics import median, pstdev
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.application.glucose_visibility import visible_glucose_filter
from glucotracker.application.product_categories import is_sweet_text
from glucotracker.application.time import (
    local_day_bounds,
    local_now,
    local_wall_time,
    utc_instant_from_local_wall,
)
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import Meal, MealItem, NightscoutGlucoseEntry, User

InsightPeriod = Literal["7d", "14d", "30d"]
InsightSlot = Literal["today", "stats"]
InsightWeight = Literal["primary", "secondary"]
InsightKind = Literal[
    "consistent",
    "weekday_pattern_sweet",
    "time_of_day_eating",
    "top_repeat_products",
    "late_meal_share",
    "today_morning",
    "meal_predictability",
    "evening_lows",
    "hypo_recovery_pattern",
    "late_meal_glucose_footprint",
]

PERIOD_DAYS: dict[InsightPeriod, int] = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
}
MIN_TRACKED_DAYS_FOR_INSIGHTS: int = 7

_KIND_FLAVOR: dict[InsightKind, str] = {
    "consistent": "both",
    "weekday_pattern_sweet": "both",
    "time_of_day_eating": "both",
    "top_repeat_products": "both",
    "late_meal_share": "both",
    "today_morning": "both",
    "meal_predictability": "gluco",
    "evening_lows": "gluco",
    "hypo_recovery_pattern": "gluco",
    "late_meal_glucose_footprint": "gluco",
}


def _flavor_for_role(role: UserRole) -> str:
    return "gluco" if role == UserRole.gluco else "food"


def _kinds_for_flavor(flavor: str) -> set[InsightKind]:
    return {
        kind
        for kind, f in _KIND_FLAVOR.items()
        if f in ("both", flavor)
    }

WEEKDAY_DATIVE = {
    0: "понедельникам",
    1: "вторникам",
    2: "средам",
    3: "четвергам",
    4: "пятницам",
    5: "субботам",
    6: "воскресеньям",
}

WINDOW_LABELS = {
    "start": "утром",
    "mid": "днём",
    "late": "вечером",
    "night_cap": "ночью",
}

BANNED_COPY = (
    "молодец",
    "лень",
    "срыв",
    "держись",
    "так держать",
    "надо",
    "нужно",
    "следует",
    "попробуй меньше",
    "попробуй больше",
    "сократи",
    "увеличь",
    "другие",
    "пользователи",
    "обычный человек",
    "подряд",
    "рекорд",
    "серия дней",
)


@dataclass(frozen=True)
class StatsInsight:
    """Rendered insight ready for client display."""

    id: str
    kind: InsightKind
    text: str
    weight: InsightWeight
    computed_at: datetime
    supporting_numbers: dict[str, str] | None = None


@dataclass(frozen=True)
class InsightCandidate:
    """Qualifying insight before top-N selection."""

    kind: InsightKind
    text: str
    signal_strength: float
    recency_factor: float
    supporting_numbers: dict[str, str] | None = None

    @property
    def score(self) -> float:
        return self.recency_factor * self.signal_strength


@dataclass(frozen=True)
class InsightMealItem:
    """Meal item feature used by deterministic insight functions."""

    name: str
    kcal: float
    product_category: str | None
    product_name: str | None
    product_brand: str | None


@dataclass(frozen=True)
class InsightMeal:
    """Accepted meal feature row scoped to one user."""

    eaten_at: datetime
    local_date: date_type
    hour: int
    source: MealSource
    total_kcal: float
    total_carbs_g: float
    total_protein_g: float
    total_fat_g: float
    confidence: float | None
    title: str | None
    taste_profile: str | None
    meal_window: str | None
    postprandial_response: dict[str, object] | None
    items: tuple[InsightMealItem, ...]


@dataclass(frozen=True)
class InsightGlucosePoint:
    """Scoped CGM point used for deterministic gluco insight functions."""

    timestamp: datetime
    local_date: date_type
    hour: int
    value_mmol_l: float


@dataclass(frozen=True)
class InsightContext:
    """Inputs shared by ADR-009 insight kinds."""

    meals: list[InsightMeal]
    glucose_points: list[InsightGlucosePoint]
    days: int
    anchor_minutes: int | None
    computed_at: datetime


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: datetime
    insights: list[StatsInsight]


_CACHE: dict[tuple[UUID, InsightPeriod, InsightSlot, date_type, str], _CacheEntry] = {}


class StatsInsightsRepository:
    """Read accepted meal features for one authenticated user."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def context_for_period(self, days: int) -> InsightContext:
        """Return scoped meal features and user schedule context."""
        today = local_now().date()
        from_day = today - timedelta(days=days - 1)
        start, _ = local_day_bounds(from_day)
        _, end = local_day_bounds(today)
        utc_start = utc_instant_from_local_wall(start)
        utc_end = utc_instant_from_local_wall(end)

        rows = self.session.scalars(
            select(Meal)
            .where(
                Meal.owner_id == self.user_id,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= start,
                Meal.eaten_at < end,
            )
            .options(selectinload(Meal.items).selectinload(MealItem.product))
            .order_by(Meal.eaten_at.asc())
        ).all()
        glucose_rows = self.session.scalars(
            select(NightscoutGlucoseEntry)
            .where(
                NightscoutGlucoseEntry.owner_id == self.user_id,
                NightscoutGlucoseEntry.timestamp >= utc_start,
                NightscoutGlucoseEntry.timestamp < utc_end,
                visible_glucose_filter(self.user_id),
            )
            .order_by(NightscoutGlucoseEntry.timestamp.asc())
        ).all()
        user = self.session.get(User, self.user_id)
        return InsightContext(
            meals=[_meal_feature(row) for row in rows],
            glucose_points=[_glucose_feature(row) for row in glucose_rows],
            days=days,
            anchor_minutes=(
                user.day_anchor_user_override_minutes
                or user.day_anchor_weekday_minutes
                if user is not None
                else None
            ),
            computed_at=datetime.now(UTC),
        )


def generate_insights(
    session: Session,
    user_id: UUID,
    period: InsightPeriod,
    slot: InsightSlot,
    role: UserRole = UserRole.gluco,
) -> list[StatsInsight]:
    """Generate ADR-009 deterministic insights for a user."""
    days = PERIOD_DAYS[period]
    context = StatsInsightsRepository(session, user_id).context_for_period(days)
    signature = _cache_signature(context)
    cache_key = (user_id, period, slot, local_now().date(), f"{role.value}:{signature}")
    cached = _CACHE.get(cache_key)
    if cached is not None and cached.expires_at > context.computed_at:
        return cached.insights

    insights = _generate_uncached(context, slot, role)
    _CACHE[cache_key] = _CacheEntry(
        expires_at=context.computed_at + timedelta(hours=1),
        insights=insights,
    )
    return insights


def _generate_uncached(
    context: InsightContext,
    slot: InsightSlot,
    role: UserRole,
) -> list[StatsInsight]:
    flavor = _flavor_for_role(role)
    allowed = _kinds_for_flavor(flavor)

    if slot == "today":
        if "today_morning" not in allowed:
            return []
        candidate = _today_morning(context)
        candidates = [candidate] if candidate is not None else []
        return _wrap_candidates(candidates, context, 1)

    if len(_tracked_days(context.meals)) < MIN_TRACKED_DAYS_FOR_INSIGHTS:
        return []

    all_candidates = [
        ("consistent", _consistent(context)),
        ("weekday_pattern_sweet", _weekday_pattern_sweet(context)),
        ("time_of_day_eating", _time_of_day_eating(context)),
        ("top_repeat_products", _top_repeat_products(context)),
        ("late_meal_share", _late_meal_share(context)),
        ("meal_predictability", _meal_predictability(context)),
        ("evening_lows", _evening_lows(context)),
        ("hypo_recovery_pattern", _hypo_recovery_pattern(context)),
        ("late_meal_glucose_footprint", _late_meal_glucose_footprint(context)),
    ]
    candidates = [
        c for kind, c in all_candidates
        if kind in allowed and c is not None
    ]
    return _wrap_candidates(candidates, context, 3)


def _wrap_candidates(
    candidates: list[InsightCandidate],
    context: InsightContext,
    limit: int,
) -> list[StatsInsight]:
    ranked = sorted(candidates, key=lambda item: (-item.score, item.kind))[:limit]
    rendered: list[StatsInsight] = []
    today = local_now().date().isoformat()
    for index, candidate in enumerate(ranked):
        _assert_copy_allowed(candidate.text)
        rendered.append(
            StatsInsight(
                id=f"{candidate.kind}:{today}",
                kind=candidate.kind,
                text=candidate.text,
                weight="primary" if index == 0 else "secondary",
                computed_at=context.computed_at,
                supporting_numbers=candidate.supporting_numbers,
            )
        )
    return rendered


def _meal_feature(meal: Meal) -> InsightMeal:
    local_at = local_wall_time(meal.eaten_at)
    ai_categories = meal.ai_categories or {}
    derived_categories = meal.derived_categories or {}
    return InsightMeal(
        eaten_at=meal.eaten_at,
        local_date=local_at.date(),
        hour=local_at.hour,
        source=meal.source,
        total_kcal=float(meal.total_kcal or 0),
        total_carbs_g=float(meal.total_carbs_g or 0),
        total_protein_g=float(meal.total_protein_g or 0),
        total_fat_g=float(meal.total_fat_g or 0),
        confidence=meal.confidence,
        title=meal.title,
        taste_profile=_str_or_none(ai_categories.get("taste_profile")),
        meal_window=(
            _str_or_none(derived_categories.get("meal_window"))
            or _fallback_window(local_at.hour)
        ),
        postprandial_response=meal.postprandial_response,
        items=tuple(
            InsightMealItem(
                name=item.name,
                kcal=float(item.kcal or 0),
                product_category=item.product.category if item.product else None,
                product_name=item.product.name if item.product else None,
                product_brand=item.product.brand if item.product else None,
            )
            for item in meal.items
        ),
    )


def _glucose_feature(row: NightscoutGlucoseEntry) -> InsightGlucosePoint:
    local_at = local_wall_time(row.timestamp)
    return InsightGlucosePoint(
        timestamp=local_at,
        local_date=local_at.date(),
        hour=local_at.hour,
        value_mmol_l=float(row.value_mmol_l),
    )


def _consistent(context: InsightContext) -> InsightCandidate | None:
    tracked = sorted(_tracked_days(context.meals))
    if len(tracked) < 7:
        return None
    totals = [
        sum(meal.total_kcal for meal in context.meals if meal.local_date == day)
        for day in tracked
    ]
    average = sum(totals) / len(totals)
    if average <= 0:
        return None
    if len(totals) > 1 and pstdev(totals) >= average * 0.25:
        return None
    return InsightCandidate(
        kind="consistent",
        text=(
            f"Привычный для тебя ритм. Около {_format_int(average)} ккал в день "
            f"за последние {len(tracked)} дней."
        ),
        signal_strength=max(
            0.1,
            1.0 - (pstdev(totals) / average if len(totals) > 1 else 0),
        ),
        recency_factor=_recency_factor(context.days),
        supporting_numbers={"kcal_avg": str(round(average)), "days": str(len(tracked))},
    )


def _weekday_pattern_sweet(context: InsightContext) -> InsightCandidate | None:
    if len(_tracked_days(context.meals)) < MIN_TRACKED_DAYS_FOR_INSIGHTS:
        return None
    cells: dict[tuple[int, str], list[float]] = defaultdict(list)
    total_sweet_kcal = 0.0
    for meal in context.meals:
        sweet_kcal = _sweet_kcal(meal)
        if sweet_kcal <= 0 or meal.meal_window not in WINDOW_LABELS:
            continue
        total_sweet_kcal += sweet_kcal
        cells[(meal.local_date.weekday(), meal.meal_window)].append(sweet_kcal)

    qualifying = {
        key: sum(values)
        for key, values in cells.items()
        if len(values) >= 2
    }
    if len(qualifying) < 3 or total_sweet_kcal <= 0:
        return None
    top_cells = sorted(qualifying.items(), key=lambda row: (-row[1], row[0]))[:3]
    top_kcal = sum(value for _, value in top_cells)
    share = top_kcal / total_sweet_kcal
    if share <= 0.25:
        return None
    window_counts = Counter(window for (weekday, window), _ in top_cells)
    window = window_counts.most_common(1)[0][0]
    weekdays = sorted(
        {
            weekday
            for (weekday, cell_window), _ in top_cells
            if cell_window == window
        }
    )
    if not weekdays:
        weekdays = sorted({weekday for (weekday, _), _ in top_cells})
    kcal = top_kcal / len(top_cells)
    return InsightCandidate(
        kind="weekday_pattern_sweet",
        text=(
            f"По {_day_label(weekdays)} {WINDOW_LABELS[window]} "
            f"сладкого больше — около {_format_int(kcal)} ккал."
        ),
        signal_strength=share,
        recency_factor=_recency_factor(context.days),
        supporting_numbers={"sweet_kcal": str(round(kcal)), "share": f"{share:.3f}"},
    )


def _time_of_day_eating(context: InsightContext) -> InsightCandidate | None:
    if len(_tracked_days(context.meals)) < MIN_TRACKED_DAYS_FOR_INSIGHTS:
        return None
    counts = Counter(meal.hour for meal in context.meals)
    if not counts:
        return None
    first_hour, first_count = max(counts.items(), key=lambda row: (row[1], -row[0]))
    if first_count < 3:
        return None
    second_options = [
        (hour, count)
        for hour, count in counts.items()
        if min((hour - first_hour) % 24, (first_hour - hour) % 24) >= 2
    ]
    second = max(second_options, key=lambda row: (row[1], -row[0]), default=None)
    if second is None or second[1] < first_count * 0.6:
        text = f"Чаще всего ешь около {first_hour:02d}:00."
        supporting = {"hour_1": str(first_hour)}
        signal = first_count / max(1, len(context.meals))
    else:
        hours = sorted([first_hour, second[0]])
        text = f"Чаще всего ешь в {hours[0]:02d}:00 и {hours[1]:02d}:00."
        supporting = {"hour_1": str(hours[0]), "hour_2": str(hours[1])}
        signal = (first_count + second[1]) / max(1, len(context.meals))
    return InsightCandidate(
        kind="time_of_day_eating",
        text=text,
        signal_strength=signal,
        recency_factor=_recency_factor(context.days),
        supporting_numbers={
            **supporting,
            **{f"h{h:02d}": str(c) for h, c in sorted(counts.items())},
        },
    )


def _top_repeat_products(context: InsightContext) -> InsightCandidate | None:
    if len(_tracked_days(context.meals)) < MIN_TRACKED_DAYS_FOR_INSIGHTS:
        return None
    names = [_meal_name(meal) for meal in context.meals]
    counts = Counter(name for name in names if name)
    top = [(name, count) for name, count in counts.most_common(3) if count >= 3]
    if not top:
        return None
    if len(top) == 1:
        name, count = top[0]
        text = (
            f"Чаще всего ешь: {name} ({count}×) — "
            "это твоя самая частая позиция."
        )
    else:
        joined = ", ".join(f"{name} ({count}×)" for name, count in top)
        text = f"Чаще всего: {joined}."
        if len(text) > 70 and len(top) > 2:
            joined = ", ".join(f"{name} ({count}×)" for name, count in top[:2])
            text = f"Чаще всего: {joined}."
    return InsightCandidate(
        kind="top_repeat_products",
        text=text,
        signal_strength=top[0][1] / max(1, len(context.meals)),
        recency_factor=_recency_factor(context.days),
        supporting_numbers={
            f"n{index + 1}": str(count) for index, (_, count) in enumerate(top)
        },
    )


def _late_meal_share(context: InsightContext) -> InsightCandidate | None:
    if len(_tracked_days(context.meals)) < MIN_TRACKED_DAYS_FOR_INSIGHTS:
        return None
    meals = [meal for meal in context.meals if meal.total_kcal > 0]
    if not meals:
        return None
    late_count = sum(1 for meal in meals if meal.meal_window in {"late", "night_cap"})
    share = late_count / len(meals)
    if share < 0.25:
        return None
    pct = round(share * 100)
    per_week = round(late_count / context.days * 7)
    threshold = _late_threshold_label(context.anchor_minutes)
    return InsightCandidate(
        kind="late_meal_share",
        text=(
            f"Около {pct}% твоих приёмов еды — после {threshold}. "
            f"{per_week} раз в неделю в среднем."
        ),
        signal_strength=share,
        recency_factor=_recency_factor(context.days),
        supporting_numbers={"pct": str(pct), "count_per_week": str(per_week)},
    )


def _today_morning(context: InsightContext) -> InsightCandidate | None:
    today = local_now().date()
    today_meals = [
        meal
        for meal in context.meals
        if meal.local_date == today and meal.meal_window == "start"
    ]
    if not today_meals:
        return None
    historical_days = sorted(day for day in _tracked_days(context.meals) if day < today)
    if len(historical_days) < 7:
        return None
    today_kcal = sum(meal.total_kcal for meal in today_meals)
    historical = [
        sum(
            meal.total_kcal
            for meal in context.meals
            if meal.local_date == day and meal.meal_window == "start"
        )
        for day in historical_days
    ]
    historical = [value for value in historical if value > 0]
    if len(historical) < 5:
        return None
    baseline = median(historical)
    if baseline <= 0:
        return None
    if today_kcal > baseline * 1.2:
        text = "К утру немного больше обычного."
    elif today_kcal >= baseline * 0.8:
        text = "Похоже на твой обычный завтрак."
    else:
        last = max(today_meals, key=lambda meal: meal.eaten_at)
        text = (
            f"{_format_int(today_kcal)} ккал к {last.hour:02d}:00 — "
            "пока меньше обычного."
        )
    return InsightCandidate(
        kind="today_morning",
        text=text,
        signal_strength=abs(today_kcal - baseline) / baseline if baseline else 0.5,
        recency_factor=1.0,
        supporting_numbers={"today_morning_kcal": str(round(today_kcal))},
    )


def _meal_predictability(context: InsightContext) -> InsightCandidate | None:
    groups: dict[str, list[float]] = defaultdict(list)
    for meal in context.meals:
        response = meal.postprandial_response or {}
        delta = _number(response.get("delta_max"))
        if delta is None:
            continue
        if response.get("delayed_peak_likely") is True:
            continue
        if response.get("glycemic_response") in {None, "unknown"}:
            continue
        name = _meal_name(meal)
        if not name:
            continue
        groups[name].append(delta)

    candidates = []
    for name, values in groups.items():
        if len(values) < 5:
            continue
        spread = pstdev(values) if len(values) > 1 else 0.0
        if spread <= 1.0:
            candidates.append((spread, name, values))
    if not candidates:
        return None

    spread, name, values = sorted(candidates, key=lambda row: (row[0], row[1]))[0]
    mean_delta = sum(values) / len(values)
    return InsightCandidate(
        kind="meal_predictability",
        text=(
            f"{name}: обычно похожий ответ глюкозы. "
            f"Средний подъем около {_format_mmol(mean_delta)} ммоль/л."
        ),
        signal_strength=max(0.1, 1.0 / max(spread, 0.2)),
        recency_factor=_recency_factor(context.days),
        supporting_numbers={
            "samples": str(len(values)),
            "mean_delta_mmol_l": f"{mean_delta:.2f}",
            "stdev_mmol_l": f"{spread:.2f}",
        },
    )


def _evening_lows(context: InsightContext) -> InsightCandidate | None:
    episodes = _low_episodes(context.glucose_points)
    if len(episodes) < 3:
        return None
    hour_counts = Counter(local_wall_time(episode[0]).hour for episode in episodes)
    evening_hours = {19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6}
    evening_count = sum(
        count for hour, count in hour_counts.items() if hour in evening_hours
    )
    share = evening_count / len(episodes)
    if share < 0.6:
        return None
    pct = round(share * 100)
    return InsightCandidate(
        kind="evening_lows",
        text=f"{pct}% низких значений пришлись на 19:00-07:00.",
        signal_strength=share,
        recency_factor=_recency_factor(context.days),
        supporting_numbers={"pct": str(pct), "episodes": str(len(episodes))},
    )


def _hypo_recovery_pattern(context: InsightContext) -> InsightCandidate | None:
    sweet_after_low = [
        meal
        for meal in context.meals
        if _sweet_kcal(meal) > 0
        and meal.meal_window in {"late", "night_cap"}
        and (meal.postprandial_response or {}).get("is_hypo_recovery") is True
    ]
    sweet_late = [
        meal
        for meal in context.meals
        if _sweet_kcal(meal) > 0 and meal.meal_window in {"late", "night_cap"}
    ]
    if len(sweet_late) < 5:
        return None
    share = len(sweet_after_low) / len(sweet_late)
    if share < 0.3:
        return None
    pct = round(share * 100)
    return InsightCandidate(
        kind="hypo_recovery_pattern",
        text=f"{pct}% позднего сладкого было после низкой глюкозы.",
        signal_strength=share,
        recency_factor=_recency_factor(context.days),
        supporting_numbers={
            "pct": str(pct),
            "count": str(len(sweet_after_low)),
            "sweet_late_count": str(len(sweet_late)),
        },
    )


def _late_meal_glucose_footprint(context: InsightContext) -> InsightCandidate | None:
    night_meals = [meal for meal in context.meals if meal.meal_window == "night_cap"]
    if len(night_meals) < 5 or not context.glucose_points:
        return None

    point_values = [point.value_mmol_l for point in context.glucose_points]
    baseline = sum(point_values) / len(point_values)
    after_values: list[float] = []
    for meal in night_meals:
        end = meal.eaten_at + timedelta(hours=3)
        after_values.extend(
            point.value_mmol_l
            for point in context.glucose_points
            if meal.eaten_at <= point.timestamp <= end
        )
    if len(after_values) < 12:
        return None
    after_avg = sum(after_values) / len(after_values)
    delta = after_avg - baseline
    if delta < 0.5:
        return None
    return InsightCandidate(
        kind="late_meal_glucose_footprint",
        text=(
            "После ночных приемов еды средняя глюкоза в следующие 3 часа "
            f"выше примерно на {_format_mmol(delta)} ммоль/л."
        ),
        signal_strength=min(1.0, delta / 2.0),
        recency_factor=_recency_factor(context.days),
        supporting_numbers={
            "night_meal_count": str(len(night_meals)),
            "delta_mmol_l": f"{delta:.2f}",
        },
    )


def _low_episodes(points: list[InsightGlucosePoint]) -> list[tuple[datetime, datetime]]:
    lows = [point for point in points if point.value_mmol_l < 4.0]
    if not lows:
        return []
    episodes: list[tuple[datetime, datetime]] = []
    start = lows[0].timestamp
    previous = lows[0].timestamp
    for point in lows[1:]:
        if (point.timestamp - previous).total_seconds() > 30 * 60:
            episodes.append((start, previous))
            start = point.timestamp
        previous = point.timestamp
    episodes.append((start, previous))
    return episodes


def _tracked_days(meals: list[InsightMeal]) -> set[date_type]:
    return {meal.local_date for meal in meals if meal.total_kcal > 0}


def _sweet_kcal(meal: InsightMeal) -> float:
    if meal.taste_profile in {"sweet", "drink_sweet"}:
        return meal.total_kcal
    return sum(_sweet_item_kcal(item) for item in meal.items)


def _sweet_item_kcal(item: InsightMealItem) -> float:
    if item.product_category == "sweet":
        return item.kcal
    if item.product_category is not None:
        return 0.0
    if is_sweet_text((item.name, item.product_name, item.product_brand)):
        return item.kcal
    return 0.0


def _meal_name(meal: InsightMeal) -> str | None:
    if meal.title and meal.title.strip():
        return meal.title.strip()
    for item in meal.items:
        for value in (item.product_name, item.name):
            if value and value.strip():
                return value.strip()
    return None


def _fallback_window(hour: int) -> str:
    if 6 <= hour < 12:
        return "start"
    if 12 <= hour < 17:
        return "mid"
    if 17 <= hour < 22:
        return "late"
    return "night_cap"


def _late_threshold_label(anchor_minutes: int | None) -> str:
    minutes = (
        (anchor_minutes + 8 * 60) % (24 * 60)
        if anchor_minutes is not None
        else 21 * 60
    )
    return f"{minutes // 60:02d}:00"


def _day_label(weekdays: list[int]) -> str:
    unique = sorted(set(weekdays))
    if set(unique) == {5, 6}:
        return "выходным"
    labels = [WEEKDAY_DATIVE[weekday] for weekday in unique]
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} и {labels[-1]}"


def _recency_factor(days: int) -> float:
    if days <= 7:
        return 0.7
    return 0.5


def _format_int(value: float) -> str:
    return f"{round(value):,}".replace(",", " ")


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _cache_signature(context: InsightContext) -> str:
    parts = ["meals=empty"]
    if context.meals:
        newest_meal = max(local_wall_time(meal.eaten_at) for meal in context.meals)
        parts[0] = f"meals={len(context.meals)}:{newest_meal.isoformat()}"
    if context.glucose_points:
        newest_glucose = max(
            local_wall_time(point.timestamp) for point in context.glucose_points
        )
        parts.append(f"glucose={len(context.glucose_points)}:{newest_glucose.isoformat()}")
    return "|".join(parts)


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _format_mmol(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _assert_copy_allowed(text: str) -> None:
    lowered = text.casefold()
    matches = [term for term in BANNED_COPY if term in lowered]
    if matches:
        raise ValueError(f"Insight text contains banned wording: {', '.join(matches)}")


def rendered_template_samples_for_lint() -> tuple[str, ...]:
    """Return representative rendered templates for CI copy lint."""
    return (
        "Привычный для тебя ритм. Около 1 970 ккал в день за последние 14 дней.",
        (
            "По средам и пятницам вечером сладкого больше всего — "
            "около 380 ккал из десертов и напитков."
        ),
        "Чаще всего ешь в 13:00 и 19:00.",
        (
            "Чаще всего: Протеиновое брауни (7×), "
            "Сырок глазированный (6×), Лаваш с курицей (5×)."
        ),
        "Около 38% твоих приёмов еды — после 21:00. 5 раз в неделю в среднем.",
        "Похоже на твой обычный завтрак.",
    )
