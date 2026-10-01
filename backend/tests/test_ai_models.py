"""Real audit aggregation, preference conflicts and two-user boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from glucotracker.api.ai_models_schemas import AIModelRoutingUpdate
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import AIRun, Meal, User
from glucotracker.infra.db.repositories.ai_models import AIModelsRepository
from glucotracker.infra.security import hash_password, issue_access_token


def _seed(api_client):
    owner = UUID(str(api_client.app_state["current_user_id"]))
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        other = User(
            username="other-model-user",
            role=UserRole.food,
            password_hash=hash_password("private-password"),
        )
        session.add(other)
        session.flush()
        meal = Meal(
            owner_id=owner,
            eaten_at=datetime.now(UTC).replace(tzinfo=None),
            source="manual",
            status="accepted",
        )
        session.add(meal)
        session.flush()
        session.add(
            AIRun(
                meal_id=meal.id,
                model="gemini-test",
                prompt_version="test",
                request_summary={
                    "latency_ms": 99999,
                    "attempts": [
                        {
                            "provider": "gemini",
                            "model": "gemini-test",
                            "status": "error",
                            "latency_ms": 1000,
                            "response_latency_ms": 800,
                            "message": "timed out SECRET_PHOTO_PAYLOAD",
                            "error_category": "overload",
                        },
                        {
                            "provider": "gemini",
                            "model": "gemini-test",
                            "status": "success",
                            "latency_ms": 3000,
                            "response_latency_ms": 2500,
                            "confidence": 0.8,
                        },
                        {
                            "provider": "gemini",
                            "model": "gemini-test",
                            "status": "skipped",
                        },
                    ],
                },
            )
        )
        AIModelsRepository(session, owner).save(
            [{"provider": "gemini", "model": "gemini-test", "enabled": True}], 0
        )
        session.commit()
        return owner, other.id


@pytest.mark.parametrize("as_owner", [True, False])
def test_repository_and_api_are_owner_scoped(api_client, as_owner):
    owner, other = _seed(api_client)
    reader = owner if as_owner else other
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        repo = AIModelsRepository(session, reader)
        assert bool(repo.routing()) == as_owner
        assert len(repo.runs(datetime.now(UTC) - timedelta(days=1))) == int(as_owner)
        if not as_owner:
            repo.save(
                [{"provider": "gemini", "model": "other-model", "enabled": True}], 0
            )
            session.commit()
            assert (
                AIModelsRepository(session, owner).routing().models_json[0]["model"]
                == "gemini-test"
            )
    token = issue_access_token(reader, UserRole.gluco if as_owner else UserRole.food)
    response = api_client.get(
        "/ai/models", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "SECRET_PHOTO_PAYLOAD" not in response.text
    rows = response.json()["models"]
    if as_owner:
        assert response.json()["history_total"] == 1
        history = response.json()["history"][0]
        assert history["model_used"] == "gemini-test"
        assert [a["status"] for a in history["attempts"]] == [
            "error",
            "success",
            "skipped",
        ]
        assert history["attempts"][0]["error_category"] == "timeout"
        assert history["attempts"][0]["latency_ms"] == 1000
        assert history["attempts"][0]["response_latency_ms"] == 800
        assert api_client.get("/ai/models?history_offset=1").json()["history"] == []
        row = next(m for m in rows if m["model"] == "gemini-test")
        assert (row["attempts"], row["successes"], row["failures"], row["skipped"]) == (
            2,
            1,
            1,
            1,
        )
        assert row["average_latency_ms"] == 2000
        assert row["average_response_latency_ms"] == 1650
        assert row["timed_responses"] == 2
        assert row["average_request_latency_ms"] == 99999
        assert row["timed_requests"] == 1
        assert row["average_confidence"] == 0.8
        assert row["success_rate"] == 0.5
        assert row["errors"][0]["category"] == "timeout"
        assert datetime.fromisoformat(
            row["last_called_at"].replace("Z", "+00:00")
        ).utcoffset() == timedelta(0)
    else:
        assert response.json()["history_total"] == 0
        assert response.json()["history"] == []
        assert all(m["attempts"] == 0 for m in rows)
        assert "gemini-test" not in response.text
    changed = api_client.put(
        "/ai/models",
        headers={"Authorization": f"Bearer {token}"},
        json={"revision": 1, "models": [{"provider": "grok", "model": "my-new-order"}]},
    )
    assert changed.status_code == 200
    with factory() as session:
        assert AIModelsRepository(session, owner).routing().models_json[0]["model"] == (
            "my-new-order" if as_owner else "gemini-test"
        )


def test_api_saves_order_and_rejects_stale_revision(api_client):
    payload = {
        "revision": 0,
        "models": [
            {"provider": "grok", "model": "grok-example"},
            {"provider": "gemini", "model": "gemini-example"},
        ],
    }
    response = api_client.put("/ai/models", json=payload)
    assert response.status_code == 200
    assert response.json()["revision"] == 1
    assert [m["model"] for m in response.json()["models"]] == [
        "grok-example",
        "gemini-example",
    ]
    assert api_client.put("/ai/models", json=payload).status_code == 409
    assert api_client.get("/ai/models").json()["models"][0]["model"] == "grok-example"
    payload["revision"] = 1
    payload["models"].reverse()
    assert api_client.put("/ai/models", json=payload).json()["revision"] == 2


@pytest.mark.parametrize(
    "models",
    [
        [],
        [{"provider": "gemini", "model": "gemini-pro"}],
        [{"provider": "grok", "model": "https://evil.test"}],
        [{"provider": "grok", "model": "grok", "enabled": False}],
        [{"provider": "grok", "model": "grok"}] * 2,
    ],
)
def test_invalid_routing_rejected(models):
    with pytest.raises(ValueError):
        AIModelRoutingUpdate(revision=0, models=models)


def test_old_chain_latency_not_attributed_to_one_model(api_client):
    owner = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        meal = Meal(
            owner_id=owner,
            eaten_at=datetime.now(UTC).replace(tzinfo=None),
            source="manual",
            status="accepted",
        )
        session.add(meal)
        session.flush()
        session.add(
            AIRun(
                meal_id=meal.id,
                model="gemini-legacy",
                prompt_version="test",
                request_summary={"latency_ms": 90000},
            )
        )
        session.commit()
    rows = api_client.get("/ai/models").json()["models"]
    row = next(r for r in rows if r["model"] == "gemini-legacy")
    assert row["average_latency_ms"] is None
    assert row["timed_attempts"] == 0
    assert row["average_response_latency_ms"] is None
    assert row["timed_responses"] == 0
    assert row["average_request_latency_ms"] == 90000
    assert row["timed_requests"] == 1
    assert row["successes"] == 1


def test_unauthenticated_model_access_rejected(api_client):
    api_client.headers.pop("Authorization")
    assert api_client.get("/ai/models").status_code == 401
    assert (
        api_client.put(
            "/ai/models",
            json={"revision": 0, "models": [{"provider": "grok", "model": "grok"}]},
        ).status_code
        == 401
    )


def test_cooldown_is_reported_and_overview_does_not_refresh_auth(
    api_client, monkeypatch, tmp_path
):
    import json

    from glucotracker.config import get_settings
    from glucotracker.infra.gemini.quota_cooldown import GeminiQuotaCooldownStore
    from glucotracker.infra.grok import auth

    owner, _ = _seed(api_client)
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps(
            {"test": {"key": "fake-token", "expires_at": "2000-01-01T00:00:00Z"}}
        )
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "grok_auth_json", auth_file)
    monkeypatch.setattr(settings, "grok_photo_fallback_enabled", True)
    monkeypatch.setattr(
        settings, "gemini_quota_cooldown_path", tmp_path / "cooldowns.json"
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Opening the overview must not refresh credentials")

    monkeypatch.setattr(auth, "_try_refresh_session", forbidden)
    deadline = GeminiQuotaCooldownStore(settings.gemini_quota_cooldown_path).block(
        "gemini-test"
    )
    response = api_client.get("/ai/models")
    assert response.status_code == 200
    row = next(m for m in response.json()["models"] if m["model"] == "gemini-test")
    assert (
        datetime.fromisoformat(row["cooldown_until"].replace("Z", "+00:00")) == deadline
    )
    assert "fake-token" not in response.text


@pytest.mark.parametrize(
    "attempt, expected",
    [
        ({"error_status": "DEADLINE_EXCEEDED", "error_code": 503}, "timeout"),
        ({"error_code": 401}, "authentication"),
        ({"error_code": 429}, "quota"),
        ({"error_code": 502, "message": "response could not be parsed"}, "parse"),
        ({"error_code": 404}, "invalid_request"),
        ({"error_code": 503}, "overload"),
    ],
)
def test_safe_error_categories_keep_provider_failure_reason(attempt, expected):
    from glucotracker.application.ai_models import error_category

    assert error_category(attempt) == expected
