"""One episode, taken apart — for every class of episode, not just a rescue.

A diary row says what was recorded. This says what happened around it, and it is
the same six blocks whatever the row is:

1. the window — calibrated CGM either side of the episode;
2. the anchors — the two or three readings that carry the story;
3. one derived figure — the response per gram, or per unit;
4. the crossings — everything else in the window, with signed offsets;
5. the probable cause — the strongest explanation the data supports;
6. how often this has happened lately.

What differs by class is only *which* readings are anchors and *which* figure is
worth deriving. A carbohydrate rescue is read from its trough, because the point
of it is the low; a correction is read from how far it pushed glucose down,
because the point of it is the fall. The frame around them does not change, so
one sheet serves the whole diary.

Read-only throughout. Nothing here writes a record or produces a dose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import GlucoseDashboardPoint
from glucotracker.application.body_states import BodyStateInterval, BodyStateService
from glucotracker.application.episode_therapy import (
    LEVEL_TWO_LOW_MMOL_L,
    LOW_GLUCOSE_MMOL_L,
    EpisodeTherapy,
    TherapyClass,
    classify_episode_therapy,
    mmol,
)
from glucotracker.application.episodes import (
    EpisodeComponent,
    EpisodeQueryService,
    component_key,
)
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.glucose_normalization import GlucoseNormalizationService
from glucotracker.application.grouping import Horizon, rising_test
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import normalized_text
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.application.twin.kernels import insulin_iob_remaining_fraction
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import Meal, NightscoutInsulinEvent, TwinParams

# The chart window. Asymmetric on purpose: two hours before is enough to show
# what was already under way, while four hours after covers a meal's full
# absorption and most of a bolus's action, so the sheet does not cut off the
# part that answers "and then what".
WINDOW_BEFORE = timedelta(hours=2)
WINDOW_AFTER = timedelta(hours=4)

# Where each class's closing reading is taken, by the question it answers.
SETTLE_HORIZON: dict[str, timedelta] = {
    "carb_correction": Horizon.IMMEDIATE_RESPONSE.value,
    "meal": Horizon.IMMEDIATE_RESPONSE.value,
    "snack": Horizon.IMMEDIATE_RESPONSE.value,
    "mixed": Horizon.FULL_ABSORPTION.value,
    "insulin_correction": Horizon.INSULIN_EXHAUSTED.value,
    "unresolved": Horizon.IMMEDIATE_RESPONSE.value,
}

PEAK_SEARCH = timedelta(minutes=150)
TROUGH_SEARCH_BEFORE = timedelta(minutes=20)
TROUGH_SEARCH_AFTER = timedelta(minutes=45)
POINT_TOLERANCE = timedelta(minutes=15)

# How far back a dose is still a candidate explanation for a low, and how much
# of it must still be active to name it as the cause.
CAUSE_INSULIN_LOOKBACK = timedelta(hours=5)
CAUSE_MIN_ACTIVE_UNITS = 0.5
CAUSE_ACTIVITY_LOOKBACK = timedelta(hours=6)
DEFAULT_DIA_MINUTES = 270

# Two lows less than this apart are one event that wobbled, not two events.
LOW_EXCURSION_GAP = timedelta(minutes=30)
FREQUENCY_DAYS = 30
# A low inside the owner's own sleep window is a different problem from one at
# noon, so it is counted against its own kind.
NIGHT_MARGIN = timedelta(minutes=30)

BreakdownAnchorRole = Literal["start", "trough", "peak", "settle"]
BreakdownCrossingKind = Literal["insulin", "episode", "sleep", "activity"]


@dataclass(frozen=True)
class BreakdownPoint:
    """One CGM reading inside the window, in the calibrated space."""

    timestamp: datetime
    value: float
    raw_value: float | None = None
    is_low: bool = False


@dataclass(frozen=True)
class BreakdownAnchor:
    """A reading the episode is read from, with what it means."""

    role: BreakdownAnchorRole
    label: str
    at: datetime
    value: float
    minutes_from_start: int
    caption: str | None = None


@dataclass(frozen=True)
class BreakdownDerived:
    """The one number this episode contributes to the owner's settings."""

    code: str
    label: str
    value: float
    unit: str
    per_label: str | None = None
    per_value: float | None = None
    per_unit: str | None = None


