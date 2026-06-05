"""Tests for mobile diagnostic log ingestion."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from glucotracker.config import get_settings


def test_mobile_photo_estimate_logs_are_appended(api_client: TestClient) -> None:
    payload = {
        "client_sent_at": "2026-06-05T10:00:04Z",
        "events": [
            {
                "event_id": "event-1",
                "trace_id": "trace-1",
                "outbox_id": "outbox-1",
                "idempotency_key": "idem-1",
                "source": "photo",
                "event_type": "estimate_visible",
                "event_at": "2026-06-05T10:00:03Z",
                "captured_at": "2026-06-05T10:00:00Z",
                "server_meal_id": "11111111-1111-1111-1111-111111111111",
                "estimate_status": "succeeded",
                "attempt": 1,
                "total_elapsed_ms": 3000,
                "queued_delay_ms": 200,
                "upload_duration_ms": 900,
                "app_flavor": "food",
                "app_version": "0.1.0",
                "android_sdk": 35,
                "device_model": "test model",
                "detail": {
                    "item_count": 1,
                    "localPhotoPath": "C:\\private\\photo.jpg",
                },
            }
        ],
    }

    response = api_client.post("/mobile/photo-estimate-logs", json=payload)

    assert response.status_code == 202
    assert response.json() == {"accepted_count": 1}

    log_path = get_settings().activity_log_dir / "mobile-photo-estimate.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event_type"] == "estimate_visible"
    assert row["user_id"] == str(api_client.app_state["current_user_id"])
    assert row["total_elapsed_ms"] == 3000
    assert row["detail"]["item_count"] == 1
    assert row["detail"]["localPhotoPath"] == "[redacted]"


def test_mobile_photo_estimate_logs_require_auth(api_client: TestClient) -> None:
    payload = {
        "events": [
            {
                "event_id": "event-1",
                "trace_id": "trace-1",
                "event_type": "capture_queued",
                "event_at": "2026-06-05T10:00:00Z",
            }
        ],
    }
    api_client.headers.pop("Authorization", None)

    response = api_client.post("/mobile/photo-estimate-logs", json=payload)

    assert response.status_code == 401
