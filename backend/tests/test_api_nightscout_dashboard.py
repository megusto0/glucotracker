"""Nightscout, daily totals, and dashboard API tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glucotracker.config import get_settings
from glucotracker.infra.db.models import DailyTotal
from glucotracker.infra.nightscout.client import (
    NightscoutHTTPError,
    NightscoutTimeoutError,
    _meal_treatment_payload,
    get_nightscout_client,
)
from glucotracker.main import app


class FakeNightscoutClient:
    """Fake configured Nightscout client for endpoint tests."""

    configured = True

    def __init__(
        self,
        *,
        post_response: dict[str, Any] | None = None,
        post_error: Exception | None = None,
        post_errors: list[Exception | None] | None = None,
        delete_error: Exception | None = None,
        status_error: Exception | None = None,
        glucose_rows: list[dict[str, Any]] | None = None,
        insulin_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.post_response = post_response or {"_id": "ns-treatment-1"}
        self.post_error = post_error
        self.post_errors = post_errors or []
        self.delete_error = delete_error
        self.status_error = status_error
        self.glucose_rows = glucose_rows or []
        self.insulin_rows = insulin_rows or []
        self.posted_meals = []
        self.deleted_ids = []

    async def get_status(self) -> dict[str, Any]:
        """Return fake status."""
        if self.status_error is not None:
            raise self.status_error
        return {"status": "ok", "version": "15.0.0", "name": "Nightscout Test"}

    async def check_status(self) -> dict[str, Any]:
        """Return fake status for settings tests."""
        return await self.get_status()

    async def post_treatment(self, meal: object) -> dict[str, Any]:
        """Record and return fake treatment creation."""
        if self.post_errors:
            error = self.post_errors.pop(0)
            if error is not None:
                raise error
        if self.post_error is not None:
            raise self.post_error
        self.posted_meals.append(meal)
        return {"_id": f"ns-{len(self.posted_meals)}", **self.post_response}

    async def delete_treatment(self, nightscout_id: str) -> dict[str, Any]:
        """Record and return fake treatment deletion."""
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted_ids.append(nightscout_id)
        return {"deleted": nightscout_id}

    async def fetch_glucose_entries(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[dict[str, Any]]:
        """Return fake glucose rows."""
        return self.glucose_rows

    async def fetch_insulin_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[dict[str, Any]]:
        """Return fake insulin rows."""
        return self.insulin_rows


def _today() -> date:
    """Return test-compatible dashboard today."""
    return datetime.now(UTC).date()


def _dt(day: date, hour: int = 8) -> str:
    """Return an ISO datetime for a test date."""
    return (
        datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        .replace(hour=hour)
        .isoformat()
    )


def _manual_item(**overrides: object) -> dict[str, Any]:
    """Return a valid manual item payload."""
    payload: dict[str, Any] = {
        "name": "Yogurt",
        "carbs_g": 10,
        "protein_g": 15,
        "fat_g": 4,
        "fiber_g": 0,
        "kcal": 136,
        "source_kind": "manual",
    }
    payload.update(overrides)
    return payload


def _create_meal(
    api_client: TestClient,
    *,
    day: date | None = None,
    status: str = "accepted",
    source: str = "manual",
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a meal through the API."""
    response = api_client.post(
        "/meals",
        json={
            "eaten_at": _dt(day or _today()),
            "title": "Meal",
            "note": "test note",
            "source": source,
            "status": status,
            "items": items if items is not None else [_manual_item()],
        },
    )
    assert response.status_code == 201
    return response.json()


def _daily_total(db_engine: Engine, day: date) -> DailyTotal:
    """Fetch a daily total row."""
    with Session(db_engine) as session:
        row = session.get(DailyTotal, day)
        assert row is not None
        return row


