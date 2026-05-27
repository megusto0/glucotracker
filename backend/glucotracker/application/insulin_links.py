"""Food/insulin day-link rules owned by the backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    InsulinLinkDayPutRequest,
    InsulinLinkDayResponse,
    InsulinLinkEventResponse,
    InsulinLinkGlucoseAnchorResponse,
    InsulinLinkMealResponse,
    MealInsulinLinkItem,
)
from glucotracker.application.nightscout_context import (
    INSULIN_WINDOW_AFTER,
    INSULIN_WINDOW_BEFORE,
    _local_wall_time,
)
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    Meal,
    MealInsulinEpisodeSnapshot,
    MealInsulinLink,
    MealInsulinLinkReview,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)

DAY_BUFFER = timedelta(minutes=90)
FOOD_ONLY_CLUSTER_WINDOW = timedelta(minutes=45)
GLUCOSE_ACTUAL_TOLERANCE = timedelta(minutes=5)
GLUCOSE_INTERPOLATION_MAX_GAP = timedelta(minutes=15)


@dataclass(frozen=True)
class AutoLink:
    """Computed link candidate for one insulin event."""

    meal_id: UUID
    insulin_event_id: UUID
    confidence: float


@dataclass(frozen=True)
class GlucoseAnchor:
    """CGM anchor sampled for episode review display."""

    value: float
    timestamp: datetime
    source: Literal["actual", "interpolated"]


@dataclass(frozen=True)
class DayLinkContext:
    """Backend-owned day workspace used by responses and snapshots."""

    day: date
    day_start: datetime
    next_day_start: datetime
    meals: list[Meal]
    insulin: list[NightscoutInsulinEvent]
    visible_insulin: list[NightscoutInsulinEvent]
    manual_by_insulin: dict[UUID, list[MealInsulinLink]]
    auto_by_insulin: dict[UUID, list[AutoLink]]
    auto_links: list[AutoLink]
    active_links: list[MealInsulinLinkItem]
    reviewed_insulin_event_ids: set[UUID]
    glucose: list[NightscoutGlucoseEntry]


@dataclass
class EpisodeSnapshotData:
    """Episode data persisted when the user saves day-link review."""

    episode_key: str
    sequence: int
    kind: str
    title: str
    start_at: datetime
    end_at: datetime
    meal_ids: list[UUID]
    insulin_event_ids: list[UUID]
    link_pairs: list[dict[str, Any]]
    total_carbs_g: float
    total_kcal: float
    total_insulin_units: float
    glucose_minus_30: GlucoseAnchor | None
    glucose_plus_2h: GlucoseAnchor | None
    snapshot_json: dict[str, Any]


class MealInsulinLinkRepository:
    """Scoped persistence for reviewed meal/insulin links."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def list_for_day(
        self,
        day_start: datetime,
        next_day_start: datetime,
    ) -> list[MealInsulinLink]:
        """Return links touching meals or insulin events visible for the day."""
        return list(
            self.session.scalars(
                select(MealInsulinLink)
                .join(Meal, Meal.id == MealInsulinLink.meal_id)
                .join(
                    NightscoutInsulinEvent,
                    NightscoutInsulinEvent.id == MealInsulinLink.insulin_event_id,
                )
                .where(
                    MealInsulinLink.owner_id == self.user_id,
                    Meal.owner_id == self.user_id,
                    NightscoutInsulinEvent.owner_id == self.user_id,
                    or_(
                        Meal.eaten_at >= day_start,
                        NightscoutInsulinEvent.timestamp >= day_start,
                    ),
                    or_(
                        Meal.eaten_at < next_day_start,
                        NightscoutInsulinEvent.timestamp < next_day_start,
                    ),
                )
                .order_by(Meal.eaten_at.asc(), NightscoutInsulinEvent.timestamp.asc())
            )
        )

    def reviewed_insulin_ids_for_day(
        self,
        day_start: datetime,
        next_day_start: datetime,
    ) -> set[UUID]:
        """Return insulin events with explicit manual review markers."""
        return set(
            self.session.scalars(
                select(MealInsulinLinkReview.insulin_event_id)
                .join(
                    NightscoutInsulinEvent,
                    NightscoutInsulinEvent.id
                    == MealInsulinLinkReview.insulin_event_id,
                )
                .where(
                    MealInsulinLinkReview.owner_id == self.user_id,
                    NightscoutInsulinEvent.owner_id == self.user_id,
                    NightscoutInsulinEvent.timestamp >= day_start - DAY_BUFFER,
                    NightscoutInsulinEvent.timestamp < next_day_start + DAY_BUFFER,
                )
            )
        )

    def replace_for_day(
        self,
        day_start: datetime,
        next_day_start: datetime,
        links: list[MealInsulinLinkItem],
        reviewed_insulin_event_ids: list[UUID],
    ) -> None:
        """Replace reviewed links for one local day."""
        meal_ids = list(
            self.session.scalars(
                select(Meal.id).where(
                    Meal.owner_id == self.user_id,
                    Meal.status == MealStatus.accepted,
                    Meal.eaten_at >= day_start,
                    Meal.eaten_at < next_day_start,
                )
            )
        )
        insulin_ids = list(
            self.session.scalars(
                select(NightscoutInsulinEvent.id).where(
                    NightscoutInsulinEvent.owner_id == self.user_id,
                    NightscoutInsulinEvent.timestamp >= day_start - DAY_BUFFER,
                    NightscoutInsulinEvent.timestamp < next_day_start + DAY_BUFFER,
                )
            )
        )
        meal_id_set = set(meal_ids)
        insulin_id_set = set(insulin_ids)
        reviewed_id_set = set(reviewed_insulin_event_ids)

        for item in links:
            if item.meal_id not in meal_id_set:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Meal is not part of this user's reviewed day.",
                )
            if item.insulin_event_id not in insulin_id_set:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Insulin event is not part of this user's reviewed day.",
                )
            reviewed_id_set.add(item.insulin_event_id)

        for insulin_id in reviewed_id_set:
            if insulin_id not in insulin_id_set:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        "Reviewed insulin event is not part of this user's "
                        "reviewed day."
                    ),
                )

        if meal_ids or insulin_ids:
            self.session.execute(
                delete(MealInsulinLink).where(
                    MealInsulinLink.owner_id == self.user_id,
                    or_(
                        MealInsulinLink.meal_id.in_(meal_ids),
                        MealInsulinLink.insulin_event_id.in_(insulin_ids),
                    ),
                )
            )
            self.session.execute(
                delete(MealInsulinLinkReview).where(
                    MealInsulinLinkReview.owner_id == self.user_id,
                    MealInsulinLinkReview.insulin_event_id.in_(insulin_ids),
                )
            )

        for insulin_id in reviewed_id_set:
            self.session.add(
                MealInsulinLinkReview(
                    owner_id=self.user_id,
                    insulin_event_id=insulin_id,
                )
            )

        seen: set[tuple[UUID, UUID]] = set()
        for item in links:
            key = (item.meal_id, item.insulin_event_id)
            if key in seen:
                continue
            seen.add(key)
            self.session.add(
                MealInsulinLink(
                    owner_id=self.user_id,
                    meal_id=item.meal_id,
                    insulin_event_id=item.insulin_event_id,
                    source="manual",
                    confidence=item.confidence,
                    note=item.note,
                )
            )

    def replace_episode_snapshots(
        self,
        day: date,
        snapshots: list[EpisodeSnapshotData],
    ) -> None:
        """Replace persisted episode snapshots for one reviewed local day."""
        self.session.execute(
            delete(MealInsulinEpisodeSnapshot).where(
                MealInsulinEpisodeSnapshot.owner_id == self.user_id,
                MealInsulinEpisodeSnapshot.date == day,
            )
        )
        for snapshot in snapshots:
            self.session.add(
                MealInsulinEpisodeSnapshot(
                    owner_id=self.user_id,
                    date=day,
                    episode_key=snapshot.episode_key,
                    sequence=snapshot.sequence,
                    kind=snapshot.kind,
                    title=snapshot.title,
                    start_at=snapshot.start_at,
                    end_at=snapshot.end_at,
                    meal_ids_json=[str(meal_id) for meal_id in snapshot.meal_ids],
                    insulin_event_ids_json=[
                        str(event_id) for event_id in snapshot.insulin_event_ids
                    ],
                    link_pairs_json=snapshot.link_pairs,
                    total_carbs_g=snapshot.total_carbs_g,
                    total_kcal=snapshot.total_kcal,
                    total_insulin_units=snapshot.total_insulin_units,
                    glucose_minus_30_mmol_l=(
                        snapshot.glucose_minus_30.value
                        if snapshot.glucose_minus_30
                        else None
                    ),
                    glucose_minus_30_at=(
                        snapshot.glucose_minus_30.timestamp
                        if snapshot.glucose_minus_30
                        else None
                    ),
                    glucose_minus_30_source=(
                        snapshot.glucose_minus_30.source
                        if snapshot.glucose_minus_30
                        else None
                    ),
                    glucose_plus_2h_mmol_l=(
                        snapshot.glucose_plus_2h.value
                        if snapshot.glucose_plus_2h
                        else None
                    ),
                    glucose_plus_2h_at=(
                        snapshot.glucose_plus_2h.timestamp
                        if snapshot.glucose_plus_2h
                        else None
                    ),
                    glucose_plus_2h_source=(
                        snapshot.glucose_plus_2h.source
                        if snapshot.glucose_plus_2h
                        else None
                    ),
                    snapshot_json=snapshot.snapshot_json,
                )
            )