@dataclass(frozen=True)
class BreakdownCrossing:
    """Something else that happened in the window."""

    kind: BreakdownCrossingKind
    label: str
    at: datetime
    offset_minutes: int
    detail: str | None = None
    therapy_class: TherapyClass | None = None


@dataclass(frozen=True)
class BreakdownCause:
    """The strongest explanation the data supports, in words."""

    code: str
    text: str


@dataclass(frozen=True)
class BreakdownFrequency:
    """How often the defining event of this class has happened lately."""

    code: str
    index: int
    count: int
    days: int
    label: str


@dataclass(frozen=True)
class EpisodeBreakdown:
    """Everything the detail sheet draws for one episode."""

    key: str
    classification: TherapyClass
    confidence: str
    title: str
    subtitle: str | None
    start_at: datetime
    window_from: datetime
    window_to: datetime
    low_threshold: float
    points: list[BreakdownPoint] = field(default_factory=list)
    anchors: list[BreakdownAnchor] = field(default_factory=list)
    derived: list[BreakdownDerived] = field(default_factory=list)
    crossings: list[BreakdownCrossing] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    cause: BreakdownCause | None = None
    frequency: BreakdownFrequency | None = None


class EpisodeBreakdownService:
    """Assemble one episode's breakdown from the same grouping the diary uses."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def breakdown(
        self,
        key: str,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> EpisodeBreakdown | None:
        """Break down the episode with [key] inside the range the diary drew.

        The range is passed rather than inferred so the grouping is byte for
        byte the one the list produced; grouping a different span can split a
        sitting differently and would resolve a key the client is holding to a
        different episode, or to none.
        """
        episodes = EpisodeQueryService(self.session, self.user_id)
        # Same predicate the list endpoint groups with, or the key it published
        # resolves to a different episode here.
        day_points = self._points(
            from_datetime - timedelta(minutes=20),
            to_datetime + timedelta(minutes=150),
        )
        components = episodes.components(
            from_datetime,
            to_datetime,
            rising_test(
                [
                    (point.timestamp, float(point.display_value))
                    for point in day_points
                    if point.display_value is not None
                ]
            ),
        )
        target = next(
            (component for component in components if component_key(component) == key),
            None,
        )
        if target is None:
            return None

        start_at = target.start_at
        window_from = start_at - WINDOW_BEFORE
        window_to = target.end_at + WINDOW_AFTER
        points = self._points(window_from, window_to)
        therapy = classify_episode_therapy(target, points)
        body_states = BodyStateService(self.session, self.user_id).intervals(
            window_from,
            window_to,
        )

        anchors = _anchors(
            therapy.classification,
            target,
            points,
            _next_start(target, components),
        )
        crossings = _crossings(
            target,
            components,
            body_states,
            points,
            window_from,
            window_to,
        )
        return EpisodeBreakdown(
            key=key,
            classification=therapy.classification,
            confidence=therapy.confidence,
            title=_title(target, therapy),
            subtitle=_subtitle(target),
            start_at=start_at,
            window_from=window_from,
            window_to=window_to,
            low_threshold=LOW_GLUCOSE_MMOL_L,
            points=_breakdown_points(points, window_from, window_to),
            anchors=anchors,
            derived=_derived(therapy.classification, target, anchors),
            crossings=crossings,
            evidence=[item.text for item in therapy.evidence],
            cause=self._cause(target, therapy, anchors, body_states),
            frequency=self._frequency(target, therapy, body_states),
        )

    def _points(
        self,
        window_from: datetime,
        window_to: datetime,
    ) -> list[GlucoseDashboardPoint]:
        return (
            GlucoseDashboardService(self.session, self.user_id)
            .dashboard(window_from, window_to, "normalized")
            .points
        )

    def _dia_minutes(self) -> int:
        row = self.session.scalar(
            select(TwinParams).where(TwinParams.owner_id == self.user_id)
        )
        return row.dia_minutes if row is not None else DEFAULT_DIA_MINUTES

    def _active_units(
        self,
        at: datetime,
        exclude: set[UUID],
    ) -> list[tuple[float, NightscoutInsulinEvent]]:
        """Boluses still working at [at], newest first, with units remaining."""
        dia = self._dia_minutes()
        rows = self.session.scalars(
            select(NightscoutInsulinEvent).where(
                NightscoutInsulinEvent.owner_id == self.user_id,
                NightscoutInsulinEvent.timestamp
                >= utc_instant_from_local_wall(at - CAUSE_INSULIN_LOOKBACK),
                NightscoutInsulinEvent.timestamp <= utc_instant_from_local_wall(at),
            )
        ).all()
        active: list[tuple[float, NightscoutInsulinEvent]] = []
        for row in rows:
            if row.id in exclude or not row.insulin_units:
                continue
            elapsed = (at - _local_wall_time(row.timestamp)).total_seconds() / 60
            remaining = insulin_iob_remaining_fraction(elapsed, dia)
            units = float(row.insulin_units) * remaining
            if units > 0:
                active.append((units, row))
        active.sort(key=lambda item: item[1].timestamp, reverse=True)
        return active

    def _cause(
        self,
        component: EpisodeComponent,
        therapy: EpisodeTherapy,
        anchors: list[BreakdownAnchor],
        body_states: list[BodyStateInterval],
    ) -> BreakdownCause | None:
        by_role = {anchor.role: anchor for anchor in anchors}
        if therapy.classification == "carb_correction":
            return self._rescue_cause(component, by_role, body_states)
        if therapy.classification == "insulin_correction":
            return _correction_cause(component, by_role)
        return _food_cause(component, by_role)

    def _rescue_cause(
        self,
        component: EpisodeComponent,
        by_role: dict[str, BreakdownAnchor],
        body_states: list[BodyStateInterval],
    ) -> BreakdownCause | None:
        """Why glucose was low — which is rarely the food that answered it."""
        trough = by_role.get("trough")
        if trough is None:
            return None
        own_insulin = {event.id for event in component.insulin}
        active = self._active_units(trough.at, own_insulin)
        if active:
            units, event = active[0]
            total = sum(item[0] for item in active)
            minutes = int(
                (trough.at - _local_wall_time(event.timestamp)).total_seconds() / 60
            )
            covered = _covers(self.session, self.user_id, event)
            if total >= CAUSE_MIN_ACTIVE_UNITS:
                if covered is None:
                    return BreakdownCause(
                        "insulin_correction_before",
                        f"Гипо через {minutes} мин после коррекции инсулином"
                        f" на активном IOB {mmol(total)} ЕД. Не еда — доза.",
                    )
                return BreakdownCause(
                    "meal_bolus_overshot",
                    f"Болюс {mmol(float(event.insulin_units or 0))} ЕД"
                    f" на {covered:.0f} г ещё работал:"
                    f" активный IOB {mmol(total)} ЕД через {minutes} мин.",
                )
        effort = _recent_activity(body_states, trough.at)
        if effort is not None:
            return BreakdownCause(
                "after_activity",
                f"Гипо после нагрузки: {effort.total_minutes} мин,"
                f" закончилась в {effort.end_at:%H:%M}.",
            )
        if _during_sleep(body_states, trough.at):
            return BreakdownCause(
                "during_sleep",
                "Ночная гипо во сне — без активного болюса рядом.",
            )
        return BreakdownCause(
            "unexplained",
            "Активного инсулина и нагрузки рядом нет — причина не установлена.",
        )

    def _frequency(
        self,
        component: EpisodeComponent,
        therapy: EpisodeTherapy,
        body_states: list[BodyStateInterval],
    ) -> BreakdownFrequency | None:
        if therapy.classification == "carb_correction":
            return self._low_frequency(component, body_states)
        if therapy.classification == "insulin_correction":
            return self._insulin_correction_frequency(component)
        return self._meal_frequency(component, therapy)

    def _low_frequency(
        self,
        component: EpisodeComponent,
        body_states: list[BodyStateInterval],
    ) -> BreakdownFrequency | None:
        """Where this low sits among the owner's recent lows.

        Counting lows rather than rescues on purpose: a low that was slept
        through and never treated is the same problem as this one, and leaving
        it out of the tally would understate exactly the thing worth knowing.
        """
        start_at = component.start_at
        window_from = start_at - timedelta(days=FREQUENCY_DAYS)
        samples = GlucoseNormalizationService(self.session, self.user_id).series(
            utc_instant_from_local_wall(window_from),
            utc_instant_from_local_wall(start_at + WINDOW_AFTER),
        )
        excursions = _low_excursions(
            [
                (_local_wall_time(sample.timestamp), sample.normalized_mmol_l)
                for sample in samples
            ]
        )
        at_night = _during_sleep(body_states, start_at)
        night_window = _sleep_window(body_states)
        if at_night and night_window is not None:
            excursions = [at for at in excursions if _in_clock_window(at, night_window)]
        if not excursions:
            return None
        index = sum(1 for at in excursions if at <= start_at + WINDOW_AFTER)
        kind = "ночная гипо" if at_night else "гипо"
        return BreakdownFrequency(
            code="night_low" if at_night else "low",
            index=max(index, 1),
            count=len(excursions),
            days=FREQUENCY_DAYS,
            label=f"{max(index, 1)}-я {kind} за {FREQUENCY_DAYS} дней",
        )

    def _insulin_correction_frequency(
        self,
        component: EpisodeComponent,
    ) -> BreakdownFrequency | None:
        start_at = component.start_at
        rows = self.session.scalars(
            select(NightscoutInsulinEvent).where(
                NightscoutInsulinEvent.owner_id == self.user_id,
                NightscoutInsulinEvent.timestamp
                >= utc_instant_from_local_wall(
                    start_at - timedelta(days=FREQUENCY_DAYS)
                ),
                NightscoutInsulinEvent.timestamp
                <= utc_instant_from_local_wall(start_at),
            )
        ).all()
        corrections = [
            row for row in rows if "correction" in normalized_text(row.event_type)
        ]
        if not corrections:
            return None
        return BreakdownFrequency(
            code="insulin_correction",
            index=len(corrections),
            count=len(corrections),
            days=FREQUENCY_DAYS,
            label=f"{len(corrections)}-я коррекция инсулином за {FREQUENCY_DAYS} дней",
        )

    def _meal_frequency(
        self,
        component: EpisodeComponent,
        therapy: EpisodeTherapy,
    ) -> BreakdownFrequency | None:
        if not component.meals:
            return None
        start_at = component.start_at
        titles = {meal.title.casefold() for meal in component.meals if meal.title}
        if not titles:
            return None
        rows = self.session.scalars(
            select(Meal).where(
                Meal.owner_id == self.user_id,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= start_at - timedelta(days=FREQUENCY_DAYS),
                Meal.eaten_at <= start_at,
            )
        ).all()
        repeats = [row for row in rows if (row.title or "").casefold() in titles]
        if len(repeats) < 2:
            return None
        return BreakdownFrequency(
            code="repeat_meal",
            index=len(repeats),
            count=len(repeats),
            days=FREQUENCY_DAYS,
            label=f"{len(repeats)}-й раз за {FREQUENCY_DAYS} дней",
        )


def _breakdown_points(
    points: list[GlucoseDashboardPoint],
    window_from: datetime,
    window_to: datetime,
) -> list[BreakdownPoint]:
    """Points as dots, not a line.

    The day chart wants shape and draws a line. Here the useful information is
    the density of measurement and where the trace breaks, so every reading is
    sent as its own point and the gaps stay visible instead of being bridged.
    """
    return [
        BreakdownPoint(
            timestamp=point.timestamp,
            value=round(value, 1),
            raw_value=round(float(point.raw_value), 1)
            if point.raw_value is not None
            else None,
            is_low=value < LOW_GLUCOSE_MMOL_L,
        )
        for point in points
        if window_from <= point.timestamp <= window_to
        if (value := _value(point)) is not None
    ]


def _anchors(
    classification: TherapyClass,
    component: EpisodeComponent,
    points: list[GlucoseDashboardPoint],
    boundary: datetime | None = None,
) -> list[BreakdownAnchor]:
    """The two or three readings the episode is read from.

    Which ones depends on what the episode was for. A rescue is about the low it
    answered, so it leads with the trough; a correction is about the fall it
    produced, so it leads with the reading it was given at.

    [boundary] is when the next episode begins. Every search stops there,
    because after it the trace is answering something else: in the night this
    module was written against, a snack seventy-five minutes after a twelve-gram
    rescue pushed glucose higher than the rescue ever did, and an uncapped
    search would have called that the rescue's peak and billed the snack's rise
    to twelve grams of juice.
    """
    start_at = component.start_at
    settle_after = SETTLE_HORIZON.get(classification, Horizon.IMMEDIATE_RESPONSE.value)
    anchors: list[BreakdownAnchor] = []

    def until(horizon: timedelta) -> datetime:
        limit = start_at + horizon
        return min(limit, boundary) if boundary is not None else limit

    def add(
        role: BreakdownAnchorRole,
        label: str,
        found: tuple[float, datetime] | None,
        caption: str | None = None,
    ) -> None:
        if found is None:
            return
        value, at = found
        anchors.append(
            BreakdownAnchor(
                role=role,
                label=label,
                at=at,
                value=round(value, 1),
                minutes_from_start=int(round((at - start_at).total_seconds() / 60)),
                caption=caption,
            )
        )

    trough = _extreme(
        points,
        start_at - TROUGH_SEARCH_BEFORE,
        until(TROUGH_SEARCH_AFTER),
        lowest=True,
    )
    peak = _extreme(points, start_at, until(PEAK_SEARCH), lowest=False)
    settle = _nearest(points, until(settle_after))
    settle_hours = settle_after.total_seconds() / 3600

    if classification == "carb_correction":
        add("trough", "Минимум перед приёмом", trough)
        add("peak", "Пик", peak, _after(peak, trough or (0.0, start_at)))
        add("settle", "После усвоения", settle, f"{_hours(settle_hours)} ч")
        return anchors

    if classification == "insulin_correction":
        add("start", "Перед болюсом", _nearest(points, start_at))
        add(
            "trough",
            "Минимум",
            _extreme(points, start_at, until(settle_after), lowest=True),
            None,
        )
        add("settle", "Через " + _hours(settle_hours) + " ч", settle)
        return anchors

    add("start", "Перед едой", _nearest(points, start_at))
    add("peak", "Пик", peak, _after(peak, (0.0, start_at)))
    add("settle", f"Через {_hours(settle_hours)} ч", settle)
    if classification == "mixed":
        add(
            "trough",
            "Минимум",
            _extreme(points, start_at, until(settle_after), lowest=True),
        )
    return anchors


def _next_start(
    component: EpisodeComponent,
    components: list[EpisodeComponent],
) -> datetime | None:
    """When the next episode begins, past which the trace is not this one's."""
    own = component_key(component)
    later = [
        other.start_at
        for other in components
        if component_key(other) != own and other.start_at > component.start_at
    ]
    return min(later) if later else None


