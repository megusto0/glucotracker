from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "backend" / "data" / "glucotracker.sqlite3"
OUT_DIR = ROOT / "docs" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "glucotracker-endocrinologist-2026-04-28_2026-04-29.pdf"

FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("GT-Regular", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("GT-Bold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("GT-Mono", str(FONT_DIR / "consola.ttf")))
pdfmetrics.registerFont(TTFont("GT-MonoBold", str(FONT_DIR / "consolab.ttf")))

PAPER = colors.HexColor("#FFFFFF")
BG = colors.HexColor("#F6F4EE")
TEXT = colors.HexColor("#0A0A0A")
MUTED = colors.HexColor("#6F6A61")
BORDER = colors.HexColor("#D8D0C3")
WARN_BG = colors.HexColor("#FFF8EA")
WARN_BORDER = colors.HexColor("#D9B77A")
WARN_TEXT = colors.HexColor("#8A6330")
EMPTY = "—"


@dataclass
class Meal:
    id: str
    ts: datetime
    title: str
    carbs: float
    kcal: float


@dataclass
class Glucose:
    ts: datetime
    value: float


@dataclass
class Insulin:
    key: str
    ts: datetime
    units: float


@dataclass
class Episode:
    meals: list[Meal]
    insulin: list[Insulin] = field(default_factory=list)
    glucose: list[Glucose] = field(default_factory=list)
    before: float | None = None
    after: float | None = None

    @property
    def start(self) -> datetime:
        return self.meals[0].ts

    @property
    def end(self) -> datetime:
        return self.meals[-1].ts

    @property
    def carbs(self) -> float:
        return sum(meal.carbs for meal in self.meals)

    @property
    def kcal(self) -> float:
        return sum(meal.kcal for meal in self.meals)

    @property
    def insulin_units(self) -> float:
        return sum(event.units for event in self.insulin)


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("T", " "))


def fmt_num(value: float | None, digits: int = 0) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return EMPTY
    if digits == 0:
        return f"{value:.0f}".replace(".", ",")
    return f"{value:.{digits}f}".replace(".", ",")


def fmt_pct(value: float | None) -> str:
    return EMPTY if value is None else f"{fmt_num(value, 0)}%"


def day_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def meal_slot(value: datetime) -> str:
    hour = value.hour
    if 6 <= hour <= 10:
        return "breakfast"
    if 11 <= hour <= 15:
        return "lunch"
    if 16 <= hour <= 21:
        return "dinner"
    return "snack"


SLOT_LABELS = {
    "breakfast": "Завтрак",
    "lunch": "Обед",
    "dinner": "Ужин",
    "snack": "Перекусы",
}


def median_or_none(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    return median(filtered) if filtered else None


def avg_or_none(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percent(values: list[float], predicate) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if predicate(value)) / len(values) * 100


def nearest_value(
    points: list[Glucose],
    anchor: datetime,
    before_min: int,
    after_min: int,
) -> float | None:
    low = anchor + timedelta(minutes=before_min)
    high = anchor + timedelta(minutes=after_min)
    candidates = [point for point in points if low <= point.ts <= high]
    if not candidates:
        return None
    return min(candidates, key=lambda point: abs((point.ts - anchor).total_seconds())).value


def glucose_before(points: list[Glucose], first_meal: datetime) -> float | None:
    values = [
        point.value
        for point in points
        if first_meal - timedelta(minutes=30)
        <= point.ts
        <= first_meal - timedelta(minutes=15)
    ]
    return median(values) if values else nearest_value(points, first_meal, -45, 5)


def glucose_after(points: list[Glucose], last_meal: datetime) -> float | None:
    values = [
        point.value
        for point in points
        if last_meal + timedelta(minutes=90)
        <= point.ts
        <= last_meal + timedelta(minutes=150)
    ]
    return (
        median(values)
        if values
        else nearest_value(points, last_meal + timedelta(minutes=120), -45, 45)
    )


def load_data() -> tuple[list[Meal], list[Glucose], list[Insulin]]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    meals = [
        Meal(
            id=row["id"],
            ts=parse_dt(row["eaten_at"]),
            title=row["title"] or "Приём пищи",
            carbs=float(row["total_carbs_g"] or 0),
            kcal=float(row["total_kcal"] or 0),
        )
        for row in conn.execute(
            """
            select id, eaten_at, title, total_carbs_g, total_kcal
            from meals
            where status = 'accepted'
            order by eaten_at asc, created_at asc
            """
        )
    ]
    if not meals:
        raise RuntimeError("No accepted meals found")

    from_date = meals[0].ts.date()
    to_date = meals[-1].ts.date()
    start_dt = datetime.combine(from_date, datetime.min.time())
    end_dt = datetime.combine(to_date, datetime.max.time()).replace(microsecond=0)
    glucose = [
        Glucose(parse_dt(row["timestamp"]), float(row["value_mmol_l"]))
        for row in conn.execute(
            """
            select timestamp, value_mmol_l
            from nightscout_glucose_entries
            where timestamp >= ? and timestamp <= ?
            order by timestamp
            """,
            (start_dt.isoformat(" "), end_dt.isoformat(" ")),
        )
    ]
    insulin = [
        Insulin(
            key=row["source_key"] or row["nightscout_id"] or row["timestamp"],
            ts=parse_dt(row["timestamp"]),
            units=float(row["insulin_units"] or 0),
        )
        for row in conn.execute(
            """
            select source_key, nightscout_id, timestamp, insulin_units
            from nightscout_insulin_events
            where timestamp >= ? and timestamp <= ?
            order by timestamp
            """,
            (start_dt.isoformat(" "), end_dt.isoformat(" ")),
        )
        if float(row["insulin_units"] or 0) > 0
    ]
    return meals, glucose, insulin


def build_episodes(
    meals: list[Meal],
    all_glucose: list[Glucose],
    all_insulin: list[Insulin],
) -> list[Episode]:
    episodes: list[Episode] = []
    for meal in meals:
        if episodes and meal.ts - episodes[-1].meals[-1].ts <= timedelta(minutes=30):
            episodes[-1].meals.append(meal)
        else:
            episodes.append(Episode([meal]))

    for episode in episodes:
        episode.insulin = [
            event
            for event in all_insulin
            if episode.start - timedelta(minutes=30)
            <= event.ts
            <= episode.end + timedelta(minutes=90)
        ]
        episode.glucose = [
            point
            for point in all_glucose
            if episode.start - timedelta(minutes=60)
            <= point.ts
            <= episode.end + timedelta(minutes=180)
        ]
        episode.before = glucose_before(episode.glucose, episode.start)
        episode.after = glucose_after(episode.glucose, episode.end)
    return episodes


def period_days(from_date: date, to_date: date) -> list[date]:
    return [
        from_date + timedelta(days=index)
        for index in range((to_date - from_date).days + 1)
    ]


def build_days(
    days_range: list[date],
    episodes: list[Episode],
    glucose: list[Glucose],
    insulin: list[Insulin],
):
    days = {
        day.isoformat(): {
            "date": day,
            "carbs": 0.0,
            "insulin": 0.0,
            "glucose": [],
            "slots": {
                key: {"carbs": 0.0, "insulin": 0.0}
                for key in ["breakfast", "lunch", "dinner"]
            },
        }
        for day in days_range
    }
    for point in glucose:
        if day_key(point.ts) in days:
            days[day_key(point.ts)]["glucose"].append(point.value)
    for event in insulin:
        if day_key(event.ts) in days:
            days[day_key(event.ts)]["insulin"] += event.units
    for episode in episodes:
        key = day_key(episode.start)
        if key not in days:
            continue
        days[key]["carbs"] += episode.carbs
        slot = meal_slot(episode.start)
        if slot != "snack":
            days[key]["slots"][slot]["carbs"] += episode.carbs
            days[key]["slots"][slot]["insulin"] += episode.insulin_units
    return days


def slot_daily_insulin(days, slot: str) -> list[float]:
    return [
        day["slots"][slot]["insulin"]
        for day in days.values()
        if day["slots"][slot]["insulin"] > 0
    ]


def slot_cell(slot_data) -> str:
    if slot_data["carbs"] <= 0 and slot_data["insulin"] <= 0:
        return EMPTY
    carbs = f"{fmt_num(slot_data['carbs'], 0)}г" if slot_data["carbs"] > 0 else EMPTY
    insulin = (
        f"{fmt_num(slot_data['insulin'], 0)}Е"
        if slot_data["insulin"] > 0
        else EMPTY
    )
    return f"{carbs} / {insulin}"


def draw_report() -> None:
    meals, all_glucose, all_insulin = load_data()
    from_date = meals[0].ts.date()
    to_date = meals[-1].ts.date()
    days_range = period_days(from_date, to_date)
    episodes = build_episodes(meals, all_glucose, all_insulin)
    days = build_days(days_range, episodes, all_glucose, all_insulin)

    glucose_values = [point.value for point in all_glucose]
    tir = percent(glucose_values, lambda value: 3.9 <= value <= 10.0)
    hypo = percent(glucose_values, lambda value: value < 3.9)
    hyper = percent(glucose_values, lambda value: value > 10.0)
    avg_glucose = avg_or_none(glucose_values)
    expected_cgm = len(days_range) * 24 * 12
    coverage = (
        min(100, round(len(all_glucose) / expected_cgm * 100)) if all_glucose else None
    )
    before_values = [episode.before for episode in episodes if episode.before is not None]
    after_values = [episode.after for episode in episodes if episode.after is not None]
    linked_insulin = sum(episode.insulin_units for episode in episodes)
    linked_carbs = sum(
        episode.carbs for episode in episodes if episode.insulin_units > 0
    )
    observed_uk = linked_carbs / linked_insulin if linked_insulin > 0 else None

    kpis = [
        (
            "ИНСУЛИН ЗАВТРАК",
            median_or_none(slot_daily_insulin(days, "breakfast")),
            "ЕД",
            "медиана за период",
            1,
        ),
        (
            "ИНСУЛИН ОБЕД",
            median_or_none(slot_daily_insulin(days, "lunch")),
            "ЕД",
            "медиана за период",
            1,
        ),
        (
            "ИНСУЛИН УЖИН",
            median_or_none(slot_daily_insulin(days, "dinner")),
            "ЕД",
            "медиана за период",
            1,
        ),
        (
            "ИНСУЛИН ЗА ДЕНЬ",
            median_or_none([day["insulin"] for day in days.values() if day["insulin"] > 0]),
            "ЕД",
            "медиана за период",
            0,
        ),
        ("САХАР ДО ЕДЫ", median_or_none(before_values), "ммоль/л", "медиана за период", 1),
        (
            "САХАР ПОСЛЕ ЕДЫ",
            median_or_none(after_values),
            "ммоль/л",
            "медиана за период",
            1,
        ),
        ("НАБЛЮДАЕМЫЙ УК", observed_uk, "г/ЕД", "по всем эпизодам", 1),
        ("TIR 3.9–10.0", tir, "%", "за выбранный период", 0),
    ]

    c = canvas.Canvas(str(OUT), pagesize=A4)
    width, height = A4
    c.setFillColor(colors.HexColor("#F2EFE8"))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    margin = 10
    c.setFillColor(PAPER)
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin, fill=1, stroke=1)
    left = 35
    right = width - 35
    y = height - 34

    def setfont(name: str, size: float, color=TEXT) -> None:
        c.setFont(name, size)
        c.setFillColor(color)

    def text(x: float, y_: float, value: str, font="GT-Regular", size=10, color=TEXT) -> None:
        setfont(font, size, color)
        c.drawString(x, y_, value)

    def center_text(
        x: float,
        y_: float,
        box_width: float,
        value: str,
        font="GT-Regular",
        size=10,
        color=TEXT,
    ) -> None:
        setfont(font, size, color)
        c.drawCentredString(x + box_width / 2, y_, value)

    def rect(x: float, y_: float, box_width: float, box_height: float, fill=None, stroke=BORDER, radius=0) -> None:
        c.setStrokeColor(stroke)
        c.setLineWidth(0.7)
        c.setFillColor(fill or colors.white)
        if radius:
            c.roundRect(x, y_, box_width, box_height, radius, fill=1 if fill else 0, stroke=1)
        else:
            c.rect(x, y_, box_width, box_height, fill=1 if fill else 0, stroke=1)

    months = [
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

    text(left, y, "glucotracker", "GT-Mono", 15)
    y -= 37
    text(left, y, "Отчёт для эндокринолога", "GT-Bold", 30)
    y -= 22
    period = f"Период: {from_date.day}–{to_date.day} {months[to_date.month - 1]} {to_date.year}"
    generated_day = date(2026, 4, 30)
    generated = (
        f"Сгенерировано: {generated_day.day} "
        f"{months[generated_day.month - 1]} {generated_day.year}"
    )
    text(left, y, f"{period} · {generated}", "GT-Regular", 12, MUTED)
    y -= 31
    chips = [
        f"{len(days_range)} дня",
        f"{sum(1 for day in days.values() if day['carbs'] > 0)}/{len(days_range)} дней с едой",
        f"CGM coverage {coverage if coverage is not None else EMPTY}%",
        f"{len(episodes)} пищевых эпизода",
    ]
    chip_x = left
    for chip in chips:
        chip_width = c.stringWidth(chip, "GT-Regular", 10) + 22
        rect(chip_x, y - 8, chip_width, 23, stroke=BORDER, radius=10)
        center_text(chip_x, y - 1, chip_width, chip, "GT-Regular", 10)
        chip_x += chip_width + 9
    y -= 44

    warning = (
        f"Данных мало: {sum(1 for day in days.values() if day['carbs'] > 0)} "
        f"дней с едой из {len(days_range)} выбранных"
    )
    rect(left, y - 8, right - left, 28, fill=WARN_BG, stroke=WARN_BORDER, radius=2)
    text(left + 13, y + 1, "!", "GT-Bold", 14, WARN_TEXT)
    text(left + 36, y + 1, warning, "GT-Regular", 11, WARN_TEXT)
    y -= 44

    card_gap = 6
    card_width = (right - left - 3 * card_gap) / 4
    card_height = 75
    for index, (label, value, unit, caption, digits) in enumerate(kpis):
        row = index // 4
        col = index % 4
        x = left + col * (card_width + card_gap)
        card_y = y - row * (card_height + 7)
        rect(x, card_y - card_height, card_width, card_height, stroke=BORDER, radius=3)
        center_text(x, card_y - 18, card_width, label, "GT-Bold", 10)
        value_text = EMPTY if value is None else fmt_num(value, digits)
        setfont("GT-MonoBold", 30, TEXT)
        c.drawCentredString(x + card_width / 2 - 10, card_y - 51, value_text)
        if value is not None:
            text(x + card_width / 2 + 31, card_y - 50, unit, "GT-Regular", 13)
        center_text(x, card_y - 65, card_width, caption, "GT-Regular", 9, MUTED)
    y -= 2 * card_height + 25

    def meal_profile_rows():
        rows = []
        for slot_key in ["breakfast", "lunch", "dinner", "snack"]:
            eps = [episode for episode in episodes if meal_slot(episode.start) == slot_key]
            total_insulin = sum(episode.insulin_units for episode in eps)
            total_linked_carbs = sum(
                episode.carbs for episode in eps if episode.insulin_units > 0
            )
            ratio = total_linked_carbs / total_insulin if total_insulin > 0 else None
            rows.append(
                [
                    SLOT_LABELS[slot_key],
                    str(len(eps)),
                    fmt_num(median_or_none([episode.carbs for episode in eps if episode.carbs > 0]), 0),
                    fmt_num(
                        median_or_none([episode.insulin_units for episode in eps if episode.insulin_units > 0]),
                        1,
                    ),
                    fmt_num(median_or_none([episode.before for episode in eps if episode.before is not None]), 1),
                    fmt_num(median_or_none([episode.after for episode in eps if episode.after is not None]), 1),
                    EMPTY if ratio is None else f"{fmt_num(ratio, 1)} г/ЕД",
                ]
            )
        rows.append(
            [
                "Итого / медиана",
                str(len(episodes)),
                fmt_num(median_or_none([episode.carbs for episode in episodes]), 0),
                fmt_num(
                    median_or_none([episode.insulin_units for episode in episodes if episode.insulin_units > 0]),
                    1,
                ),
                fmt_num(median_or_none(before_values), 1),
                fmt_num(median_or_none(after_values), 1),
                EMPTY if observed_uk is None else f"{fmt_num(observed_uk, 1)} г/ЕД",
            ]
        )
        return rows

    def draw_table(headers, rows, col_widths, y_, row_height=22):
        rect(left, y_ - row_height, sum(col_widths), row_height, fill=BG, stroke=BORDER)
        x_ = left
        for idx, header in enumerate(headers):
            center_text(x_, y_ - 14, col_widths[idx], header, "GT-Regular", 9)
            x_ += col_widths[idx]
        y_ -= row_height
        for row_index, row in enumerate(rows):
            fill = BG if row_index == len(rows) - 1 else None
            rect(left, y_ - row_height, sum(col_widths), row_height, fill=fill, stroke=BORDER)
            x_ = left
            for idx, cell in enumerate(row):
                if idx == 0 and len(col_widths) == 7:
                    text(
                        x_ + 7,
                        y_ - 14,
                        cell,
                        "GT-Bold" if row_index == len(rows) - 1 else "GT-Regular",
                        9.3,
                    )
                else:
                    center_text(
                        x_,
                        y_ - 14,
                        col_widths[idx],
                        cell,
                        "GT-Bold" if row_index == len(rows) - 1 and idx == 0 else "GT-Regular",
                        8.8,
                    )
                c.setStrokeColor(BORDER)
                c.line(x_, y_, x_, y_ - row_height)
                x_ += col_widths[idx]
            c.line(left + sum(col_widths), y_, left + sum(col_widths), y_ - row_height)
            y_ -= row_height
        return y_

    text(left, y, "Профиль приёмов пищи", "GT-Bold", 14)
    y -= 18
    y = draw_table(
        ["Приём пищи", "Эпизодов", "Угл., г", "Инсулин, ЕД", "Сахар до", "Сахар +2ч", "УК"],
        meal_profile_rows(),
        [112, 60, 58, 78, 68, 72, 70],
        y,
        22,
    )
    y -= 25

    def daily_rows():
        rows = []
        for day_data in days.values():
            glucose = day_data["glucose"]
            rows.append(
                [
                    day_data["date"].strftime("%d.%m"),
                    fmt_num(day_data["carbs"], 0) if day_data["carbs"] > 0 else EMPTY,
                    fmt_num(day_data["insulin"], 1) if day_data["insulin"] > 0 else EMPTY,
                    fmt_pct(percent(glucose, lambda value: 3.9 <= value <= 10.0)),
                    "1" if any(value < 3.9 for value in glucose) else "0",
                    slot_cell(day_data["slots"]["breakfast"]),
                    slot_cell(day_data["slots"]["lunch"]),
                    slot_cell(day_data["slots"]["dinner"]),
                ]
            )
        rows.append(
            [
                "Медиана",
                fmt_num(median_or_none([day["carbs"] for day in days.values() if day["carbs"] > 0]), 0),
                fmt_num(median_or_none([day["insulin"] for day in days.values() if day["insulin"] > 0]), 1),
                fmt_pct(
                    median_or_none(
                        [
                            percent(day["glucose"], lambda value: 3.9 <= value <= 10.0)
                            for day in days.values()
                            if day["glucose"]
                        ]
                    )
                ),
                str(sum(1 for day in days.values() if any(value < 3.9 for value in day["glucose"]))),
                EMPTY,
                EMPTY,
                EMPTY,
            ]
        )
        return rows

    text(left, y, "Сводка по дням", "GT-Bold", 14)
    y -= 18
    y = draw_table(
        ["Дата", "Угл., г", "Инсулин, ЕД", "TIR", "Гипо", "Завтрак", "Обед", "Ужин"],
        daily_rows(),
        [58, 62, 80, 60, 52, 76, 76, 76],
        y,
        21,
    )
    y -= 24

    strip_height = 54
    rect(left, y - strip_height, right - left, strip_height, fill=BG, stroke=BORDER, radius=3)
    metrics = [
        ("Средняя глюкоза", fmt_num(avg_glucose, 1), "ммоль/л"),
        ("Время <3.9", fmt_num(hypo, 0), "%"),
        ("Время >10", fmt_num(hyper, 0), "%"),
        ("До еды: -30...-15 мин; после еды: +90...+150 мин", "", ""),
    ]
    segment = (right - left) / 4
    for index, (label, value, unit) in enumerate(metrics):
        x = left + index * segment
        if index > 0:
            c.setStrokeColor(BORDER)
            c.line(x, y - 7, x, y - strip_height + 7)
        text(x + 12, y - 18, label, "GT-Regular", 9, MUTED)
        if value:
            text(x + 12, y - 42, value, "GT-MonoBold", 20, TEXT)
            text(x + 58, y - 40, unit, "GT-Regular", 10, TEXT)
        else:
            text(x + 12, y - 38, "окна CGM", "GT-Regular", 11, TEXT)
    y -= strip_height + 23

    footer = (
        "Инсулин получен из Nightscout (только чтение). Наблюдаемый УК — "
        "эмпирический показатель: граммы углеводов на 1 ЕД зарегистрированного "
        "meal-linked инсулина. Отчёт информационный и не является медицинской рекомендацией."
    )
    setfont("GT-Regular", 9, MUTED)
    line = ""
    for word in footer.split():
        candidate = f"{line} {word}".strip()
        if c.stringWidth(candidate, "GT-Regular", 9) > right - left:
            c.drawString(left, y, line)
            y -= 13
            line = word
        else:
            line = candidate
    if line:
        c.drawString(left, y, line)

    c.showPage()
    c.save()
    print(OUT)
    print(
        "meals",
        len(meals),
        "episodes",
        len(episodes),
        "glucose",
        len(all_glucose),
        "insulin",
        len(all_insulin),
    )


if __name__ == "__main__":
    draw_report()
