"""Application services for optional Nightscout synchronization."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.api.schemas import (
    NightscoutDayStatusResponse,
    NightscoutEventsResponse,
    NightscoutGlucoseEntryResponse,
    NightscoutInsulinEventResponse,
    NightscoutSettingsPatch,
    NightscoutSettingsResponse,
    NightscoutStatusResponse,
    NightscoutSyncResponse,
    NightscoutSyncTodayMealResult,
    NightscoutSyncTodayResponse,
    NightscoutTestResponse,
)
from glucotracker.config import get_settings
from glucotracker.domain.entities import MealStatus, NightscoutSyncStatus
from glucotracker.infra.db.models import Meal, MealItem, NightscoutSettings, utc_now
from glucotracker.infra.nightscout.client import (
    NIGHTSCOUT_NOT_CONFIGURED,
    NightscoutClient,
    NightscoutHTTPError,
    NightscoutTimeoutError,
)


class NightscoutSettingsService:
    """Manage masked server-side Nightscout settings with .env fallback."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(self) -> NightscoutSettings:
        """Return the singleton settings row."""
        row = self.session.get(NightscoutSettings, 1)
        if row is not None:
            return row

        env = get_settings()
        row = NightscoutSettings(
            id=1,
            enabled=bool(env.nightscout_url and env.nightscout_api_secret),
            url=env.nightscout_url,
            api_secret=env.nightscout_api_secret,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, payload: NightscoutSettingsPatch) -> NightscoutSettingsResponse:
        """Update settings. API secret is write-only and never echoed back."""
        row = self.get_or_create()
        data = payload.model_dump(exclude_unset=True)
        field_map = {
            "nightscout_enabled": "enabled",
            "nightscout_url": "url",
            "nightscout_api_secret": "api_secret",
            "sync_glucose": "sync_glucose",
            "show_glucose_in_journal": "show_glucose_in_journal",
            "import_insulin_events": "import_insulin_events",
            "allow_meal_send": "allow_meal_send",
            "confirm_before_send": "confirm_before_send",
            "autosend_meals": "autosend_meals",
        }
        for request_field, model_field in field_map.items():
            if request_field not in data:
                continue
            value = data[request_field]
            if request_field == "nightscout_api_secret" and value == "":
                value = row.api_secret
            if request_field == "autosend_meals":
                value = False
            setattr(row, model_field, value)
        row.updated_at = utc_now()
        self.session.commit()
        return self.response(row)

    def response(
        self,
        row: NightscoutSettings | None = None,
        *,
        connected: bool | None = None,
    ) -> NightscoutSettingsResponse:
        """Return masked settings suitable for frontend display."""
        row = row or self.get_or_create()
        effective_url, effective_secret = self.effective_credentials(row)
        configured = bool(effective_url and effective_secret)
        return NightscoutSettingsResponse(
            enabled=row.enabled,
            configured=configured,
            connected=bool(connected) if connected is not None else configured
            and not row.last_error,
            url=effective_url,
            secret_is_set=bool(effective_secret),
            last_status_check_at=row.last_status_check_at,
            last_error=row.last_error,
            sync_glucose=row.sync_glucose,
            show_glucose_in_journal=row.show_glucose_in_journal,
            import_insulin_events=row.import_insulin_events,
            allow_meal_send=row.allow_meal_send,
            confirm_before_send=row.confirm_before_send,
            autosend_meals=False,
        )

    def effective_credentials(
        self,
        row: NightscoutSettings | None = None,
    ) -> tuple[str | None, str | None]:
        """Return DB settings with .env fallback for legacy deployments."""
        row = row or self.get_or_create()
        env = get_settings()
        return (
            row.url or env.nightscout_url,
            row.api_secret or env.nightscout_api_secret,
        )

    def client(
        self,
        injected: NightscoutClient | None = None,
    ) -> NightscoutClient | None:
        """Return an injected fake client or a DB/env configured Nightscout client."""
        if injected is not None:
            return injected
        row = self.get_or_create()
        url, secret = self.effective_credentials(row)
        if not url or not secret:
            return None
        return NightscoutClient(base_url=url, api_secret=secret)

    async def test_connection(
        self,
        injected: NightscoutClient | None = None,
    ) -> NightscoutTestResponse:
        """Test Nightscout connection and persist masked status metadata."""
        row = self.get_or_create()
        client = self.client(injected)
        row.last_status_check_at = utc_now()
        if client is None or not client.configured:
            row.last_error = NIGHTSCOUT_NOT_CONFIGURED
            self.session.commit()
            return NightscoutTestResponse(ok=False, error=NIGHTSCOUT_NOT_CONFIGURED)

        try:
            if hasattr(client, "check_status"):
                status_payload = await client.check_status()
            else:
                status_payload = await client.get_status()
        except Exception as exc:
            mapped = NightscoutSyncService.map_error(exc)
            row.last_error = _detail_to_text(mapped.detail)
            self.session.commit()
            return NightscoutTestResponse(ok=False, error=row.last_error)

        row.last_error = None
        self.session.commit()
        return NightscoutTestResponse(
            ok=True,
            status=status_payload,
            server_name=_status_server_name(status_payload),
            version=_status_version(status_payload),
        )


