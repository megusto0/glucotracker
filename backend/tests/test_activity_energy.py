"""Heart-rate-priced effort feeds the energy balance, owner by owner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.application.activity_energy import ActivityEnergyService
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import HealthConnectRecord, User, UserProfile
from glucotracker.infra.security import hash_password

DAY = datetime(2026, 7, 25, tzinfo=UTC)
RIDE = (DAY + timedelta(hours=18), DAY + timedelta(hours=20))


def _profile(owner_id) -> UserProfile:
    return UserProfile(
        owner_id=owner_id,
        weight_kg=82,
        height_cm=180,
        age_years=25,
        sex="male",
        activity_level="moderate",
    )


def _ride(session, owner_id) -> None:
    at = DAY - timedelta(hours=6)
    while at < DAY + timedelta(hours=23):
        bpm = 135 if RIDE[0] <= at <= RIDE[1] else 60
        session.add(
            HealthConnectRecord(
                owner_id=owner_id,
                record_id=f"hr-{owner_id}-{at.isoformat()}",
                record_type="HeartRateRecord",
                start_time=at,
                end_time=at,
                payload={"samples": [{"beatsPerMinute": bpm}]},
            )
        )
        at += timedelta(minutes=2)
    for origin, count in (("com.glucotracker.bridge", 3000), ("android", 1200)):
        session.add(
            HealthConnectRecord(
                owner_id=owner_id,
                record_id=f"steps-{owner_id}-{origin}",
                record_type="StepsRecord",
                data_origin=origin,
                start_time=RIDE[0],
                end_time=RIDE[1],
                payload={"count": count},
            )
        )


@pytest.mark.parametrize("ride_belongs_to_admin", [True, False])
def test_effort_is_priced_from_the_owners_heart_rate_only(
    api_client: TestClient,
    ride_belongs_to_admin: bool,
) -> None:
    factory = api_client.app_state["session_factory"]
    admin_id = api_client.app_state["current_user_id"]
    with factory() as session:
        other = User(
            username=f"other-{uuid4()}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        rider, idle = (
            (admin_id, other.id) if ride_belongs_to_admin else (other.id, admin_id)
        )
        _ride(session, rider)
        session.commit()

    with factory() as session:
        ridden = ActivityEnergyService(session, rider).for_day(
            DAY.date(),
            _profile(rider),
        )
        quiet = ActivityEnergyService(session, idle).for_day(
            DAY.date(),
            _profile(idle),
        )

    assert ridden is not None and quiet is not None
    # Two hours at 135 bpm for an 82 kg 25-year-old: Keytel gives 12.3 kcal a
    # minute gross, 1.3 of it resting metabolism the day already counts.
    assert 1250 < ridden.kcal < 1400
    assert 115 <= ridden.minutes <= 125
    # The strap and the phone saw the same minutes; the larger count stands.
    assert ridden.steps == 3000
    assert (quiet.kcal, quiet.minutes, quiet.steps) == (0.0, 0, 0)


def test_balance_counts_a_ride_the_device_total_missed(api_client: TestClient) -> None:
    factory = api_client.app_state["session_factory"]
    admin_id = api_client.app_state["current_user_id"]
    with factory() as session:
        _ride(session, admin_id)
        session.commit()
    profile = api_client.put(
        "/profile",
        json={
            "weight_kg": 82,
            "height_cm": 180,
            "age_years": 25,
            "sex": "male",
            "activity_level": "moderate",
        },
    )
    synced = api_client.post(
        "/activity/sync",
        json={
            "date": DAY.date().isoformat(),
            "steps": 4000,
            "kcal_burned": 1564.5,
            "source": "health_connect_total",
            "calorie_confidence": "high",
        },
    )
    assert profile.status_code == 200 and synced.status_code == 200

    tdee = api_client.get(
        "/activity/balance",
        params={"day": DAY.date().isoformat()},
    ).json()["tdee"]

    # Sedentary 1825 * 1.2 = 2190, plus the ride rather than 4000 "steps".
    assert tdee > 2190 + 900