def _derived(
    classification: TherapyClass,
    component: EpisodeComponent,
    anchors: list[BreakdownAnchor],
) -> list[BreakdownDerived]:
    """The single figure this episode contributes to the owner's settings.

    One episode is an anecdote. A dozen of them agreeing is the argument for
    moving a carbohydrate ratio or a sensitivity factor, which is why the
    per-gram and per-unit numbers are surfaced here rather than kept internal.
    """
    by_role = {anchor.role: anchor for anchor in anchors}
    carbs = sum(float(meal.total_carbs_g or 0) for meal in component.meals)
    units = sum(float(event.insulin_units or 0) for event in component.insulin)
    derived: list[BreakdownDerived] = []

    base = (
        by_role.get("trough")
        if classification == "carb_correction"
        else by_role.get("start")
    )
    peak = by_role.get("peak")
    if carbs > 0 and base is not None and peak is not None and peak.value > base.value:
        rise = peak.value - base.value
        derived.append(
            BreakdownDerived(
                code="rise_per_carb",
                label=f"Подъём на {carbs:.0f} г",
                value=round(rise, 1),
                unit="ммоль/л",
                per_label="на грамм",
                per_value=round(rise / carbs, 2),
                per_unit="ммоль/л на г",
            )
        )

    start = by_role.get("start")
    trough = by_role.get("trough")
    if (
        classification == "insulin_correction"
        and units > 0
        and start is not None
        and trough is not None
        and start.value > trough.value
    ):
        drop = start.value - trough.value
        derived.append(
            BreakdownDerived(
                code="drop_per_unit",
                label=f"Снижение на {mmol(units)} ЕД",
                value=round(-drop, 1),
                unit="ммоль/л",
                per_label="на единицу",
                per_value=round(drop / units, 2),
                per_unit="ммоль/л на ЕД",
            )
        )
    return derived