def test_nightscout_not_configured_only_sync_503(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset Nightscout config only blocks sync endpoints."""
    monkeypatch.setenv("NIGHTSCOUT_URL", "")
    monkeypatch.setenv("NIGHTSCOUT_API_SECRET", "")
    get_settings.cache_clear()
    meal = _create_meal(api_client)

    status_response = api_client.get("/nightscout/status")
    sync_response = api_client.post(f"/meals/{meal['id']}/sync_nightscout")
    meals_response = api_client.get("/meals")

    assert status_response.status_code == 200
    assert status_response.json() == {"configured": False, "status": None}
    assert sync_response.status_code == 503
    assert sync_response.json()["detail"] == "Nightscout не подключён"
    assert meals_response.status_code == 200


def test_nightscout_sync_and_unsync_success(api_client: TestClient) -> None:
    """Configured Nightscout sync stores and clears remote id."""
    fake = FakeNightscoutClient(post_response={"_id": "abc123"})
    app.dependency_overrides[get_nightscout_client] = lambda: fake
    meal = _create_meal(api_client)

    sync_response = api_client.post(f"/meals/{meal['id']}/sync_nightscout")
    assert sync_response.status_code == 200
    assert sync_response.json()["nightscout_id"] == "abc123"
    assert fake.posted_meals

    duplicate_response = api_client.post(f"/meals/{meal['id']}/sync_nightscout")
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"]["nightscout_id"] == "abc123"

    unsync_response = api_client.post(f"/meals/{meal['id']}/unsync_nightscout")
    assert unsync_response.status_code == 200
    assert unsync_response.json()["synced"] is False
    assert fake.deleted_ids == ["abc123"]


def test_nightscout_treatment_payload_uses_explicit_utc_timestamp() -> None:
    """Nightscout treatment preserves local wall time and utcOffset."""
    meal = SimpleNamespace(
        id="meal-1",
        eaten_at=datetime(2026, 4, 28, 8, 30),
        title="Lunch",
        note=None,
        total_carbs_g=42,
        total_protein_g=20,
        total_fat_g=10,
        total_kcal=380,
        items=[],
    )

    payload = _meal_treatment_payload(meal)

    assert payload["created_at"] == "2026-04-28T08:30:00+04:00"
    assert payload["utcOffset"] == 240
    assert payload["date"] == int(
        datetime(2026, 4, 28, 8, 30, tzinfo=timezone(timedelta(hours=4))).timestamp()
        * 1000
    )


def test_nightscout_treatment_payload_converts_aware_local_time_to_utc() -> None:
    """Aware local values keep their timezone offset in the payload."""
    samara = timezone(timedelta(hours=4))
    meal = SimpleNamespace(
        id="meal-1",
        eaten_at=datetime(2026, 4, 28, 12, 30, tzinfo=samara),
        title="Lunch",
        note=None,
        total_carbs_g=42,
        total_protein_g=20,
        total_fat_g=10,
        total_kcal=380,
        items=[],
    )

    payload = _meal_treatment_payload(meal)

    assert payload["created_at"] == "2026-04-28T12:30:00+04:00"
    assert payload["utcOffset"] == 240


def test_nightscout_500_and_timeout_are_mapped(api_client: TestClient) -> None:
    """Nightscout HTTP failures and timeouts return gateway errors."""
    meal = _create_meal(api_client)

    app.dependency_overrides[get_nightscout_client] = lambda: FakeNightscoutClient(
        post_error=NightscoutHTTPError(500, "remote boom")
    )
    error_response = api_client.post(f"/meals/{meal['id']}/sync_nightscout")
    assert error_response.status_code == 502
    assert error_response.json()["detail"]["status_code"] == 500

    app.dependency_overrides[get_nightscout_client] = lambda: FakeNightscoutClient(
        post_error=NightscoutTimeoutError("Nightscout request timed out")
    )
    timeout_response = api_client.post(f"/meals/{meal['id']}/sync_nightscout")
    assert timeout_response.status_code == 504


def test_cannot_sync_draft_meal(api_client: TestClient) -> None:
    """Draft meals cannot sync to Nightscout."""
    app.dependency_overrides[get_nightscout_client] = lambda: FakeNightscoutClient()
    meal = _create_meal(api_client, source="photo", status="draft", items=[])

    response = api_client.post(f"/meals/{meal['id']}/sync_nightscout")

    assert response.status_code == 409
    assert "accepted" in response.json()["detail"]


def test_nightscout_settings_save_get_masks_secret(api_client: TestClient) -> None:
    """Nightscout settings persist server-side without returning the secret."""
    response = api_client.put(
        "/settings/nightscout",
        json={
            "nightscout_enabled": True,
            "nightscout_url": "https://nightscout.example",
            "nightscout_api_secret": "super-secret",
            "show_glucose_in_journal": True,
            "import_insulin_events": True,
            "allow_meal_send": True,
            "confirm_before_send": True,
            "autosend_meals": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["configured"] is True
    assert body["url"] == "https://nightscout.example"
    assert body["secret_is_set"] is True
    assert "super-secret" not in response.text
    assert body["autosend_meals"] is False

    fetched = api_client.get("/settings/nightscout")
    assert fetched.status_code == 200
    assert fetched.json()["secret_is_set"] is True
    assert "super-secret" not in fetched.text


def test_nightscout_connection_test_success_and_failure(api_client: TestClient) -> None:
    """Connection testing stores masked success/failure state."""
    api_client.put(
        "/settings/nightscout",
        json={
            "nightscout_enabled": True,
            "nightscout_url": "https://nightscout.example",
            "nightscout_api_secret": "secret",
        },
    )
    app.dependency_overrides[get_nightscout_client] = lambda: FakeNightscoutClient()

    success = api_client.post("/settings/nightscout/test")
    assert success.status_code == 200
    assert success.json()["ok"] is True
    assert success.json()["server_name"] == "Nightscout Test"

    app.dependency_overrides[get_nightscout_client] = lambda: FakeNightscoutClient(
        status_error=NightscoutHTTPError(401, "unauthorized")
    )
    failure = api_client.post("/settings/nightscout/test")
    assert failure.status_code == 200
    assert failure.json()["ok"] is False
    assert "Nightscout request failed" in failure.json()["error"]


def test_sync_today_sends_only_accepted_unsynced_meals(
    api_client: TestClient,
) -> None:
    """Manual day sync skips drafts and already synced accepted meals."""
    day = date(2026, 4, 28)
    fake = FakeNightscoutClient()
    app.dependency_overrides[get_nightscout_client] = lambda: fake
    first = _create_meal(api_client, day=day)
    second = _create_meal(api_client, day=day)
    _create_meal(api_client, day=day, source="photo", status="draft", items=[])
    assert api_client.post(f"/meals/{first['id']}/sync_nightscout").status_code == 200

    response = api_client.post(
        "/nightscout/sync/today",
        json={"date": str(day), "confirm": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_candidates"] == 2
    assert body["sent_count"] == 1
    assert body["skipped_count"] == 1
    assert {result["meal_id"] for result in body["results"]} == {
        first["id"],
        second["id"],
    }


def test_sync_today_continues_on_partial_failure(api_client: TestClient) -> None:
    """Manual day sync keeps going when one meal fails."""
    day = date(2026, 4, 29)
    fake = FakeNightscoutClient(
        post_errors=[NightscoutHTTPError(500, "remote boom"), None]
    )
    app.dependency_overrides[get_nightscout_client] = lambda: fake
    _create_meal(api_client, day=day, items=[_manual_item(name="Meal one")])
    _create_meal(api_client, day=day, items=[_manual_item(name="Meal two")])

    response = api_client.post(
        "/nightscout/sync/today",
        json={"date": str(day), "confirm": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sent_count"] == 1
    assert body["failed_count"] == 1


def test_nightscout_read_glucose_and_insulin_events(api_client: TestClient) -> None:
    """Read-only endpoints normalize glucose and insulin events."""
    fake = FakeNightscoutClient(
        glucose_rows=[
            {
                "dateString": "2026-04-28T08:00:00Z",
                "sgv": 110,
                "direction": "Flat",
                "device": "CGM",
            }
        ],
        insulin_rows=[
            {
                "created_at": "2026-04-28T08:10:00Z",
                "insulin": 4,
                "eventType": "Correction Bolus",
                "enteredBy": "Nightscout",
                "_id": "insulin-1",
            }
        ],
    )
    app.dependency_overrides[get_nightscout_client] = lambda: fake
    params = {
        "from": "2026-04-28T07:00:00Z",
        "to": "2026-04-28T10:00:00Z",
    }

    glucose = api_client.get("/nightscout/glucose", params=params)
    insulin = api_client.get("/nightscout/insulin", params=params)
    events = api_client.get("/nightscout/events", params=params)

    assert glucose.status_code == 200
    assert glucose.json()[0]["value"] == 6.1
    assert glucose.json()[0]["unit"] == "mmol/L"
    assert insulin.status_code == 200
    assert insulin.json()[0]["insulin_units"] == 4
    assert events.status_code == 200
    assert events.json()["glucose"][0]["value"] == 6.1
    assert events.json()["insulin"][0]["nightscout_id"] == "insulin-1"


def test_daily_totals_recalculate_on_create_update_delete(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Meal and item mutations update daily_totals."""
    day = date(2026, 4, 1)
    meal = _create_meal(api_client, day=day)
    assert _daily_total(db_engine, day).carbs_g == 10

    item_id = meal["items"][0]["id"]
    patch_response = api_client.patch(
        f"/meal_items/{item_id}",
        json={"carbs_g": 20, "kcal": 176},
    )
    assert patch_response.status_code == 200
    assert _daily_total(db_engine, day).carbs_g == 20

    delete_item_response = api_client.delete(f"/meal_items/{item_id}")
    assert delete_item_response.status_code == 200
    assert _daily_total(db_engine, day).carbs_g == 0

    add_item_response = api_client.post(
        f"/meals/{meal['id']}/items",
        json=_manual_item(carbs_g=12, kcal=144),
    )
    assert add_item_response.status_code == 201
    assert _daily_total(db_engine, day).carbs_g == 12

    delete_meal_response = api_client.delete(f"/meals/{meal['id']}")
    assert delete_meal_response.status_code == 200
    assert _daily_total(db_engine, day).meal_count == 0


def test_draft_meals_do_not_count_until_accepted(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Draft meal totals stay out of daily_totals until the draft is accepted."""
    day = date(2026, 4, 2)
    draft = _create_meal(
        api_client,
        day=day,
        source="photo",
        status="draft",
        items=[_manual_item(carbs_g=40, kcal=300)],
    )

    daily = _daily_total(db_engine, day)
    assert daily.meal_count == 0
    assert daily.carbs_g == 0

    item_id = draft["items"][0]["id"]
    patch_response = api_client.patch(
        f"/meal_items/{item_id}",
        json={"carbs_g": 44, "kcal": 320},
    )
    assert patch_response.status_code == 200
    assert _daily_total(db_engine, day).carbs_g == 0

    accepted = api_client.post(
        f"/meals/{draft['id']}/accept",
        json={
            "items": [
                {
                    "name": "Photo draft item",
                    "carbs_g": 44,
                    "protein_g": 15,
                    "fat_g": 8,
                    "fiber_g": 2,
                    "kcal": 320,
                    "source_kind": "photo_estimate",
                }
            ]
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    accepted_total = _daily_total(db_engine, day)
    assert accepted_total.meal_count == 1
    assert accepted_total.carbs_g == 44
    assert accepted_total.kcal == 320


def test_admin_recalculate_and_dashboard_range(api_client: TestClient) -> None:
    """Admin backfill and range dashboard use accepted meals."""
    today = _today()
    _create_meal(api_client, day=today, items=[_manual_item(carbs_g=20, kcal=200)])
    _create_meal(
        api_client,
        day=today - timedelta(days=1),
        items=[_manual_item(carbs_g=40, kcal=400)],
    )

    recalc = api_client.post(
        "/admin/recalculate",
        params={"from": str(today - timedelta(days=1)), "to": str(today)},
    )
    range_response = api_client.get(
        "/dashboard/range",
        params={"from": str(today - timedelta(days=1)), "to": str(today)},
    )

    assert recalc.status_code == 200
    assert recalc.json()["days_recalculated"] == 2
    assert range_response.status_code == 200
    body = range_response.json()
    assert body["summary"]["total_meals"] == 2
    assert body["summary"]["total_carbs_g"] == 60
    assert body["summary"]["avg_carbs_g"] == 30


def test_dashboard_averages_ignore_days_without_meals(
    api_client: TestClient,
) -> None:
    """Dashboard averages divide by logged days, not empty calendar days."""
    today = _today()
    _create_meal(
        api_client,
        day=today,
        items=[_manual_item(carbs_g=60, protein_g=30, fat_g=20, fiber_g=6, kcal=600)],
    )

    range_response = api_client.get(
        "/dashboard/range",
        params={"from": str(today - timedelta(days=6)), "to": str(today)},
    )
    today_response = api_client.get("/dashboard/today")

    assert range_response.status_code == 200
    range_body = range_response.json()
    assert range_body["summary"]["total_meals"] == 1
    assert range_body["summary"]["avg_carbs_g"] == 60
    assert range_body["summary"]["avg_protein_g"] == 30
    assert range_body["summary"]["avg_fat_g"] == 20
    assert range_body["summary"]["avg_fiber_g"] == 6
    assert range_body["summary"]["avg_kcal"] == 600

    assert today_response.status_code == 200
    today_body = today_response.json()
    assert today_body["week_avg_carbs"] == 60
    assert today_body["week_avg_kcal"] == 600


def test_dashboard_endpoints_with_seeded_data(api_client: TestClient) -> None:
    """Dashboard endpoints return expected aggregates for accepted meals."""
    today = _today()
    pattern = api_client.post(
        "/patterns",
        json={
            "prefix": "bk",
            "key": "whopper",
            "display_name": "Whopper",
            "default_carbs_g": 51,
            "default_protein_g": 28,
            "default_fat_g": 35,
            "default_fiber_g": 3,
            "default_kcal": 635,
            "aliases": ["воппер"],
        },
    ).json()
    _create_meal(
        api_client,
        day=today,
        items=[
            _manual_item(
                name="Whopper",
                carbs_g=51,
                protein_g=28,
                fat_g=35,
                fiber_g=3,
                kcal=635,
                source_kind="pattern",
                pattern_id=pattern["id"],
            )
        ],
    )

    today_response = api_client.get("/dashboard/today")
    heatmap_response = api_client.get("/dashboard/heatmap", params={"weeks": 4})
    top_patterns_response = api_client.get(
        "/dashboard/top_patterns",
        params={"days": 7, "limit": 10},
    )
    source_response = api_client.get("/dashboard/source_breakdown", params={"days": 7})

    assert today_response.status_code == 200
    assert today_response.json()["carbs_g"] >= 51
    assert heatmap_response.status_code == 200
    assert heatmap_response.json()["cells"]
    assert top_patterns_response.status_code == 200
    assert top_patterns_response.json()[0]["token"] == "bk:whopper"
    assert source_response.status_code == 200
    assert source_response.json()["items"][0]["source_kind"] == "pattern"


def test_dashboard_data_quality_classifies_source_kinds(
    api_client: TestClient,
) -> None:
    """Data quality endpoint classifies item source and confidence."""
    _create_meal(
        api_client,
        items=[
            _manual_item(
                name="Exact label",
                source_kind="label_calc",
                calculation_method="label_visible_weight_backend_calc",
            ),
            _manual_item(
                name="Assumed label",
                source_kind="label_calc",
                calculation_method="label_assumed_weight_backend_calc",
            ),
            _manual_item(name="Restaurant", source_kind="restaurant_db"),
            _manual_item(name="Product", source_kind="product_db"),
            _manual_item(name="Pattern", source_kind="pattern"),
            _manual_item(
                name="Visual",
                source_kind="photo_estimate",
                confidence=0.4,
                confidence_reason="unclear photo",
            ),
            _manual_item(name="Manual", source_kind="manual"),
        ],
    )

    response = api_client.get("/dashboard/data_quality", params={"days": 7})

    assert response.status_code == 200
    body = response.json()
    assert body["exact_label_count"] == 1
    assert body["assumed_label_count"] == 1
    assert body["restaurant_db_count"] == 1
    assert body["product_db_count"] == 1
    assert body["pattern_count"] == 1
    assert body["visual_estimate_count"] == 1
    assert body["manual_count"] == 1
    assert body["low_confidence_count"] == 1
    assert body["low_confidence_items"][0]["name"] == "Visual"
