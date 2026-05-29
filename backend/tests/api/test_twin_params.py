"""Digital twin parameter and curve API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from glucotracker.application.twin.estimator import (
    BGAnchor,
    CarbEvent,
    EstimatorParams,
    InsulinEvent,
    estimate_curve,
)
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    FingerstickReading,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    SensorSession,
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


def test_twin_data_summary_counts_scoped_fit_sources(api_client: TestClient) -> None:
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add_all(
            [
                NightscoutGlucoseEntry(
                    owner_id=user_id,
                    source_key="summary-cgm-1",
                    timestamp=datetime(2026, 4, 28, 8, 0),
                    value_mmol_l=6.0,
                ),
                FingerstickReading(
                    owner_id=user_id,
                    measured_at=datetime(2026, 4, 28, 8, 5),
                    glucose_mmol_l=6.1,
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
                    source_key="summary-insulin-1",
                    timestamp=datetime(2026, 4, 28, 8, 10),
                    insulin_units=1.0,
                ),
            ]
        )
        session.commit()

    response = api_client.get(
        "/twin/data/summary",
        params={
            "from": "2026-04-28T08:00:00",
            "to": "2026-04-28T10:00:00",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["cgm_count"] == 1
    assert data["fingerstick_count"] == 1
    assert data["meal_count"] == 1
    assert data["insulin_count"] == 1
    assert data["ready_for_fit"] is False
    assert "cgm_count<200" in data["fit_blockers"]


def test_twin_data_summary_excludes_corrupt_sensor_cgm(
    api_client: TestClient,
) -> None:
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add_all(
            [
                SensorSession(
                    owner_id=user_id,
                    started_at=datetime(2026, 4, 28, 8, 0),
                    ended_at=datetime(2026, 4, 28, 9, 0),
                    excluded_from_analytics=True,
                    exclusion_reason="corrupt",
                ),
                SensorSession(
                    owner_id=user_id,
                    started_at=datetime(2026, 4, 28, 9, 30),
                ),
                NightscoutGlucoseEntry(
                    owner_id=user_id,
                    source_key="twin-corrupt",
                    timestamp=datetime(2026, 4, 28, 8, 30),
                    value_mmol_l=20.0,
                ),
                NightscoutGlucoseEntry(
                    owner_id=user_id,
                    source_key="twin-visible",
                    timestamp=datetime(2026, 4, 28, 9, 45),
                    value_mmol_l=7.0,
                ),
            ]
        )
        session.commit()

    response = api_client.get(
        "/twin/data/summary",
        params={
            "from": "2026-04-28T08:00:00",
            "to": "2026-04-28T10:00:00",
        },
    )

    assert response.status_code == 200
    assert response.json()["cgm_count"] == 1


def test_twin_fit_empty_db_returns_insufficient_cgm(api_client: TestClient) -> None:
    response = api_client.post(
        "/twin/fit",
        json={
            "data_from": "2026-04-01T00:00:00",
            "data_to": "2026-04-15T00:00:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "insufficient_cgm"


def test_twin_fit_applies_params_and_writes_log(api_client: TestClient) -> None:
    _seed_synthetic_fit_data(api_client)

    response = api_client.post(
        "/twin/fit",
        json={
            "data_from": "2026-04-01T00:00:00",
            "data_to": "2026-04-10T23:59:00",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["applied"] is True
    assert data["params"]["is_fitted"] is True
    assert data["params"]["last_fit_method"] == "least_squares"
    assert data["result"]["holdout_window_count"] >= 2

    params = api_client.get("/twin/params").json()
    assert params["is_fitted"] is True

    history = api_client.get("/twin/fit/history").json()
    assert history[0]["method"] == "least_squares"


def _seed_synthetic_fit_data(api_client: TestClient) -> None:
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    params = EstimatorParams(
        icr_morning=11.5,
        icr_day=12.5,
        icr_evening=13.0,
        isf=2.1,
        baseline_drift_per_hour=0.05,
    )
    with session_factory() as session:
        for day_idx in range(10):
            day = datetime(2026, 4, 1) + timedelta(days=day_idx)
            for hour, grams, units in [
                (6, 34.5, 1.0),
                (11, 50.0, 1.5),
                (18, 52.0, 1.8),
            ]:
                start = day.replace(hour=hour)
                meal = CarbEvent(start + timedelta(minutes=15), grams)
                bolus = InsulinEvent(start + timedelta(minutes=15), units)
                session.add(
                    Meal(
                        owner_id=user_id,
                        eaten_at=meal.timestamp,
                        title="Приём пищи",
                        source=MealSource.manual,
                        status=MealStatus.accepted,
                        total_carbs_g=grams,
                        total_kcal=200,
                    )
                )
                session.add(
                    NightscoutInsulinEvent(
                        owner_id=user_id,
                        source_key=f"fit-insulin-{day_idx}-{hour}",
                        timestamp=bolus.timestamp,
                        insulin_units=units,
                        event_type="Meal Bolus",
                    )
                )
                points = estimate_curve(
                    bg_anchors=[BGAnchor(start, 6.0, source="cgm")],
                    carbs=[meal],
                    insulin=[bolus],
                    params=params,
                    start=start,
                    end=start + timedelta(minutes=180),
                    step_minutes=5,
                )
                session.add_all(
                    NightscoutGlucoseEntry(
                        owner_id=user_id,
                        source_key=f"fit-cgm-{day_idx}-{hour}-{idx}",
                        timestamp=point.timestamp,
                        value_mmol_l=point.mmol,
                    )
                    for idx, point in enumerate(points)
                )
        session.commit()
