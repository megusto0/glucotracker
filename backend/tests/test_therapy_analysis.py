"""Long-term retrospective ICR/ISF analysis API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    FingerstickReading,
    HealthConnectRecord,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    SensorSession,
    User,
)
from glucotracker.infra.db.repositories.twin import TwinRepository
from glucotracker.infra.security import hash_password


def _meal(session, owner_id, at: datetime, carbs: float, title: str) -> None:
    session.add(
        Meal(
            owner_id=owner_id,
            eaten_at=at,
            title=title,
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=carbs,
            total_protein_g=4,
            total_fat_g=4,
            total_kcal=carbs * 5,
        )
    )


def _insulin(
    session,
    owner_id,
    at: datetime,
    units: float,
    *,
    correction: bool = True,
) -> None:
    key = f"analysis-insulin-{uuid4()}"
    session.add(
        NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key=key,
            nightscout_id=key,
            timestamp=at,
            insulin_units=units,
            event_type="Correction Bolus" if correction else "Insulin",
            entered_by="test",
        )
    )


def _glucose(session, owner_id, at: datetime, value: float) -> None:
    session.add(
        NightscoutGlucoseEntry(
            owner_id=owner_id,
            source_key=f"analysis-cgm-{uuid4()}",
            timestamp=at,
            value_mmol_l=value,
            value_mg_dl=round(value * 18.0182),
            source="CGM",
        )
    )


def _heart_rate(
    session,
    owner_id,
    at: datetime,
    values: list[float],
    *,
    record_id: str,
) -> None:
    samples = [
        {
            "time": utc_instant_from_local_wall(
                at + timedelta(minutes=index * 20 + 5)
            ).isoformat(),
            "beatsPerMinute": value,
        }
        for index, value in enumerate(values)
    ]
    start_utc = utc_instant_from_local_wall(at)
    session.add(
        HealthConnectRecord(
            owner_id=owner_id,
            record_id=record_id,
            record_type="HeartRateRecord",
            start_time=start_utc,
            end_time=start_utc + timedelta(hours=1),
            payload={"samples": samples},
        )
    )


def test_analysis_reports_time_slots_and_isolates_owner_data(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 31, 12)
    monkeypatch.setattr(
        "glucotracker.application.therapy_analysis.local_now",
        lambda: now,
    )
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 10)
    meal_at = day + timedelta(hours=10)
    correction_at = day + timedelta(hours=18)

    with session_factory() as session:
        session.add(
            SensorSession(
                owner_id=owner_id,
                started_at=utc_instant_from_local_wall(datetime(2026, 7, 1)),
            )
        )
        _meal(session, owner_id, meal_at, 40, "Чистый завтрак")
        _insulin(session, owner_id, meal_at, 4, correction=False)
        _glucose(session, owner_id, meal_at, 6.0)
        _glucose(session, owner_id, meal_at + timedelta(hours=2), 6.0)
        session.add(
            FingerstickReading(
                owner_id=owner_id,
                measured_at=utc_instant_from_local_wall(meal_at),
                glucose_mmol_l=6.0,
            )
        )

        _insulin(session, owner_id, correction_at, 1)
        _glucose(session, owner_id, correction_at, 9.0)
        _glucose(
            session,
            owner_id,
            correction_at + timedelta(hours=4),
            6.5,
        )
        for offset, end_value in enumerate((6.2, 6.1, 6.3), start=1):
            background_at = datetime(2026, 7, 14 + offset, 2)
            _glucose(session, owner_id, background_at, 6.0)
            _glucose(
                session,
                owner_id,
                background_at + timedelta(hours=1),
                end_value,
            )
            _heart_rate(
                session,
                owner_id,
                background_at,
                [56, 60, 62],
                record_id=f"quiet-{offset}",
            )

        active_at = datetime(2026, 7, 18, 14)
        _glucose(session, owner_id, active_at, 6.5)
        _glucose(session, owner_id, active_at + timedelta(hours=1), 5.5)
        _heart_rate(
            session,
            owner_id,
            active_at,
            [105, 112, 109],
            record_id="active-owner",
        )

        other = User(
            username="therapy-analysis-other",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        _meal(session, other.id, meal_at, 100, "Чужая еда")
        _insulin(session, other.id, meal_at, 1, correction=False)
        _glucose(session, other.id, meal_at, 6.0)
        _glucose(session, other.id, meal_at + timedelta(hours=2), 6.0)
        _insulin(session, other.id, correction_at, 1)
        _glucose(session, other.id, correction_at, 12.0)
        _glucose(
            session,
            other.id,
            correction_at + timedelta(hours=4),
            4.0,
        )
        other_background = datetime(2026, 7, 15, 2)
        _glucose(session, other.id, other_background, 5.0)
        _glucose(
            session,
            other.id,
            other_background + timedelta(hours=1),
            12.0,
        )
        _heart_rate(
            session,
            other.id,
            other_background,
            [180, 180, 180],
            record_id="other-heart-rate",
        )
        session.commit()

    response = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 30, "target_mmol_l": 6},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["from_date"] == "2026-07-02"
    assert body["to_date"] == "2026-07-31"
    assert body["period_days"] == 30
    assert body["icr_horizon_minutes"] == 120
    # 4.5 h, not 4: insulin action is ~90% done by 244 min, so the old window
    # cut the correction evidence short (ADR-019 §2.4).
    assert body["isf_horizon_minutes"] == 270
    assert body["bin_hours"] == 4
    assert body["model_version"].startswith("retrospective-therapy-analysis-v7")
    assert body["overall_icr_g_per_unit"] == {
        "value": 10.0,
        "q1": 10.0,
        "q3": 10.0,
        "sample_count": 1,
        "confidence": "low",
    }
    assert body["overall_isf_mmol_l_per_unit"] == {
        "value": 2.5,
        "q1": 2.5,
        "q3": 2.5,
        "sample_count": 1,
        "confidence": "low",
    }
    assert body["isf_source"] == "correction_episodes"
    slots = {slot["label"]: slot for slot in body["slots"]}
    assert slots["08:00–12:00"]["icr_g_per_unit"]["value"] == 10.0
    assert slots["16:00–20:00"]["isf_mmol_l_per_unit"]["value"] == 2.5
    assert sum(slot["icr_g_per_unit"]["sample_count"] for slot in body["slots"]) == 1
    assert (
        sum(slot["isf_mmol_l_per_unit"]["sample_count"] for slot in body["slots"]) == 1
    )
    basal = body["basal_profile"]
    assert basal["window_minutes"] == 60
    assert basal["washout_minutes"] == 240
    assert basal["resting_reference_bpm"] == 59.0
    assert basal["elevated_hr_threshold_bpm"] == 80.0
    assert basal["quiet_window_count"] == 3
    assert basal["elevated_hr_window_count"] == 1
    assert basal["unknown_hr_window_count"] == 0
    assert basal["autotune_isf_mmol_l_per_unit"] == 3.6
    assert basal["configured_daily_basal_units"] == 19.9
    assert basal["projected_daily_basal_units"] == 19.96
    assert basal["autotuned_hour_count"] == 1
    compressions = {
        compression["window_count"]: compression
        for compression in basal["compressions"]
    }
    assert set(compressions) == set(range(4, 25))
    four_windows = compressions[4]
    assert len(four_windows["slots"]) == 4
    assert four_windows["slots"][0]["start_hour"] == 0
    assert four_windows["slots"][-1]["end_hour"] == 24
    assert four_windows["projected_daily_basal_units"] == 19.96
    compressed_total = sum(
        (slot["end_hour"] - slot["start_hour"]) * slot["autotuned_basal_u_per_hour"]
        for slot in four_windows["slots"]
    )
    assert compressed_total == pytest.approx(19.96, abs=0.01)
    assert len(compressions[24]["slots"]) == 24
    basal_slots = {slot["label"]: slot for slot in basal["slots"]}
    assert basal_slots["02:00"]["quiet_drift_mmol_l_per_hour"] == {
        "value": 0.2,
        "q1": 0.15,
        "q3": 0.25,
        "sample_count": 3,
        "confidence": "low",
    }
    assert basal_slots["02:00"]["signal"] == "stable"
    assert basal_slots["02:00"]["configured_basal_u_per_hour"] == 0.8
    assert basal_slots["02:00"]["basal_adjustment_u_per_hour"] == 0.06
    assert basal_slots["02:00"]["autotuned_basal_u_per_hour"] == 0.86
    assert basal_slots["14:00"]["elevated_hr_drift_mmol_l_per_hour"]["value"] == -1.0
    assert basal_slots["14:00"]["quiet_drift_mmol_l_per_hour"]["sample_count"] == 0


def test_basal_autotune_never_falls_back_to_raw_cgm(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw values may exist, but without normalization they are not evidence."""
    monkeypatch.setattr(
        "glucotracker.application.therapy_analysis.local_now",
        lambda: datetime(2026, 7, 31, 12),
    )
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        for offset in range(3):
            background_at = datetime(2026, 7, 10 + offset, 2)
            _glucose(session, owner_id, background_at, 6.0)
            _glucose(session, owner_id, background_at + timedelta(hours=1), 7.0)
            _heart_rate(
                session,
                owner_id,
                background_at,
                [55, 58, 60],
                record_id=f"raw-only-{offset}",
            )
        session.commit()

    body = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 30, "target_mmol_l": 6},
    ).json()

    basal = body["basal_profile"]
    assert basal["quiet_window_count"] == 0
    assert basal["autotuned_hour_count"] == 0
    slot = next(item for item in basal["slots"] if item["hour"] == 2)
    assert slot["quiet_drift_mmol_l_per_hour"]["value"] is None
    assert slot["autotuned_basal_u_per_hour"] is None


