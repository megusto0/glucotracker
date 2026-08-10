"""Sleep/activity breakdowns and owner-scoped activity annotations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import (
    HealthConnectRecord,
    NightscoutGlucoseEntry,
    User,
)
from glucotracker.infra.db.repositories.activity_annotations import (
    ActivityAnnotationRepository,
)
from glucotracker.infra.security import hash_password

DAY = datetime(2026, 8, 6, tzinfo=UTC)


def _owner(api_client: TestClient):
    return (
        UUID(str(api_client.app_state["current_user_id"])),
        api_client.app_state["session_factory"],
    )


def _record(
    session,
    owner_id: UUID,
    record_type: str,
    start: datetime,
    end: datetime,
    payload: dict,
    suffix: str = "",
) -> None:
    session.add(
        HealthConnectRecord(
            owner_id=owner_id,
            record_id=f"breakdown-{record_type}-{start.isoformat()}-{suffix}",
            record_type=record_type,
            start_time=start,
            end_time=end,
            payload=payload,
        )
    )


def _heart_rate(
    session,
    owner_id: UUID,
    start: datetime,
    end: datetime,
    bpm,
) -> None:
    samples = []
    at = start
    while at <= end:
        samples.append(
            {
                "time": at.isoformat().replace("+00:00", "Z"),
                "beatsPerMinute": bpm(at),
            }
        )
        at += timedelta(minutes=5)
    _record(
        session,
        owner_id,
        "HeartRateRecord",
        start,
        end,
        {"samples": samples},
    )


def _glucose(session, owner_id: UUID, at: datetime, value: float) -> None:
    session.add(
        NightscoutGlucoseEntry(
            owner_id=owner_id,
            source_key=f"body-state-{at.isoformat()}",
            timestamp=at,
            value_mmol_l=value,
            value_mg_dl=round(value * 18.0182),
            source="CGM",
        )
    )


def _get(api_client: TestClient, kind: str, start: datetime, end: datetime):
    return api_client.get(
        "/glucose/body-states/breakdown",
        params={
            "kind": kind,
            "start": start.replace(tzinfo=None).isoformat(),
            "end": end.replace(tzinfo=None).isoformat(),
        },
    )


def test_sleep_breakdown_aligns_stages_low_and_waking(
    api_client: TestClient,
) -> None:
    owner_id, session_factory = _owner(api_client)
    start = DAY + timedelta(minutes=40)
    end = DAY + timedelta(hours=6, minutes=42)
    with session_factory() as session:
        _record(
            session,
            owner_id,
            "SleepSessionRecord",
            start,
            end,
            {
                "startTime": start.isoformat().replace("+00:00", "Z"),
                "endTime": end.isoformat().replace("+00:00", "Z"),
                "stages": [
                    {
                        "startTime": start.isoformat().replace("+00:00", "Z"),
                        "endTime": (DAY + timedelta(hours=2, minutes=15))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "stage": 5,
                    },
                    {
                        "startTime": (DAY + timedelta(hours=2, minutes=15))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "endTime": (DAY + timedelta(hours=2, minutes=30))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "stage": 1,
                    },
                    {
                        "startTime": (DAY + timedelta(hours=2, minutes=30))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "endTime": end.isoformat().replace("+00:00", "Z"),
                        "stage": 4,
                    },
                ],
            },
        )
        _heart_rate(session, owner_id, start, end, lambda _: 58)
        at = start
        while at <= end:
            low_start = DAY + timedelta(hours=2, minutes=15)
            low_end = DAY + timedelta(hours=2, minutes=35)
            value = 3.6 if low_start <= at <= low_end else 6.0
            _glucose(session, owner_id, at, value)
            at += timedelta(minutes=5)
        session.commit()

    response = _get(api_client, "sleep", start, end)
    assert response.status_code == 200
    body = response.json()
    assert [stage["stage"] for stage in body["sleep_stages"]] == [
        "deep",
        "awake",
        "light",
    ]
    assert body["mean_bpm"] == 58.0
    assert body["low_minutes"] >= 15
    assert body["tir_percent"] < 100
    assert body["insight_code"] == "sleep_low_near_wake"
    assert body["insight_value"] == 3.6


def test_activity_without_step_records_suggests_cycling_and_shows_glucose(
    api_client: TestClient,
) -> None:
    owner_id, session_factory = _owner(api_client)
    start = DAY + timedelta(hours=17, minutes=5)
    end = DAY + timedelta(hours=18, minutes=17)
    with session_factory() as session:
        _record(
            session,
            owner_id,
            "ExerciseSessionRecord",
            start,
            end,
            {"startTime": start.isoformat(), "endTime": end.isoformat()},
        )
        _heart_rate(
            session,
            owner_id,
            start,
            end,
            lambda at: 126 + (at.minute % 3),
        )
        for offset, value in ((0, 9.2), (72, 7.0), (132, 5.4), (180, 5.8)):
            _glucose(session, owner_id, start + timedelta(minutes=offset), value)
        session.commit()

    response = _get(api_client, "activity", start, end)
    assert response.status_code == 200
    body = response.json()
    assert body["steps"] is None
    assert body["steps_available"] is False
    assert body["steady_percent"] >= 70
    assert body["suggested_activity_type"] == "cycling"
    assert body["glucose_start"] == 9.2
    assert body["glucose_two_hour_minimum"] == 5.4
    assert body["glucose_delta_two_hours"] == -3.8


def test_activity_label_and_no_steps_rule_are_reused(api_client: TestClient) -> None:
    owner_id, session_factory = _owner(api_client)
    first = DAY + timedelta(hours=17)
    second = DAY + timedelta(days=1, hours=17)
    with session_factory() as session:
        for index, start in enumerate((first, second)):
            end = start + timedelta(hours=1)
            _record(
                session,
                owner_id,
                "ExerciseSessionRecord",
                start,
                end,
                {"startTime": start.isoformat(), "endTime": end.isoformat()},
                str(index),
            )
            _heart_rate(session, owner_id, start, end, lambda _: 128)
        session.commit()

    saved = api_client.put(
        "/glucose/body-states/activity-label",
        json={
            "start_at": first.replace(tzinfo=None).isoformat(),
            "end_at": (first + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
            "activity_type": "cycling",
            "remember_no_steps_rule": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["activity_type_source"] == "user"

    reused = _get(api_client, "activity", second, second + timedelta(hours=1))
    assert reused.status_code == 200
    assert reused.json()["activity_type"] == "cycling"
    assert reused.json()["activity_type_source"] == "rule"


@pytest.mark.parametrize("reader", ["alice", "bob"])
def test_activity_annotation_repository_isolates_two_users(
    api_client: TestClient,
    reader: str,
) -> None:
    alice_id, session_factory = _owner(api_client)
    with session_factory() as session:
        bob = User(
            username=f"body-state-{reader}",
            password_hash=hash_password("body-state-password"),
            role=UserRole.gluco,
        )
        session.add(bob)
        session.commit()
        span = {
            "start_at": DAY.replace(tzinfo=None),
            "end_at": (DAY + timedelta(hours=1)).replace(tzinfo=None),
        }
        ActivityAnnotationRepository(session, alice_id).upsert(
            **span,
            activity_type="cycling",
            remember_no_steps_rule=True,
        )
        ActivityAnnotationRepository(session, bob.id).upsert(
            **span,
            activity_type="gym",
            remember_no_steps_rule=False,
        )
        session.commit()
        selected = alice_id if reader == "alice" else bob.id
        row = ActivityAnnotationRepository(session, selected).get(**span)

    assert row is not None
    assert row.owner_id == selected
    assert row.activity_type == ("cycling" if reader == "alice" else "gym")


def test_activity_annotation_repository_requires_owner(api_client: TestClient) -> None:
    _, session_factory = _owner(api_client)
    with session_factory() as session, pytest.raises(ValueError):
        ActivityAnnotationRepository(session, None)  # type: ignore[arg-type]
