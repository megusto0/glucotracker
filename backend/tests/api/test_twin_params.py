"""Digital twin parameter and curve API tests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi.testclient import TestClient

from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    FingerstickReading,
    Meal,
    NightscoutInsulinEvent,
    TwinParams,
)


def test_get_twin_params_clean_db_is_not_fitted(api_client: TestClient) -> None:
    response = api_client.get("/twin/params")

    assert response.status_code == 200
    data = response.json()
    assert data["is_fitted"] is False
    assert data["hint"] == "not_fitted"
    assert data["dia_minutes"] == 270
    assert data["carb_duration_minutes"] == 180


def test_twin_curve_on_clean_db_does_not_create_params_row(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/twin/curve",
        params={
            "from": "2026-04-28T08:00:00",
            "to": "2026-04-28T10:00:00",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["params"]["is_fitted"] is False
    assert data["points"] == []

    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        rows = session.query(TwinParams).filter_by(owner_id=user_id).all()
    assert rows == []


def test_patch_twin_params_invalid_icr_returns_422(api_client: TestClient) -> None:
    response = api_client.patch("/twin/params", json={"icr_morning": 2.9})

    assert response.status_code == 422


def test_patch_twin_params_invalid_slot_order_returns_422(
    api_client: TestClient,
) -> None:
    response = api_client.patch(
        "/twin/params",
        json={
            "morning_start_minutes": 660,
            "day_start_minutes": 660,
            "evening_start_minutes": 1080,
        },
    )

    assert response.status_code == 422


def test_patch_twin_params_updates_values_and_writes_manual_log(
    api_client: TestClient,
) -> None:
    response = api_client.patch(
        "/twin/params",
        json={
            "icr_morning": 11.5,
            "icr_day": 12.25,
            "icr_evening": 13.0,
            "isf": 2.1,
            "baseline_drift_per_hour": 0.02,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_fitted"] is True
    assert data["hint"] == "ready"
    assert data["icr_morning"] == 11.5

    params = api_client.get("/twin/params").json()
    assert params["icr_day"] == 12.25

    history = api_client.get("/twin/fit/history").json()
    assert history[0]["method"] == "manual"
    assert history[0]["params_snapshot"]["icr_evening"] == 13.0


def test_twin_fit_history_is_reverse_chronological(api_client: TestClient) -> None:
    for value in [11.0, 12.0, 13.0]:
        response = api_client.patch(
            "/twin/params",
            json={
                "icr_morning": value,
                "icr_day": value,
                "icr_evening": value,
                "isf": 2.0,
            },
        )
        assert response.status_code == 200

    history = api_client.get("/twin/fit/history", params={"limit": 3}).json()

    assert [row["method"] for row in history] == ["manual", "manual", "manual"]
    assert history == sorted(history, key=lambda row: row["fit_at"], reverse=True)


def test_twin_curve_uses_scoped_fingersticks_and_events(
    api_client: TestClient,
) -> None:
    api_client.patch(
        "/twin/params",
        json={
            "icr_morning": 12.0,
            "icr_day": 12.0,
            "icr_evening": 12.0,
            "isf": 2.0,
        },
    )
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add_all(
            [
                FingerstickReading(
                    owner_id=user_id,
                    measured_at=datetime(2026, 4, 28, 8, 0),
                    glucose_mmol_l=6.0,
                ),
                FingerstickReading(
                    owner_id=user_id,
                    measured_at=datetime(2026, 4, 28, 9, 0),
                    glucose_mmol_l=8.0,
                ),
                Meal(
                    owner_id=user_id,
                    eaten_at=datetime(2026, 4, 28, 8, 15),
                    title="Завтрак",
                    source=MealSource.manual,
                    status=MealStatus.accepted,
                    total_carbs_g=24.0,
                    total_kcal=180.0,
                ),
                NightscoutInsulinEvent(
                    owner_id=user_id,
                    source_key="twin-insulin-1",
                    timestamp=datetime(2026, 4, 28, 8, 10),
                    insulin_units=1.0,
                    event_type="Meal Bolus",
                ),
            ]
        )
        session.commit()

    response = api_client.get(
        "/twin/curve",
        params={
            "from": "2026-04-28T08:00:00",
            "to": "2026-04-28T10:00:00",
            "step_minutes": 30,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["anchors"]) == 2
    assert len(data["food_events"]) == 1
    assert len(data["insulin_events"]) == 1
    assert {point["mode"] for point in data["points"]} == {
        "forecast",
        "interpolation",
    }
