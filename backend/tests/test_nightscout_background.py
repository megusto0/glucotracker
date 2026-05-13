"""Background Nightscout glucose import tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from glucotracker.application import nightscout_background
from glucotracker.application.nightscout_background import NightscoutBackgroundImporter
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.base import Base
from glucotracker.infra.db.models import (
    NightscoutGlucoseEntry,
    NightscoutImportState,
    NightscoutSettings,
    User,
)
from glucotracker.infra.db.session import GlucotrackerSession


def _session_factory() -> sessionmaker[GlucotrackerSession]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine,
        class_=GlucotrackerSession,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )


@pytest.mark.asyncio
async def test_background_import_stores_gluco_rows_and_skips_food(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "UTC")
    get_settings.cache_clear()
    session_factory = _session_factory()
    with session_factory() as session:
        gluco = User(username="gluco", password_hash="hash", role=UserRole.gluco)
        food = User(username="food", password_hash="hash", role=UserRole.food)
        session.add_all([gluco, food])
        session.flush()
        session.add_all(
            [
                NightscoutSettings(
                    owner_id=gluco.id,
                    enabled=True,
                    url="https://nightscout.example",
                    api_secret="secret",
                    sync_glucose=True,
                ),
                NightscoutSettings(
                    owner_id=food.id,
                    enabled=True,
                    url="https://nightscout-food.example",
                    api_secret="secret",
                    sync_glucose=True,
                ),
            ]
        )
        session.commit()
        gluco_id = gluco.id

    calls: list[tuple[str, datetime, datetime]] = []

    class FakeNightscoutClient:
        def __init__(self, *, base_url: str, api_secret: str) -> None:
            self.base_url = base_url
            self.api_secret = api_secret

        async def fetch_glucose_entries(
            self,
            from_datetime: datetime,
            to_datetime: datetime,
        ) -> list[dict[str, Any]]:
            calls.append((self.base_url, from_datetime, to_datetime))
            return [
                {
                    "_id": "glucose-1",
                    "dateString": "2026-05-10T08:55:00+00:00",
                    "sgv": 126,
                    "direction": "Flat",
                    "device": "Nightscout",
                }
            ]

    monkeypatch.setattr(
        nightscout_background,
        "NightscoutClient",
        FakeNightscoutClient,
    )

    imported = await NightscoutBackgroundImporter(
        session_factory,
        now=lambda: datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    ).run_once()

    assert imported == 1
    assert [call[0] for call in calls] == ["https://nightscout.example"]
    assert calls[0][1] == datetime(2026, 5, 9, 9, 0, tzinfo=UTC)
    assert calls[0][2] == datetime(2026, 5, 10, 9, 0, tzinfo=UTC)
    with session_factory() as session:
        entries = list(session.scalars(select(NightscoutGlucoseEntry)))
        assert len(entries) == 1
        assert entries[0].owner_id == gluco_id
        assert entries[0].value_mmol_l == 7.0


@pytest.mark.asyncio
async def test_background_import_records_fetch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "UTC")
    get_settings.cache_clear()
    session_factory = _session_factory()
    with session_factory() as session:
        gluco = User(username="gluco", password_hash="hash", role=UserRole.gluco)
        session.add(gluco)
        session.flush()
        session.add(
            NightscoutSettings(
                owner_id=gluco.id,
                enabled=True,
                url="https://nightscout.example",
                api_secret="secret",
                sync_glucose=True,
            )
        )
        session.commit()
        gluco_id = gluco.id

    class FailingNightscoutClient:
        def __init__(self, *, base_url: str, api_secret: str) -> None:
            self.base_url = base_url
            self.api_secret = api_secret

        async def fetch_glucose_entries(
            self,
            from_datetime: datetime,
            to_datetime: datetime,
        ) -> list[dict[str, Any]]:
            raise RuntimeError("temporary nightscout failure")

    monkeypatch.setattr(
        nightscout_background,
        "NightscoutClient",
        FailingNightscoutClient,
    )

    imported = await NightscoutBackgroundImporter(
        session_factory,
        now=lambda: datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    ).run_once()

    assert imported == 0
    with session_factory() as session:
        state = session.scalar(
            select(NightscoutImportState).where(
                NightscoutImportState.owner_id == gluco_id
            )
        )
        assert state is not None
        assert state.last_error == "temporary nightscout failure"