def test_isf_says_how_thin_its_evidence_is_next_to_a_solid_icr(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One isolated correction is not a measurement, and the page said nothing
    to distinguish it from the 76-episode ICR beside it."""
    monkeypatch.setattr(
        "glucotracker.application.therapy_analysis.local_now",
        lambda: datetime(2026, 7, 31, 12),
    )
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    correction_at = datetime(2026, 7, 10, 18)
    with session_factory() as session:
        _insulin(session, owner_id, correction_at, 1)
        _glucose(session, owner_id, correction_at, 9.0)
        _glucose(session, owner_id, correction_at + timedelta(hours=4), 6.5)
        session.commit()

    body = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 30, "target_mmol_l": 6},
    ).json()

    assert body["overall_isf_mmol_l_per_unit"]["sample_count"] == 1
    assert body["isf_identifiability"] == "thin"
    assert body["isf_correction_count"] == 1
    assert "только ICR" in body["isf_note"]
    # The median is auditable: the episode behind it is reported.
    assert len(body["isf_cases"]) == 1
    assert body["isf_cases"][0]["glucose_start"] == 9.0
    assert body["isf_cases"][0]["isf_mmol_l_per_unit"] == 2.5


def test_isf_measures_the_fall_a_correction_caused_not_the_rebound(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reported 2026-08-04: 1 U visibly took 11 to 7, but the page's range
    topped out at 3.26. It read glucose at exactly four hours, by which point
    insulin is ~90% finished and the curve has already turned back up."""
    monkeypatch.setattr(
        "glucotracker.application.therapy_analysis.local_now",
        lambda: datetime(2026, 7, 31, 12),
    )
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    correction_at = datetime(2026, 7, 10, 14)
    with session_factory() as session:
        _insulin(session, owner_id, correction_at, 1)
        # 11.0 down to 7.0 at +2h30, drifting back to 8.6 by the horizon.
        for minutes, value in (
            (0, 11.0),
            (60, 9.8),
            (120, 7.6),
            (150, 7.0),
            (210, 7.9),
            (240, 8.6),
        ):
            _glucose(
                session,
                owner_id,
                correction_at + timedelta(minutes=minutes),
                value,
            )
        session.commit()

    body = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 30, "target_mmol_l": 6},
    ).json()

    case = body["isf_cases"][0]
    assert case["glucose_start"] == 11.0
    assert case["glucose_nadir"] == 7.0
    assert case["minutes_to_nadir"] == 150
    # The endpoint is still reported, so the difference stays visible.
    assert case["glucose_at_horizon"] == 8.6
    # 4.0, not the 2.4 the four-hour reading would have produced.
    assert case["isf_mmol_l_per_unit"] == 4.0
    assert body["overall_isf_mmol_l_per_unit"]["value"] == 4.0