def _crossings(
    component: EpisodeComponent,
    components: list[EpisodeComponent],
    body_states: list[BodyStateInterval],
    points: list[GlucoseDashboardPoint],
    window_from: datetime,
    window_to: datetime,
) -> list[BreakdownCrossing]:
    """Everything else inside the window, with a signed offset.

    The meaning of an episode is rarely in the episode. Twelve grams of juice
    says nothing on its own; twelve grams of juice forty-seven minutes after a
    correction, during sleep, says the whole thing.
    """
    start_at = component.start_at
    own = component_key(component)
    crossings: list[BreakdownCrossing] = []

    for other in components:
        if component_key(other) == own:
            continue
        at = other.start_at
        if not window_from <= at <= window_to:
            continue
        crossings.append(
            BreakdownCrossing(
                kind="episode" if other.meals else "insulin",
                label=_episode_label(other),
                at=at,
                offset_minutes=int((at - start_at).total_seconds() / 60),
                # Its own label, so a neighbouring rescue reads as a rescue in
                # this sheet too rather than as an anonymous nearby plate.
                therapy_class=classify_episode_therapy(other, points).classification,
            )
        )

    for state in body_states:
        if state.end_at < window_from or state.start_at > window_to:
            continue
        crossings.append(
            BreakdownCrossing(
                kind=state.kind,
                label="Сон" if state.kind == "sleep" else (state.label or "Нагрузка"),
                at=state.start_at,
                offset_minutes=int((state.start_at - start_at).total_seconds() / 60),
                detail=f"{state.start_at:%H:%M}—{state.end_at:%H:%M}",
            )
        )

    crossings.sort(key=lambda crossing: crossing.at)
    return crossings