class NightscoutSyncService:
    """Coordinate Nightscout capability checks, meal sync, and read-only imports."""

    def __init__(
        self,
        session: Session,
        client: NightscoutClient | None = None,
    ) -> None:
        self.session = session
        self.settings = NightscoutSettingsService(session)
        self.client = self.settings.client(client)

    async def status(self) -> NightscoutStatusResponse:
        """Return optional Nightscout status without blocking local app use."""
        settings_row = self.settings.get_or_create()
        if self.client is None or not self.client.configured:
            base = self.settings.response(settings_row, connected=False)
            return NightscoutStatusResponse(configured=base.configured, status=None)
        try:
            status_payload = await self.client.get_status()
        except Exception as exc:
            mapped = self.map_error(exc)
            settings_row.last_status_check_at = utc_now()
            settings_row.last_error = _detail_to_text(mapped.detail)
            self.session.commit()
            base = self.settings.response(settings_row, connected=False)
            return NightscoutStatusResponse(configured=base.configured, status=None)

        settings_row.last_status_check_at = utc_now()
        settings_row.last_error = None
        self.session.commit()
        base = self.settings.response(settings_row, connected=True)
        return NightscoutStatusResponse(
            configured=base.configured,
            status=status_payload,
        )

    async def sync_meal(self, meal_id: UUID) -> NightscoutSyncResponse:
        """Sync one accepted meal as a diary-only Nightscout treatment."""
        nightscout = self._require_client()
        meal = self._get_meal(meal_id)
        self._ensure_syncable(meal)
        if meal.nightscout_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Запись уже отправлена",
                    "nightscout_id": meal.nightscout_id,
                },
            )

        response = await self._post_meal(nightscout, meal)
        return self._sync_success(meal, response)

    async def unsync_meal(self, meal_id: UUID) -> NightscoutSyncResponse:
        """Delete a Nightscout treatment and clear local sync fields."""
        nightscout = self._require_client()
        meal = self._get_meal(meal_id)
        if not meal.nightscout_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meal is not synced to Nightscout.",
            )

        remote_id = meal.nightscout_id
        try:
            response = await nightscout.delete_treatment(remote_id)
        except Exception as exc:
            raise self.map_error(exc) from exc

        meal.nightscout_id = None
        meal.nightscout_synced_at = None
        meal.nightscout_sync_status = NightscoutSyncStatus.not_synced
        meal.nightscout_sync_error = None
        meal.nightscout_last_attempt_at = utc_now()
        self.session.commit()
        return NightscoutSyncResponse(
            synced=False,
            nightscout_id=None,
            nightscout_synced_at=None,
            nightscout_sync_status=meal.nightscout_sync_status.value,
            response=response,
        )

    async def sync_today(
        self,
        sync_date: date,
        *,
        confirm: bool = True,
    ) -> NightscoutSyncTodayResponse:
        """Manually send accepted unsynced meals for one diary day."""
        nightscout = self._require_client()
        if not confirm:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нужно подтвердить отправку дня в Nightscout.",
            )

        meals = self._accepted_meals_for_day(sync_date)
        results: list[NightscoutSyncTodayMealResult] = []
        for meal in meals:
            if meal.nightscout_id:
                meal.nightscout_sync_status = NightscoutSyncStatus.skipped
                results.append(
                    NightscoutSyncTodayMealResult(
                        meal_id=meal.id,
                        title=meal.title,
                        status="skipped",
                        nightscout_id=meal.nightscout_id,
                    )
                )
                continue

            try:
                response = await self._post_meal(nightscout, meal)
                self._sync_success(meal, response, commit=False)
                results.append(
                    NightscoutSyncTodayMealResult(
                        meal_id=meal.id,
                        title=meal.title,
                        status="sent",
                        nightscout_id=meal.nightscout_id,
                    )
                )
            except HTTPException as exc:
                meal.nightscout_sync_status = NightscoutSyncStatus.failed
                meal.nightscout_sync_error = _detail_to_text(exc.detail)
                meal.nightscout_last_attempt_at = utc_now()
                results.append(
                    NightscoutSyncTodayMealResult(
                        meal_id=meal.id,
                        title=meal.title,
                        status="failed",
                        error=meal.nightscout_sync_error,
                    )
                )

        self.session.commit()
        return NightscoutSyncTodayResponse(
            date=sync_date,
            total_candidates=len(meals),
            sent_count=sum(1 for result in results if result.status == "sent"),
            skipped_count=sum(1 for result in results if result.status == "skipped"),
            failed_count=sum(1 for result in results if result.status == "failed"),
            results=results,
        )

    async def day_status(self, sync_date: date) -> NightscoutDayStatusResponse:
        """Return manual-sync counters for one day."""
        settings = await self.status()
        meals = self._accepted_meals_for_day(sync_date)
        synced = [meal for meal in meals if meal.nightscout_id]
        failed = [
            meal
            for meal in meals
            if meal.nightscout_sync_status == NightscoutSyncStatus.failed
        ]
        last_sync_at = max(
            (meal.nightscout_synced_at for meal in synced if meal.nightscout_synced_at),
            default=None,
        )
        return NightscoutDayStatusResponse(
            date=sync_date,
            connected=settings.status is not None,
            configured=settings.configured,
            accepted_meals_count=len(meals),
            unsynced_meals_count=len(
                [meal for meal in meals if not meal.nightscout_id]
            ),
            synced_meals_count=len(synced),
            failed_meals_count=len(failed),
            last_sync_at=last_sync_at,
        )

    async def glucose(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[NightscoutGlucoseEntryResponse]:
        """Fetch read-only glucose entries normalized to mmol/L."""
        nightscout = self._require_client()
        try:
            rows = await nightscout.fetch_glucose_entries(from_datetime, to_datetime)
        except Exception as exc:
            raise self.map_error(exc) from exc
        return [_glucose_response(row) for row in rows if _glucose_response(row)]

    async def insulin(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[NightscoutInsulinEventResponse]:
        """Fetch read-only insulin treatment entries."""
        nightscout = self._require_client()
        try:
            rows = await nightscout.fetch_insulin_events(from_datetime, to_datetime)
        except Exception as exc:
            raise self.map_error(exc) from exc
        return [_insulin_response(row) for row in rows if _insulin_response(row)]

    async def events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> NightscoutEventsResponse:
        """Return combined glucose and insulin Nightscout context events."""
        return NightscoutEventsResponse(
            glucose=await self.glucose(from_datetime, to_datetime),
            insulin=await self.insulin(from_datetime, to_datetime),
        )

    def _get_meal(self, meal_id: UUID) -> Meal:
        meal = self.session.get(
            Meal,
            meal_id,
            options=(selectinload(Meal.items).selectinload(MealItem.nutrients),),
        )
        if meal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meal not found.",
            )
        return meal

    def _require_client(self) -> NightscoutClient:
        if self.client is None or not self.client.configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=NIGHTSCOUT_NOT_CONFIGURED,
            )
        return self.client

    @staticmethod
    def _ensure_syncable(meal: Meal) -> None:
        if meal.status != MealStatus.accepted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Черновики не отправляются. Отправлять можно только "
                    "accepted/принятые записи."
                ),
            )

    async def _post_meal(
        self,
        nightscout: NightscoutClient,
        meal: Meal,
    ) -> dict[str, Any]:
        self._ensure_syncable(meal)
        meal.nightscout_last_attempt_at = utc_now()
        meal.nightscout_sync_error = None
        try:
            if hasattr(nightscout, "post_meal_treatment"):
                return await nightscout.post_meal_treatment(meal)
            return await nightscout.post_treatment(meal)
        except Exception as exc:
            meal.nightscout_sync_status = NightscoutSyncStatus.failed
            meal.nightscout_sync_error = _detail_to_text(self.map_error(exc).detail)
            self.session.flush()
            raise self.map_error(exc) from exc

    def _sync_success(
        self,
        meal: Meal,
        response: dict[str, Any],
        *,
        commit: bool = True,
    ) -> NightscoutSyncResponse:
        remote_id = self._nightscout_id(response)
        if remote_id is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Nightscout response did not include treatment id.",
            )
        meal.nightscout_id = remote_id
        meal.nightscout_synced_at = utc_now()
        meal.nightscout_sync_status = NightscoutSyncStatus.synced
        meal.nightscout_sync_error = None
        meal.nightscout_last_attempt_at = meal.nightscout_synced_at
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return NightscoutSyncResponse(
            synced=True,
            nightscout_id=meal.nightscout_id,
            nightscout_synced_at=meal.nightscout_synced_at,
            nightscout_sync_status=meal.nightscout_sync_status.value,
            response=response,
        )

    def _accepted_meals_for_day(self, sync_date: date) -> list[Meal]:
        start = datetime.combine(sync_date, time.min, tzinfo=UTC)
        end = datetime.combine(sync_date, time.max, tzinfo=UTC)
        return list(
            self.session.scalars(
                select(Meal)
                .where(
                    Meal.status == MealStatus.accepted,
                    Meal.eaten_at >= start,
                    Meal.eaten_at <= end,
                )
                .options(selectinload(Meal.items))
                .order_by(Meal.eaten_at.asc())
            )
        )

    @staticmethod
    def map_error(exc: Exception) -> HTTPException:
        """Map Nightscout client failures to stable API errors."""
        if isinstance(exc, NightscoutTimeoutError):
            return HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=str(exc),
            )
        if isinstance(exc, NightscoutHTTPError):
            return HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Nightscout request failed",
                    "status_code": exc.status_code,
                    "response": exc.detail,
                },
            )
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Nightscout request failed",
        )

    @staticmethod
    def _nightscout_id(response: dict) -> str | None:
        value = response.get("_id") or response.get("id")
        if value is not None:
            return str(value)
        result = response.get("result")
        if isinstance(result, dict):
            nested = result.get("_id") or result.get("id")
            return str(nested) if nested is not None else None
        items = response.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            item_id = items[0].get("_id") or items[0].get("id")
            return str(item_id) if item_id is not None else None
        return None


