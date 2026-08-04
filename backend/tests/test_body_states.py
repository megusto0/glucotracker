"""Sleep and hard-effort detection from sessions and from heart rate alone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from glucotracker.infra.db.models import HealthConnectRecord

DAY = datetime(2026, 7, 25, tzinfo=UTC)


def _session(
    session,
    owner_id: UUID,
    record_type: str,
    start: datetime,
    end: datetime,
    payload: dict | None = None,
) -> None:
    session.add(
        HealthConnectRecord(
            owner_id=owner_id,
            record_id=f"{record_type}-{start.isoformat()}",
            record_type=record_type,
            start_time=start,
            end_time=end,
            payload=payload or {},
        )
    )


def _heart_rate(
    session,
    owner_id: UUID,
    *,
    start: datetime,
    end: datetime,
    bpm_at,
    step: timedelta = timedelta(minutes=5),
) -> None:
    """Write one heart-rate row per sample, the way the sync stores them."""
    at = start
    while at < end:
        session.add(
            HealthConnectRecord(
                owner_id=owner_id,
                record_id=f"hr-{at.isoformat()}",
                record_type="HeartRateRecord",
                start_time=at,
                end_time=at,
                payload={"samples": [{"beatsPerMinute": bpm_at(at)}]},
            )
        )
        at += step


def _states(api_client: TestClient, *, hours: int = 24) -> list[dict]:
    response = api_client.get(
        "/glucose/body-states",
        params={
            "from": DAY.replace(tzinfo=None).isoformat(),
            "to": (DAY.replace(tzinfo=None) + timedelta(hours=hours)).isoformat(),
        },
    )
    assert response.status_code == 200
    return response.json()["states"]


def _owner(api_client: TestClient) -> tuple[UUID, object]:
    return (
        UUID(str(api_client.app_state["current_user_id"])),
        api_client.app_state["session_factory"],
    )


def test_recorded_sleep_and_workout_are_reported_as_recorded(
    api_client: TestClient,
) -> None:
    owner_id, session_factory = _owner(api_client)
    with session_factory() as session:
        _session(
            session,
            owner_id,
            "SleepSessionRecord",
            DAY,
            DAY + timedelta(hours=7),
        )
        _session(
            session,
            owner_id,
            "ExerciseSessionRecord",
            DAY + timedelta(hours=18),
            DAY + timedelta(hours=18, minutes=40),
            {"title": "Бег"},
        )
        session.commit()

    states = _states(api_client)
    assert [(state["kind"], state["source"]) for state in states] == [
        ("sleep", "recorded"),
        ("activity", "recorded"),
    ]
    assert states[0]["total_minutes"] == 420
    assert states[1]["label"] == "Бег"
    assert all(state["confidence"] == "high" for state in states)


def test_a_night_without_a_sleep_record_is_read_from_the_heart_rate_trough(
    api_client: TestClient,
) -> None:
    """The watch syncs sleep late, so the nightly trough has to stand in."""
    owner_id, session_factory = _owner(api_client)
    trough_start = DAY + timedelta(hours=1)
    trough_end = DAY + timedelta(hours=6)
    with session_factory() as session:
        _heart_rate(
            session,
            owner_id,
            start=DAY - timedelta(hours=6),
            end=DAY + timedelta(hours=18),
            bpm_at=lambda at: 48 if trough_start <= at <= trough_end else 72,
        )
        session.commit()

    states = _states(api_client)
    assert [(state["kind"], state["source"]) for state in states] == [
        ("sleep", "heart_rate"),
    ]
    sleep = states[0]
    assert sleep["confidence"] == "medium"
    assert sleep["start_at"] == trough_start.replace(tzinfo=None).isoformat()
    assert sleep["end_at"] == trough_end.replace(tzinfo=None).isoformat()
    assert sleep["mean_bpm"] == 48.0


def test_a_sustained_climb_above_resting_reads_as_hard_effort(
    api_client: TestClient,
) -> None:
    owner_id, session_factory = _owner(api_client)
    effort_start = DAY + timedelta(hours=17)
    effort_end = DAY + timedelta(hours=17, minutes=30)
    with session_factory() as session:
        _heart_rate(
            session,
            owner_id,
            start=DAY,
            end=DAY + timedelta(hours=20),
            bpm_at=lambda at: 140 if effort_start <= at <= effort_end else 64,
        )
        session.commit()

    activity = [state for state in _states(api_client) if state["kind"] == "activity"]
    assert len(activity) == 1
    assert activity[0]["source"] == "heart_rate"
    assert activity[0]["confidence"] == "medium"
    assert activity[0]["peak_bpm"] == 140.0
    assert activity[0]["total_minutes"] == 30


def test_a_recorded_session_replaces_the_inferred_one_it_covers(
    api_client: TestClient,
) -> None:
    """Both signals describe one night; the reply must not show it twice."""
    owner_id, session_factory = _owner(api_client)
    trough_start = DAY + timedelta(hours=1)
    trough_end = DAY + timedelta(hours=6)
    with session_factory() as session:
        _session(
            session,
            owner_id,
            "SleepSessionRecord",
            trough_start,
            trough_end,
        )
        _heart_rate(
            session,
            owner_id,
            start=DAY - timedelta(hours=6),
            end=DAY + timedelta(hours=18),
            bpm_at=lambda at: 48 if trough_start <= at <= trough_end else 72,
        )
        session.commit()

    states = _states(api_client)
    assert [(state["kind"], state["source"]) for state in states] == [
        ("sleep", "recorded"),
    ]


def test_a_flat_day_is_not_mistaken_for_one_long_sleep(
    api_client: TestClient,
) -> None:
    """A percentile with nothing to separate would swallow the whole window."""
    owner_id, session_factory = _owner(api_client)
    with session_factory() as session:
        _heart_rate(
            session,
            owner_id,
            start=DAY - timedelta(hours=6),
            end=DAY + timedelta(hours=18),
            bpm_at=lambda at: 70,
        )
        session.commit()

    assert _states(api_client) == []


def test_the_range_must_be_ordered_and_bounded(api_client: TestClient) -> None:
    backwards = api_client.get(
        "/glucose/body-states",
        params={"from": "2026-07-25T12:00:00", "to": "2026-07-25T11:00:00"},
    )
    assert backwards.status_code == 422

    too_wide = api_client.get(
        "/glucose/body-states",
        params={"from": "2026-07-01T00:00:00", "to": "2026-07-25T00:00:00"},
    )
    assert too_wide.status_code == 422
