"""Recorded fasted stretches, and the outcome derived from the trace."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    FingerstickReading,
    Meal,
    NightscoutGlucoseEntry,
    SensorSession,
)

SENSOR_START = datetime(2026, 8, 5, 0, 0)
START = datetime(2026, 8, 8, 20, 0)


def _falling_trace(session: Session, owner_id: UUID, hours: int) -> None:
    """A quiet stretch drifting down 1,0 mmol/L per hour from 8,0.

    Seeded with a calibrated sensor session, because the outcome refuses raw
    CGM for the same reason the autotune table does: the segment measures an
    absolute drift, and this owner's raw stream carries a per-session offset.
    """
    session.add(SensorSession(owner_id=owner_id, started_at=SENSOR_START))
    # Fingersticks land on the trace, so the fitted bias is zero and the
    # calibrated series equals the raw one. A meter reading agreeing with the
    # sensor is still a calibration — it is what makes the values normalized
    # rather than merely present.
    session.add_all(
        FingerstickReading(
            owner_id=owner_id,
            measured_at=START + timedelta(minutes=offset),
            glucose_mmol_l=8.0 - offset / 60,
        )
        for offset in (0, 45, 90, 135)
    )
    minutes = 0
    while minutes <= hours * 60:
        value = 8.0 - minutes / 60
        session.add(
            NightscoutGlucoseEntry(
                owner_id=owner_id,
                source_key=f"fast-{minutes}",
                timestamp=START + timedelta(minutes=minutes),
                value_mmol_l=value,
                value_mg_dl=round(value * 18.0182),
                source="CGM",
            )
        )
        minutes += 5


def test_a_held_fast_reports_the_drift_it_measured(api_client: TestClient) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        _falling_trace(session, owner_id, hours=4)
        session.commit()

    started = api_client.post(
        "/glucose/basal-tests",
        json={"window_start_hour": 20, "window_end_hour": 22, "planned_hours": 4},
    )
    assert started.status_code == 201
    run_id = started.json()["id"]
    assert started.json()["status"] == "running"
    # Nothing to measure yet: a running stretch has no outcome.
    assert started.json()["outcome"] is None

    with api_client.app_state["session_factory"]() as session:
        from glucotracker.infra.db.models import BasalFastingTest

        row = session.get(BasalFastingTest, UUID(run_id))
        row.started_at = START
        session.commit()

    stopped = api_client.patch(
        f"/glucose/basal-tests/{run_id}",
        json={"status": "completed"},
    )

    assert stopped.status_code == 200
    outcome = stopped.json()["outcome"]
    assert outcome is not None
    assert outcome["fast_held"] is True
    assert outcome["intervention_count"] == 0
    assert outcome["start_glucose_mmol_l"] == 8.0
    assert outcome["drift_mmol_l_per_hour"] == -1.0


def test_eating_during_a_run_keeps_the_record_and_voids_the_measurement(
    api_client: TestClient,
) -> None:
    """A broken fast is still worth recording — it is just not evidence.

    Dropping the run would lose the fact that the evening was attempted; keeping
    it without saying the fast broke would publish a drift that measured a meal.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        _falling_trace(session, owner_id, hours=4)
        session.add(
            Meal(
                owner_id=owner_id,
                eaten_at=START + timedelta(hours=2),
                title="Печенье",
                source=MealSource.manual,
                status=MealStatus.accepted,
                total_carbs_g=30,
                total_protein_g=2,
                total_fat_g=6,
                total_kcal=200,
            )
        )
        session.commit()

    run_id = api_client.post(
        "/glucose/basal-tests",
        json={"window_start_hour": 20, "window_end_hour": 22, "planned_hours": 4},
    ).json()["id"]
    with api_client.app_state["session_factory"]() as session:
        from glucotracker.infra.db.models import BasalFastingTest

        row = session.get(BasalFastingTest, UUID(run_id))
        row.started_at = START
        session.commit()

    stopped = api_client.patch(
        f"/glucose/basal-tests/{run_id}",
        json={"status": "aborted", "abort_reason": "ate"},
    ).json()

    assert stopped["status"] == "aborted"
    assert stopped["abort_reason"] == "ate"
    assert stopped["outcome"]["fast_held"] is False
    assert stopped["outcome"]["intervention_count"] == 1


def test_starting_a_run_supersedes_one_left_open(api_client: TestClient) -> None:
    """Two runs at once cannot both be true, and the stale one is the older."""
    first = api_client.post(
        "/glucose/basal-tests",
        json={"window_start_hour": 20, "window_end_hour": 22, "planned_hours": 4},
    ).json()
    api_client.post(
        "/glucose/basal-tests",
        json={"window_start_hour": 2, "window_end_hour": 5, "planned_hours": 5},
    )

    runs = api_client.get("/glucose/basal-tests").json()
    superseded = next(run for run in runs if run["id"] == first["id"])

    assert superseded["status"] == "aborted"
    assert superseded["abort_reason"] == "superseded"
    assert sum(run["status"] == "running" for run in runs) == 1
