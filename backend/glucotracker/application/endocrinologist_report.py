"""Backend-owned endocrinologist report aggregation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, time, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.config import get_settings
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)

SlotKey = Literal["breakfast", "lunch", "dinner", "snack"]
MainSlotKey = Literal["breakfast", "lunch", "dinner"]

EMPTY = "—"
MEAL_CLUSTER_WINDOW = timedelta(minutes=30)
INSULIN_WINDOW_BEFORE = timedelta(minutes=30)
INSULIN_WINDOW_AFTER = timedelta(minutes=90)
GLUCOSE_WINDOW_BEFORE = timedelta(minutes=60)
GLUCOSE_WINDOW_AFTER = timedelta(minutes=180)

SLOT_LABELS: dict[SlotKey, str] = {
    "breakfast": "Завтрак",
    "lunch": "Обед",
    "dinner": "Ужин",
    "snack": "Перекусы",
}
MONTHS_RU = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


@dataclass(frozen=True)
class GlucosePoint:
    """One local CGM reading."""

    timestamp: datetime
    value: float


@dataclass(frozen=True)
class InsulinPoint:
    """One local Nightscout insulin event."""

    timestamp: datetime
    units: float
    key: str


@dataclass
class SlotDailyStats:
    """Daily slot totals used for meal-linked insulin metrics."""

    carbs: float = 0
    insulin: float = 0


@dataclass
class DailyStats:
    """One calendar day in the selected report range."""

    date: date_type
    carbs: float = 0
    insulin: float = 0
    glucose: list[GlucosePoint] = field(default_factory=list)
    slots: dict[MainSlotKey, SlotDailyStats] = field(
        default_factory=lambda: {
            "breakfast": SlotDailyStats(),
            "lunch": SlotDailyStats(),
            "dinner": SlotDailyStats(),
        }
    )


@dataclass
class FoodEpisode:
    """Grouped accepted meals plus linked Nightscout context."""

    id: str
    meals: list[Meal]
    start: datetime
    end: datetime
    slot: SlotKey
    carbs: float
    linked_insulin: list[InsulinPoint] = field(default_factory=list)
    glucose_before: float | None = None
    glucose_after: float | None = None

    @property
    def insulin(self) -> float:
        """Return linked insulin units for this food episode."""
        return sum(event.units for event in self.linked_insulin)


class EndocrinologistReportService:
    """Build one-page PDF report data from locally stored facts."""

    def __init__(self, session: Session, now: datetime | None = None) -> None:
        self.session = session
        self.now = _local_wall_time(now) if now is not None else _now_local()

    def build(self, from_date: date_type, to_date: date_type) -> dict[str, object]:
        """Return presentation-ready report data for a selected date range."""
        from_datetime = datetime.combine(from_date, time.min)
        to_datetime = datetime.combine(to_date, time.max)
        period_days = _enumerate_days(from_date, to_date)
        daily = {day: DailyStats(day) for day in period_days}

        meals = self._meals(from_datetime, to_datetime)
        episodes = _build_food_episodes(meals)

        selected_glucose = _glucose_points(self._glucose(from_datetime, to_datetime))
        extended_glucose = _glucose_points(
            self._glucose(
                from_datetime - GLUCOSE_WINDOW_BEFORE,
                to_datetime + GLUCOSE_WINDOW_AFTER,
            )
        )
        selected_insulin = _insulin_points(self._insulin(from_datetime, to_datetime))
        extended_insulin = _insulin_points(
            self._insulin(
                from_datetime - INSULIN_WINDOW_BEFORE,
                to_datetime + INSULIN_WINDOW_AFTER,
            )
        )

        _link_insulin_to_episodes(episodes, extended_insulin)
        _add_glucose_windows_to_episodes(episodes, extended_glucose)
        _add_daily_context(daily, episodes, selected_glucose, selected_insulin)

        day_rows = [_daily_row(day) for day in daily.values()]
        shown_rows = _select_daily_rows(day_rows)
        days_with_food = sum(1 for day in daily.values() if day.carbs > 0)
        cgm_coverage = _coverage_percent(len(selected_glucose), len(period_days))
        linked_insulin_total = sum(episode.insulin for episode in episodes)
        linked_carbs_total = sum(
            episode.carbs for episode in episodes if episode.insulin > 0
        )

        notes = []
        if not selected_glucose:
            notes.append("CGM нет за период")
        if not selected_insulin and linked_insulin_total <= 0:
            notes.append("Инсулин не найден")

        warning = (
            f"Данных мало: {days_with_food} дней с едой из "
            f"{len(period_days)} выбранных"
            if days_with_food < 7
            else _missing_food_warning(list(daily.values()))
        )

        daily_rows_note = (
            f"Показано {len(shown_rows)} из {len(day_rows)} дней"
            if len(shown_rows) < len(day_rows)
            else None
        )

        return {
            "app_name": "glucotracker",
            "title": "Отчёт для эндокринолога",
            "period_label": f"Период: {_format_period(from_date, to_date)}",
            "generated_label": f"Сгенерировано: {_format_date_long(self.now.date())}",
            "chips": [
                {"label": f"{len(period_days)} дней"},
                {"label": f"{days_with_food}/{len(period_days)} дней с едой"},
                {
                    "label": (
                        f"CGM coverage {cgm_coverage}%"
                        if cgm_coverage is not None
                        else f"CGM coverage {EMPTY}"
                    )
                },
                {"label": f"{len(episodes)} пищевых эпизода"},
            ],
            "warning": warning,
            "notes": notes,
            "kpis": _kpis(
                list(daily.values()),
                episodes,
                selected_glucose,
                linked_carbs_total,
                linked_insulin_total,
            ),
            "meal_profile_rows": _meal_profile_rows(episodes),
            "daily_rows": day_rows,
            "shown_daily_rows": shown_rows,
            "daily_median_row": _daily_median_row(list(daily.values())),
            "daily_rows_note": daily_rows_note,
            "bottom_metrics": _bottom_metrics(selected_glucose),
            "footer": (
                "Инсулин получен из Nightscout (только чтение). "
                "Наблюдаемый УК - эмпирический показатель: граммы углеводов "
                "на 1 ЕД зарегистрированного meal-linked инсулина по эпизодам "
                "питания. Отчёт информационный и не является медицинской "
                "рекомендацией."
            ),
        }

    def _meals(self, from_datetime: datetime, to_datetime: datetime) -> list[Meal]:
        return list(
            self.session.scalars(
                select(Meal)
                .where(
                    Meal.status == MealStatus.accepted,
                    Meal.eaten_at >= from_datetime,
                    Meal.eaten_at <= to_datetime,
                )
                .order_by(Meal.eaten_at.asc(), Meal.created_at.asc())
            )
        )

    def _glucose(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[NightscoutGlucoseEntry]:
        return list(
            self.session.scalars(
                select(NightscoutGlucoseEntry)
                .where(
                    NightscoutGlucoseEntry.timestamp >= from_datetime,
                    NightscoutGlucoseEntry.timestamp <= to_datetime,
                )
                .order_by(NightscoutGlucoseEntry.timestamp.asc())
            )
        )

    def _insulin(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[NightscoutInsulinEvent]:
        return list(
            self.session.scalars(
                select(NightscoutInsulinEvent)
                .where(
                    NightscoutInsulinEvent.timestamp >= from_datetime,
                    NightscoutInsulinEvent.timestamp <= to_datetime,
                )
                .order_by(NightscoutInsulinEvent.timestamp.asc())
            )
        )


def _build_food_episodes(meals: list[Meal]) -> list[FoodEpisode]:
    clusters: list[list[Meal]] = []
    for meal in meals:
        meal_at = _local_wall_time(meal.eaten_at)
        if not clusters:
            clusters.append([meal])
            continue
        previous = clusters[-1][-1]
        previous_at = _local_wall_time(previous.eaten_at)
        if meal_at - previous_at <= MEAL_CLUSTER_WINDOW:
            clusters[-1].append(meal)
        else:
            clusters.append([meal])

    episodes: list[FoodEpisode] = []
    for index, cluster in enumerate(clusters):
        start = _local_wall_time(cluster[0].eaten_at)
        end = _local_wall_time(cluster[-1].eaten_at)
        episodes.append(
            FoodEpisode(
                id=f"episode-{start.isoformat()}-{index}",
                meals=cluster,
                start=start,
                end=end,
                slot=_meal_slot(start),
                carbs=sum(meal.total_carbs_g for meal in cluster),
            )
        )
    return episodes


def _link_insulin_to_episodes(
    episodes: list[FoodEpisode],
    insulin: list[InsulinPoint],
) -> None:
    linked_keys: set[str] = set()
    for episode in episodes:
        window_start = episode.start - INSULIN_WINDOW_BEFORE
        window_end = episode.end + INSULIN_WINDOW_AFTER
        for event in insulin:
            if event.key in linked_keys:
                continue
            if window_start <= event.timestamp <= window_end:
                episode.linked_insulin.append(event)
                linked_keys.add(event.key)


def _add_glucose_windows_to_episodes(
    episodes: list[FoodEpisode],
    glucose: list[GlucosePoint],
) -> None:
    for episode in episodes:
        nearby = [
            point
            for point in glucose
            if episode.start - GLUCOSE_WINDOW_BEFORE
            <= point.timestamp
            <= episode.end + GLUCOSE_WINDOW_AFTER
        ]
        episode.glucose_before = _glucose_before(nearby, episode.start)
        episode.glucose_after = _glucose_after(nearby, episode.end)


def _add_daily_context(
    daily: dict[date_type, DailyStats],
    episodes: list[FoodEpisode],
    glucose: list[GlucosePoint],
    insulin: list[InsulinPoint],
) -> None:
    for point in glucose:
        day = daily.get(point.timestamp.date())
        if day is not None:
            day.glucose.append(point)

    for event in insulin:
        day = daily.get(event.timestamp.date())
        if day is not None:
            day.insulin += event.units

    for episode in episodes:
        day = daily.get(episode.start.date())
        if day is None:
            continue
        day.carbs += episode.carbs
        if episode.slot != "snack":
            slot = day.slots[episode.slot]
            slot.carbs += episode.carbs
            slot.insulin += episode.insulin


def _kpis(
    days: list[DailyStats],
    episodes: list[FoodEpisode],
    glucose: list[GlucosePoint],
    linked_carbs_total: float,
    linked_insulin_total: float,
) -> list[dict[str, str]]:
    before_values = [
        episode.glucose_before
        for episode in episodes
        if episode.glucose_before is not None
    ]
    after_values = [
        episode.glucose_after
        for episode in episodes
        if episode.glucose_after is not None
    ]
    observed_ratio = (
        linked_carbs_total / linked_insulin_total if linked_insulin_total > 0 else None
    )
    tir = _percent_in_range(glucose, 3.9, 10.0)
    return [
        _insulin_kpi("ИНСУЛИН ЗАВТРАК", _daily_slot_values(days, "breakfast")),
        _insulin_kpi("ИНСУЛИН ОБЕД", _daily_slot_values(days, "lunch")),
        _insulin_kpi("ИНСУЛИН УЖИН", _daily_slot_values(days, "dinner")),
        _insulin_kpi(
            "ИНСУЛИН ЗА ДЕНЬ",
            [day.insulin for day in days if day.insulin > 0],
        ),
        _glucose_kpi("САХАР ДО ЕДЫ", before_values),
        _glucose_kpi("САХАР ПОСЛЕ ЕДЫ", after_values),
        {
            "label": "НАБЛЮДАЕМЫЙ УК",
            "value": (
                EMPTY
                if observed_ratio is None
                else _format_number(observed_ratio, 1)
            ),
            "unit": "" if observed_ratio is None else "г/ЕД",
            "caption": "по всем эпизодам",
        },
        {
            "label": "TIR 3.9-10.0",
            "value": EMPTY if tir is None else _format_number(tir, 0),
            "unit": "" if tir is None else "%",
            "caption": "за выбранный период" if glucose else "CGM нет",
        },
    ]


def _meal_profile_rows(episodes: list[FoodEpisode]) -> list[dict[str, str]]:
    rows = [
        _meal_profile_row(
            slot,
            [episode for episode in episodes if episode.slot == slot],
        )
        for slot in ("breakfast", "lunch", "dinner", "snack")
    ]
    rows.append(_meal_profile_row("total", episodes))
    return rows


def _meal_profile_row(
    slot: SlotKey | Literal["total"],
    episodes: list[FoodEpisode],
) -> dict[str, str]:
    carbs = [episode.carbs for episode in episodes if episode.carbs > 0]
    insulin = [episode.insulin for episode in episodes if episode.insulin > 0]
    before = [
        episode.glucose_before
        for episode in episodes
        if episode.glucose_before is not None
    ]
    after = [
        episode.glucose_after
        for episode in episodes
        if episode.glucose_after is not None
    ]
    linked_insulin = sum(episode.insulin for episode in episodes)
    linked_carbs = sum(episode.carbs for episode in episodes if episode.insulin > 0)
    ratio = linked_carbs / linked_insulin if linked_insulin > 0 else None
    return {
        "key": slot,
        "label": "Итого / медиана" if slot == "total" else SLOT_LABELS[slot],
        "episodes": str(len(episodes)),
        "carbs": _format_nullable(_median(carbs), 0),
        "insulin": _format_nullable(_median(insulin), 1),
        "glucose_before": _format_nullable(_median(before), 1),
        "glucose_after": _format_nullable(_median(after), 1),
        "observed_ratio": (
            EMPTY if ratio is None else f"{_format_number(ratio, 1)} г/ЕД"
        ),
    }


def _daily_row(day: DailyStats) -> dict[str, object]:
    tir = _percent_in_range(day.glucose, 3.9, 10.0)
    hypo = any(point.value < 3.9 for point in day.glucose)
    return {
        "date": day.date.isoformat(),
        "date_label": day.date.strftime("%d.%m"),
        "carbs": _format_number(day.carbs, 0) if day.carbs > 0 else EMPTY,
        "insulin": (
            _format_compact_number(day.insulin, 1) if day.insulin > 0 else EMPTY
        ),
        "tir": EMPTY if tir is None else f"{_format_number(tir, 0)}%",
        "hypo": "1" if hypo else "0",
        "breakfast": _slot_cell(day.slots["breakfast"]),
        "lunch": _slot_cell(day.slots["lunch"]),
        "dinner": _slot_cell(day.slots["dinner"]),
        "flagged": _is_flagged_day(day, tir),
    }


def _daily_median_row(days: list[DailyStats]) -> dict[str, object]:
    tir_values = [_percent_in_range(day.glucose, 3.9, 10.0) for day in days]
    valid_tir = [value for value in tir_values if value is not None]
    return {
        "date": "median",
        "date_label": "Медиана",
        "carbs": _format_nullable(
            _median([day.carbs for day in days if day.carbs > 0]),
            0,
        ),
        "insulin": _format_nullable(
            _median([day.insulin for day in days if day.insulin > 0]),
            1,
        ),
        "tir": _format_percent(_median(valid_tir)),
        "hypo": str(
            sum(1 for day in days if any(point.value < 3.9 for point in day.glucose))
        ),
        "breakfast": _median_slot_cell([day.slots["breakfast"] for day in days]),
        "lunch": _median_slot_cell([day.slots["lunch"] for day in days]),
        "dinner": _median_slot_cell([day.slots["dinner"] for day in days]),
        "flagged": False,
    }


def _bottom_metrics(glucose: list[GlucosePoint]) -> list[dict[str, str]]:
    avg_glucose = _average([point.value for point in glucose])
    hypo = _percent_below(glucose, 3.9)
    hyper = _percent_above(glucose, 10.0)
    return [
        {
            "label": "Средняя глюкоза",
            "value": EMPTY if avg_glucose is None else _format_number(avg_glucose, 1),
            "unit": "" if avg_glucose is None else "ммоль/л",
        },
        {
            "label": "Время <3.9",
            "value": EMPTY if hypo is None else _format_number(hypo, 0),
            "unit": "" if hypo is None else "%",
        },
        {
            "label": "Время >10",
            "value": EMPTY if hyper is None else _format_number(hyper, 0),
            "unit": "" if hyper is None else "%",
        },
        {
            "label": "Окна расчёта",
            "value": "до еды -30...-15 мин; после +90...+150 мин",
            "unit": "",
        },
    ]


def _select_daily_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if len(rows) <= 9:
        return rows
    latest = rows[-7:]
    latest_dates = {row["date"] for row in latest}
    flagged = [
        row
        for row in rows
        if row["flagged"] is True and row["date"] not in latest_dates
    ][-2:]
    return (flagged + latest)[-9:]


def _glucose_before(points: list[GlucosePoint], first_meal: datetime) -> float | None:
    direct = [
        point.value
        for point in points
        if first_meal - timedelta(minutes=30)
        <= point.timestamp
        <= first_meal - timedelta(minutes=15)
    ]
    if direct:
        return _median(direct)
    return _nearest_glucose_value(
        points,
        first_meal,
        first_meal - timedelta(minutes=45),
        first_meal + timedelta(minutes=5),
    )


def _glucose_after(points: list[GlucosePoint], last_meal: datetime) -> float | None:
    direct = [
        point.value
        for point in points
        if last_meal + timedelta(minutes=90)
        <= point.timestamp
        <= last_meal + timedelta(minutes=150)
    ]
    if direct:
        return _median(direct)
    anchor = last_meal + timedelta(minutes=120)
    return _nearest_glucose_value(
        points,
        anchor,
        anchor - timedelta(minutes=45),
        anchor + timedelta(minutes=45),
    )


def _nearest_glucose_value(
    points: list[GlucosePoint],
    anchor: datetime,
    from_datetime: datetime,
    to_datetime: datetime,
) -> float | None:
    best: GlucosePoint | None = None
    best_distance = float("inf")
    for point in points:
        if not from_datetime <= point.timestamp <= to_datetime:
            continue
        distance = abs((point.timestamp - anchor).total_seconds())
        if distance < best_distance:
            best = point
            best_distance = distance
    return best.value if best is not None else None


def _daily_slot_values(days: list[DailyStats], slot: MainSlotKey) -> list[float]:
    return [day.slots[slot].insulin for day in days if day.slots[slot].insulin > 0]


def _insulin_kpi(label: str, values: list[float]) -> dict[str, str]:
    value = _median(values)
    return {
        "label": label,
        "value": EMPTY if value is None else _format_number(value, 1),
        "unit": "" if value is None else "ЕД",
        "caption": "медиана за период",
    }


def _glucose_kpi(label: str, values: list[float]) -> dict[str, str]:
    value = _median(values)
    return {
        "label": label,
        "value": EMPTY if value is None else _format_number(value, 1),
        "unit": "" if value is None else "ммоль/л",
        "caption": "медиана за период",
    }


def _slot_cell(slot: SlotDailyStats) -> str:
    if slot.carbs <= 0 and slot.insulin <= 0:
        return EMPTY
    carbs = f"{_format_number(slot.carbs, 0)}г" if slot.carbs > 0 else EMPTY
    insulin = (
        f"{_format_compact_number(slot.insulin, 1)}Е"
        if slot.insulin > 0
        else EMPTY
    )
    return f"{carbs} / {insulin}"


def _median_slot_cell(slots: list[SlotDailyStats]) -> str:
    carbs = _median([slot.carbs for slot in slots if slot.carbs > 0])
    insulin = _median([slot.insulin for slot in slots if slot.insulin > 0])
    if carbs is None and insulin is None:
        return EMPTY
    carbs_text = EMPTY if carbs is None else f"{_format_number(carbs, 0)}г"
    insulin_text = (
        EMPTY if insulin is None else f"{_format_compact_number(insulin, 1)}Е"
    )
    return f"{carbs_text} / {insulin_text}"


def _meal_slot(value: datetime) -> SlotKey:
    if 6 <= value.hour <= 10:
        return "breakfast"
    if 11 <= value.hour <= 15:
        return "lunch"
    if 16 <= value.hour <= 21:
        return "dinner"
    return "snack"


def _coverage_percent(reading_count: int, day_count: int) -> int | None:
    if reading_count <= 0:
        return None
    expected = max(day_count * 24 * 12, 1)
    return min(100, round((reading_count / expected) * 100))


def _percent_in_range(
    points: list[GlucosePoint],
    min_value: float,
    max_value: float,
) -> float | None:
    if not points:
        return None
    count = sum(1 for point in points if min_value <= point.value <= max_value)
    return (count / len(points)) * 100


def _percent_below(points: list[GlucosePoint], threshold: float) -> float | None:
    if not points:
        return None
    return (sum(1 for point in points if point.value < threshold) / len(points)) * 100


def _percent_above(points: list[GlucosePoint], threshold: float) -> float | None:
    if not points:
        return None
    return (sum(1 for point in points if point.value > threshold) / len(points)) * 100


def _is_flagged_day(day: DailyStats, tir: float | None) -> bool:
    if tir is not None and tir < 50:
        return True
    if any(point.value < 3.0 for point in day.glucose):
        return True
    return _glucose_minutes(day.glucose, lambda value: value < 3.9) >= 15 or (
        _glucose_minutes(day.glucose, lambda value: value > 13.9) >= 120
    )


def _glucose_minutes(
    points: list[GlucosePoint],
    predicate: Callable[[float], bool],
) -> float:
    if not points:
        return 0
    if len(points) == 1:
        return 5 if predicate(points[0].value) else 0
    minutes = 0.0
    for index, point in enumerate(points[:-1]):
        if not predicate(point.value):
            continue
        delta = (points[index + 1].timestamp - point.timestamp).total_seconds() / 60
        minutes += min(max(delta, 0), 15)
    return minutes


def _missing_food_warning(days: list[DailyStats]) -> str | None:
    first_food_index = next(
        (index for index, day in enumerate(days) if day.carbs > 0),
        None,
    )
    if first_food_index is not None and first_food_index > 0:
        return f"Данных мало: {first_food_index} дня в начале периода без еды"
    return None


def _glucose_points(rows: list[NightscoutGlucoseEntry]) -> list[GlucosePoint]:
    return [
        GlucosePoint(timestamp=_local_wall_time(row.timestamp), value=row.value_mmol_l)
        for row in rows
        if row.value_mmol_l is not None
    ]


def _insulin_points(rows: list[NightscoutInsulinEvent]) -> list[InsulinPoint]:
    points: list[InsulinPoint] = []
    for row in rows:
        if row.insulin_units is None or row.insulin_units <= 0:
            continue
        timestamp = _local_wall_time(row.timestamp)
        points.append(
            InsulinPoint(
                timestamp=timestamp,
                units=row.insulin_units,
                key=row.source_key
                or row.nightscout_id
                or f"{timestamp.isoformat()}:{row.insulin_units}",
            )
        )
    return points


def _enumerate_days(from_date: date_type, to_date: date_type) -> list[date_type]:
    result: list[date_type] = []
    cursor = from_date
    while cursor <= to_date:
        result.append(cursor)
        cursor += timedelta(days=1)
    return result


def _median(values: list[float | int]) -> float | None:
    finite = sorted(float(value) for value in values if isinstance(value, int | float))
    if not finite:
        return None
    middle = len(finite) // 2
    if len(finite) % 2:
        return finite[middle]
    return (finite[middle - 1] + finite[middle]) / 2


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _format_nullable(value: float | None, digits: int) -> str:
    return EMPTY if value is None else _format_number(value, digits)


def _format_percent(value: float | None) -> str:
    return EMPTY if value is None else f"{_format_number(value, 0)}%"


def _format_number(value: float, digits: int) -> str:
    rounded = round(value, digits)
    return f"{rounded:.{digits}f}".replace(".", ",")


def _format_compact_number(value: float, digits: int) -> str:
    text = _format_number(value, digits)
    if "," not in text:
        return text
    return text.rstrip("0").rstrip(",")


def _format_period(from_date: date_type, to_date: date_type) -> str:
    if from_date == to_date:
        return _format_date_long(from_date)
    if from_date.year == to_date.year and from_date.month == to_date.month:
        return (
            f"{from_date.day}-{to_date.day} "
            f"{MONTHS_RU[to_date.month]} {to_date.year}"
        )
    if from_date.year == to_date.year:
        return (
            f"{from_date.day} {MONTHS_RU[from_date.month]} - "
            f"{to_date.day} {MONTHS_RU[to_date.month]} {to_date.year}"
        )
    return f"{_format_date_long(from_date)} - {_format_date_long(to_date)}"


def _format_date_long(value: date_type) -> str:
    return f"{value.day} {MONTHS_RU[value.month]} {value.year}"


def _now_local() -> datetime:
    return datetime.now(get_settings().local_zoneinfo).replace(tzinfo=None)


def _local_wall_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(get_settings().local_zoneinfo).replace(tzinfo=None)
