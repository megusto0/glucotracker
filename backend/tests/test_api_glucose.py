"""Glucose dashboard, sensor, and fingerstick API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from glucotracker.infra.db.models import NightscoutGlucoseEntry


def _seed_cgm(
    api_client: TestClient,
    *,
    start: datetime,
    values: list[tuple[int, float]],
    prefix: str = "cgm",
) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add_all(
            [
                NightscoutGlucoseEntry(
                    source_key=f"{prefix}-{minutes}",
                    timestamp=start + timedelta(minutes=minutes),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
                for minutes, value in values
            ]
        )
        session.commit()


def _create_sensor(api_client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": "manual",
        "vendor": "Ottai",
        "model": "Ottai",
        "label": "Sensor A",
        "started_at": "2026-04-28T00:00:00",
        "expected_life_days": 15,
    }
    payload.update(overrides)
    response = api_client.post("/sensors", json=payload)
    assert response.status_code == 201
    return response.json()


def _create_fingerstick(
    api_client: TestClient,
    *,
    measured_at: str,
    value: float,
) -> dict[str, Any]:
    response = api_client.post(
        "/fingersticks",
        json={
            "measured_at": measured_at,
            "glucose_mmol_l": value,
            "meter_name": "Contour",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_sensor_and_fingerstick_crud(api_client: TestClient) -> None:
    """Sensor and fingerstick endpoints preserve local wall-clock timestamps."""
    sensor = _create_sensor(api_client)
    fingerstick = _create_fingerstick(
        api_client,
        measured_at="2026-04-28T08:10:00",
        value=7.2,
    )

    sensors_response = api_client.get("/sensors")
    fingersticks_response = api_client.get(
        "/fingersticks",
        params={
            "from": "2026-04-28T00:00:00",
            "to": "2026-04-28T23:59:59",
        },
    )

    assert sensors_response.status_code == 200
    assert sensors_response.json()[0]["id"] == sensor["id"]
    assert sensors_response.json()[0]["started_at"].startswith("2026-04-28T00:00:00")
    assert fingersticks_response.status_code == 200
    assert fingersticks_response.json()[0]["id"] == fingerstick["id"]
    assert fingersticks_response.json()[0]["measured_at"].startswith(
        "2026-04-28T08:10:00"
    )

    patch_response = api_client.patch(
        f"/fingersticks/{fingerstick['id']}",
        json={
            "measured_at": "2026-04-28T21:45:00",
            "glucose_mmol_l": 4.8,
            "meter_name": "Contour Next",
        },
    )

    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["id"] == fingerstick["id"]
    assert patched["measured_at"].startswith("2026-04-28T21:45:00")
    assert patched["glucose_mmol_l"] == 4.8
    assert patched["meter_name"] == "Contour Next"


def test_dashboard_normalizes_display_without_overwriting_raw_cgm(
    api_client: TestClient,
) -> None:
    """Normalized mode is derived display data; raw Nightscout rows stay intact."""
    start = datetime.fromisoformat("2026-04-28T08:00:00")
    _seed_cgm(
        api_client,
        start=start,
        values=[(0, 6.0), (10, 6.0), (20, 6.0), (60, 6.0), (70, 6.0), (80, 6.0)],
    )
    _create_sensor(api_client, started_at="2026-04-26T00:00:00")
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T08:10:00",
        value=7.0,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T09:10:00",
        value=7.0,
    )

    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": "2026-04-28T08:00:00",
            "to": "2026-04-28T09:30:00",
            "mode": "normalized",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "normalized"
    assert body["quality"]["valid_calibration_points"] == 2
    assert body["quality"]["confidence"] == "low"
    assert body["points"][0]["raw_value"] == 6.0
    assert body["points"][0]["normalized_value"] == 7.0
    assert body["points"][0]["display_value"] == 7.0

    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        raw_row = (
            session.query(NightscoutGlucoseEntry).filter_by(source_key="cgm-0").one()
        )
        assert raw_row.value_mmol_l == 6.0


def test_dashboard_smooths_normalized_series_when_available(
    api_client: TestClient,
) -> None:
    """Smoothed mode uses normalized values when calibration is available."""
    start = datetime.fromisoformat("2026-04-28T08:00:00")
    _seed_cgm(
        api_client,
        start=start,
        prefix="smooth",
        values=[
            (0, 6.0),
            (10, 6.0),
            (20, 6.0),
            (60, 6.0),
            (70, 6.0),
            (80, 6.0),
        ],
    )
    _create_sensor(api_client, started_at="2026-04-26T00:00:00")
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T08:10:00",
        value=7.0,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T09:10:00",
        value=7.0,
    )

    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": "2026-04-28T08:00:00",
            "to": "2026-04-28T09:30:00",
            "mode": "smoothed",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "smoothed"
    assert body["points"][0]["raw_value"] == 6.0
    assert body["points"][0]["normalized_value"] == 7.0
    assert body["points"][0]["smoothed_value"] == 7.0
    assert body["points"][0]["display_value"] == 7.0


def test_dashboard_models_warmup_separately_from_stable_calibration(
    api_client: TestClient,
) -> None:
    """First 12h residuals are reported but do not drive stable offset."""
    start = datetime.fromisoformat("2026-04-28T00:00:00")
    _seed_cgm(
        api_client,
        start=start,
        prefix="warmup",
        values=[
            (60, 6.0),
            (70, 6.0),
            (360, 6.0),
            (370, 6.0),
            (660, 6.0),
            (670, 6.0),
            (780, 6.0),
            (790, 6.0),
            (840, 6.0),
            (850, 6.0),
        ],
    )
    _create_sensor(api_client, started_at="2026-04-28T00:00:00")
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T01:05:00",
        value=6.1,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T06:05:00",
        value=9.0,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T11:05:00",
        value=6.7,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T13:05:00",
        value=7.0,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T14:05:00",
        value=7.0,
    )

    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": "2026-04-28T01:00:00",
            "to": "2026-04-28T15:00:00",
            "mode": "normalized",
        },
    )

    assert response.status_code == 200
    body = response.json()
    quality = body["quality"]
    assert quality["valid_calibration_points"] == 2
    assert quality["matched_calibration_points"] == 5
    assert quality["stable_calibration_points"] == 0
    assert quality["warmup_calibration_points"] == 5
    assert quality["calibration_basis"] == "warmup_after_12h_fallback"
    assert quality["confidence"] == "low"
    assert quality["warmup_metrics"]["initial_residual_mmol_l"] == 0.1
    assert quality["warmup_metrics"]["max_warmup_residual_mmol_l"] == 3.0
    assert quality["warmup_metrics"]["plateau_residual_mmol_l"] == 1.0
    assert quality["warmup_metrics"]["residual_sequence_mmol_l"] == [0.1, 3.0, 0.7]
    assert body["points"][0]["raw_value"] == 6.0
    assert body["points"][0]["normalized_value"] == 7.0


def test_dashboard_recomputes_b0_after_capping_drift(api_client: TestClient) -> None:
    """Capped drift is followed by a fresh intercept fit against the capped slope."""
    start = datetime.fromisoformat("2026-04-30T00:00:00")
    _seed_cgm(
        api_client,
        start=start,
        prefix="capped-drift",
        values=[
            (810, 6.0),
            (846, 6.0),
            (1174, 6.0),
            (1224, 6.0),
        ],
    )
    _create_sensor(api_client, started_at="2026-04-30T00:00:00")
    _create_fingerstick(api_client, measured_at="2026-04-30T13:30:00", value=6.77)
    _create_fingerstick(api_client, measured_at="2026-04-30T14:06:00", value=6.89)
    _create_fingerstick(api_client, measured_at="2026-04-30T19:34:00", value=7.10)

    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": "2026-04-30T13:00:00",
            "to": "2026-04-30T20:24:00",
            "mode": "normalized",
        },
    )

    assert response.status_code == 200
    body = response.json()
    quality = body["quality"]
    assert quality["b1_raw_mmol_l_per_day"] > 0.5
    assert quality["b1_capped_mmol_l_per_day"] == 0.5
    assert quality["b0_mmol_l"] == pytest.approx(0.596, abs=0.01)


def test_dashboard_warmup_blends_capped_linear_with_median_delta(
    api_client: TestClient,
) -> None:
    """Warmup normalization with 3 points is provisional and stays near the deltas."""
    start = datetime.fromisoformat("2026-04-30T00:00:00")
    _seed_cgm(
        api_client,
        start=start,
        prefix="warmup-blend",
        values=[
            (810, 6.0),
            (846, 6.0),
            (1174, 6.0),
            (1224, 6.0),
        ],
    )
    _create_sensor(api_client, started_at="2026-04-30T00:00:00")
    _create_fingerstick(api_client, measured_at="2026-04-30T13:30:00", value=6.77)
    _create_fingerstick(api_client, measured_at="2026-04-30T14:06:00", value=6.89)
    _create_fingerstick(api_client, measured_at="2026-04-30T19:34:00", value=7.10)

    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": "2026-04-30T13:00:00",
            "to": "2026-04-30T20:24:00",
            "mode": "normalized",
        },
    )

    assert response.status_code == 200
    body = response.json()
    quality = body["quality"]
    latest = body["points"][-1]
    assert quality["sensor_phase"] == "warmup"
    assert quality["calibration_strategy"] == "warmup_blend"
    assert quality["confidence"] == "low"
    assert quality["median_delta_mmol_l"] == pytest.approx(0.89, abs=0.01)
    assert quality["correction_now_mmol_l"] == pytest.approx(0.94, abs=0.02)
    assert latest["correction_mmol_l"] == pytest.approx(1.1, abs=0.02)
    assert abs(quality["correction_now_mmol_l"] - 0.89) < abs(0.619 - 0.89)


def test_dashboard_uses_median_delta_with_fewer_than_three_valid_points(
    api_client: TestClient,
) -> None:
    """One or two valid points create a provisional constant median-delta offset."""
    start = datetime.fromisoformat("2026-04-28T00:00:00")
    _seed_cgm(
        api_client,
        start=start,
        prefix="median-delta",
        values=[(780, 6.0), (840, 6.0), (900, 6.0)],
    )
    _create_sensor(api_client, started_at="2026-04-28T00:00:00")
    _create_fingerstick(api_client, measured_at="2026-04-28T13:00:00", value=6.7)
    _create_fingerstick(api_client, measured_at="2026-04-28T14:00:00", value=7.1)

    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": "2026-04-28T13:00:00",
            "to": "2026-04-28T15:00:00",
            "mode": "normalized",
        },
    )

    assert response.status_code == 200
    body = response.json()
    quality = body["quality"]
    assert quality["valid_calibration_points"] == 2
    assert quality["calibration_strategy"] == "median_delta"
    assert quality["median_delta_mmol_l"] == pytest.approx(0.9, abs=0.01)
    assert quality["correction_now_mmol_l"] == pytest.approx(0.9, abs=0.01)
    assert body["points"][-1]["correction_mmol_l"] == pytest.approx(1.1, abs=0.02)


def test_dashboard_excludes_rapid_change_fingersticks(
    api_client: TestClient,
) -> None:
    """Fingersticks on rapidly changing CGM segments are not calibration points."""
    start = datetime.fromisoformat("2026-04-28T08:00:00")
    _seed_cgm(
        api_client,
        start=start,
        prefix="rapid",
        values=[(0, 5.0), (10, 7.0), (20, 9.0), (60, 7.0), (70, 7.0), (80, 7.0)],
    )
    _create_sensor(api_client, started_at="2026-04-26T00:00:00")
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T08:10:00",
        value=8.0,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T09:10:00",
        value=8.0,
    )

    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": "2026-04-28T08:00:00",
            "to": "2026-04-28T09:30:00",
            "mode": "normalized",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["quality"]["fingerstick_count"] == 2
    assert body["quality"]["matched_calibration_points"] == 1
    assert body["quality"]["valid_calibration_points"] == 1
    assert body["quality"]["calibration_strategy"] == "median_delta"
    assert body["quality"]["confidence"] == "low"
    assert body["points"][0]["normalized_value"] is not None


def test_recalculate_calibration_persists_active_model(
    api_client: TestClient,
) -> None:
    """Recalculation stores one active display calibration model for the sensor."""
    start = datetime.fromisoformat("2026-04-28T08:00:00")
    _seed_cgm(
        api_client,
        start=start,
        prefix="persisted",
        values=[(0, 6.0), (10, 6.0), (20, 6.0), (60, 6.0), (70, 6.0), (80, 6.0)],
    )
    sensor = _create_sensor(api_client, started_at="2026-04-26T00:00:00")
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T08:10:00",
        value=7.0,
    )
    _create_fingerstick(
        api_client,
        measured_at="2026-04-28T09:10:00",
        value=7.0,
    )

    first = api_client.post(f"/sensors/{sensor['id']}/recalculate-calibration")
    second = api_client.post(f"/sensors/{sensor['id']}/recalculate-calibration")
    quality = api_client.get(f"/sensors/{sensor['id']}/quality")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["active"] is True
    assert second.json()["active"] is True
    assert second.json()["id"] != first.json()["id"]
    assert quality.status_code == 200
    assert quality.json()["active_model"]["id"] == second.json()["id"]
