"""JWT authentication tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from glucotracker import cli
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.base import Base
from glucotracker.infra.db.models import User
from glucotracker.infra.db.session import (
    get_engine,
    get_session_factory,
    reset_engine_for_tests,
)
from glucotracker.infra.security import issue_access_token, verify_password
from glucotracker.main import app


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_register_via_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The admin CLI creates a password-hashed user."""
    monkeypatch.setenv("GLUCOTRACKER_JWT_SECRET", "cli-test-secret-with-32-characters")
    monkeypatch.setenv("GLUCOTRACKER_DATABASE_URL", _sqlite_url(tmp_path / "auth.db"))
    get_settings.cache_clear()
    reset_engine_for_tests()
    Base.metadata.create_all(get_engine())

    passwords = iter(["secret-password", "secret-password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(passwords))

    try:
        exit_code = cli.main(
            ["create-user", "--username", "sister", "--role", UserRole.food.value]
        )
        captured = capsys.readouterr()

        assert exit_code == 0
        assert captured.out.startswith("user_id=")

        session = get_session_factory()()
        try:
            user = session.scalar(select(User).where(User.username == "sister"))
            assert user is not None
            assert user.role == UserRole.food
            assert verify_password("secret-password", user.password_hash)
        finally:
            session.close()
    finally:
        reset_engine_for_tests()
        get_settings.cache_clear()


def test_cli_refuses_missing_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("GLUCOTRACKER_JWT_SECRET", raising=False)
    monkeypatch.setenv("GLUCOTRACKER_DATABASE_URL", _sqlite_url(tmp_path / "auth.db"))
    get_settings.cache_clear()
    reset_engine_for_tests()

    try:
        exit_code = cli.main(
            ["create-user", "--username", "sister", "--role", UserRole.food.value]
        )
        captured = capsys.readouterr()

        assert exit_code == 2
        assert "JWT_SECRET" in captured.err
    finally:
        reset_engine_for_tests()
        get_settings.cache_clear()


def test_login_ok(api_client: TestClient) -> None:
    response = api_client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access"]
    assert body["refresh"]
    assert body["access_expires_at"]
    assert body["refresh_expires_at"]


def test_login_wrong_password(api_client: TestClient) -> None:
    response = api_client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized"}


def test_expired_access_token(api_client: TestClient) -> None:
    expired = issue_access_token(
        UUID(str(api_client.app_state["current_user_id"])),
        UserRole.gluco,
        expires_delta=timedelta(seconds=-1),
    )

    response = api_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired}"},
    )

    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized"}


def test_refresh_rotation(api_client: TestClient) -> None:
    login_response = api_client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )
    first_refresh = login_response.json()["refresh"]

    refresh_response = api_client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    second_refresh = refresh_response.json()["refresh"]

    assert refresh_response.status_code == 200
    assert second_refresh != first_refresh

    replay_response = api_client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert replay_response.status_code == 401
    assert replay_response.json() == {"code": "unauthorized"}


def test_logout_revokes_refresh(api_client: TestClient) -> None:
    login_response = api_client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )
    refresh_token = login_response.json()["refresh"]

    logout_response = api_client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    refresh_response = api_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert logout_response.status_code == 204
    assert refresh_response.status_code == 401
    assert refresh_response.json() == {"code": "unauthorized"}


def test_auth_me(api_client: TestClient, current_user_token: str) -> None:
    response = api_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {current_user_token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert response.json()["role"] == UserRole.gluco.value


def test_backend_refuses_missing_or_weak_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("GLUCOTRACKER_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        with TestClient(app):
            pass

    monkeypatch.setenv("GLUCOTRACKER_JWT_SECRET", "short")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        with TestClient(app):
            pass
    get_settings.cache_clear()
