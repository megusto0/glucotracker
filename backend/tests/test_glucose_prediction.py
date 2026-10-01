"""Personal glucose prediction API and feature-alignment tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import sin
from uuid import UUID

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from glucotracker.application.glucose_prediction import MODEL_ALGORITHM, MODEL_VERSION
from glucotracker.application.glucose_prediction_experimental import (
    FEATURE_NAMES,
    _chronological_day_splits,
    _fit_audit_calibration,
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
from glucotracker.infra.db.repositories.glucose_prediction_audit import (
    EvaluatedForecastPoint,
)


def _seed_glucose_history(api_client: TestClient, count: int) -> datetime:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    start = datetime.now(UTC) - timedelta(minutes=5 * (count - 1))
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


@pytest.mark.parametrize("experimental", [False, True])
def test_prediction_uses_history_and_payload_corrected_health_context(
    api_client: TestClient,
    monkeypatch,
    experimental,
) -> None:
    from glucotracker.application.glucose_prediction_runtime import selected_predictor
    from glucotracker.config import get_settings

    monkeypatch.setenv(
        "GLUCOTRACKER_EXPERIMENTAL_GLUCOSE_PREDICTION_ENABLED", str(experimental)
    )
    get_settings.cache_clear()
    prediction = selected_predictor()
    anchor = _seed_glucose_history(api_client, 1800)
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

    from glucotracker.workers.glucose_prediction import GlucosePredictionWorker

    GlucosePredictionWorker(session_factory).run_once()
    response = api_client.get(
        "/glucose/prediction",
        params={"mode": "raw", "horizon_minutes": 90, "step_minutes": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["points"]) == 18
    assert payload["points"][-1]["horizon_minutes"] == 90
    assert payload["model"]["sample_count"] >= 240
    assert payload["model"]["version"] == prediction.MODEL_VERSION
    assert payload["model"]["algorithm"] == prediction.MODEL_ALGORITHM
    assert payload["model"]["version"].endswith("_v9" if experimental else "_v8")
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
    calibration_90 = payload["model"]["audit_calibration_by_horizon"][-1]
    assert calibration_90["horizon_minutes"] == 90
    assert (
        calibration_90["base_prediction_mmol_l"] == payload["points"][-1]["raw_value"]
    )
    assert calibration_90["sample_count"] == 0

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


def test_audit_calibration_shrinks_bad_long_horizon_toward_persistence() -> None:
    start = datetime(2026, 7, 20, tzinfo=UTC)
    samples = [
        EvaluatedForecastPoint(
            anchor_timestamp=start + timedelta(minutes=30 * index),
            anchor_value_mmol_l=6.0,
            horizon_minutes=90,
            base_predicted_value_mmol_l=4.0,
            actual_value_mmol_l=6.0,
        )
        for index in range(240)
    ]

    calibration = _fit_audit_calibration(samples, [30, 90])

    assert calibration[30].sample_count == 0
    assert calibration[30].weight == 1.0
    assert calibration[90].sample_count == 240
    assert calibration[90].weight < 1.0
    adjusted = (
        6.0 + calibration[90].weight * (4.0 - 6.0) + calibration[90].correction_mmol_l
    )
    assert abs(6.0 - adjusted) < abs(6.0 - 4.0)
    assert calibration[90].calibrated_mae_mmol_l is not None
    assert calibration[90].calibrated_mae_mmol_l < calibration[90].base_mae_mmol_l


def test_no_new_input_scenario_preserves_a_current_downward_trend(
    api_client: TestClient,
) -> None:
    _seed_glucose_history(api_client, 1800)
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

    from glucotracker.workers.glucose_prediction import GlucosePredictionWorker

    GlucosePredictionWorker(session_factory).run_once()
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
    assert any("в фоне" in note for note in payload["notes"])


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
    assert row_times[calibration_end - 1].date() < row_times[calibration_end].date()
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


def test_purge_respects_horizon_and_cgm_matching_tolerance() -> None:
    from glucotracker.application.glucose_prediction_experimental import (
        _purge_overlapping_targets,
    )

    start = datetime(2026, 7, 1, tzinfo=UTC)
    times = [start + timedelta(minutes=15 * i) for i in range(30)]
    eligible = np.ones((30, 2), dtype=bool)
    purged = _purge_overlapping_targets(times, [15, 90], eligible, (10, 20))
    assert eligible.all()  # The input array is not mutated.
    for boundary in (10, 20):
        for row in range(boundary):
            for column, horizon in enumerate((15, 90)):
                if purged[row, column]:
                    assert times[row] + timedelta(minutes=horizon + 8) < times[boundary]
    assert purged[8, 0] and not purged[8, 1]
    assert not purged[9].any()
    assert purged[20:].all()


def test_delayed_health_sample_is_not_backfilled_into_training() -> None:
    from glucotracker.application.glucose_prediction_experimental import _health_series

    event = datetime(2026, 7, 1, 10, tzinfo=UTC)
    imported = event + timedelta(days=1)
    record = HealthConnectRecord(
        record_type="HeartRateRecord",
        record_id="late-heart-rate",
        created_at=imported,
        updated_at=imported,
        payload={"samples": [{"time": event.isoformat(), "beatsPerMinute": 110}]},
    )
    heart, *_ = _health_series([record])
    assert heart.latest(event, 15) is None
    assert heart.window_mean(event, 30) is None
    # Once imported it can be examined retrospectively, but it is not fresh now.
    assert heart.latest(event, 15, known_at=imported) == 110
    assert heart.latest(imported, 15) is None


def test_calibration_rejects_correction_that_fails_on_later_days() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    samples = [
        EvaluatedForecastPoint(
            anchor_timestamp=start + timedelta(days=day, minutes=15 * i),
            anchor_value_mmol_l=6,
            horizon_minutes=90,
            base_predicted_value_mmol_l=4,
            actual_value_mmol_l=6 if day < 3 else 4,
        )
        for day in range(5)
        for i in range(40)
    ]
    result = _fit_audit_calibration(samples, [90])[90]
    assert result.weight == 1
    assert result.correction_mmol_l == 0


def test_many_correlated_points_in_one_day_cannot_enable_calibration() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    samples = [
        EvaluatedForecastPoint(
            anchor_timestamp=start + timedelta(minutes=i),
            anchor_value_mmol_l=6,
            horizon_minutes=90,
            base_predicted_value_mmol_l=4,
            actual_value_mmol_l=6,
        )
        for i in range(500)
    ]
    assert _fit_audit_calibration(samples, [90])[90].weight == 1


def _feature_test_context():
    from glucotracker.application.glucose_prediction_experimental import (
        POPULATION_INSULIN_KERNEL_V2,
        _FeatureContext,
        _GlucoseSample,
        _Series,
    )

    at = datetime(2026, 7, 1, 12, tzinfo=UTC)
    glucose = [
        _GlucoseSample(at - timedelta(minutes=5 * i), 6 + 0.01 * i, raw=6 + 0.01 * i)
        for i in reversed(range(19))
    ]
    return _FeatureContext(
        glucose,
        [p.timestamp for p in glucose],
        _Series([]),
        _Series([]),
        [],
        [],
        [],
        [],
        POPULATION_INSULIN_KERNEL_V2,
        _Series([]),
        _Series([]),
        _Series([]),
        [],
        [],
        60,
    ), at


def test_absent_health_context_differs_from_observed_rest():
    from dataclasses import replace

    from glucotracker.application.glucose_prediction_experimental import (
        _features_at,
        _Series,
    )

    context, at = _feature_test_context()
    missing, missing_coverage = _features_at(context, at)
    observed, observed_coverage = _features_at(
        replace(
            context,
            heart_rate=_Series([(at, 60)]),
            active_kcal=_Series([(at, 0)]),
        ),
        at,
    )
    assert not missing_coverage["health"]
    assert observed_coverage["heart_rate"] and observed_coverage["activity"]
    for feature in ["heart_rate_available", "activity_available"]:
        assert missing[FEATURE_NAMES.index(feature)] == 0
        assert observed[FEATURE_NAMES.index(feature)] == 1


def test_later_sensor_calibration_does_not_rewrite_shape_features():
    from dataclasses import replace

    from glucotracker.application.glucose_prediction_experimental import _features_at

    context, at = _feature_test_context()
    before, _ = _features_at(context, at)
    changed = replace(
        context,
        glucose=[
            replace(p, value=p.value + 1 + i * 0.1)
            for i, p in enumerate(context.glucose)
        ],
    )
    after, _ = _features_at(changed, at)
    np.testing.assert_array_equal(
        _shape_features(np.asarray([before])), _shape_features(np.asarray([after]))
    )


def test_worker_skips_unchanged_anchor_without_training(api_client, monkeypatch):
    from glucotracker.application.glucose_prediction import GlucosePredictionService
    from glucotracker.infra.db.models import GlucosePredictionRun
    from glucotracker.workers.glucose_prediction import GlucosePredictionWorker

    anchor = _seed_glucose_history(api_client, 2)
    factory = api_client.app_state["session_factory"]
    owner = UUID(str(api_client.app_state["current_user_id"]))
    with factory() as session:
        session.add(
            GlucosePredictionRun(
                owner_id=owner,
                anchor_timestamp=anchor,
                generated_at=anchor,
                anchor_value_mmol_l=6,
                model_version=MODEL_VERSION,
                algorithm=MODEL_ALGORITHM,
                horizon_minutes=90,
                step_minutes=5,
                model_json={},
                inputs_json={},
                notes_json=[],
            )
        )
        session.commit()

    def forbidden(*args, **kwargs):
        raise AssertionError("The same anchor must not be recalculated")

    monkeypatch.setattr(GlucosePredictionService, "predict", forbidden)
    assert GlucosePredictionWorker(factory).run_once() == 0
