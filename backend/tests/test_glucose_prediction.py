"""Personal glucose prediction API and feature-alignment tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import sin
from uuid import UUID

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import select

from glucotracker.application.glucose_prediction import (
    FEATURE_NAMES,
    _chronological_day_splits,
    _post_meal_validation_metrics,
    _select_shape_blend,
    _shape_features,
)
from glucotracker.infra.db.models import (
    GlucosePredictionPointAudit,
    GlucosePredictionRun,
    HealthConnectRecord,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)


def _seed_glucose_history(api_client: TestClient, count: int) -> datetime:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    start = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    with session_factory() as session:
        for index in range(count):
            timestamp = start + timedelta(minutes=index * 5)
            value = 6.0 + 0.8 * sin(index / 18) + 0.2 * sin(index / 5)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"prediction-cgm-{index}",
                    timestamp=timestamp,
                    value_mmol_l=value,
                )
            )
        session.commit()
    return start + timedelta(minutes=(count - 1) * 5)


def test_prediction_uses_history_and_payload_corrected_health_context(
    api_client: TestClient,
) -> None:
    anchor = _seed_glucose_history(api_client, 1200)
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    heart_rate_at = anchor - timedelta(minutes=4)
    with session_factory() as session:
        session.add(
            Meal(
                owner_id=owner_id,
                eaten_at=(anchor - timedelta(minutes=30)).replace(tzinfo=None),
                status="accepted",
                source="manual",
                total_carbs_g=24,
                total_protein_g=0,
                total_fat_g=0,
                total_fiber_g=0,
                total_kcal=96,
            )
        )
        session.add(
            NightscoutInsulinEvent(
                owner_id=owner_id,
                source_key="prediction-insulin",
                timestamp=anchor - timedelta(minutes=25),
                insulin_units=2.5,
                event_type="Insulin",
            )
        )
        session.add(
            HealthConnectRecord(
                owner_id=owner_id,
                record_id="prediction-heart-rate",
                record_type="HeartRateRecord",
                # Reproduce the imported double-zone-offset index defect.
                start_time=heart_rate_at + timedelta(hours=8),
                end_time=heart_rate_at + timedelta(hours=8, minutes=1),
                payload={
                    "startTime": heart_rate_at.isoformat(),
                    "endTime": (heart_rate_at + timedelta(minutes=1)).isoformat(),
                    "samples": [
                        {
                            "time": heart_rate_at.isoformat(),
                            "beatsPerMinute": 92,
                        }
                    ],
                },
            )
        )
        session.commit()

    response = api_client.get(
        "/glucose/prediction",
        params={"mode": "raw", "horizon_minutes": 90, "step_minutes": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["points"]) == 18
    assert payload["points"][-1]["horizon_minutes"] == 90
    assert payload["model"]["sample_count"] >= 240
    assert (
        payload["model"]["version"]
        == "personal_known_input_shape_scenario_v4"
    )
    assert (
        payload["model"]["algorithm"]
        == "known_input_kinetic_shape_ensemble"
    )
    assert payload["model"]["forecast_assumption"] == "no_new_food_or_insulin"
    assert "cob_remaining_g" in payload["model"]["features_used"]
    assert "iob_remaining_units" in payload["model"]["features_used"]
    assert payload["model"]["feature_coverage"]["heart_rate"] is True
    assert payload["inputs"]["heart_rate_bpm"] == 92
    assert payload["inputs"]["carbs_g_4h"] == 24
    assert payload["inputs"]["insulin_units_5h"] == 2.5
    assert 0 < payload["inputs"]["cob_remaining_g"] < 24
    assert 0 < payload["inputs"]["carb_absorption_next_30m_g"] < 24
    assert 0 < payload["inputs"]["iob_remaining_units"] < 2.5
    assert 0 < payload["inputs"]["insulin_action_next_30m_units"] < 2.5
    assert all(2 <= point["display_value"] <= 22 for point in payload["points"])
    assert payload["raw_anchor_value"] is not None
    assert all(
        point["raw_ci_low"] <= point["raw_value"] <= point["raw_ci_high"]
        for point in payload["points"]
    )

    duplicate_response = api_client.get(
        "/glucose/prediction",
        params={"mode": "normalized", "horizon_minutes": 90, "step_minutes": 5},
    )
    assert duplicate_response.status_code == 200

    with session_factory() as session:
        runs = list(
            session.scalars(
                select(GlucosePredictionRun).where(
                    GlucosePredictionRun.owner_id == owner_id
                )
            )
        )
        points = list(
            session.scalars(
                select(GlucosePredictionPointAudit)
                .where(GlucosePredictionPointAudit.owner_id == owner_id)
                .order_by(GlucosePredictionPointAudit.horizon_minutes)
            )
        )

    assert len(runs) == 1
    assert len(points) == 18
    assert runs[0].anchor_value_mmol_l == payload["raw_anchor_value"]
    assert points[-1].predicted_value_mmol_l == payload["points"][-1]["raw_value"]
    assert points[-1].ci_low_mmol_l == payload["points"][-1]["raw_ci_low"]
    assert points[-1].ci_high_mmol_l == payload["points"][-1]["raw_ci_high"]


def test_no_new_input_scenario_preserves_a_current_downward_trend(
    api_client: TestClient,
) -> None:
    _seed_glucose_history(api_client, 1200)
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with session_factory() as session:
        recent = list(
            session.scalars(
                select(NightscoutGlucoseEntry)
                .where(NightscoutGlucoseEntry.owner_id == owner_id)
                .order_by(NightscoutGlucoseEntry.timestamp.desc())
                .limit(7)
            )
        )
        values = [4.4, 4.2, 4.0, 3.8, 3.6, 3.4, 3.2]
        for row, value in zip(reversed(recent), values, strict=True):
            row.value_mmol_l = value
        session.commit()

    response = api_client.get(
        "/glucose/prediction",
        params={"mode": "raw", "horizon_minutes": 90, "step_minutes": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_anchor_value"] == 3.2
    assert payload["points"][5]["raw_value"] < 3.2
    assert payload["points"][-1]["raw_value"] <= payload["points"][5]["raw_value"]
    assert any("не добавляются еда или инсулин" in note for note in payload["notes"])


def test_prediction_returns_provenance_when_history_is_insufficient(
    api_client: TestClient,
) -> None:
    _seed_glucose_history(api_client, 30)

    response = api_client.get("/glucose/prediction", params={"mode": "normalized"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["points"] == []
    assert payload["model"]["confidence"] == "none"
    assert payload["model"]["sample_count"] < 240
    assert any("Недостаточно" in note for note in payload["notes"])


def test_prediction_query_bounds_are_validated(api_client: TestClient) -> None:
    response = api_client.get(
        "/glucose/prediction",
        params={"horizon_minutes": 95, "step_minutes": 1},
    )

    assert response.status_code == 422


def test_prediction_validation_splits_are_day_disjoint_and_stable() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    row_times = [
        start + timedelta(days=day, minutes=15 * point)
        for day in range(30)
        for point in range(20)
    ]

    train_end, calibration_end = _chronological_day_splits(row_times)
    extended_train_end, extended_calibration_end = _chronological_day_splits(
        [*row_times, row_times[-1] + timedelta(minutes=15)]
    )

    assert row_times[train_end - 1].date() < row_times[train_end].date()
    assert (
        row_times[calibration_end - 1].date()
        < row_times[calibration_end].date()
    )
    assert (train_end, calibration_end) == (
        extended_train_end,
        extended_calibration_end,
    )


def test_shape_model_cannot_use_absolute_glucose_for_mean_reversion() -> None:
    features = np.zeros((2, len(FEATURE_NAMES)), dtype=float)
    features[:, FEATURE_NAMES.index("glucose_now")] = [3.0, 14.0]
    features[:, FEATURE_NAMES.index("glucose_mean_30m")] = [3.2, 13.8]
    features[:, FEATURE_NAMES.index("glucose_mean_60m")] = [3.4, 13.5]

    shape = _shape_features(features)

    np.testing.assert_array_equal(shape[0], shape[1])


def test_shape_blend_prefers_more_shape_when_scores_are_effectively_tied() -> None:
    kinetic = np.zeros((4, 3), dtype=float)
    shape = np.zeros((4, 3), dtype=float)
    targets = np.zeros((4, 3), dtype=float)
    eligibility = np.ones((4, 3), dtype=bool)

    assert _select_shape_blend(kinetic, shape, targets, eligibility) == 0.75


def test_post_meal_metrics_only_use_recent_carb_windows() -> None:
    features = np.zeros((3, len(FEATURE_NAMES)), dtype=float)
    features[:2, FEATURE_NAMES.index("carbs_120m")] = [20, 35]
    targets = np.zeros((3, 18), dtype=float)
    predictions = np.zeros((3, 18), dtype=float)
    targets[0, [5, 11, 17]] = [1, 2, 3]
    targets[1, [5, 11, 17]] = [-1, -2, -1]
    targets[2, [5, 11, 17]] = [20, 20, 20]

    metrics = _post_meal_validation_metrics(features, targets, predictions)

    assert metrics == {
        "count": 2,
        "mae_30": 1.0,
        "mae_60": 2.0,
        "mae_90": 2.0,
        "baseline_mae_90": 2.0,
    }
