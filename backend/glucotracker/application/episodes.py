"""Single backend-owned engine for grouping meals and insulin into episodes.

This is the one place that decides "what belongs together": window-based
auto-links, manual-link overrides, connected-component grouping, and
food-only clustering. ``insulin_links`` (desktop review page), the
``/glucose/episodes`` endpoint (mobile attribution), and the episode
snapshot worker all delegate here so the grouping can never diverge.

Descriptive only: episodes attribute records to each other; they never
suggest doses or treatment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.nightscout_context import (
    INSULIN_WINDOW_AFTER,
    INSULIN_WINDOW_BEFORE,
    _local_wall_time,
)
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    Meal,
    MealInsulinLink,
    NightscoutInsulinEvent,
)

FOOD_ONLY_CLUSTER_WINDOW = timedelta(minutes=45)
EPISODE_INSULIN_BUFFER = timedelta(minutes=90)


@dataclass(frozen=True)
class AutoLink:
    """Computed link candidate for one insulin event."""

    meal_id: UUID
    insulin_event_id: UUID
    confidence: float


@dataclass(frozen=True)
class EpisodePair:
    """One effective meal/insulin pair inside an episode."""

    meal_id: UUID
    insulin_event_id: UUID
    source: str
    confidence: float | None


@dataclass(frozen=True)
class EpisodeComponent:
    """One grouped episode: meals + insulin connected by links or proximity."""

    meals: list[Meal]
    insulin: list[NightscoutInsulinEvent]
    pairs: list[EpisodePair]

    @property
    def start_at(self) -> datetime:
        return min(self._timestamps())

    @property
    def end_at(self) -> datetime:
        return max(self._timestamps())

    def _timestamps(self) -> list[datetime]:
        return [meal.eaten_at for meal in self.meals] + [
            _local_wall_time(event.timestamp) for event in self.insulin
        ]


def auto_links(
    meals: list[Meal],
    insulin: list[NightscoutInsulinEvent],
) -> list[AutoLink]:
    """Window-based link candidates: every meal in the insulin window."""
    links: list[AutoLink] = []
    for event in insulin:
        if event.insulin_units is None or event.insulin_units <= 0:
            continue
        event_time = _local_wall_time(event.timestamp)
        for meal in meals:
            window_start = meal.eaten_at - INSULIN_WINDOW_BEFORE
            window_end = meal.eaten_at + INSULIN_WINDOW_AFTER
            if window_start <= event_time <= window_end:
                delta_minutes = abs((event_time - meal.eaten_at).total_seconds()) / 60
                links.append(
                    AutoLink(
                        meal_id=meal.id,
                        insulin_event_id=event.id,
                        confidence=link_confidence(delta_minutes),
                    )
                )
    return links


def link_confidence(delta_minutes: float) -> float:
    if delta_minutes <= 15:
        return 0.9
    if delta_minutes <= 45:
        return 0.75
    if delta_minutes <= 90:
        return 0.6
    return 0.4


def group_components(
    meals: list[Meal],
    insulin: list[NightscoutInsulinEvent],
    pairs: list[EpisodePair],
) -> list[EpisodeComponent]:
    """Connected components over link edges plus food-only clustering."""
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

    visible_pairs = [
        pair
        for pair in pairs
        if pair.meal_id in meal_by_id and pair.insulin_event_id in insulin_by_id
    ]
    for pair in visible_pairs:
        add_edge(f"m:{pair.meal_id}", f"i:{pair.insulin_event_id}")

    linked_meal_ids = {pair.meal_id for pair in visible_pairs}
    food_only_meals = sorted(
        (meal for meal in meals if meal.id not in linked_meal_ids),
        key=lambda meal: meal.eaten_at,
    )
    for previous, current in zip(
        food_only_meals,
        food_only_meals[1:],
        strict=False,
    ):
        if current.eaten_at - previous.eaten_at <= FOOD_ONLY_CLUSTER_WINDOW:
            add_edge(f"m:{previous.id}", f"m:{current.id}")

    visited: set[str] = set()
    components: list[EpisodeComponent] = []
    for node in graph:
        if node in visited:
            continue
        stack = [node]
        component_nodes: list[str] = []
        visited.add(node)
        while stack:
            current = stack.pop()
            component_nodes.append(current)
            for next_node in graph.get(current, set()):
                if next_node in visited:
                    continue
                visited.add(next_node)
                stack.append(next_node)

        component_meals = sorted(
            (
                meal_by_id[UUID(node[2:])]
                for node in component_nodes
                if node.startswith("m:") and UUID(node[2:]) in meal_by_id
            ),
            key=lambda meal: meal.eaten_at,
        )
        component_insulin = sorted(
            (
                insulin_by_id[UUID(node[2:])]
                for node in component_nodes
                if node.startswith("i:") and UUID(node[2:]) in insulin_by_id
            ),
            key=lambda event: _local_wall_time(event.timestamp),
        )
        if not component_meals and not component_insulin:
            continue
        component_meal_ids = {meal.id for meal in component_meals}
        component_insulin_ids = {event.id for event in component_insulin}
        component_pairs = [
            pair
            for pair in visible_pairs
            if pair.meal_id in component_meal_ids
            and pair.insulin_event_id in component_insulin_ids
        ]
        components.append(
            EpisodeComponent(
                meals=component_meals,
                insulin=component_insulin,
                pairs=component_pairs,
            )
        )

    components.sort(key=lambda component: component.start_at)
    return components


def anchor_meal_id(
    event: NightscoutInsulinEvent,
    component: EpisodeComponent,
) -> UUID | None:
    """Nearest meal of the episode — where the insulin line renders on mobile."""
    paired_meal_ids = {
        pair.meal_id for pair in component.pairs if pair.insulin_event_id == event.id
    }
    candidates = [
        meal for meal in component.meals if meal.id in paired_meal_ids
    ] or component.meals
    if not candidates:
        return None
    event_time = _local_wall_time(event.timestamp)
    return min(
        candidates,
        key=lambda meal: abs((meal.eaten_at - event_time).total_seconds()),
    ).id


class EpisodeQueryService:
    """Read-only episode grouping for a local wall-clock range."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def components(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[EpisodeComponent]:
        """Group accepted meals and insulin in the range into episodes.

        Accepts aware or naive datetimes; both are normalized to the local
        wall clock. Manual links (reviewed insulin) override auto
        suggestions, mirroring the desktop review semantics.
        """
        local_from = _local_wall_time(from_datetime)
        local_to = _local_wall_time(to_datetime)
        meals = list(
            self.session.scalars(
                select(Meal)
                .where(
                    Meal.owner_id == self.user_id,
                    Meal.status == MealStatus.accepted,
                    Meal.eaten_at >= local_from,
                    Meal.eaten_at < local_to,
                )
                .order_by(Meal.eaten_at.asc(), Meal.created_at.asc())
            )
        )
        utc_from = utc_instant_from_local_wall(local_from)
        utc_to = utc_instant_from_local_wall(local_to)
        insulin = _dedupe_insulin_events(
            list(
                self.session.scalars(
                    select(NightscoutInsulinEvent)
                    .where(
                        NightscoutInsulinEvent.owner_id == self.user_id,
                        NightscoutInsulinEvent.timestamp
                        >= utc_from - EPISODE_INSULIN_BUFFER,
                        NightscoutInsulinEvent.timestamp
                        < utc_to + EPISODE_INSULIN_BUFFER,
                    )
                    .order_by(NightscoutInsulinEvent.timestamp.asc())
                )
            )
        )
        visible_insulin = [
            event
            for event in insulin
            if local_from <= _local_wall_time(event.timestamp) < local_to
        ]
        manual_links = list(
            self.session.scalars(
                select(MealInsulinLink).where(
                    MealInsulinLink.owner_id == self.user_id,
                    MealInsulinLink.insulin_event_id.in_(
                        [event.id for event in visible_insulin] or [None]
                    ),
                )
            )
        )
        manual_by_insulin: dict[UUID, list[MealInsulinLink]] = {}
        for link in manual_links:
            manual_by_insulin.setdefault(link.insulin_event_id, []).append(link)

        pairs: list[EpisodePair] = []
        for links in manual_by_insulin.values():
            pairs.extend(
                EpisodePair(
                    meal_id=link.meal_id,
                    insulin_event_id=link.insulin_event_id,
                    source="manual",
                    confidence=link.confidence,
                )
                for link in links
            )
        pairs.extend(
            EpisodePair(
                meal_id=link.meal_id,
                insulin_event_id=link.insulin_event_id,
                source="auto",
                confidence=link.confidence,
            )
            for link in auto_links(meals, visible_insulin)
            if link.insulin_event_id not in manual_by_insulin
        )
        return group_components(meals, visible_insulin, pairs)


def _dedupe_insulin_events(
    events: list[NightscoutInsulinEvent],
) -> list[NightscoutInsulinEvent]:
    """Collapse historical cache duplicates without deleting source records."""
    by_remote_key: dict[str, NightscoutInsulinEvent] = {}
    for event in events:
        key = event.nightscout_id or event.source_key
        current = by_remote_key.get(key)
        if current is None or (
            event.source_key.startswith("manual_insulin:")
            and not current.source_key.startswith("manual_insulin:")
        ):
            by_remote_key[key] = event
    return sorted(by_remote_key.values(), key=lambda event: event.timestamp)
