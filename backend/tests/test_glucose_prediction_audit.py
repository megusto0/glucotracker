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
from glucotracker.domain.entities import MealStatus
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
    ("read_as_owner", "expected_runs", "expected_due", "expected_evaluated"),
    [(True, 2, 1, 1), (False, 0, 0, 0)],
)
def test_prediction_audit_repository_is_owner_scoped(
    api_client: TestClient,
    *,
    read_as_owner: bool,
    expected_runs: int,
    expected_due: int,
    expected_evaluated: int,
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
        evaluated = _add_forecast(
            GlucosePredictionAuditRepository(session, owner_id),
            anchor=anchor - timedelta(hours=1),
            predicted=7.5,
        )
        evaluated.run.model_json = {
            **evaluated.run.model_json,
            "audit_calibration_by_horizon": [
                {
                    "horizon_minutes": 30,
                    "base_prediction_mmol_l": 7.25,
                }
            ],
        }
        evaluated.evaluation_status = "evaluated"
        evaluated.actual_value_mmol_l = 7.0
        evaluated.actual_timestamp = evaluated.target_timestamp
        evaluated.evaluated_at = evaluated.target_timestamp + timedelta(minutes=10)
        session.commit()

    with session_factory() as session:
        repository = GlucosePredictionAuditRepository(session, reader_id)
        due = repository.list_due_points(
            anchor + timedelta(hours=1),
            limit=10,
        )
        evaluated_points = repository.evaluated_base_points(
            since=anchor - timedelta(hours=2),
            before=anchor,
            model_versions=("audit-test-v1",),
        )
        assert repository.count_runs() == expected_runs
        assert len(due) == expected_due
        assert len(evaluated_points) == expected_evaluated
        if read_as_owner:
            assert evaluated_points[0].base_predicted_value_mmol_l == 7.25


@pytest.mark.parametrize(
    "unavailable_field",
    ["generated_at", "target_timestamp", "actual_timestamp", "evaluated_at"],
)
def test_calibration_excludes_outcomes_unavailable_at_cutoff(
    api_client: TestClient,
    unavailable_field: str,
) -> None:
    factory = api_client.app_state["session_factory"]
    owner = UUID(str(api_client.app_state["current_user_id"]))
    cutoff = datetime(2026, 7, 20, 12, tzinfo=UTC)
    with factory() as session:
        repo = GlucosePredictionAuditRepository(session, owner)
        point = _add_forecast(repo, anchor=cutoff - timedelta(hours=2))
        point.evaluation_status = "evaluated"
        point.actual_value_mmol_l = 7.0
        point.actual_timestamp = point.target_timestamp
        point.evaluated_at = point.target_timestamp + timedelta(minutes=10)
        target = point.run if unavailable_field == "generated_at" else point
        setattr(target, unavailable_field, cutoff + timedelta(minutes=1))
        session.commit()
        assert (
            repo.evaluated_base_points(
                since=cutoff - timedelta(days=1),
                before=cutoff,
                model_versions=("audit-test-v1",),
            )
            == []
        )


@pytest.mark.parametrize("read_other", [False, True])
def test_snapshot_and_intervention_reads_are_owner_scoped(api_client, read_other):
    factory = api_client.app_state["session_factory"]
    owner = UUID(str(api_client.app_state["current_user_id"]))
    at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    with factory() as session:
        other = User(
            username=f"snapshot-other-{read_other}",
            password_hash="unused",
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        own = GlucosePredictionAuditRepository(session, owner)
        point = _add_forecast(own, anchor=at)
        point.run.horizon_minutes = 90
        point.run.step_minutes = 5
        session.add(
            NightscoutGlucoseEntry(
                owner_id=owner,
                source_key="snapshot-cgm",
                timestamp=at,
                value_mmol_l=6,
                created_at=at,
            )
        )
        session.add(
            Meal(
                owner_id=owner,
                eaten_at=(at + timedelta(minutes=15)).replace(tzinfo=None),
                status="accepted",
                source="manual",
                updated_at=at,
                created_at=at,
            )
        )
        session.commit()
        repo = GlucosePredictionAuditRepository(
            session, other.id if read_other else owner
        )
        forecast = repo.latest_forecast(
            model_version="audit-test-v1", since=at - timedelta(minutes=1), before=at
        )
        glucose = repo.latest_glucose_at(since=at - timedelta(minutes=1), before=at)
        events = repo.intervention_times(
            since=at, before=at + timedelta(hours=1), known_at=at + timedelta(hours=1)
        )
        assert (forecast is None) == read_other
        assert (glucose is None) == read_other
        assert len(events) == (0 if read_other else 1)


def test_late_meal_is_excluded_from_calibration_without_rewriting_forecast(api_client):
    factory = api_client.app_state["session_factory"]
    owner = UUID(str(api_client.app_state["current_user_id"]))
    at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    cutoff = at + timedelta(hours=2)
    with factory() as session:
        repo = GlucosePredictionAuditRepository(session, owner)
        point = _add_forecast(repo, anchor=at, no_new_input=True)
        point.evaluation_status = "evaluated"
        point.actual_value_mmol_l = 7
        point.actual_timestamp = point.target_timestamp
        point.evaluated_at = at + timedelta(minutes=45)
        session.add(
            Meal(
                owner_id=owner,
                eaten_at=(at + timedelta(minutes=15)).replace(tzinfo=None),
                status="accepted",
                source="manual",
                updated_at=cutoff - timedelta(minutes=1),
                created_at=cutoff - timedelta(minutes=1),
            )
        )
        session.commit()
        assert (
            repo.evaluated_base_points(
                since=at - timedelta(minutes=1),
                before=cutoff,
                model_versions=("audit-test-v1",),
            )
            == []
        )
        assert point.evaluation_status == "evaluated"
        assert point.predicted_value_mmol_l == 7


@pytest.mark.parametrize(
    "mode,step", [("normalized", 5), ("raw", 7), ("normalized", 30)]
)
def test_cached_response_resamples_without_training(
    api_client, monkeypatch, mode, step
):
    from glucotracker.api.schemas import (
        GlucosePredictionInputs,
        GlucosePredictionModel,
        GlucosePredictionPoint,
        GlucosePredictionResponse,
    )
    from glucotracker.application.glucose_prediction import (
        MODEL_VERSION,
        GlucosePredictionService,
    )

    at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    response = GlucosePredictionResponse(
        generated_at=at,
        anchor_timestamp=at.replace(tzinfo=None),
        anchor_value=8,
        raw_anchor_value=6,
        horizon_minutes=90,
        step_minutes=5,
        mode="normalized",
        model=GlucosePredictionModel(version=MODEL_VERSION, algorithm="test"),
        inputs=GlucosePredictionInputs(),
        notes=[],
        points=[
            GlucosePredictionPoint(
                timestamp=(at + timedelta(minutes=h)).replace(tzinfo=None),
                horizon_minutes=h,
                raw_value=6 + h / 90,
                raw_ci_low=5 + h / 90,
                raw_ci_high=7 + h / 90,
                normalized_value=8 + h / 90,
                display_value=8 + h / 90,
                ci_low=7 + h / 90,
                ci_high=9 + h / 90,
                confidence=0.5,
                band="in_range",
            )
            for h in range(5, 91, 5)
        ],
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Serving a snapshot must not train")

    monkeypatch.setattr(GlucosePredictionService, "predict", forbidden)
    factory = api_client.app_state["session_factory"]
    owner = UUID(str(api_client.app_state["current_user_id"]))
    with factory() as session:
        service = GlucosePredictionAuditService(session, owner)
        service.record(response)
        session.commit()
        served = service.latest(
            now=at, mode=mode, horizon_minutes=90, step_minutes=step
        )
        assert len(served.points) == 90 // step
        assert served.anchor_value == (6 if mode == "raw" else 8)
        for point in served.points:
            assert abs(point.raw_value - (6 + point.horizon_minutes / 90)) < 0.002
            assert (
                abs(point.display_value - point.raw_value - (0 if mode == "raw" else 2))
                < 0.002
            )
        stale = service.latest(now=at + timedelta(minutes=16))
        assert stale.points == []

        # Clipping raw and normalized trajectories can make their difference vary.
        # Serving must preserve the stored normalized value and anchor separately.
        from glucotracker.application.glucose_prediction_audit import _resample_snapshot

        clipped = response.model_copy(deep=True)
        clipped.points[0].raw_value = 2
        clipped.points[0].normalized_value = 2.5
        clipped.points[0].display_value = 2.5
        resampled = _resample_snapshot(clipped, "normalized", 90, 5)
        assert resampled.anchor_value == 8
        assert resampled.points[0].normalized_value == 2.5
        assert resampled.points[1].normalized_value == pytest.approx(
            response.points[1].normalized_value, abs=0.001
        )

        # A new meal invalidates the no-new-input snapshot immediately.
        session.add(
            Meal(
                owner_id=owner,
                eaten_at=(at + timedelta(minutes=1)).replace(tzinfo=None),
                status=MealStatus.accepted,
                source="manual",
                created_at=at + timedelta(minutes=1),
                updated_at=at + timedelta(minutes=1),
            )
        )
        session.commit()
        assert service.latest(now=at + timedelta(minutes=2)).points == []
