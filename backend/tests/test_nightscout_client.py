"""Unit tests for the Nightscout API v1 request contract."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from glucotracker.infra.nightscout.client import NightscoutClient


@pytest.mark.asyncio
async def test_update_insulin_uses_collection_put_with_remote_id() -> None:
    """Nightscout updates use PUT /treatments with the id in the body."""
    client = NightscoutClient(
        base_url="https://nightscout.example",
        api_secret="test-secret",
    )
    request = AsyncMock(return_value={"_id": "remote-insulin-id"})
    client._request = request

    response = await client.update_insulin_treatment(
        "remote-insulin-id",
        insulin_units=2.75,
        recorded_at=datetime(2026, 4, 28, 8, 20, tzinfo=UTC),
        idempotency_key="manual-insulin-update-key",
    )

    assert response == {"_id": "remote-insulin-id"}
    request.assert_awaited_once()
    method, path = request.await_args.args
    payload = request.await_args.kwargs["json_payload"]
    assert method == "PUT"
    assert path == "/api/v1/treatments/"
    assert payload["_id"] == "remote-insulin-id"
    assert payload["insulin"] == 2.75
    assert payload["glucotracker_insulin_entry_id"] == (
        "manual-insulin-update-key"
    )


@pytest.mark.asyncio
async def test_update_meal_uses_collection_put_with_remote_id() -> None:
    """Meal edits use the same Nightscout collection update contract."""
    client = NightscoutClient(
        base_url="https://nightscout.example",
        api_secret="test-secret",
    )
    request = AsyncMock(return_value={"_id": "remote-meal-id"})
    client._request = request
    meal = SimpleNamespace(
        id="local-meal-id",
        eaten_at=datetime(2026, 4, 28, 8, 20, tzinfo=UTC),
        total_carbs_g=25.0,
        total_protein_g=10.0,
        total_fat_g=7.0,
        total_kcal=203.0,
        title="Breakfast",
        note=None,
        items=[],
    )

    response = await client.update_meal_treatment("remote-meal-id", meal)

    assert response == {"_id": "remote-meal-id"}
    request.assert_awaited_once()
    method, path = request.await_args.args
    payload = request.await_args.kwargs["json_payload"]
    assert method == "PUT"
    assert path == "/api/v1/treatments/"
    assert payload["_id"] == "remote-meal-id"
    assert payload["glucotracker_meal_id"] == "local-meal-id"
