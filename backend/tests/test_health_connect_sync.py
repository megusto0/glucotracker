"""Health Connect raw mirror API and repository isolation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import HealthConnectRecord, User
from glucotracker.infra.db.repositories.health_connect import (
    HealthConnectRepository,
    normalize_health_connect_record,
)
from glucotracker.infra.security import hash_password, issue_access_token


def _record(record_id: str, record_type: str, value: float) -> dict:
    timestamp = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)
    return normalize_health_connect_record(
        record_id=record_id,
        record_type=record_type,
        client_record_id=None,
        client_record_version=0,
        data_origin="com.example.watch",
        recording_method=1,
        start_time=timestamp,
        end_time=timestamp,
        last_modified_time=timestamp,
        payload={"value": value},
    )


@pytest.mark.parametrize("reader", ["alice", "bob"])
def test_repository_isolates_two_users(api_client: TestClient, reader: str) -> None:
    session_factory = api_client.app_state["session_factory"]
    alice_id = UUID(str(api_client.app_state["current_user_id"]))
    with session_factory() as session:
        bob = User(
            username="health-connect-bob",
            password_hash=hash_password("health-connect-bob-password"),
            role=UserRole.gluco,
        )
        session.add(bob)
        session.commit()
        bob_id = bob.id

        HealthConnectRepository(session, alice_id).sync(
            [_record("same-health-connect-id", "WeightRecord", 70.0)],
            [],
        )
        HealthConnectRepository(session, bob_id).sync(
            [_record("same-health-connect-id", "WeightRecord", 82.0)],
            [],
        )
        session.commit()

        selected_id = alice_id if reader == "alice" else bob_id
        expected_value = 70.0 if reader == "alice" else 82.0
        rows = HealthConnectRepository(session, selected_id).list_records()

    assert len(rows) == 1
    assert rows[0].owner_id == selected_id
    assert rows[0].payload == {"value": expected_value}


def test_repository_refuses_missing_user_id(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session, pytest.raises(ValueError):
        HealthConnectRepository(session, None)  # type: ignore[arg-type]


def test_api_upserts_and_deletes_idempotently(api_client: TestClient) -> None:
    payload = {
        "records": [
            {
                "record_id": "health-connect-weight-1",
                "record_type": "WeightRecord",
                "client_record_version": 1,
                "data_origin": "com.example.scale",
                "recording_method": 2,
                "start_time": "2026-07-15T08:30:00Z",
                "end_time": "2026-07-15T08:30:00Z",
                "last_modified_time": "2026-07-15T08:31:00Z",
                "payload": {"weight": {"inKilograms": 70.4}},
            }
        ],
        "deleted_record_ids": [],
    }
    created = api_client.post("/health-connect/records:sync", json=payload)
    assert created.status_code == 200
    assert created.json() == {"received": 1, "upserted": 1, "deleted": 0}

    payload["records"][0]["payload"] = {"weight": {"inKilograms": 70.1}}
    updated = api_client.post("/health-connect/records:sync", json=payload)
    assert updated.status_code == 200

    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with session_factory() as session:
        rows = HealthConnectRepository(session, owner_id).list_records()
        assert len(rows) == 1
        assert rows[0].payload == {"weight": {"inKilograms": 70.1}}

    deleted = api_client.post(
        "/health-connect/records:sync",
        json={"records": [], "deleted_record_ids": ["health-connect-weight-1"]},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"received": 1, "upserted": 0, "deleted": 1}
    with session_factory() as session:
        assert HealthConnectRepository(session, owner_id).list_records() == []


def test_api_accepts_unset_client_record_version(api_client: TestClient) -> None:
    """Health Connect writes -1 when the record's writer set no version.

    The schema required `>= 0`, so one such record rejected the whole batch of
    500 with a 422 and steps never reached the server. The value is opaque
    metadata mirrored as-is, and the column is a BigInteger.
    """
    response = api_client.post(
        "/health-connect/records:sync",
        json={
            "records": [
                {
                    "record_id": "health-connect-steps-1",
                    "record_type": "StepsRecord",
                    "client_record_version": -1,
                    "data_origin": "com.google.android.apps.fitness",
                    "start_time": "2026-07-15T08:30:00Z",
                    "end_time": "2026-07-15T08:40:00Z",
                    "last_modified_time": "2026-07-15T08:41:00Z",
                    "payload": {"count": 420},
                }
            ],
            "deleted_record_ids": [],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"received": 1, "upserted": 1, "deleted": 0}

    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with session_factory() as session:
        rows = HealthConnectRepository(session, owner_id).list_records()
        assert rows[0].client_record_version == -1


def test_api_returns_ten_minute_heart_rate_medians_from_sample_time(
    api_client: TestClient,
) -> None:
    uploaded = api_client.post(
        "/health-connect/records:sync",
        json={
            "records": [
                {
                    "record_id": "heart-rate-shifted-metadata",
                    "record_type": "HeartRateRecord",
                    "start_time": "2026-07-15T12:01:00Z",
                    "end_time": "2026-07-15T12:20:00Z",
                    "last_modified_time": "2026-07-15T12:30:00Z",
                    "payload": {
                        "samples": [
                            {
                                "time": "2026-07-15T08:01:00Z",
                                "beatsPerMinute": 70,
                            },
                            {
                                "time": "2026-07-15T08:05:00Z",
                                "beatsPerMinute": 100,
                            },
                            {
                                "time": "2026-07-15T08:09:00Z",
                                "beatsPerMinute": 80,
                            },
                            {
                                "time": "2026-07-15T08:12:00Z",
                                "beatsPerMinute": 90,
                            },
                            {
                                "time": "2026-07-15T08:13:00Z",
                                "beatsPerMinute": 0,
                            },
                            {
                                "time": "2026-07-15T09:00:00Z",
                                "beatsPerMinute": 120,
                            },
                        ]
                    },
                }
            ],
            "deleted_record_ids": [],
        },
    )
    assert uploaded.status_code == 200

    response = api_client.get(
        "/health-connect/heart-rate",
        params={
            "from": "2026-07-15T08:00:00Z",
            "to": "2026-07-15T09:00:00Z",
            "bin_minutes": 10,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "from_datetime": "2026-07-15T08:00:00",
        "to_datetime": "2026-07-15T09:00:00",
        "bin_minutes": 10,
        "points": [
            {
                "timestamp": "2026-07-15T08:00:00",
                "bpm": 80.0,
                "sample_count": 3,
            },
            {
                "timestamp": "2026-07-15T08:10:00",
                "bpm": 90.0,
                "sample_count": 1,
            },
        ],
    }


def test_food_user_cannot_sync_health_connect(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        food_user = User(
            username="health-connect-food",
            password_hash=hash_password("health-connect-food-password"),
            role=UserRole.food,
        )
        session.add(food_user)
        session.commit()
        token = issue_access_token(food_user.id, UserRole.food)

    response = api_client.post(
        "/health-connect/records:sync",
        headers={"Authorization": f"Bearer {token}"},
        json={"records": [], "deleted_record_ids": []},
    )
    assert response.status_code == 403
    assert response.json() == {
        "detail": {"code": "feature_disabled", "feature": "glucose"}
    }


def _hr_row(
    start_time: datetime,
    end_time: datetime,
    offset: str,
) -> HealthConnectRecord:
    return HealthConnectRecord(
        owner_id=UUID("00000000-0000-0000-0000-000000000000"),
        record_id="resolve",
        record_type="HeartRateRecord",
        start_time=start_time,
        end_time=end_time,
        payload={"startZoneOffset": offset},
    )


def test_resolve_instant_keeps_the_embedded_true_utc(
    api_client: TestClient,
) -> None:
    """Real rows embed the true instant and shift the columns by the offset."""
    from glucotracker.application.health_connect_samples import resolve_instant

    row = _hr_row(
        datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
        datetime(2026, 8, 3, 6, 1, tzinfo=UTC),
        "+04:00",
    )

    assert resolve_instant("2026-08-03T02:00:00Z", row) == datetime(
        2026, 8, 3, 2, 0, tzinfo=UTC
    )


def test_resolve_instant_pulls_back_a_local_wall_writer(
    api_client: TestClient,
) -> None:
    """A hypothetical local-wall writer is corrected back onto the timeline."""
    from glucotracker.application.health_connect_samples import resolve_instant

    row = _hr_row(
        datetime(2026, 8, 3, 2, 0, tzinfo=UTC),
        datetime(2026, 8, 3, 2, 1, tzinfo=UTC),
        "+04:00",
    )

    assert resolve_instant("2026-08-03T06:00:00Z", row) == datetime(
        2026, 8, 3, 2, 0, tzinfo=UTC
    )


def test_resolve_instant_end_falls_back_to_the_end_column(
    api_client: TestClient,
) -> None:
    """Without an embedded time each side falls back to its own column."""
    from glucotracker.application.health_connect_samples import resolve_instant

    row = _hr_row(
        datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
        datetime(2026, 8, 3, 7, 30, tzinfo=UTC),
        "+04:00",
    )

    assert resolve_instant(None, row) == datetime(2026, 8, 3, 6, 0, tzinfo=UTC)
    assert resolve_instant(None, row, fallback_to_end=True) == datetime(
        2026, 8, 3, 7, 30, tzinfo=UTC
    )