def _episode_label(component: EpisodeComponent) -> str:
    units = sum(float(event.insulin_units or 0) for event in component.insulin)
    if not component.meals:
        return f"Коррекция инсулином {mmol(units)} ЕД"
    carbs = sum(float(meal.total_carbs_g or 0) for meal in component.meals)
    title = component.meals[0].title or "Приём"
    if units > 0:
        return f"{title}, {carbs:.0f} г · {mmol(units)} ЕД"
    return f"{title}, {carbs:.0f} г"


def _correction_cause(
    component: EpisodeComponent,
    by_role: dict[str, BreakdownAnchor],
) -> BreakdownCause | None:
    start = by_role.get("start")
    trough = by_role.get("trough")
    units = sum(float(event.insulin_units or 0) for event in component.insulin)
    if start is None or trough is None or units <= 0:
        return None
    if trough.value < LOW_GLUCOSE_MMOL_L:
        severity = (
            "во вторую степень" if trough.value < LEVEL_TWO_LOW_MMOL_L else "в гипо"
        )
        return BreakdownCause(
            "correction_overshot",
            f"Коррекция {mmol(units)} ЕД при {mmol(start.value)}"
            f" увела {severity}: {mmol(trough.value)}"
            f" через {trough.minutes_from_start} мин.",
        )
    return BreakdownCause(
        "correction_landed",
        f"Коррекция {mmol(units)} ЕД снизила с {mmol(start.value)}"
        f" до {mmol(trough.value)} за {trough.minutes_from_start} мин.",
    )


