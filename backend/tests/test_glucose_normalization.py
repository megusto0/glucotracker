"""Shared CGM normalization used by every model that learns from glucose."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.application.glucose_dashboard import _local_wall_from_utc
from glucotracker.application.glucose_normalization import (
    GlucoseNormalizationService,
)
from glucotracker.application.postprandial.analyzer import (
    compute_pre_meal_state,
    detect_hypo_recovery,
)
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import (
    MealSource,
    MealStatus,
    PreMealState,
    TasteProfile,
)
from glucotracker.infra.db.models import (
    FingerstickReading,
    Meal,
    NightscoutGlucoseEntry,
    SensorSession,
    User,
)
from glucotracker.infra.security import hash_password

SENSOR_START = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)


def _local(value: datetime) -> str:
    """Render a UTC instant the way the dashboard reports local wall time."""
    return _local_wall_from_utc(value).strftime("%Y-%m-%dT%H:%M:%S")


def _entries(owner_id: UUID, start: datetime, values: list[float], prefix: str):
    return [
        NightscoutGlucoseEntry(
            owner_id=owner_id,
            source_key=f"{prefix}-{index}",
            timestamp=start + timedelta(minutes=5 * index),
            value_mmol_l=value,
            value_mg_dl=round(value * 18.0182),
            source="CGM",
        )
        for index, value in enumerate(values)
    ]


def _stable_fingersticks(owner_id: UUID, start: datetime, offset: float, count: int):
    """Fingersticks past the 48 h stability gate, each ``offset`` above raw."""
    return [
        FingerstickReading(
            owner_id=owner_id,
            measured_at=start + timedelta(hours=50 + 6 * index),
            glucose_mmol_l=5.0 + offset,
        )
        for index in range(count)
    ]


def test_series_applies_fingerstick_bias_to_raw_values(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add(SensorSession(owner_id=owner_id, started_at=SENSOR_START))
        # A flat raw 5.0 series so every fingerstick residual is exactly +1.5.
        session.add_all(
            _entries(
                owner_id,
                SENSOR_START + timedelta(hours=49),
                [5.0] * 24,
                "flat",
            )
        )
        session.add_all(_stable_fingersticks(owner_id, SENSOR_START, 1.5, 4))
        session.commit()

    with session_factory() as session:
        samples = GlucoseNormalizationService(session, owner_id).series(
            SENSOR_START,
            SENSOR_START + timedelta(days=5),
        )

    assert samples
    assert all(sample.raw_mmol_l == 5.0 for sample in samples)
    assert all(sample.is_normalized for sample in samples)
    assert all(abs(sample.normalized_mmol_l - 6.5) < 0.01 for sample in samples)
    assert all(
        sample.bias_confidence in {"low", "medium", "high"} for sample in samples
    )


def test_fingerstick_is_matched_to_the_cgm_point_at_the_same_instant(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fingerstick and the CGM series share one UTC convention.

    Runs under a non-UTC app timezone on purpose: with UTC every conversion
    helper agrees, so the rest of the suite cannot see a mismatch between the
    fingerstick and CGM paths. The ramp turns any hour offset into a large
    residual instead of a silent one.
    """
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "Europe/Samara")
    get_settings.cache_clear()
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    ramp_start = SENSOR_START + timedelta(hours=48)
    # 5.0 rising by 0.1 every 5 minutes over 12 hours.
    values = [5.0 + 0.1 * index for index in range(144)]
    with session_factory() as session:
        session.add(SensorSession(owner_id=owner_id, started_at=SENSOR_START))
        session.add_all(_entries(owner_id, ramp_start, values, "ramp"))
        # Taken 6 h into the ramp, where raw reads 5.0 + 0.1 * 72 = 12.2.
        session.add(
            FingerstickReading(
                owner_id=owner_id,
                measured_at=ramp_start + timedelta(hours=6),
                glucose_mmol_l=13.2,
            )
        )
        session.commit()

    with session_factory() as session:
        samples = GlucoseNormalizationService(session, owner_id).series(
            SENSOR_START,
            SENSOR_START + timedelta(days=5),
        )

    assert samples
    # Correct alignment gives a +1.0 residual. Any hour offset against a ramp
    # of 1.2 mmol/L per hour would show up here as a much larger bias.
    assert all(abs(sample.bias_mmol_l - 1.0) < 0.2 for sample in samples)


