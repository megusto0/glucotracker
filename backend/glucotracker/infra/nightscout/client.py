"""Async Nightscout REST client for optional treatment sync."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from glucotracker.config import get_settings
from glucotracker.infra.db.models import Meal

NIGHTSCOUT_NOT_CONFIGURED = "Nightscout not configured"


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
        parts.append("Items: " + ", ".join(item_names))
    parts.append("glucotracker diary-only estimate")
    return "\n".join(parts)


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
    ) -> dict[str, Any]:
        """Perform a Nightscout request and normalize errors."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json_payload,
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
        payload = {
            "eventType": "Carb Correction",
            "created_at": meal.eaten_at.isoformat(),
            "carbs": meal.total_carbs_g,
            "protein": meal.total_protein_g,
            "fat": meal.total_fat_g,
            "notes": _meal_notes(meal),
            "enteredBy": "glucotracker",
        }
        return await self._request("POST", "/api/v1/treatments", json_payload=payload)

    async def delete_treatment(self, nightscout_id: str) -> dict[str, Any]:
        """Delete a Nightscout treatment by id."""
        return await self._request("DELETE", f"/api/v1/treatments/{nightscout_id}")

    async def get_status(self) -> dict[str, Any]:
        """Return Nightscout status."""
        return await self._request("GET", "/api/v1/status.json")


def get_nightscout_client() -> NightscoutClient | None:
    """FastAPI dependency factory for optional Nightscout integration."""
    if not is_nightscout_configured():
        return None
    return NightscoutClient()
