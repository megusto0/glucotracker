"""Shared API test fixtures."""

from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from glucotracker.api.dependencies import get_read_session, get_session
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db import models  # noqa: F401
from glucotracker.infra.db.base import Base
from glucotracker.infra.db.models import (
    DailyActivity,
    DailyTotal,
    FingerstickReading,
    Meal,
    MealAuditEvent,
    MealInsulinEpisodeSnapshot,
    MealInsulinLink,
    MealInsulinLinkReview,
    NightscoutGlucoseEntry,
    NightscoutImportState,
    NightscoutInsulinEvent,
    NightscoutSettings,
    Pattern,
    Photo,
    SensorSession,
    TwinFitLog,
    TwinParams,
    User,
    UserProfile,
)
from glucotracker.infra.db.session import GlucotrackerSession
from glucotracker.infra.security import hash_password, issue_access_token
from glucotracker.main import app

TEST_JWT_SECRET = "test-jwt-secret-for-auth-fixtures-32chars"


@pytest.fixture
def api_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[TestClient]:
    """Return a TestClient backed by an isolated in-memory SQLite database."""
    monkeypatch.setenv("GLUCOTRACKER_TOKEN", "dev")
    monkeypatch.setenv("GLUCOTRACKER_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "UTC")
    monkeypatch.setenv("GLUCOTRACKER_NIGHTSCOUT_BACKGROUND_IMPORT_ENABLED", "false")
    monkeypatch.setenv("PHOTO_STORAGE_DIR", str(tmp_path / "photos"))
    monkeypatch.setenv("ACTIVITY_LOG_DIR", str(tmp_path / "activity_logs"))
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=GlucotrackerSession,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    private_owner_models = (
        DailyActivity,
        DailyTotal,
        FingerstickReading,
        Meal,
        MealAuditEvent,
        MealInsulinEpisodeSnapshot,
        MealInsulinLink,
        MealInsulinLinkReview,
        NightscoutGlucoseEntry,
        NightscoutImportState,
        NightscoutInsulinEvent,
        NightscoutSettings,
        Pattern,
        Photo,
        SensorSession,
        TwinFitLog,
        TwinParams,
        UserProfile,
    )
    seed_session = session_factory()
    try:
        admin_user = User(
            username="admin",
            password_hash=hash_password("admin-password"),
            role=UserRole.gluco,
        )
        seed_session.add(admin_user)
        seed_session.commit()
        admin_user_id = admin_user.id
    finally:
        seed_session.close()
    session_factory.configure(info={"current_user_id": admin_user_id})

    @event.listens_for(session_factory, "before_flush")
    def assign_test_owner(session: Session, _: object, __: object) -> None:
        owner_id = session.info.get("current_user_id", admin_user_id)
        for row in session.new:
            if isinstance(row, private_owner_models) and row.owner_id is None:
                row.owner_id = owner_id

    def override_get_session() -> Generator[Session]:
        session = session_factory()
        session.info["current_user_id"] = admin_user_id
        try:
            yield session
        finally:
            session.close()

    def override_get_read_session() -> Generator[Session]:
        session = session_factory()
        session.info["read_only"] = True
        session.info["current_user_id"] = admin_user_id
        try:
            yield session
        finally:
            session.rollback()
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_read_session] = override_get_read_session

    with TestClient(app) as client:
        client.headers.update(
            {
                "Authorization": (
                    "Bearer "
                    + issue_access_token(UUID(str(admin_user_id)), UserRole.gluco)
                )
            }
        )
        client.app_state = {
            "engine": engine,
            "session_factory": session_factory,
            "current_user_id": admin_user_id,
        }
        yield client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def db_engine(api_client: TestClient) -> Engine:
    """Return the active API test engine."""
    return api_client.app_state["engine"]


@pytest.fixture
def current_user_token(api_client: TestClient) -> str:
    """Return a valid JWT access token for the seeded admin user."""
    return issue_access_token(
        UUID(str(api_client.app_state["current_user_id"])),
        UserRole.gluco,
    )