def test_series_bias_matches_dashboard_normalization(
    api_client: TestClient,
) -> None:
    """The shared series must agree with what the dashboard displays."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add(SensorSession(owner_id=owner_id, started_at=SENSOR_START))
        session.add_all(
            _entries(
                owner_id,
                SENSOR_START + timedelta(hours=49),
                [5.0 + 0.05 * i for i in range(36)],
                "agree",
            )
        )
        session.add_all(_stable_fingersticks(owner_id, SENSOR_START, 1.5, 4))
        session.commit()

    with session_factory() as session:
        samples = GlucoseNormalizationService(session, owner_id).series(
            SENSOR_START,
            SENSOR_START + timedelta(days=5),
        )
    dashboard = api_client.get(
        "/glucose/dashboard",
        params={
            "from": (SENSOR_START + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S"),
            "to": (SENSOR_START + timedelta(hours=56)).strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "normalized",
        },
    )

    assert dashboard.status_code == 200
    shown = {
        point["timestamp"]: point["normalized_value"]
        for point in dashboard.json()["points"]
        if point["normalized_value"] is not None
    }
    assert shown
    by_local = {
        _local(sample.timestamp): sample.normalized_mmol_l for sample in samples
    }
    compared = 0
    for timestamp, value in shown.items():
        if timestamp in by_local:
            assert abs(by_local[timestamp] - value) < 0.02
            compared += 1
    assert compared >= 5


def test_series_calibrates_each_sensor_session_separately(
    api_client: TestClient,
) -> None:
    """Two sensors with different bias must not share one correction."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    second_start = SENSOR_START + timedelta(days=10)
    with session_factory() as session:
        session.add_all(
            [
                SensorSession(
                    owner_id=owner_id,
                    started_at=SENSOR_START,
                    ended_at=second_start - timedelta(hours=1),
                ),
                SensorSession(owner_id=owner_id, started_at=second_start),
            ]
        )
        session.add_all(
            _entries(
                owner_id,
                SENSOR_START + timedelta(hours=49),
                [5.0] * 12,
                "first",
            )
        )
        session.add_all(
            _entries(
                owner_id,
                second_start + timedelta(hours=49),
                [5.0] * 12,
                "second",
            )
        )
        session.add_all(_stable_fingersticks(owner_id, SENSOR_START, 1.0, 4))
        session.add_all(_stable_fingersticks(owner_id, second_start, 2.5, 4))
        session.commit()

    with session_factory() as session:
        samples = GlucoseNormalizationService(session, owner_id).series(
            SENSOR_START,
            second_start + timedelta(days=5),
        )

    first = [s for s in samples if s.timestamp < second_start]
    second = [s for s in samples if s.timestamp >= second_start]
    assert first and second
    assert all(abs(s.normalized_mmol_l - 6.0) < 0.01 for s in first)
    assert all(abs(s.normalized_mmol_l - 7.5) < 0.01 for s in second)
    assert {s.sensor_session_id for s in first} != {s.sensor_session_id for s in second}


