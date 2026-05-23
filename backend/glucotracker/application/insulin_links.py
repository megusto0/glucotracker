"""Food/insulin day-link rules owned by the backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    InsulinLinkDayPutRequest,
    InsulinLinkDayResponse,
    InsulinLinkEventResponse,
    InsulinLinkMealResponse,
    MealInsulinLinkItem,
)
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
    MealInsulinLinkReview,
    NightscoutInsulinEvent,
)

DAY_BUFFER = timedelta(minutes=90)


@dataclass(frozen=True)
class AutoLink:
    """Computed link candidate for one insulin event."""

    meal_id: UUID
    insulin_event_id: UUID
    confidence: float


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
        utc_day_start = utc_instant_from_local_wall(day_start)
        utc_next_day_start = utc_instant_from_local_wall(next_day_start)
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
                        NightscoutInsulinEvent.timestamp >= utc_day_start,
                    ),
                    or_(
                        Meal.eaten_at < next_day_start,
                        NightscoutInsulinEvent.timestamp < utc_next_day_start,
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
        utc_day_start = utc_instant_from_local_wall(day_start)
        utc_next_day_start = utc_instant_from_local_wall(next_day_start)
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
                    NightscoutInsulinEvent.timestamp >= utc_day_start - DAY_BUFFER,
                    NightscoutInsulinEvent.timestamp < utc_next_day_start + DAY_BUFFER,
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
        utc_day_start = utc_instant_from_local_wall(day_start)
        utc_next_day_start = utc_instant_from_local_wall(next_day_start)
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
                    NightscoutInsulinEvent.timestamp >= utc_day_start - DAY_BUFFER,
                    NightscoutInsulinEvent.timestamp < utc_next_day_start + DAY_BUFFER,
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


class InsulinLinkDayService:
    """Build and save the no-graph day review workspace."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.links = MealInsulinLinkRepository(session, user_id)

    def get_day(self, day: date) -> InsulinLinkDayResponse:
        """Return meals, insulin events, manual links, and auto suggestions."""
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

        return InsulinLinkDayResponse(
            date=day,
            meals=[
                InsulinLinkMealResponse(
                    id=meal.id,
                    eaten_at=meal.eaten_at,
                    title=meal.title or "Приём пищи",
                    total_carbs_g=round(meal.total_carbs_g, 1),
                    total_kcal=round(meal.total_kcal, 1),
                )
                for meal in meals
            ],
            insulin_events=[
                _event_response(
                    event,
                    manual_by_insulin.get(event.id, []),
                    auto_by_insulin.get(event.id, []),
                    event.id in reviewed_insulin_event_ids,
                )
                for event in insulin
                if _is_visible_event(
                    event,
                    day_start,
                    next_day_start,
                    manual_by_insulin,
                )
            ],
            links=_effective_link_items(
                reviewed_insulin_event_ids,
                manual_by_insulin,
                auto_links,
            ),
            auto_links=[
                MealInsulinLinkItem(
                    meal_id=link.meal_id,
                    insulin_event_id=link.insulin_event_id,
                    source="auto",
                    confidence=link.confidence,
                )
                for link in auto_links
            ],
            reviewed_insulin_event_ids=sorted(
                reviewed_insulin_event_ids,
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
        self.session.commit()
        return self.get_day(payload.date)

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
        utc_day_start = utc_instant_from_local_wall(day_start)
        utc_next_day_start = utc_instant_from_local_wall(next_day_start)
        return list(
            self.session.scalars(
                select(NightscoutInsulinEvent)
                .where(
                    NightscoutInsulinEvent.owner_id == self.user_id,
                    NightscoutInsulinEvent.timestamp >= utc_day_start - DAY_BUFFER,
                    NightscoutInsulinEvent.timestamp < utc_next_day_start + DAY_BUFFER,
                )
                .order_by(NightscoutInsulinEvent.timestamp.asc())
            )
        )


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    day_start = datetime.combine(day, time.min)
    return day_start, day_start + timedelta(days=1)


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