def _food_cause(
    component: EpisodeComponent,
    by_role: dict[str, BreakdownAnchor],
) -> BreakdownCause | None:
    start = by_role.get("start")
    peak = by_role.get("peak")
    if start is None or peak is None:
        return None
    rise = peak.value - start.value
    units = sum(float(event.insulin_units or 0) for event in component.insulin)
    if units <= 0 and rise >= 2.0:
        return BreakdownCause(
            "uncovered_rise",
            f"Подъём +{mmol(rise)} без болюса,"
            f" пик через {peak.minutes_from_start} мин.",
        )
    if units > 0 and rise >= 3.0:
        return BreakdownCause(
            "bolus_late",
            f"Болюс {mmol(units)} ЕД не удержал подъём:"
            f" +{mmol(rise)} к {peak.at:%H:%M}.",
        )
    if units > 0:
        return BreakdownCause(
            "bolus_held",
            f"Болюс {mmol(units)} ЕД удержал подъём: +{mmol(rise)}"
            f" за {peak.minutes_from_start} мин.",
        )
    return BreakdownCause(
        "flat_response",
        f"Подъём +{mmol(rise)} — глюкоза осталась в пределах приёма.",
    )


def _covers(
    session: Session,
    user_id: UUID,
    event: NightscoutInsulinEvent,
) -> float | None:
    """Carbohydrate this bolus was dosed against, or None if it stood alone."""
    at = _local_wall_time(event.timestamp)
    rows = session.scalars(
        select(Meal).where(
            Meal.owner_id == user_id,
            Meal.status == MealStatus.accepted,
            Meal.eaten_at >= at - timedelta(minutes=30),
            Meal.eaten_at <= at + timedelta(minutes=30),
        )
    ).all()
    if not rows:
        return None
    return sum(float(row.total_carbs_g or 0) for row in rows)