def test_series_reports_sensor_age_and_falls_back_without_fingersticks(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add(SensorSession(owner_id=owner_id, started_at=SENSOR_START))
        session.add_all(
            _entries(owner_id, SENSOR_START + timedelta(days=2), [6.0] * 6, "bare")
        )
        session.commit()

    with session_factory() as session:
        samples = GlucoseNormalizationService(session, owner_id).series(
            SENSOR_START,
            SENSOR_START + timedelta(days=5),
        )

    assert samples
    # No fingersticks: values stay raw and are flagged as uncalibrated.
    assert all(sample.normalized_mmol_l == sample.raw_mmol_l for sample in samples)
    assert all(not sample.is_normalized for sample in samples)
    assert all(sample.bias_confidence == "none" for sample in samples)
    assert samples[0].sensor_age_days is not None
    assert 1.9 < samples[0].sensor_age_days < 2.1


def test_series_excludes_corrupt_sensor_intervals(api_client: TestClient) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add(
            SensorSession(
                owner_id=owner_id,
                started_at=SENSOR_START,
                ended_at=SENSOR_START + timedelta(hours=6),
                excluded_from_analytics=True,
                exclusion_reason="corrupt",
            )
        )
        session.add_all(
            _entries(owner_id, SENSOR_START + timedelta(hours=1), [21.0] * 4, "corrupt")
        )
        session.add_all(
            _entries(owner_id, SENSOR_START + timedelta(hours=8), [6.0] * 4, "clean")
        )
        session.commit()

    with session_factory() as session:
        samples = GlucoseNormalizationService(session, owner_id).series(
            SENSOR_START,
            SENSOR_START + timedelta(days=1),
        )

    assert [sample.raw_mmol_l for sample in samples] == [6.0] * 4


def test_series_never_reads_another_users_glucose(api_client: TestClient) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        other = User(
            username=f"normalization-other-{uuid4().hex}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        session.add_all(_entries(owner_id, SENSOR_START, [6.0] * 3, "mine"))
        session.add_all(_entries(other.id, SENSOR_START, [12.0] * 3, "theirs"))
        session.commit()

    with session_factory() as session:
        samples = GlucoseNormalizationService(session, owner_id).series(
            SENSOR_START,
            SENSOR_START + timedelta(days=1),
        )

    assert [sample.raw_mmol_l for sample in samples] == [6.0] * 3


def test_postprandial_hypo_recovery_reads_the_calibrated_value(
    api_client: TestClient,
) -> None:
    """A sweet drink at a calibrated 5.5 is a snack, not hypo treatment.

    The postprandial analyzer used to compare the stored sensor number against
    4.0. On this owner's stream that number runs well under true glucose, so an
    ordinary drink arrived as a raw 3.2, was recorded as `is_hypo_recovery`, and
    was then dropped from the IOB/COB fits as a hypo outlier — a mislabel that
    removed real training data. It now reads the same calibrated series the
    dashboard and the episode classifier read.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    eaten_at = _local_wall_from_utc(SENSOR_START + timedelta(hours=52))

    with session_factory() as session:
        session.add(SensorSession(owner_id=owner_id, started_at=SENSOR_START))
        session.add_all(
            _entries(
                owner_id,
                SENSOR_START + timedelta(hours=49),
                [3.2] * 60,
                "flat-low-raw",
            )
        )
        # Every fingerstick lands 2.3 above the flat raw 3.2, so the calibrated
        # series sits at 5.5 — comfortably in range.
        session.add_all(
            [
                FingerstickReading(
                    owner_id=owner_id,
                    measured_at=SENSOR_START + timedelta(hours=50 + 6 * index),
                    glucose_mmol_l=5.5,
                )
                for index in range(4)
            ]
        )
        drink = Meal(
            owner_id=owner_id,
            title="Сок яблочный",
            eaten_at=eaten_at,
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_kcal=90,
            total_carbs_g=20,
            total_protein_g=0,
            total_fat_g=0,
            ai_categories={"taste_profile": TasteProfile.drink_sweet.value},
            derived_categories={"meal_role": "drink"},
        )
        session.add(drink)
        session.commit()
        meal_id = drink.id

    with session_factory() as session:
        meal = session.get(Meal, meal_id)
        assert meal is not None
        state, _ = compute_pre_meal_state(session, meal)
        assert state == PreMealState.in_range
        assert detect_hypo_recovery(meal, state) is False
