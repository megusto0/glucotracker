"""Shared API test fixtures."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from glucotracker.api.dependencies import get_session
from glucotracker.config import get_settings
from glucotracker.infra.db import models  # noqa: F401
from glucotracker.infra.db.base import Base
from glucotracker.main import app


@pytest.fixture
def api_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[TestClient]:
    """Return a TestClient backed by an isolated in-memory SQLite database."""
    monkeypatch.setenv("GLUCOTRACKER_TOKEN", "dev")
    monkeypatch.setenv("PHOTO_STORAGE_DIR", str(tmp_path / "photos"))
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
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )

    def override_get_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer dev"})
        client.app_state = {"engine": engine, "session_factory": session_factory}
        yield client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def db_engine(api_client: TestClient) -> Engine:
    """Return the active API test engine."""
    return api_client.app_state["engine"]