def _recent_activity(
    body_states: list[BodyStateInterval],
    at: datetime,
) -> BodyStateInterval | None:
    candidates = [
        state
        for state in body_states
        if state.kind == "activity"
        and at - CAUSE_ACTIVITY_LOOKBACK <= state.end_at <= at
    ]
    return max(candidates, key=lambda state: state.end_at) if candidates else None


def _during_sleep(body_states: list[BodyStateInterval], at: datetime) -> bool:
    return any(
        state.kind == "sleep" and state.start_at <= at <= state.end_at
        for state in body_states
    )


def _sleep_window(
    body_states: list[BodyStateInterval],
) -> tuple[int, int] | None:
    """The night's clock band, as minutes from midnight."""
    nights = [state for state in body_states if state.kind == "sleep"]
    if not nights:
        return None
    night = max(nights, key=lambda state: state.total_minutes)
    start = night.start_at - NIGHT_MARGIN
    end = night.end_at + NIGHT_MARGIN
    return (
        start.hour * 60 + start.minute,
        end.hour * 60 + end.minute,
    )


def _in_clock_window(at: datetime, window: tuple[int, int]) -> bool:
    minutes = at.hour * 60 + at.minute
    start, end = window
    if start <= end:
        return start <= minutes <= end
    return minutes >= start or minutes <= end


def _low_excursions(series: list[tuple[datetime, float]]) -> list[datetime]:
    """Start times of distinct low events, merging wobbles inside one low."""
    excursions: list[datetime] = []
    last_low: datetime | None = None
    for at, value in series:
        if value >= LOW_GLUCOSE_MMOL_L:
            continue
        if last_low is None or at - last_low > LOW_EXCURSION_GAP:
            excursions.append(at)
        last_low = at
    return excursions


def _title(component: EpisodeComponent, therapy: EpisodeTherapy) -> str:
    if not component.meals:
        units = sum(float(event.insulin_units or 0) for event in component.insulin)
        return f"Коррекция {mmol(units)} ЕД"
    carbs = sum(float(meal.total_carbs_g or 0) for meal in component.meals)
    titles = [meal.title for meal in component.meals if meal.title]
    head = titles[0] if titles else "Приём"
    if len(titles) > 1:
        head = f"{head} +{len(titles) - 1}"
    return f"{head}, {carbs:.0f} г"


def _subtitle(component: EpisodeComponent) -> str | None:
    units = sum(float(event.insulin_units or 0) for event in component.insulin)
    if units <= 0 or not component.meals:
        return None
    return f"{mmol(units)} ЕД"


def _after(
    later: tuple[float, datetime] | None,
    earlier: tuple[float, datetime],
) -> str | None:
    if later is None:
        return None
    minutes = int((later[1] - earlier[1]).total_seconds() / 60)
    return f"через {minutes} мин" if minutes > 0 else None


def _hours(hours: float) -> str:
    """2.0 as "2", 4.5 as "4,5" — a horizon reads as a duration, not a float."""
    return f"{hours:.1f}".replace(".", ",").removesuffix(",0")


def _extreme(
    points: list[GlucoseDashboardPoint],
    window_from: datetime,
    window_to: datetime,
    *,
    lowest: bool,
) -> tuple[float, datetime] | None:
    found = [
        (value, point.timestamp)
        for point in points
        if window_from <= point.timestamp <= window_to
        if (value := _value(point)) is not None
    ]
    if not found:
        return None
    return min(found) if lowest else max(found)


def _nearest(
    points: list[GlucoseDashboardPoint],
    target: datetime,
) -> tuple[float, datetime] | None:
    candidates = [
        (point.timestamp, value)
        for point in points
        if (value := _value(point)) is not None
    ]
    if not candidates:
        return None
    at, value = min(candidates, key=lambda item: abs(item[0] - target))
    return (value, at) if abs(at - target) <= POINT_TOLERANCE else None


def _value(point: GlucoseDashboardPoint) -> float | None:
    value = (
        point.normalized_value
        if point.normalized_value is not None
        else point.raw_value
    )
    return float(value) if value is not None else None
