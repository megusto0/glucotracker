from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import User
from glucotracker.infra.security import hash_password, issue_access_token


def test_create_meal_from_photo_is_idempotent_per_user(
    api_client: TestClient,
    monkeypatch,
) -> None:
    """Same idempotency key reuses one user's meal but not another user's meal."""
    from glucotracker.api.routers import photos as photos_router

    monkeypatch.setattr(
        photos_router,
        "_run_single_call_photo_estimate",
        lambda *_args, **_kwargs: None,
    )

    key = "11111111-1111-1111-1111-111111111111"
    data = {
        "captured_at": "2026-05-10T03:17:13Z",
        "source": "camera",
        "idempotency_key": key,
    }

    first = api_client.post(
        "/meals/from-photo",
        data=data,
        files={"photo": ("meal.jpg", b"fake jpeg", "image/jpeg")},
    )
    assert first.status_code == 202
    first_body = first.json()
    assert first_body["estimate_status"] == "estimating"
    assert first_body["photo_url"].startswith("/photos/")

    second = api_client.post(
        "/meals/from-photo",
        data=data,
        files={"photo": ("meal.jpg", b"fake jpeg again", "image/jpeg")},
    )
    assert second.status_code == 202
    assert second.json()["meal_id"] == first_body["meal_id"]

    session_factory: sessionmaker = api_client.app_state["session_factory"]
    with session_factory() as session:
        other = User(
            username="other",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.commit()
        other_id = UUID(str(other.id))

    api_client.headers["Authorization"] = (
        "Bearer " + issue_access_token(other_id, UserRole.gluco)
    )
    third = api_client.post(
        "/meals/from-photo",
        data=data,
        files={"photo": ("meal.jpg", b"fake jpeg", "image/jpeg")},
    )
    assert third.status_code == 202
    assert third.json()["meal_id"] != first_body["meal_id"]


def test_create_meal_from_photo_returns_captured_at_as_utc_instant(
    api_client: TestClient,
    monkeypatch,
) -> None:
    """Mobile clients parse photo capture timestamps as instants."""
    from glucotracker.api.routers import photos as photos_router

    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "Europe/Samara")
    get_settings.cache_clear()
    monkeypatch.setattr(
        photos_router,
        "_run_single_call_photo_estimate",
        lambda *_args, **_kwargs: None,
    )

    response = api_client.post(
        "/meals/from-photo",
        data={
            "captured_at": "2026-05-10T03:17:13Z",
            "source": "camera",
            "idempotency_key": "12121212-1212-1212-1212-121212121212",
        },
        files={"photo": ("meal.jpg", b"fake jpeg", "image/jpeg")},
    )

    assert response.status_code == 202
    captured_at = datetime.fromisoformat(
        response.json()["captured_at"].replace("Z", "+00:00")
    )
    assert captured_at.utcoffset() == timedelta(0)
    assert captured_at.isoformat() == "2026-05-10T03:17:13+00:00"


def test_list_meals_by_idempotency_key(
    api_client: TestClient,
    monkeypatch,
) -> None:
    """GET /meals?idempotency_key= returns the matching meal for the user."""
    from glucotracker.api.routers import photos as photos_router

    monkeypatch.setattr(
        photos_router,
        "_run_single_call_photo_estimate",
        lambda *_args, **_kwargs: None,
    )

    key = "22222222-2222-2222-2222-222222222222"
    data = {
        "captured_at": "2026-05-10T04:00:00Z",
        "source": "camera",
        "idempotency_key": key,
    }
    create_resp = api_client.post(
        "/meals/from-photo",
        data=data,
        files={"photo": ("meal.jpg", b"fake jpeg", "image/jpeg")},
    )
    assert create_resp.status_code == 202
    meal_id = create_resp.json()["meal_id"]

    lookup = api_client.get("/meals", params={"idempotency_key": key})
    assert lookup.status_code == 200
    body = lookup.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == meal_id
    assert body["items"][0]["photo_idempotency_key"] == key

    missing = api_client.get(
        "/meals",
        params={"idempotency_key": "33333333-3333-3333-3333-333333333333"},
    )
    assert missing.status_code == 200
    assert missing.json()["total"] == 0