def test_measured_ratios_are_compared_against_the_configured_slots(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The four-hour table cannot answer "should I change my settings?"; its
    bins are not the bins the settings use."""
    monkeypatch.setattr(
        "glucotracker.application.therapy_analysis.local_now",
        lambda: datetime(2026, 7, 31, 12),
    )
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = 8.0
        params.icr_day = 9.3
        params.icr_evening = 10.0
        params.last_fit_method = "manual"
        # Eight clean day-slot meals, every one landing on target at 40 g for
        # 4 U, which implies 10.0 g/U against the configured 9.3.
        for index in range(8):
            meal_at = datetime(2026, 7, 5 + index, 13)
            _meal(session, owner_id, meal_at, 40, f"Обед {index}")
            _insulin(session, owner_id, meal_at, 4, correction=False)
            _glucose(session, owner_id, meal_at, 6.0)
            _glucose(session, owner_id, meal_at + timedelta(hours=2), 6.0)
        session.commit()

    body = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 30, "target_mmol_l": 6},
    ).json()

    by_daypart = {row["daypart"]: row for row in body["icr_proposals"]}
    assert set(by_daypart) == {"morning", "day", "evening"}
    day = by_daypart["day"]
    assert day["configured_icr_g_per_unit"] == 9.3
    assert day["measured_icr_g_per_unit"] == 10.0
    assert day["episode_count"] == 8
    # Shrunk toward the configured value rather than jumping to the measurement.
    assert 9.3 < day["proposed_icr_g_per_unit"] < 10.0
    # Slots without evidence say so instead of proposing from nothing.
    assert by_daypart["morning"]["proposed_icr_g_per_unit"] is None
    assert by_daypart["morning"]["confidence"] == "none"


def test_analysis_rejects_unsupported_period(api_client: TestClient) -> None:
    response = api_client.get(
        "/glucose/therapy-analysis",
        params={"period_days": 60},
    )

    assert response.status_code == 422
