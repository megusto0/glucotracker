"""Forecast-based glucose projection used as a dose input."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.application.glucose_prediction import MODEL_VERSION
from glucotracker.application.glucose_trend_projection import (
    DEFAULT_PROJECTION_HORIZON_MINUTES,
    MAX_UPWARD_PROJECTION_MMOL_L,
    GlucoseTrendProjectionService,
)
from glucotracker.infra.db.models import (
    GlucosePredictionPointAudit,
    GlucosePredictionRun,
)

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
H = DEFAULT_PROJECTION_HORIZON_MINUTES


def _run(
    session: Session,
    owner_id: UUID,
    *,
    anchor_at: datetime,
    anchor_value: float,
    predicted: float,
    horizon: int = H,
    model_version: str = MODEL_VERSION,
    actual: float | None = None,
) -> GlucosePredictionRun:
    run = GlucosePredictionRun(
        owner_id=owner_id,
        generated_at=anchor_at,
        anchor_timestamp=anchor_at,
        anchor_value_mmol_l=anchor_value,
        model_version=model_version,
        algorithm="test",
        horizon_minutes=90,
        step_minutes=5,
        model_json={},
        inputs_json={},
        notes_json=[],
    )
    run.points = [
        GlucosePredictionPointAudit(
            owner_id=owner_id,
            target_timestamp=anchor_at + timedelta(minutes=horizon),
            horizon_minutes=horizon,
            predicted_value_mmol_l=predicted,
            ci_low_mmol_l=predicted - 1,
            ci_high_mmol_l=predicted + 1,
            confidence=0.6,
            predicted_band="in_range",
            evaluation_status="evaluated" if actual is not None else "pending",
            actual_value_mmol_l=actual,
        )
    ]
    session.add(run)
    session.flush()
    return run


def _owner(api_client: TestClient) -> UUID:
    return UUID(str(api_client.app_state["current_user_id"]))


def test_falling_forecast_projects_below_the_current_reading(
    api_client: TestClient,
) -> None:
    """In range but heading down is the case a flat reading cannot express."""
    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        _run(session, owner_id, anchor_at=NOW, anchor_value=7.0, predicted=5.2)
        session.commit()

    with factory() as session:
        projection = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert projection.status == "ready"
    assert projection.is_usable
    # Too few evaluated outcomes to calibrate, so the raw move is used as-is.
    assert projection.calibration_factor == 1.0
    assert projection.projected_mmol_l == 5.2
    assert projection.move_mmol_l is not None
    assert abs(projection.move_mmol_l + 1.8) < 1e-6


def test_rising_forecast_is_capped_much_tighter_than_a_falling_one(
    api_client: TestClient,
) -> None:
    """Dosing more on a predicted rise is the unrecoverable direction."""
    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        _run(session, owner_id, anchor_at=NOW, anchor_value=7.0, predicted=12.0)
        session.commit()

    with factory() as session:
        rising = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert rising.status == "ready"
    assert rising.capped
    assert rising.move_mmol_l == MAX_UPWARD_PROJECTION_MMOL_L

    with factory() as session:
        _run(
            session,
            owner_id,
            anchor_at=NOW + timedelta(minutes=5),
            anchor_value=7.0,
            predicted=2.0,
        )
        session.commit()
    with factory() as session:
        falling = GlucoseTrendProjectionService(session, owner_id).project(
            NOW + timedelta(minutes=5)
        )

    assert falling.capped
    # The downward allowance is three times the upward one.
    assert falling.move_mmol_l == -3.0


def test_small_predicted_move_is_ignored(api_client: TestClient) -> None:
    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        _run(session, owner_id, anchor_at=NOW, anchor_value=7.0, predicted=7.3)
        session.commit()

    with factory() as session:
        projection = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert projection.status == "move_below_threshold"
    assert not projection.is_usable


def test_stale_forecast_is_not_used(api_client: TestClient) -> None:
    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        _run(
            session,
            owner_id,
            anchor_at=NOW - timedelta(hours=2),
            anchor_value=7.0,
            predicted=5.0,
        )
        session.commit()

    with factory() as session:
        projection = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert projection.status == "no_forecast"
    assert not projection.is_usable


def test_forecast_made_after_the_decision_is_never_used(
    api_client: TestClient,
) -> None:
    """A retrospective review must not borrow a later forecast."""
    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        _run(
            session,
            owner_id,
            anchor_at=NOW + timedelta(minutes=10),
            anchor_value=7.0,
            predicted=4.0,
        )
        session.commit()

    with factory() as session:
        projection = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert projection.status == "no_forecast"


def test_calibration_scales_a_shy_forecast_toward_observed_moves(
    api_client: TestClient,
) -> None:
    """A model that consistently under-states its moves gets scaled up."""
    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        # 220 evaluated outcomes where the real move was twice the predicted one.
        for index in range(220):
            at = NOW - timedelta(days=10) + timedelta(minutes=30 * index)
            _run(
                session,
                owner_id,
                anchor_at=at,
                anchor_value=7.0,
                predicted=6.0,
                actual=5.0,
            )
        _run(session, owner_id, anchor_at=NOW, anchor_value=7.0, predicted=6.0)
        session.commit()

    with factory() as session:
        projection = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert projection.status == "ready"
    assert projection.calibration_samples == 220
    assert projection.calibration_factor == 2.0
    # -1.0 predicted becomes -2.0 applied.
    assert projection.projected_mmol_l == 5.0


def test_calibration_is_shrunk_toward_one_on_a_thin_history(
    api_client: TestClient,
) -> None:
    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        for index in range(60):
            at = NOW - timedelta(days=5) + timedelta(minutes=30 * index)
            _run(
                session,
                owner_id,
                anchor_at=at,
                anchor_value=7.0,
                predicted=6.0,
                actual=5.0,
            )
        _run(session, owner_id, anchor_at=NOW, anchor_value=7.0, predicted=6.0)
        session.commit()

    with factory() as session:
        projection = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert projection.calibration_samples == 60
    # 60 of the 200 needed for full strength: 1 + 0.125 * (2 - 1).
    assert 1.0 < projection.calibration_factor < 1.2


def test_projection_never_reads_another_users_forecast(
    api_client: TestClient,
) -> None:
    from glucotracker.domain.auth import UserRole
    from glucotracker.infra.db.models import User
    from glucotracker.infra.security import hash_password

    owner_id = _owner(api_client)
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        other = User(
            username=f"projection-other-{uuid4().hex}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        _run(session, other.id, anchor_at=NOW, anchor_value=7.0, predicted=3.0)
        session.commit()

    with factory() as session:
        projection = GlucoseTrendProjectionService(session, owner_id).project(NOW)

    assert projection.status == "no_forecast"
