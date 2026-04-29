"""Async Nightscout REST client for optional treatment sync."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import httpx

from glucotracker.config import get_settings
from glucotracker.infra.db.models import Meal

NIGHTSCOUT_NOT_CONFIGURED = "Nightscout не подключён"


class NightscoutClientError(RuntimeError):
    """Base Nightscout client error."""


class NightscoutNotConfiguredError(NightscoutClientError):
    """Raised when Nightscout settings are incomplete."""


class NightscoutHTTPError(NightscoutClientError):
    """Raised when Nightscout responds with an error status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class NightscoutTimeoutError(NightscoutClientError):
    """Raised when Nightscout does not respond in time."""


def is_nightscout_configured() -> bool:
    """Return whether Nightscout has the required settings."""
    settings = get_settings()
    return bool(settings.nightscout_url and settings.nightscout_api_secret)


def _api_secret_hash(api_secret: str) -> str:
    """Return the SHA1 hash Nightscout expects in the api-secret header."""
    return hashlib.sha1(api_secret.encode("utf-8")).hexdigest()


def _meal_notes(meal: Meal) -> str:
    """Build a diary-only Nightscout treatment note."""
    parts = []
    if meal.title:
        parts.append(meal.title)
    if meal.note:
        parts.append(meal.note)
    item_names = [item.name for item in meal.items]
    if item_names:
        parts.append("items: " + ", ".join(item_names))
    parts.append(f"kcal: {meal.total_kcal:g}")
    parts.append(f"protein: {meal.total_protein_g:g}g")
    parts.append(f"fat: {meal.total_fat_g:g}g")
    parts.append("glucotracker diary-only estimate")
    return "\n".join(parts)


def _meal_datetime(value: datetime) -> datetime:
    """Return a timezone-aware local meal datetime for Nightscout payloads.

    The app stores `eaten_at` as the user's local wall time. SQLite drops the
    timezone info, so naive datetimes must be re-attached using the configured
    app timezone before any UTC conversion or offset math happens.
    """
    settings = get_settings()
    if value.tzinfo is None:
        return value.replace(tzinfo=settings.local_zoneinfo)
    return value.astimezone(settings.local_zoneinfo)


def _nightscout_created_at(value: datetime) -> str:
    """Return a timezone-explicit local timestamp for Nightscout treatments."""
    return _meal_datetime(value).isoformat()


def _nightscout_mills(value: datetime) -> int:
    """Return epoch milliseconds for Nightscout's treatment date field."""
    return int(_meal_datetime(value).timestamp() * 1000)


def _nightscout_utc_offset_minutes(value: datetime) -> int:
    """Return the local UTC offset in minutes for one meal timestamp."""
    offset = _meal_datetime(value).utcoffset()
    if offset is None:
        return 0
    return int(offset.total_seconds() // 60)


def _meal_treatment_payload(meal: Meal) -> dict[str, Any]:
    """Build the Nightscout treatment payload for a meal."""
    return {
        "eventType": "Carb Correction",
        "created_at": _nightscout_created_at(meal.eaten_at),
        "date": _nightscout_mills(meal.eaten_at),
        "utcOffset": _nightscout_utc_offset_minutes(meal.eaten_at),
        "carbs": meal.total_carbs_g,
        "protein": meal.total_protein_g,
        "fat": meal.total_fat_g,
        "notes": _meal_notes(meal),
        "enteredBy": "glucotracker",
        "glucotracker_meal_id": str(meal.id),
        "source": "glucotracker",
    }


def _date_query(from_datetime: datetime, to_datetime: datetime) -> dict[str, str]:
    """Return Nightscout range query params using ISO dateString bounds."""
    return {
        "find[dateString][$gte]": from_datetime.isoformat(),
        "find[dateString][$lte]": to_datetime.isoformat(),
        "count": "1000",
    }


def _created_at_query(from_datetime: datetime, to_datetime: datetime) -> dict[str, str]:
    """Return Nightscout treatment range query params."""
    return {
        "find[created_at][$gte]": from_datetime.isoformat(),
        "find[created_at][$lte]": to_datetime.isoformat(),
        "count": "1000",
    }


class NightscoutClient:
    """Small async client for Nightscout API v1."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_secret: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.nightscout_url or "").rstrip("/")
        self.api_secret = api_secret or settings.nightscout_api_secret
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        """Return whether this client can call Nightscout."""
        return bool(self.base_url and self.api_secret)

    def _headers(self) -> dict[str, str]:
        """Return Nightscout authentication headers."""
        if not self.api_secret:
            raise NightscoutNotConfiguredError(NIGHTSCOUT_NOT_CONFIGURED)
        return {"api-secret": _api_secret_hash(self.api_secret)}

    def _url(self, path: str) -> str:
        """Build a Nightscout URL."""
        if not self.base_url:
            raise NightscoutNotConfiguredError(NIGHTSCOUT_NOT_CONFIGURED)
        return f"{self.base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Perform a Nightscout request and normalize errors."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json_payload,
                    params=params,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise NightscoutTimeoutError("Nightscout request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise NightscoutHTTPError(
                exc.response.status_code,
                exc.response.text or "Nightscout request failed",
            ) from exc

        if not response.content:
            return {}
        data = response.json()
        if isinstance(data, list):
            return {"items": data}
        if isinstance(data, dict):
            return data
        return {"value": data}

    async def post_treatment(self, meal: Meal) -> dict[str, Any]:
        """Post a diary-only carb treatment for an accepted meal."""
        return await self.post_meal_treatment(meal)

    async def post_meal_treatment(self, meal: Meal) -> dict[str, Any]:
        """Post a diary-only carb treatment for an accepted meal."""
        return await self._request(
            "POST",
            "/api/v1/treatments",
            json_payload=_meal_treatment_payload(meal),
        )

    async def delete_treatment(self, nightscout_id: str) -> dict[str, Any]:
        """Delete a Nightscout treatment by id."""
        return await self._request("DELETE", f"/api/v1/treatments/{nightscout_id}")

    async def get_status(self) -> dict[str, Any]:
        """Return Nightscout status."""
        return await self._request("GET", "/api/v1/status.json")

    async def check_status(self) -> dict[str, Any]:
        """Return Nightscout status for settings connection tests."""
        return await self.get_status()

    async def fetch_glucose_entries(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch CGM glucose entries from Nightscout."""
        payload = await self._request(
            "GET",
            "/api/v1/entries/sgv.json",
            params=_date_query(from_datetime, to_datetime),
        )
        items = payload.get("items")
        return items if isinstance(items, list) else []

    async def fetch_treatments(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch Nightscout treatments in a time range."""
        payload = await self._request(
            "GET",
            "/api/v1/treatments.json",
            params=_created_at_query(from_datetime, to_datetime),
        )
        items = payload.get("items")
        return items if isinstance(items, list) else []

    async def fetch_insulin_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch insulin-related Nightscout treatment entries."""
        treatments = await self.fetch_treatments(from_datetime, to_datetime)
        insulin_events: list[dict[str, Any]] = []
        for treatment in treatments:
            event_type = str(treatment.get("eventType") or "").casefold()
            insulin = treatment.get("insulin")
            if insulin is not None or "bolus" in event_type or "insulin" in event_type:
                insulin_events.append(treatment)
        return insulin_events


def get_nightscout_client() -> NightscoutClient | None:
    """FastAPI dependency factory for optional Nightscout integration."""
    if not is_nightscout_configured():
        return None
    return NightscoutClient()
