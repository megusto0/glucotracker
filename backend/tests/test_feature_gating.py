"""Role-based feature gating tests."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import NightscoutGlucoseEntry, User
from glucotracker.infra.nightscout.client import get_nightscout_client
from glucotracker.infra.security import hash_password, issue_access_token
from glucotracker.main import app


class FeatureGateNightscoutClient:
    """Configured Nightscout client double for feature-gating tests."""

    configured = True

    async def get_status(self) -> dict[str, Any]:
        return {"status": "ok", "name": "Nightscout Test"}

    async def check_status(self) -> dict[str, Any]:
        return await self.get_status()

    async def fetch_glucose_entries(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[dict[str, Any]]:
        return []

    async def fetch_insulin_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[dict[str, Any]]:
        return []

    async def post_insulin_treatment(
        self,
        *,
        insulin_units: float,
        recorded_at: datetime,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return {"_id": f"ns-{idempotency_key or 'manual-insulin'}"}

    async def find_insulin_treatment(
        self,
        *,
        insulin_units: float,
        recorded_at: datetime,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        return None


def _create_user(api_client: TestClient, role: UserRole) -> UUID:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        user = User(
            username=f"{role.value}-{uuid4().hex}",
            password_hash=hash_password("password"),
            role=role,
        )
        session.add(user)
        session.commit()
        return user.id


def _token(api_client: TestClient, role: UserRole) -> str:
    user_id = (
        UUID(str(api_client.app_state["current_user_id"]))
        if role == UserRole.gluco
        else _create_user(api_client, role)
    )
    return issue_access_token(user_id, role)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _feature_disabled(response: Any, feature: str) -> None:
    assert response.status_code == 403
    assert response.json() == {
        "detail": {"code": "feature_disabled", "feature": feature}
    }


GLUCOSE_FORBIDDEN_REQUESTS = [
    (
        "GET",
        "/glucose/dashboard",
        {
            "params": {
                "from": "2026-04-28T08:00:00",
                "to": "2026-04-28T10:00:00",
            }
        },
    ),
    ("GET", "/glucose/tir-daily", {"params": {"period": "7d"}}),
    (
        "POST",
        "/fingersticks",
        {
            "json": {
                "measured_at": "2026-04-28T08:10:00",
                "glucose_mmol_l": 7.2,
            }
        },
    ),
    ("GET", "/fingersticks", {}),
    (
        "PATCH",
        f"/fingersticks/{uuid4()}",
        {"json": {"glucose_mmol_l": 6.8}},
    ),
    ("DELETE", f"/fingersticks/{uuid4()}", {}),
    ("GET", "/sensors", {}),
    (
        "POST",
        "/sensors",
        {
            "json": {
                "source": "manual",
                "started_at": "2026-04-28T00:00:00",
                "expected_life_days": 15,
            }
        },
    ),
    (
        "PATCH",
        f"/sensors/{uuid4()}",
        {"json": {"label": "Sensor B"}},
    ),
    ("GET", f"/sensors/{uuid4()}/quality", {}),
    ("POST", f"/sensors/{uuid4()}/recalculate-calibration", {}),
    ("GET", "/twin/params", {}),
    ("PATCH", "/twin/params", {"json": {"icr_morning": 12}}),
    ("POST", "/twin/params/reset", {}),
    (
        "POST",
        "/twin/fit",
        {
            "json": {
                "data_from": "2026-04-01T00:00:00",
                "data_to": "2026-04-15T00:00:00",
            }
        },
    ),
    ("GET", "/twin/fit/history", {}),
    (
        "GET",
        "/twin/data/summary",
        {
            "params": {
                "from": "2026-04-01T00:00:00",
                "to": "2026-04-15T00:00:00",
            }
        },
    ),
    (
        "GET",
        "/twin/curve",
        {
            "params": {
                "from": "2026-04-28T08:00:00",
                "to": "2026-04-28T10:00:00",
            }
        },
    ),
]


NIGHTSCOUT_FORBIDDEN_REQUESTS = [
    ("GET", "/settings/nightscout", {}),
    ("PUT", "/settings/nightscout", {"json": {}}),
    ("POST", "/settings/nightscout/test", {}),
    ("GET", "/nightscout/status", {}),
    ("POST", f"/meals/{uuid4()}/sync_nightscout", {}),
    ("POST", f"/meals/{uuid4()}/unsync_nightscout", {}),
    ("POST", "/nightscout/sync/today", {"json": {"date": "2026-04-28"}}),
    ("GET", "/nightscout/day_status", {"params": {"date": "2026-04-28"}}),
    (
        "GET",
        "/nightscout/glucose",
        {
            "params": {
                "from": "2026-04-28T08:00:00",
                "to": "2026-04-28T10:00:00",
            }
        },
    ),
    (
        "GET",
        "/nightscout/insulin",
        {
            "params": {
                "from": "2026-04-28T08:00:00",
                "to": "2026-04-28T10:00:00",
            }
        },
    ),
    (
        "POST",
        "/nightscout/insulin",
        {
            "json": {
                "insulin_units": 1.0,
                "recorded_at": "2026-04-28T08:00:00",
                "idempotency_key": "feature-gate-insulin",
            }
        },
    ),
    (
        "GET",
        "/nightscout/events",
        {
            "params": {
                "from": "2026-04-28T08:00:00",
                "to": "2026-04-28T10:00:00",
            }
        },
    ),
    ("GET", "/nightscout/latest-reading", {}),
    (
        "POST",
        "/nightscout/import",
        {
            "json": {
                "from_datetime": "2026-04-28T08:00:00",
                "to_datetime": "2026-04-28T10:00:00",
            }
        },
    ),
]


@pytest.mark.parametrize("method,path,kwargs", GLUCOSE_FORBIDDEN_REQUESTS)
def test_food_user_gets_403_on_glucose_endpoints(
    api_client: TestClient,
    method: str,
    path: str,
    kwargs: dict[str, Any],
) -> None:
    response = api_client.request(
        method,
        path,
        headers=_headers(_token(api_client, UserRole.food)),
        **kwargs,
    )

    _feature_disabled(response, "glucose")


@pytest.mark.parametrize("method,path,kwargs", NIGHTSCOUT_FORBIDDEN_REQUESTS)
def test_food_user_gets_403_on_nightscout_endpoints(
    api_client: TestClient,
    method: str,
    path: str,
    kwargs: dict[str, Any],
) -> None:
    response = api_client.request(
        method,
        path,
        headers=_headers(_token(api_client, UserRole.food)),
        **kwargs,
    )

    _feature_disabled(response, "nightscout")


def test_gluco_user_can_read_feature_endpoints(api_client: TestClient) -> None:
    app.dependency_overrides[get_nightscout_client] = FeatureGateNightscoutClient
    try:
        sensor = api_client.post(
            "/sensors",
            json={
                "source": "manual",
                "started_at": "2026-04-28T00:00:00",
                "expected_life_days": 15,
            },
        ).json()
        requests = [
            (
                "GET",
                "/glucose/dashboard",
                {
                    "params": {
                        "from": "2026-04-28T08:00:00",
                        "to": "2026-04-28T10:00:00",
                    }
                },
            ),
            ("GET", "/fingersticks", {}),
            ("GET", "/sensors", {}),
            ("GET", f"/sensors/{sensor['id']}/quality", {}),
            ("GET", "/twin/params", {}),
            (
                "GET",
                "/twin/data/summary",
                {
                    "params": {
                        "from": "2026-04-01T00:00:00",
                        "to": "2026-04-15T00:00:00",
                    }
                },
            ),
            ("GET", "/twin/fit/history", {}),
            (
                "GET",
                "/twin/curve",
                {
                    "params": {
                        "from": "2026-04-28T08:00:00",
                        "to": "2026-04-28T10:00:00",
                    }
                },
            ),
            ("GET", "/settings/nightscout", {}),
            ("POST", "/settings/nightscout/test", {}),
            ("GET", "/nightscout/status", {}),
            ("GET", "/nightscout/day_status", {"params": {"date": "2026-04-28"}}),
            (
                "GET",
                "/nightscout/glucose",
                {
                    "params": {
                        "from": "2026-04-28T08:00:00",
                        "to": "2026-04-28T10:00:00",
                    }
                },
            ),
            (
                "GET",
                "/nightscout/insulin",
                {
                    "params": {
                        "from": "2026-04-28T08:00:00",
                        "to": "2026-04-28T10:00:00",
                    }
                },
            ),
            (
                "POST",
                "/nightscout/insulin",
                {
                    "json": {
                        "insulin_units": 1.0,
                        "recorded_at": "2026-04-28T08:00:00",
                        "idempotency_key": "feature-gate-insulin",
                    }
                },
            ),
            (
                "GET",
                "/nightscout/events",
                {
                    "params": {
                        "from": "2026-04-28T08:00:00",
                        "to": "2026-04-28T10:00:00",
                    }
                },
            ),
            ("GET", "/nightscout/latest-reading", {}),
        ]

        for method, path, kwargs in requests:
            response = api_client.request(method, path, **kwargs)
            assert response.status_code == 200, (method, path, response.text)
    finally:
        app.dependency_overrides.pop(get_nightscout_client, None)


def test_dashboard_today_omits_glucose_fields_for_food_users(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add(
            NightscoutGlucoseEntry(
                source_key="dashboard-latest",
                timestamp=datetime.now(),
                value_mmol_l=6.4,
                value_mg_dl=115,
                source="CGM",
            )
        )
        session.commit()

    gluco_response = api_client.get("/dashboard/today")
    food_response = api_client.get(
        "/dashboard/today",
        headers=_headers(_token(api_client, UserRole.food)),
    )

    assert gluco_response.status_code == 200
    assert "current_glucose" in gluco_response.json()
    assert "current_glucose_at" in gluco_response.json()
    assert food_response.status_code == 200
    assert "current_glucose" not in food_response.json()
    assert "current_glucose_at" not in food_response.json()


def test_auth_me_exposes_role_and_resolved_features(api_client: TestClient) -> None:
    food_response = api_client.get(
        "/auth/me",
        headers=_headers(_token(api_client, UserRole.food)),
    )
    gluco_response = api_client.get(
        "/auth/me",
        headers=_headers(_token(api_client, UserRole.gluco)),
    )

    assert food_response.status_code == 200
    assert food_response.json()["role"] == UserRole.food.value
    assert food_response.json()["features"] == []
    assert gluco_response.status_code == 200
    assert gluco_response.json()["role"] == UserRole.gluco.value
    assert gluco_response.json()["features"] == ["glucose", "insulin", "nightscout"]
