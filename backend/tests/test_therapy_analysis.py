"""Long-term retrospective ICR/ISF analysis API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    HealthConnectRecord,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    User,
)
from glucotracker.infra.security import hash_password


def _meal(session, owner_id, at: datetime, carbs: float, title: str) -> None:
    session.add(
        Meal(
            owner_id=owner_id,
            eaten_at=at,
            title=title,
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=carbs,
            total_protein_g=4,
            total_fat_g=4,
            total_kcal=carbs * 5,
        )
    )


def _insulin(
    session,
    owner_id,
    at: datetime,
    units: float,
    *,
    correction: bool = True,
) -> None:
    key = f"analysis-insulin-{uuid4()}"
    session.add(
        NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key=key,
            nightscout_id=key,
            timestamp=at,
            insulin_units=units,
            event_type="Correction Bolus" if correction else "Insulin",
            entered_by="test",
        )
    )


def _glucose(session, owner_id, at: datetime, value: float) -> None:
    session.add(
        NightscoutGlucoseEntry(
            owner_id=owner_id,
            source_key=f"analysis-cgm-{uuid4()}",
            timestamp=at,
            value_mmol_l=value,
            value_mg_dl=round(value * 18.0182),
            source="CGM",
        )
    )


def _heart_rate(
    session,
    owner_id,
    at: datetime,
    values: list[float],
    *,
    record_id: str,
) -> None:
    samples = [
        {
            "time": utc_instant_from_local_wall(
                at + timedelta(minutes=index * 20 + 5)
            ).isoformat(),
            "beatsPerMinute": value,
        }
        for index, value in enumerate(values)
    ]
    start_utc = utc_instant_from_local_wall(at)
    session.add(
        HealthConnectRecord(
            owner_id=owner_id,
            record_id=record_id,
            record_type="HeartRateRecord",
            start_time=start_utc,
            end_time=start_utc + timedelta(hours=1),
            payload={"samples": samples},
        )
    )


def test_analysis_reports_time_slots_and_isolates_owner_data(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 31, 12)
    monkeypatch.setattr(
        "glucotracker.application.therapy_analysis.local_now",
        lambda: now,
    )
    monkeypatch.setattr(
        "glucotracker.application.therapy_review.local_now",
        lambda: now,
    )
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 10)
    meal_at = day + timedelta(hours=10)
    correction_at = day + timedelta(hours=18)

    with session_factory() as session:
        _meal(session, owner_id, meal_at, 40, "Чистый завтрак")
        _insulin(session, owner_id, meal_at, 4, correction=False)
        _glucose(session, owner_id, meal_at, 6.0)
        _glucose(session, owner_id, meal_at + timedelta(hours=2), 6.0)

        _insulin(session, owner_id, correction_at, 1)
        _glucose(session, owner_id, correction_at, 9.0)
        _glucose(
            session,
            owner_id,
            correction_at + timedelta(hours=4),
            6.5,
        )
        for offset, end_value in enumerate((6.2, 6.1, 6.3), start=1):
            background_at = datetime(2026, 7, 14 + offset, 2)
            _glucose(session, owner_id, background_at, 6.0)
            _glucose(
                session,
                owner_id,
                background_at + timedelta(hours=1),
                end_value,
            )
            _heart_rate(
                session,
                owner_id,
                background_at,
                [56, 60, 62],
                record_id=f"quiet-{offset}",
            )

        active_at = datetime(2026, 7, 18, 14)
        _glucose(session, owner_id, active_at, 6.5)
        _glucose(session, owner_id, active_at + timedelta(hours=1), 5.5)
        _heart_rate(
            session,
            owner_id,
            active_at,
            [105, 112, 109],
            record_id="active-owner",
        )

        other = User(
            username="therapy-analysis-other",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        _meal(session, other.id, meal_at, 100, "Чужая еда")
        _insulin(session, other.id, meal_at, 1, correction=False)
        _glucose(session, other.id, meal_at, 6.0)
        _glucose(session, other.id, meal_at + timedelta(hours=2), 6.0)
        _insulin(session, other.id, correction_at, 1)
        _glucose(session, other.id, correction_at, 12.0)
        _glucose(
            session,
            other.id,
            correction_at + timedelta(hours=4),
            4.0,
        )
        other_background = datetime(2026, 7, 15, 2)
        _glucose(session, other.id, other_background, 5.0)
        _glucose(
            session,
            other.id,
            other_background + timedelta(hours=1),
            12.0,
        )
        _heart_rate(
            session,
            other.id,
            other_background,
            [180, 180, 180],
            record_id="other-heart-rate",
        )
        session.commit()

    response = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 30, "target_mmol_l": 6},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["from_date"] == "2026-07-02"
    assert body["to_date"] == "2026-07-31"
    assert body["period_days"] == 30
    assert body["icr_horizon_minutes"] == 120
    assert body["isf_horizon_minutes"] == 240
    assert body["bin_hours"] == 4
    assert body["model_version"] == "retrospective-therapy-analysis-v2"
    assert body["overall_icr_g_per_unit"] == {
        "value": 10.0,
        "q1": 10.0,
        "q3": 10.0,
        "sample_count": 1,
        "confidence": "low",
    }
    assert body["overall_isf_mmol_l_per_unit"] == {
        "value": 2.5,
        "q1": 2.5,
        "q3": 2.5,
        "sample_count": 1,
        "confidence": "low",
    }
    assert body["isf_source"] == "correction_episodes"
    slots = {slot["label"]: slot for slot in body["slots"]}
    assert slots["08:00–12:00"]["icr_g_per_unit"]["value"] == 10.0
    assert slots["16:00–20:00"]["isf_mmol_l_per_unit"]["value"] == 2.5
    assert sum(
        slot["icr_g_per_unit"]["sample_count"] for slot in body["slots"]
    ) == 1
    assert sum(
        slot["isf_mmol_l_per_unit"]["sample_count"] for slot in body["slots"]
    ) == 1
    basal = body["basal_profile"]
    assert basal["window_minutes"] == 60
    assert basal["washout_minutes"] == 240
    assert basal["resting_reference_bpm"] == 59.0
    assert basal["elevated_hr_threshold_bpm"] == 80.0
    assert basal["quiet_window_count"] == 3
    assert basal["elevated_hr_window_count"] == 1
    assert basal["unknown_hr_window_count"] == 0
    basal_slots = {slot["label"]: slot for slot in basal["slots"]}
    assert basal_slots["02:00"]["quiet_drift_mmol_l_per_hour"] == {
        "value": 0.2,
        "q1": 0.15,
        "q3": 0.25,
        "sample_count": 3,
        "confidence": "low",
    }
    assert basal_slots["02:00"]["signal"] == "stable"
    assert basal_slots["14:00"]["elevated_hr_drift_mmol_l_per_hour"][
        "value"
    ] == -1.0
    assert basal_slots["14:00"]["quiet_drift_mmol_l_per_hour"][
        "sample_count"
    ] == 0


def test_analysis_rejects_unsupported_period(api_client: TestClient) -> None:
    response = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 60},
    )

    assert response.status_code == 422
