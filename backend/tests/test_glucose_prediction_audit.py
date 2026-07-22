"""Prospective glucose forecast audit and outcome evaluation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from glucotracker.application.glucose_prediction_audit import (
    GlucosePredictionAuditService,
)
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import (
    GlucosePredictionPointAudit,
    Meal,
    NightscoutGlucoseEntry,
    User,
)
from glucotracker.infra.db.repositories.glucose_prediction_audit import (
    ForecastPointSnapshot,
    GlucosePredictionAuditRepository,
)
from glucotracker.infra.security import hash_password


def _add_forecast(
    repository: GlucosePredictionAuditRepository,
    *,
    anchor: datetime,
    predicted: float = 7.0,
    no_new_input: bool = False,
) -> GlucosePredictionPointAudit:
    run, created = repository.add_forecast(
        generated_at=anchor,
        anchor_timestamp=anchor,
        anchor_value_mmol_l=6.0,
        model_version="audit-test-v1",
        algorithm="test",
        horizon_minutes=30,
        step_minutes=30,
        model_json={
            "version": "audit-test-v1",
            "forecast_assumption": (
                "no_new_food_or_insulin" if no_new_input else "observed_policy"
            ),
        },
        inputs_json={"carbs_g_4h": 20.0},
        notes_json=["test"],
        points=[
            ForecastPointSnapshot(
                target_timestamp=anchor + timedelta(minutes=30),
                horizon_minutes=30,
                predicted_value_mmol_l=predicted,
                ci_low_mmol_l=6.5,
                ci_high_mmol_l=7.5,
                confidence=0.7,
                predicted_band="in_range",
            )
        ],
    )
    assert created is True
    return run.points[0]


def test_outcome_evaluation_is_delayed_scored_and_owner_scoped(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    anchor = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)

    with session_factory() as session:
        other = User(
            username="prediction-audit-other",
            password_hash=hash_password("prediction-audit-other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        other_id = other.id
        point = _add_forecast(
            GlucosePredictionAuditRepository(session, owner_id),
            anchor=anchor,
        )
        point_id = point.id
        session.add_all(
            [
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key="prediction-audit-actual",
                    timestamp=anchor + timedelta(minutes=33),
                    value_mmol_l=7.2,
                ),
                NightscoutGlucoseEntry(
                    owner_id=other_id,
                    source_key="prediction-audit-other-actual",
                    timestamp=anchor + timedelta(minutes=30),
                    value_mmol_l=20.0,
                ),
            ]
        )
        session.commit()

    with session_factory() as session:
        early = GlucosePredictionAuditService(session, owner_id).evaluate_due(
            now=anchor + timedelta(minutes=39)
        )
        session.commit()
    assert early.evaluated == 0

    with session_factory() as session:
        result = GlucosePredictionAuditService(session, owner_id).evaluate_due(
            now=anchor + timedelta(minutes=41)
        )
        session.commit()
    assert result.evaluated == 1
    assert result.missing == 0

    with session_factory() as session:
        evaluated = session.scalar(
            select(GlucosePredictionPointAudit).where(
                GlucosePredictionPointAudit.id == point_id
            )
        )
        assert evaluated is not None
        assert evaluated.evaluation_status == "evaluated"
        assert evaluated.actual_value_mmol_l == 7.2
        assert evaluated.signed_error_mmol_l == pytest.approx(-0.2)
        assert evaluated.absolute_error_mmol_l == pytest.approx(0.2)
        assert evaluated.baseline_absolute_error_mmol_l == pytest.approx(1.2)
        assert evaluated.direction_correct is True
        assert evaluated.within_interval is True
        assert GlucosePredictionAuditRepository(session, other_id).count_runs() == 0


def test_outcome_becomes_missing_after_maximum_wait(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    anchor = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)

    with session_factory() as session:
        point = _add_forecast(
            GlucosePredictionAuditRepository(session, owner_id),
            anchor=anchor,
        )
        point_id = point.id
        session.commit()

    with session_factory() as session:
        result = GlucosePredictionAuditService(session, owner_id).evaluate_due(
            now=anchor + timedelta(hours=25)
        )
        session.commit()
    assert result.missing == 1

    with session_factory() as session:
        missing = session.get(GlucosePredictionPointAudit, point_id)
        assert missing is not None
        assert missing.evaluation_status == "missing"
        assert missing.actual_value_mmol_l is None


def test_no_input_outcome_is_not_scored_after_intervention(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    anchor = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)

    with session_factory() as session:
        point = _add_forecast(
            GlucosePredictionAuditRepository(session, owner_id),
            anchor=anchor,
            no_new_input=True,
        )
        point_id = point.id
        session.add(
            Meal(
                owner_id=owner_id,
                eaten_at=(anchor + timedelta(minutes=10)).replace(tzinfo=None),
                status="accepted",
                source="manual",
                total_carbs_g=15,
                total_protein_g=0,
                total_fat_g=0,
                total_fiber_g=0,
                total_kcal=60,
            )
        )
        session.add(
            NightscoutGlucoseEntry(
                owner_id=owner_id,
                source_key="prediction-intervened-actual",
                timestamp=anchor + timedelta(minutes=30),
                value_mmol_l=8.0,
            )
        )
        session.commit()

    with session_factory() as session:
        result = GlucosePredictionAuditService(session, owner_id).evaluate_due(
            now=anchor + timedelta(minutes=41)
        )
        session.commit()

    assert result.intervened == 1
    assert result.evaluated == 0
    with session_factory() as session:
        intervened = session.get(GlucosePredictionPointAudit, point_id)
        assert intervened is not None
        assert intervened.evaluation_status == "intervened"
        assert intervened.intervention_detected is True
        assert intervened.actual_value_mmol_l == 8.0
        assert intervened.absolute_error_mmol_l is None


@pytest.mark.parametrize(
    ("read_as_owner", "expected_runs", "expected_due"),
    [(True, 1, 1), (False, 0, 0)],
)
def test_prediction_audit_repository_is_owner_scoped(
    api_client: TestClient,
    *,
    read_as_owner: bool,
    expected_runs: int,
    expected_due: int,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    anchor = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)

    with session_factory() as session:
        other = User(
            username=f"prediction-reader-{read_as_owner}",
            password_hash=hash_password("prediction-reader-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        reader_id = owner_id if read_as_owner else other.id
        _add_forecast(
            GlucosePredictionAuditRepository(session, owner_id),
            anchor=anchor,
        )
        session.commit()

    with session_factory() as session:
        repository = GlucosePredictionAuditRepository(session, reader_id)
        due = repository.list_due_points(
            anchor + timedelta(hours=1),
            limit=10,
        )
        assert repository.count_runs() == expected_runs
        assert len(due) == expected_due
