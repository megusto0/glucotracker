"""Activity sync API tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from glucotracker.config import get_settings


def test_activity_sync_writes_readable_local_log(api_client: TestClient) -> None:
    payload = {
        "date": "2026-05-05",
        "steps": 8432,
        "active_minutes": 57,
        "kcal_burned": 412.5,
        "heart_rate_avg": 91,
        "heart_rate_rest": 62,
        "source": "zepp",
        "hr_samples": 288,
        "hr_active_minutes": 43,
        "kcal_hr_active": 210.4,
        "kcal_steps": 182.1,
        "kcal_no_move_hr": 20,
        "calorie_confidence": "hybrid",
    }

    response = api_client.post("/activity/sync", json=payload)

    assert response.status_code == 200
    log_path = Path(get_settings().activity_log_dir) / "activity-2026-05-05.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "Readable summary:" in log_text
    assert "Action: created" in log_text
    assert "Source: zepp" in log_text
    assert "Steps: 8432" in log_text
    assert "Calories burned: 412.5 kcal" in log_text
    assert '"heart_rate_avg": 91.0' in log_text


def test_activity_balance_exposes_activity_source(api_client: TestClient) -> None:
    payload = {
        "date": "2026-05-05",
        "steps": 8432,
        "kcal_burned": 2234.6,
        "source": "health_connect_total",
        "calorie_confidence": "high",
    }

    sync_response = api_client.post("/activity/sync", json=payload)
    balance_response = api_client.get("/activity/balance", params={"day": "2026-05-05"})

    assert sync_response.status_code == 200
    assert balance_response.status_code == 200
    assert balance_response.json()["activity_source"] == "health_connect_total"