class InsulinLinkDayService:
    """Build and save the no-graph day review workspace."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.links = MealInsulinLinkRepository(session, user_id)

    def get_day(self, day: date) -> InsulinLinkDayResponse:
        """Return meals, insulin events, manual links, and auto suggestions."""
        context = self._day_context(day)

        return InsulinLinkDayResponse(
            date=day,
            meals=[
                InsulinLinkMealResponse(
                    id=meal.id,
                    eaten_at=meal.eaten_at,
                    title=meal.title or "Приём пищи",
                    total_carbs_g=round(meal.total_carbs_g, 1),
                    total_kcal=round(meal.total_kcal, 1),
                    glucose_minus_30=_glucose_anchor_response(
                        _glucose_anchor(
                            context.glucose,
                            meal.eaten_at - timedelta(minutes=30),
                        )
                    ),
                    glucose_plus_2h=_glucose_anchor_response(
                        _glucose_anchor(
                            context.glucose,
                            meal.eaten_at + timedelta(hours=2),
                        )
                    ),
                )
                for meal in context.meals
            ],
            insulin_events=[
                _event_response(
                    event,
                    context.manual_by_insulin.get(event.id, []),
                    context.auto_by_insulin.get(event.id, []),
                    event.id in context.reviewed_insulin_event_ids,
                )
                for event in context.visible_insulin
            ],
            links=context.active_links,
            auto_links=[
                MealInsulinLinkItem(
                    meal_id=link.meal_id,
                    insulin_event_id=link.insulin_event_id,
                    source="auto",
                    confidence=link.confidence,
                )
                for link in context.auto_links
            ],
            reviewed_insulin_event_ids=sorted(
                context.reviewed_insulin_event_ids,
                key=str,
            ),
        )

    def replace_day(self, payload: InsulinLinkDayPutRequest) -> InsulinLinkDayResponse:
        """Replace manual links for the payload date and return fresh labels."""
        day_start, next_day_start = _day_bounds(payload.date)
        self.links.replace_for_day(
            day_start,
            next_day_start,
            payload.links,
            payload.reviewed_insulin_event_ids,
        )
        self.session.flush()
        self._replace_episode_snapshots(payload.date)
        self.session.commit()
        return self.get_day(payload.date)

    def _day_context(self, day: date) -> DayLinkContext:
        day_start, next_day_start = _day_bounds(day)
        meals = self._meals(day_start, next_day_start)
        insulin = self._insulin(day_start, next_day_start)
        manual_links = self.links.list_for_day(day_start, next_day_start)
        reviewed_insulin_event_ids = self.links.reviewed_insulin_ids_for_day(
            day_start,
            next_day_start,
        )
        manual_by_insulin: dict[UUID, list[MealInsulinLink]] = {}
        for link in manual_links:
            manual_by_insulin.setdefault(link.insulin_event_id, []).append(link)
        reviewed_insulin_event_ids.update(manual_by_insulin)

        auto_links = _auto_links(meals, insulin)
        auto_by_insulin: dict[UUID, list[AutoLink]] = {}
        for link in auto_links:
            auto_by_insulin.setdefault(link.insulin_event_id, []).append(link)

        visible_insulin = [
            event
            for event in insulin
            if _is_visible_event(
                event,
                day_start,
                next_day_start,
                manual_by_insulin,
            )
        ]
        active_links = _effective_link_items(
            reviewed_insulin_event_ids,
            manual_by_insulin,
            auto_links,
        )
        glucose = self._glucose(
            day_start - timedelta(minutes=30),
            next_day_start + timedelta(hours=2),
        )
        return DayLinkContext(
            day=day,
            day_start=day_start,
            next_day_start=next_day_start,
            meals=meals,
            insulin=insulin,
            visible_insulin=visible_insulin,
            manual_by_insulin=manual_by_insulin,
            auto_by_insulin=auto_by_insulin,
            auto_links=auto_links,
            active_links=active_links,
            reviewed_insulin_event_ids=reviewed_insulin_event_ids,
            glucose=glucose,
        )

    def _replace_episode_snapshots(self, day: date) -> None:
        context = self._day_context(day)
        snapshots = _episode_snapshots(
            context.day,
            context.meals,
            context.visible_insulin,
            context.active_links,
            context.glucose,
        )
        self.links.replace_episode_snapshots(day, snapshots)

    def _meals(self, day_start: datetime, next_day_start: datetime) -> list[Meal]:
        return list(
            self.session.scalars(
                select(Meal)
                .where(
                    Meal.owner_id == self.user_id,
                    Meal.status == MealStatus.accepted,
                    Meal.eaten_at >= day_start,
                    Meal.eaten_at < next_day_start,
                )
                .order_by(Meal.eaten_at.asc(), Meal.created_at.asc())
            )
        )

    def _insulin(
        self,
        day_start: datetime,
        next_day_start: datetime,
    ) -> list[NightscoutInsulinEvent]:
        return list(
            self.session.scalars(
                select(NightscoutInsulinEvent)
                .where(
                    NightscoutInsulinEvent.owner_id == self.user_id,
                    NightscoutInsulinEvent.timestamp >= day_start - DAY_BUFFER,
                    NightscoutInsulinEvent.timestamp < next_day_start + DAY_BUFFER,
                )
                .order_by(NightscoutInsulinEvent.timestamp.asc())
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
                    NightscoutGlucoseEntry.owner_id == self.user_id,
                    NightscoutGlucoseEntry.timestamp >= from_datetime,
                    NightscoutGlucoseEntry.timestamp < to_datetime,
                )
                .order_by(NightscoutGlucoseEntry.timestamp.asc())
            )
        )


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    day_start = datetime.combine(day, time.min)
    return day_start, day_start + timedelta(days=1)


def _glucose_anchor_response(
    anchor: GlucoseAnchor | None,
) -> InsulinLinkGlucoseAnchorResponse | None:
    if anchor is None:
        return None
    return InsulinLinkGlucoseAnchorResponse(
        value=anchor.value,
        timestamp=anchor.timestamp,
        source=anchor.source,
    )


def _glucose_anchor(
    readings: list[NightscoutGlucoseEntry],
    target: datetime,
) -> GlucoseAnchor | None:
    """Return CGM value nearest to target or interpolated across a short gap."""
    if not readings:
        return None

    ordered = sorted(readings, key=_reading_local_timestamp)
    nearest = min(
        ordered,
        key=lambda reading: abs(
            (_reading_local_timestamp(reading) - target).total_seconds()
        ),
    )
    nearest_time = _reading_local_timestamp(nearest)
    if abs(nearest_time - target) <= GLUCOSE_ACTUAL_TOLERANCE:
        return GlucoseAnchor(
            value=round(nearest.value_mmol_l, 1),
            timestamp=nearest_time,
            source="actual",
        )

    before: NightscoutGlucoseEntry | None = None
    after: NightscoutGlucoseEntry | None = None
    for reading in ordered:
        reading_time = _reading_local_timestamp(reading)
        if reading_time <= target:
            before = reading
        if reading_time >= target and after is None:
            after = reading

    if before is None or after is None:
        return None

    before_time = _reading_local_timestamp(before)
    after_time = _reading_local_timestamp(after)
    if before_time == after_time:
        return GlucoseAnchor(
            value=round(before.value_mmol_l, 1),
            timestamp=before_time,
            source="actual",
        )

    gap = after_time - before_time
    if gap > GLUCOSE_INTERPOLATION_MAX_GAP:
        return None

    fraction = (target - before_time).total_seconds() / gap.total_seconds()
    value = before.value_mmol_l + (
        after.value_mmol_l - before.value_mmol_l
    ) * fraction
    return GlucoseAnchor(
        value=round(value, 1),
        timestamp=target,
        source="interpolated",
    )


def _reading_local_timestamp(reading: NightscoutGlucoseEntry) -> datetime:
    return _local_wall_time(reading.timestamp)


def _episode_snapshots(
    day: date,
    meals: list[Meal],
    insulin: list[NightscoutInsulinEvent],
    links: list[MealInsulinLinkItem],
    glucose: list[NightscoutGlucoseEntry],
) -> list[EpisodeSnapshotData]:
    graph: dict[str, set[str]] = {}
    meal_by_id = {meal.id: meal for meal in meals}
    insulin_by_id = {event.id: event for event in insulin}

    def add_node(node: str) -> None:
        graph.setdefault(node, set())

    def add_edge(left: str, right: str) -> None:
        add_node(left)
        add_node(right)
        graph[left].add(right)
        graph[right].add(left)

    for meal in meals:
        add_node(f"m:{meal.id}")
    for event in insulin:
        add_node(f"i:{event.id}")

    visible_links = [
        link
        for link in links
        if link.meal_id in meal_by_id and link.insulin_event_id in insulin_by_id
    ]
    for link in visible_links:
        add_edge(f"m:{link.meal_id}", f"i:{link.insulin_event_id}")

    linked_meal_ids = {link.meal_id for link in visible_links}
    food_only_meals = sorted(
        (meal for meal in meals if meal.id not in linked_meal_ids),
        key=lambda meal: meal.eaten_at,
    )
    for previous, current in zip(food_only_meals, food_only_meals[1:], strict=False):
        if current.eaten_at - previous.eaten_at <= FOOD_ONLY_CLUSTER_WINDOW:
            add_edge(f"m:{previous.id}", f"m:{current.id}")

    visited: set[str] = set()
    components: list[list[str]] = []
    for node in graph:
        if node in visited:
            continue
        stack = [node]
        component: list[str] = []
        visited.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for next_node in graph.get(current, set()):
                if next_node in visited:
                    continue
                visited.add(next_node)
                stack.append(next_node)
        components.append(component)

    snapshots: list[EpisodeSnapshotData] = []
    for component in components:
        component_meals = sorted(
            (
                meal_by_id[UUID(node[2:])]
                for node in component
                if node.startswith("m:") and UUID(node[2:]) in meal_by_id
            ),
            key=lambda meal: meal.eaten_at,
        )
        component_insulin = sorted(
            (
                insulin_by_id[UUID(node[2:])]
                for node in component
                if node.startswith("i:") and UUID(node[2:]) in insulin_by_id
            ),
            key=lambda event: _local_wall_time(event.timestamp),
        )
        component_links = [
            link
            for link in visible_links
            if link.meal_id in {meal.id for meal in component_meals}
            and link.insulin_event_id in {event.id for event in component_insulin}
        ]
        timestamps = [meal.eaten_at for meal in component_meals] + [
            _local_wall_time(event.timestamp) for event in component_insulin
        ]
        if not timestamps:
            continue

        kind = _episode_kind(component_meals, component_insulin, component_links)
        glucose_minus_30 = (
            _glucose_anchor(
                glucose,
                component_meals[0].eaten_at - timedelta(minutes=30),
            )
            if component_meals
            else None
        )
        glucose_plus_2h = (
            _glucose_anchor(glucose, component_meals[-1].eaten_at + timedelta(hours=2))
            if component_meals
            else None
        )
        snapshot = EpisodeSnapshotData(
            episode_key="|".join(sorted(component)),
            sequence=0,
            kind=kind,
            title=_episode_title(component_meals, component_insulin, kind),
            start_at=min(timestamps),
            end_at=max(timestamps),
            meal_ids=[meal.id for meal in component_meals],
            insulin_event_ids=[event.id for event in component_insulin],
            link_pairs=_link_pair_payloads(component_links),
            total_carbs_g=round(
                sum(meal.total_carbs_g for meal in component_meals),
                1,
            ),
            total_kcal=round(sum(meal.total_kcal for meal in component_meals), 1),
            total_insulin_units=round(
                sum(event.insulin_units or 0 for event in component_insulin),
                2,
            ),
            glucose_minus_30=glucose_minus_30,
            glucose_plus_2h=glucose_plus_2h,
            snapshot_json={},
        )
        snapshots.append(snapshot)

    snapshots.sort(key=lambda snapshot: (snapshot.start_at, snapshot.episode_key))
    for index, snapshot in enumerate(snapshots, start=1):
        snapshot.sequence = index
        snapshot.snapshot_json = _episode_snapshot_payload(day, snapshot)
    return snapshots


def _episode_kind(
    meals: list[Meal],
    insulin: list[NightscoutInsulinEvent],
    links: list[MealInsulinLinkItem],
) -> str:
    if any(link.source == "manual" for link in links):
        return "manual"
    if meals and not insulin:
        return "food_only"
    if len(insulin) > 1:
        return "mixed"
    if links:
        return "food"
    if insulin and "correction" in (insulin[0].event_type or "").casefold():
        return "correction"
    return "unresolved"


def _episode_title(
    meals: list[Meal],
    insulin: list[NightscoutInsulinEvent],
    kind: str,
) -> str:
    if len(meals) > 1:
        return f"{meals[0].title or 'Приём пищи'} + {len(meals) - 1}"
    if len(meals) == 1:
        return meals[0].title or "Приём пищи"
    if kind == "correction":
        return "Коррекция без еды"
    if kind == "unresolved":
        return "Требует разбора"
    if len(insulin) > 1:
        return "Несколько bolus events"
    return "Bolus event"


def _link_pair_payloads(links: list[MealInsulinLinkItem]) -> list[dict[str, Any]]:
    return [
        {
            "meal_id": str(link.meal_id),
            "insulin_event_id": str(link.insulin_event_id),
            "source": link.source,
            "confidence": link.confidence,
            "note": link.note,
        }
        for link in links
    ]


def _episode_snapshot_payload(
    day: date,
    snapshot: EpisodeSnapshotData,
) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "episode_key": snapshot.episode_key,
        "sequence": snapshot.sequence,
        "kind": snapshot.kind,
        "title": snapshot.title,
        "start_at": snapshot.start_at.isoformat(),
        "end_at": snapshot.end_at.isoformat(),
        "meal_ids": [str(meal_id) for meal_id in snapshot.meal_ids],
        "insulin_event_ids": [
            str(event_id) for event_id in snapshot.insulin_event_ids
        ],
        "link_pairs": snapshot.link_pairs,
        "totals": {
            "carbs_g": snapshot.total_carbs_g,
            "kcal": snapshot.total_kcal,
            "insulin_units": snapshot.total_insulin_units,
        },
        "glucose": {
            "minus_30": _anchor_payload(snapshot.glucose_minus_30),
            "plus_2h": _anchor_payload(snapshot.glucose_plus_2h),
        },
    }


def _anchor_payload(anchor: GlucoseAnchor | None) -> dict[str, Any] | None:
    if anchor is None:
        return None
    return {
        "value": anchor.value,
        "timestamp": anchor.timestamp.isoformat(),
        "source": anchor.source,
    }


def _auto_links(
    meals: list[Meal],
    insulin: list[NightscoutInsulinEvent],
) -> list[AutoLink]:
    links: list[AutoLink] = []
    for event in insulin:
        if event.insulin_units is None or event.insulin_units <= 0:
            continue
        event_time = _local_wall_time(event.timestamp)
        for meal in meals:
            meal_window_start = meal.eaten_at - INSULIN_WINDOW_BEFORE
            meal_window_end = meal.eaten_at + INSULIN_WINDOW_AFTER
            if meal_window_start <= event_time <= meal_window_end:
                delta_minutes = abs((event_time - meal.eaten_at).total_seconds()) / 60
                links.append(
                    AutoLink(
                        meal_id=meal.id,
                        insulin_event_id=event.id,
                        confidence=_confidence(delta_minutes),
                    )
                )
    return links


def _confidence(delta_minutes: float) -> float:
    if delta_minutes <= 15:
        return 0.9
    if delta_minutes <= 45:
        return 0.75
    if delta_minutes <= 90:
        return 0.6
    return 0.4


def _event_response(
    event: NightscoutInsulinEvent,
    manual_links: list[MealInsulinLink],
    auto_links: list[AutoLink],
    is_reviewed: bool,
) -> InsulinLinkEventResponse:
    manual_meal_ids = [link.meal_id for link in manual_links]
    auto_meal_ids = [link.meal_id for link in auto_links]
    active_meal_ids = manual_meal_ids if is_reviewed else auto_meal_ids
    context_label = _context_label(
        event,
        manual_meal_ids,
        auto_meal_ids,
        is_reviewed,
    )
    link_source = (
        "manual"
        if is_reviewed
        else "auto"
        if auto_meal_ids
        else "none"
    )
    confidence_values = (
        [link.confidence for link in manual_links if link.confidence is not None]
        or [link.confidence for link in auto_links]
    )
    confidence = max(confidence_values) if confidence_values else None
    reason = _reason(context_label, link_source, len(active_meal_ids))
    return InsulinLinkEventResponse(
        id=event.id,
        timestamp=event.timestamp,
        insulin_units=event.insulin_units,
        raw_event_type=event.event_type,
        insulin_type=event.insulin_type,
        enteredBy=event.entered_by,
        notes=event.notes,
        nightscout_id=event.nightscout_id,
        context_label=context_label,
        link_source=link_source,
        linked_meal_ids=manual_meal_ids,
        suggested_meal_ids=auto_meal_ids,
        confidence=confidence,
        reason=reason,
        covers_multiple_food_events=len(active_meal_ids) > 1,
    )


def _context_label(
    event: NightscoutInsulinEvent,
    manual_meal_ids: list[UUID],
    auto_meal_ids: list[UUID],
    is_reviewed: bool,
) -> str:
    if manual_meal_ids:
        return "manual"
    if auto_meal_ids and not is_reviewed:
        return "food"
    event_type = (event.event_type or "").casefold()
    if "correction" in event_type:
        return "correction"
    return "unresolved"


def _reason(context_label: str, link_source: str, food_count: int) -> str:
    if link_source == "manual":
        return "ручная связь"
    if link_source == "auto":
        return (
            "в окне нескольких приёмов пищи"
            if food_count > 1
            else "в окне приёма пищи"
        )
    if context_label == "correction":
        return "рядом нет записей о еде"
    return "требует разбора"


def _link_item(link: MealInsulinLink) -> MealInsulinLinkItem:
    return MealInsulinLinkItem(
        meal_id=link.meal_id,
        insulin_event_id=link.insulin_event_id,
        source=link.source,
        confidence=link.confidence,
        note=link.note,
    )


def _effective_link_items(
    reviewed_insulin_event_ids: set[UUID],
    manual_by_insulin: dict[UUID, list[MealInsulinLink]],
    auto_links: list[AutoLink],
) -> list[MealInsulinLinkItem]:
    links: list[MealInsulinLinkItem] = []
    for manual_links in manual_by_insulin.values():
        links.extend(_link_item(link) for link in manual_links)
    links.extend(
        MealInsulinLinkItem(
            meal_id=link.meal_id,
            insulin_event_id=link.insulin_event_id,
            source="auto",
            confidence=link.confidence,
        )
        for link in auto_links
        if link.insulin_event_id not in reviewed_insulin_event_ids
    )
    return links


def _is_visible_event(
    event: NightscoutInsulinEvent,
    day_start: datetime,
    next_day_start: datetime,
    manual_by_insulin: dict[UUID, list[MealInsulinLink]],
) -> bool:
    local_timestamp = _local_wall_time(event.timestamp)
    return (
        day_start <= local_timestamp < next_day_start
        or event.id in manual_by_insulin
    )
