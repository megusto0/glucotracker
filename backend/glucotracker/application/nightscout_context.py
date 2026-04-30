"""Local Nightscout context import and food-episode grouping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from glucotracker.api.schemas import (
    FoodEpisodeResponse,
    MealResponse,
    NightscoutGlucoseEntryResponse,
    NightscoutImportResponse,
    NightscoutInsulinEventResponse,
    TimelineGlucoseSummary,
    TimelineInsulinEventResponse,
    TimelineResponse,
)
from glucotracker.config import get_settings
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    Meal,
    MealItem,
    NightscoutGlucoseEntry,
    NightscoutImportState,
    NightscoutInsulinEvent,
    utc_now,
)
from glucotracker.infra.nightscout.client import (
    NIGHTSCOUT_NOT_CONFIGURED,
    NightscoutClient,
)

MEAL_CLUSTER_WINDOW = timedelta(minutes=30)
INSULIN_WINDOW_BEFORE = timedelta(minutes=30)
INSULIN_WINDOW_AFTER = timedelta(minutes=90)
GLUCOSE_WINDOW_BEFORE = timedelta(minutes=60)
GLUCOSE_WINDOW_AFTER = timedelta(minutes=180)


class NightscoutContextImportService:
    """Import read-only Nightscout context into local tables."""

    def __init__(
        self,
        session: Session,
        client: NightscoutClient | None = None,
    ) -> None:
        self.session = session
        self.client = client

    async def import_range(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        *,
        sync_glucose: bool = True,
        import_insulin_events: bool = True,
    ) -> NightscoutImportResponse:
        """Fetch Nightscout context and upsert it into the local cache."""
        if not sync_glucose and not import_insulin_events:
            return self._response(from_datetime, to_datetime, 0, 0)
        if self.client is None or not self.client.configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=NIGHTSCOUT_NOT_CONFIGURED,
            )

        glucose_rows = []
        insulin_rows = []
        if sync_glucose:
            glucose_rows = await self.client.fetch_glucose_entries(
                from_datetime, to_datetime,
            )
        if import_insulin_events:
            insulin_rows = await self.client.fetch_insulin_events(
                from_datetime, to_datetime,
            )

        return self.import_fetched(
            from_datetime, to_datetime,
            glucose_rows=glucose_rows,
            insulin_rows=insulin_rows,
        )

    def import_fetched(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        *,
        glucose_rows: list[dict[str, Any]],
        insulin_rows: list[dict[str, Any]],
    ) -> NightscoutImportResponse:
        """Upsert pre-fetched Nightscout data into the local cache."""
        glucose_imported = 0
        insulin_imported = 0
        state = self._state()
        try:
            for row in glucose_rows:
                if self._upsert_glucose(row):
                    glucose_imported += 1
            if glucose_rows:
                state.last_glucose_import_at = utc_now()

            for row in insulin_rows:
                if self._upsert_insulin(row):
                    insulin_imported += 1
            if insulin_rows:
                state.last_insulin_import_at = utc_now()

            state.last_error = None
            state.updated_at = utc_now()
            self.session.commit()
        except Exception as exc:
            state.last_error = str(exc) or "Nightscout import failed"
            state.updated_at = utc_now()
            self.session.commit()
            raise

        return self._response(
            from_datetime, to_datetime,
            glucose_imported, insulin_imported,
        )

    def _response(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        glucose_imported: int,
        insulin_imported: int,
    ) -> NightscoutImportResponse:
        local_from = _local_wall_time(from_datetime)
        local_to = _local_wall_time(to_datetime)
        glucose_total = self.session.scalar(
            select(func.count(NightscoutGlucoseEntry.id)).where(
                NightscoutGlucoseEntry.timestamp >= local_from,
                NightscoutGlucoseEntry.timestamp <= local_to,
            )
        )
        insulin_total = self.session.scalar(
            select(func.count(NightscoutInsulinEvent.id)).where(
                NightscoutInsulinEvent.timestamp >= local_from,
                NightscoutInsulinEvent.timestamp <= local_to,
            )
        )
        return NightscoutImportResponse(
            from_datetime=from_datetime,
            to_datetime=to_datetime,
            glucose_imported=glucose_imported,
            insulin_imported=insulin_imported,
            glucose_total=glucose_total or 0,
            insulin_total=insulin_total or 0,
            last_error=self._state().last_error,
        )

    def _state(self) -> NightscoutImportState:
        row = self.session.get(NightscoutImportState, 1)
        if row is not None:
            return row
        row = NightscoutImportState(id=1)
        self.session.add(row)
        self.session.flush()
        return row

    def _upsert_glucose(self, row: dict[str, Any]) -> bool:
        normalized = _normalize_glucose_row(row)
        if normalized is None:
            return False
        existing = self.session.scalar(
            select(NightscoutGlucoseEntry).where(
                NightscoutGlucoseEntry.source_key == normalized["source_key"]
            )
        )
        if existing is None:
            self.session.add(NightscoutGlucoseEntry(**normalized))
            return True
        for key, value in normalized.items():
            setattr(existing, key, value)
        existing.updated_at = utc_now()
        existing.fetched_at = utc_now()
        return True

    def _upsert_insulin(self, row: dict[str, Any]) -> bool:
        normalized = _normalize_insulin_row(row)
        if normalized is None:
            return False
        existing = self.session.scalar(
            select(NightscoutInsulinEvent).where(
                NightscoutInsulinEvent.source_key == normalized["source_key"]
            )
        )
        if existing is None:
            self.session.add(NightscoutInsulinEvent(**normalized))
            return True
        for key, value in normalized.items():
            setattr(existing, key, value)
        existing.updated_at = utc_now()
        existing.fetched_at = utc_now()
        return True


class FoodEpisodeService:
    """Build backend-owned timeline episodes from local meals and NS context."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def timeline(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> TimelineResponse:
        """Return computed food episodes for a history range."""
        local_from = _local_wall_time(from_datetime)
        local_to = _local_wall_time(to_datetime)
        meals = self._meals(local_from, local_to)
        insulin = self._insulin(
            local_from - INSULIN_WINDOW_BEFORE,
            local_to + INSULIN_WINDOW_AFTER,
        )
        glucose = self._glucose(
            local_from - GLUCOSE_WINDOW_BEFORE,
            local_to + GLUCOSE_WINDOW_AFTER,
        )
        clusters = _cluster_meals(meals)
        linked_insulin_keys: set[str] = set()
        episodes: list[FoodEpisodeResponse] = []

        for index, cluster in enumerate(clusters):
            first_meal_at = cluster[0].eaten_at
            last_meal_at = cluster[-1].eaten_at
            insulin_window_start = first_meal_at - INSULIN_WINDOW_BEFORE
            insulin_window_end = last_meal_at + INSULIN_WINDOW_AFTER
            glucose_window_start = first_meal_at - GLUCOSE_WINDOW_BEFORE
            glucose_window_end = last_meal_at + GLUCOSE_WINDOW_AFTER

            linked_insulin = [
                event
                for event in insulin
                if insulin_window_start <= event.timestamp <= insulin_window_end
            ]
            linked_glucose = [
                entry
                for entry in glucose
                if glucose_window_start <= entry.timestamp <= glucose_window_end
            ]
            linked_insulin_keys.update(event.source_key for event in linked_insulin)
            episode_start = min(
                [meal.eaten_at for meal in cluster]
                + [event.timestamp for event in linked_insulin],
                default=first_meal_at,
            )
            episode_end = max(
                [meal.eaten_at for meal in cluster]
                + [event.timestamp for event in linked_insulin],
                default=last_meal_at,
            )
            episode_id = f"episode-{first_meal_at.isoformat()}-{index}"
            episodes.append(
                FoodEpisodeResponse(
                    id=episode_id,
                    start_at=episode_start,
                    end_at=episode_end,
                    title=_episode_title(cluster),
                    meals=[MealResponse.model_validate(meal) for meal in cluster],
                    insulin=[_insulin_response(event) for event in linked_insulin],
                    glucose=[_glucose_response(entry) for entry in linked_glucose],
                    glucose_summary=_glucose_summary(linked_glucose, first_meal_at),
                    total_carbs_g=round(sum(meal.total_carbs_g for meal in cluster), 1),
                    total_kcal=round(sum(meal.total_kcal for meal in cluster), 1),
                )
            )

        ungrouped_insulin = [
            TimelineInsulinEventResponse(
                **_insulin_response(event).model_dump(),
                linked_episode_id=None,
            )
            for event in insulin
            if event.source_key not in linked_insulin_keys
            and local_from <= event.timestamp <= local_to
        ]

        return TimelineResponse(
            from_datetime=from_datetime,
            to_datetime=to_datetime,
            episodes=episodes,
            ungrouped_insulin=ungrouped_insulin,
        )

    def _meals(self, from_datetime: datetime, to_datetime: datetime) -> list[Meal]:
        return list(
            self.session.scalars(
                select(Meal)
                .where(
                    Meal.status == MealStatus.accepted,
                    Meal.eaten_at >= from_datetime,
                    Meal.eaten_at <= to_datetime,
                )
                .options(
                    selectinload(Meal.items).selectinload(MealItem.nutrients),
                    selectinload(Meal.items).selectinload(MealItem.pattern),
                    selectinload(Meal.items).selectinload(MealItem.product),
                    selectinload(Meal.photos),
                )
                .order_by(Meal.eaten_at.asc(), Meal.created_at.asc())
            )
        )

    def _glucose(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[NightscoutGlucoseEntry]:
        # Future: history should stay on raw CGM by default; normalized display
        # data needs an explicit opt-in path and clear UI labeling.
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


def _cluster_meals(meals: list[Meal]) -> list[list[Meal]]:
    clusters: list[list[Meal]] = []
    for meal in meals:
        if not clusters:
            clusters.append([meal])
            continue
        previous = clusters[-1][-1]
        if meal.eaten_at - previous.eaten_at <= MEAL_CLUSTER_WINDOW:
            clusters[-1].append(meal)
        else:
            clusters.append([meal])
    return clusters


def _episode_title(meals: list[Meal]) -> str:
    if len(meals) == 1:
        if meals[0].title:
            return meals[0].title
        if meals[0].items:
            return meals[0].items[0].name
        return "Приём пищи"
    return "Пищевой эпизод"


def _glucose_summary(
    entries: list[NightscoutGlucoseEntry],
    meal_at: datetime,
) -> TimelineGlucoseSummary:
    if not entries:
        return TimelineGlucoseSummary()
    values = [entry.value_mmol_l for entry in entries]
    before_entries = [entry for entry in entries if entry.timestamp <= meal_at]
    before = before_entries[-1].value_mmol_l if before_entries else None
    latest = entries[-1].value_mmol_l
    return TimelineGlucoseSummary(
        before_value=before,
        peak_value=max(values),
        latest_value=latest,
        min_value=min(values),
        max_value=max(values),
    )


def _glucose_response(row: NightscoutGlucoseEntry) -> NightscoutGlucoseEntryResponse:
    return NightscoutGlucoseEntryResponse(
        timestamp=row.timestamp,
        value=row.value_mmol_l,
        trend=row.trend,
        source=row.source,
    )


def _insulin_response(row: NightscoutInsulinEvent) -> NightscoutInsulinEventResponse:
    return NightscoutInsulinEventResponse(
        timestamp=row.timestamp,
        insulin_units=row.insulin_units,
        eventType=row.event_type,
        insulin_type=row.insulin_type,
        enteredBy=row.entered_by,
        notes=row.notes,
        nightscout_id=row.nightscout_id,
    )


def _normalize_glucose_row(row: dict[str, Any]) -> dict[str, Any] | None:
    timestamp = _timestamp_from_row(row)
    sgv = _as_float(row.get("sgv") or row.get("mbg"))
    if timestamp is None or sgv is None:
        return None
    nightscout_id = _nightscout_id(row)
    value_mmol_l = round(sgv / 18.0182, 1)
    source = str(row.get("device")) if row.get("device") else "Nightscout"
    return {
        "source_key": _source_key("glucose", row, timestamp, value_mmol_l),
        "nightscout_id": nightscout_id,
        "timestamp": timestamp,
        "value_mmol_l": value_mmol_l,
        "value_mg_dl": sgv,
        "trend": str(row.get("direction")) if row.get("direction") else None,
        "source": source,
        "raw_json": row,
        "fetched_at": utc_now(),
    }


def _normalize_insulin_row(row: dict[str, Any]) -> dict[str, Any] | None:
    timestamp = _timestamp_from_row(row)
    if timestamp is None:
        return None
    insulin_units = _as_float(row.get("insulin"))
    event_type = str(row.get("eventType")) if row.get("eventType") else None
    nightscout_id = _nightscout_id(row)
    return {
        "source_key": _source_key("insulin", row, timestamp, insulin_units),
        "nightscout_id": nightscout_id,
        "timestamp": timestamp,
        "insulin_units": insulin_units,
        "event_type": event_type,
        "insulin_type": str(row.get("insulinType")) if row.get("insulinType") else None,
        "entered_by": str(row.get("enteredBy")) if row.get("enteredBy") else None,
        "notes": str(row.get("notes")) if row.get("notes") else None,
        "raw_json": row,
        "fetched_at": utc_now(),
    }


def _source_key(
    kind: str,
    row: dict[str, Any],
    timestamp: datetime,
    value: object,
) -> str:
    nightscout_id = _nightscout_id(row)
    if nightscout_id:
        return f"{kind}:{nightscout_id}"
    source_name = row.get("device") or row.get("eventType") or ""
    return f"{kind}:{timestamp.isoformat()}:{value}:{source_name}"


def _nightscout_id(row: dict[str, Any]) -> str | None:
    value = row.get("_id") or row.get("id")
    return str(value) if value is not None else None


def _timestamp_from_row(row: dict[str, Any]) -> datetime | None:
    raw = row.get("dateString") or row.get("created_at") or row.get("createdAt")
    if isinstance(raw, str) and raw:
        try:
            return _local_wall_time(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            return None
    raw_date = row.get("date")
    if isinstance(raw_date, int | float):
        return _local_wall_time(datetime.fromtimestamp(raw_date / 1000, tz=UTC))
    return None


def _local_wall_time(value: datetime) -> datetime:
    """Convert aware timestamps to app-local naive wall time for grouping."""
    if value.tzinfo is None:
        return value
    return value.astimezone(get_settings().local_zoneinfo).replace(tzinfo=None)


def _as_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None