def _detail_to_text(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        return str(message if message is not None else detail)
    return str(detail)


def _status_server_name(payload: dict[str, Any]) -> str | None:
    return (
        _nested_string(payload, "name")
        or _nested_string(payload, "server")
        or _nested_string(payload, "settings", "customTitle")
    )


def _status_version(payload: dict[str, Any]) -> str | None:
    return _nested_string(payload, "version") or _nested_string(
        payload,
        "serverTime",
        "version",
    )


def _nested_string(payload: dict[str, Any], *keys: str) -> str | None:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return str(value) if value is not None else None


def _timestamp_from_row(row: dict[str, Any]) -> datetime | None:
    raw = row.get("dateString") or row.get("created_at") or row.get("createdAt")
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    raw_date = row.get("date")
    if isinstance(raw_date, int | float):
        return datetime.fromtimestamp(raw_date / 1000, tz=UTC)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _glucose_response(row: dict[str, Any]) -> NightscoutGlucoseEntryResponse | None:
    timestamp = _timestamp_from_row(row)
    sgv = _as_float(row.get("sgv") or row.get("mbg"))
    if timestamp is None or sgv is None:
        return None
    mmol = round(sgv / 18.0182, 1)
    return NightscoutGlucoseEntryResponse(
        timestamp=timestamp,
        value=mmol,
        trend=str(row.get("direction")) if row.get("direction") else None,
        source=str(row.get("device")) if row.get("device") else "Nightscout",
    )


def _insulin_response(row: dict[str, Any]) -> NightscoutInsulinEventResponse | None:
    timestamp = _timestamp_from_row(row)
    if timestamp is None:
        return None
    return NightscoutInsulinEventResponse(
        timestamp=timestamp,
        insulin_units=_as_float(row.get("insulin")),
        eventType=str(row.get("eventType")) if row.get("eventType") else None,
        insulin_type=str(row.get("insulinType")) if row.get("insulinType") else None,
        enteredBy=str(row.get("enteredBy")) if row.get("enteredBy") else None,
        notes=str(row.get("notes")) if row.get("notes") else None,
        nightscout_id=str(row.get("_id") or row.get("id"))
        if row.get("_id") or row.get("id")
        else None,
    )
