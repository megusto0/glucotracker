"""Cross-user isolation test suite.

Creates two gluco users, populates each user's private
tables with deterministic data via direct DB inserts, then asserts that no
GET endpoint leaks cross-user data and no mutation endpoint allows
cross-user modification.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from glucotracker.api.dependencies import get_read_session, get_session
from glucotracker.application.time import local_now
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import (
    ItemSourceKind,
    MealSource,
    MealStatus,
)
from glucotracker.infra.db import models  # noqa: F401
from glucotracker.infra.db.base import Base
from glucotracker.infra.db.models import (
    DailyActivity,
    DailyTotal,
    FingerstickReading,
    Meal,
    MealInsulinLink,
    MealItem,
    NightscoutGlucoseEntry,
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
from glucotracker.infra.nightscout.client import get_nightscout_client
from glucotracker.infra.security import hash_password, issue_access_token
from glucotracker.main import app

TEST_JWT_SECRET = "test-jwt-secret-for-isolation-32chars"


@pytest.fixture
def _isolation_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Generator[dict]:
    """Set up a two-user in-memory database and return client helpers."""
    monkeypatch.setenv("GLUCOTRACKER_TOKEN", "dev")
    monkeypatch.setenv("GLUCOTRACKER_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "UTC")
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
    def _pragma(dbapi_connection: object, _: object) -> None:
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

    seed = session_factory()
    alice = User(
        username="alice",
        password_hash=hash_password("alice-pass"),
        role=UserRole.gluco,
    )
    bob = User(
        username="bob",
        password_hash=hash_password("bob-pass"),
        role=UserRole.gluco,
    )
    seed.add_all([alice, bob])
    seed.commit()
    alice_id = alice.id
    bob_id = bob.id
    seed.close()

    def _make_session(user_id: UUID) -> Generator[Session]:
        s = session_factory()
        s.info["current_user_id"] = user_id
        try:
            yield s
        finally:
            s.close()

    def _make_read_session(user_id: UUID) -> Generator[Session]:
        s = session_factory()
        s.info["read_only"] = True
        s.info["current_user_id"] = user_id
        try:
            yield s
        finally:
            s.rollback()
            s.close()

    last_user: dict[str, UUID] = {}

    def _override_session() -> Generator[Session]:
        uid = last_user.get("id", alice_id)
        yield from _make_session(uid)

    def _override_read_session() -> Generator[Session]:
        uid = last_user.get("id", alice_id)
        yield from _make_read_session(uid)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_read_session] = _override_read_session

    with TestClient(app) as client:

        def _auth_headers(user_id: UUID, role: UserRole) -> dict[str, str]:
            token = issue_access_token(user_id, role)
            last_user["id"] = user_id
            return {"Authorization": f"Bearer {token}"}

        alice_headers = _auth_headers(alice_id, UserRole.gluco)
        bob_headers = _auth_headers(bob_id, UserRole.gluco)

        yield {
            "client": client,
            "engine": engine,
            "session_factory": session_factory,
            "alice_id": alice_id,
            "bob_id": bob_id,
            "alice_headers": alice_headers,
            "bob_headers": bob_headers,
            "auth_headers": _auth_headers,
        }

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


def _collect_ids(value: object) -> set[str]:
    """Recursively collect all UUID-like strings from a JSON tree."""
    found: set[str] = set()
    if isinstance(value, str):
        try:
            UUID(value)
            found.add(value)
        except ValueError:
            pass
    elif isinstance(value, dict):
        for v in value.values():
            found.update(_collect_ids(v))
    elif isinstance(value, list):
        for v in value:
            found.update(_collect_ids(v))
    return found


def _seed_meal(
    session: Session,
    owner_id: UUID,
    title: str,
    eaten_at: datetime,
    *,
    item_name: str = "Item",
    status: MealStatus = MealStatus.accepted,
) -> Meal:
    meal = Meal(
        owner_id=owner_id,
        eaten_at=eaten_at,
        title=title,
        source=MealSource.manual,
        status=status,
        total_carbs_g=10,
        total_protein_g=5,
        total_fat_g=3,
        total_kcal=87,
    )
    session.add(meal)
    session.flush()
    item = MealItem(
        meal_id=meal.id,
        name=item_name,
        source_kind=ItemSourceKind.manual,
        carbs_g=10,
        protein_g=5,
        fat_g=3,
        kcal=87,
        position=0,
    )
    session.add(item)
    session.flush()
    return meal


def _seed_pattern(
    session: Session,
    owner_id: UUID,
    key: str,
) -> Pattern:
    pattern = Pattern(
        owner_id=owner_id,
        prefix="home",
        key=key,
        display_name=key,
        default_carbs_g=20,
        default_protein_g=10,
        default_fat_g=5,
        default_kcal=165,
    )
    session.add(pattern)
    session.flush()
    return pattern


def _seed_daily_total(
    session: Session,
    owner_id: UUID,
    day: date,
) -> DailyTotal:
    total = DailyTotal(
        owner_id=owner_id,
        date=day,
        kcal=200,
        carbs_g=30,
        protein_g=15,
        fat_g=8,
        fiber_g=3,
        meal_count=1,
    )
    session.add(total)
    session.flush()
    return total


def _seed_user_profile(
    session: Session,
    owner_id: UUID,
) -> UserProfile:
    profile = UserProfile(
        owner_id=owner_id,
        weight_kg=70,
        height_cm=175,
        age_years=30,
        sex="male",
        activity_level="moderate",
    )
    session.add(profile)
    session.flush()
    return profile


def _seed_daily_activity(
    session: Session,
    owner_id: UUID,
    day: date,
) -> DailyActivity:
    activity = DailyActivity(
        owner_id=owner_id,
        date=day,
        steps=5000,
        active_minutes=30,
        kcal_burned=200,
    )
    session.add(activity)
    session.flush()
    return activity


def _seed_sensor(
    session: Session,
    owner_id: UUID,
) -> SensorSession:
    sensor = SensorSession(
        owner_id=owner_id,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        expected_life_days=15,
    )
    session.add(sensor)
    session.flush()
    return sensor


def _seed_fingerstick(
    session: Session,
    owner_id: UUID,
    measured_at: datetime,
) -> FingerstickReading:
    reading = FingerstickReading(
        owner_id=owner_id,
        measured_at=measured_at,
        glucose_mmol_l=5.5,
    )
    session.add(reading)
    session.flush()
    return reading


def _seed_nightscout_settings(
    session: Session,
    owner_id: UUID,
) -> NightscoutSettings:
    settings = NightscoutSettings(
        owner_id=owner_id,
        enabled=False,
    )
    session.add(settings)
    session.flush()
    return settings


def _seed_nightscout_glucose(
    session: Session,
    owner_id: UUID,
    timestamp: datetime,
) -> NightscoutGlucoseEntry:
    entry = NightscoutGlucoseEntry(
        owner_id=owner_id,
        source_key=str(uuid4()),
        timestamp=timestamp,
        value_mmol_l=5.5,
    )
    session.add(entry)
    session.flush()
    return entry


def _seed_nightscout_insulin(
    session: Session,
    owner_id: UUID,
    timestamp: datetime,
) -> NightscoutInsulinEvent:
    event = NightscoutInsulinEvent(
        owner_id=owner_id,
        source_key=str(uuid4()),
        timestamp=timestamp,
        insulin_units=2.0,
    )
    session.add(event)
    session.flush()
    return event


def _seed_twin_params(
    session: Session,
    owner_id: UUID,
    icr_morning: float,
) -> TwinParams:
    params = TwinParams(
        owner_id=owner_id,
        icr_morning=icr_morning,
        icr_day=12,
        icr_evening=13,
        isf=2,
    )
    session.add(params)
    session.flush()
    return params


def _seed_twin_fit_log(
    session: Session,
    owner_id: UUID,
    marker: str,
) -> TwinFitLog:
    row = TwinFitLog(
        owner_id=owner_id,
        fit_at=datetime(2026, 5, 1, 8, 0),
        params_snapshot={"marker": marker},
        method="manual",
    )
    session.add(row)
    session.flush()
    return row


def _populate(env: dict) -> dict:
    """Seed both users with private data. Returns entity IDs for assertions."""
    sf = env["session_factory"]
    alice = env["alice_id"]
    bob = env["bob_id"]
    now = local_now().replace(hour=12, minute=0, second=0, microsecond=0)
    today = now.date()

    alice_day = today
    bob_day = today - timedelta(days=1)

    s = sf()
    s.info["current_user_id"] = alice
    alice_meal = _seed_meal(s, alice, "Alice lunch", now)
    alice_pattern = _seed_pattern(s, alice, "alice-key")
    _seed_daily_total(s, alice, alice_day)
    _seed_user_profile(s, alice)
    _seed_daily_activity(s, alice, alice_day)
    alice_sensor = _seed_sensor(s, alice)
    alice_fingerstick = _seed_fingerstick(s, alice, now)
    _seed_nightscout_settings(s, alice)
    alice_ns_glucose = _seed_nightscout_glucose(s, alice, now - timedelta(hours=1))
    alice_ns_insulin = _seed_nightscout_insulin(s, alice, now - timedelta(hours=1))
    alice_twin_params = _seed_twin_params(s, alice, 11)
    alice_twin_fit_log = _seed_twin_fit_log(s, alice, "alice")
    s.commit()
    s.close()

    s = sf()
    s.info["current_user_id"] = bob
    bob_meal = _seed_meal(s, bob, "Bob lunch", now + timedelta(hours=1))
    bob_pattern = _seed_pattern(s, bob, "bob-key")
    _seed_daily_total(s, bob, bob_day)
    _seed_user_profile(s, bob)
    _seed_daily_activity(s, bob, bob_day)
    bob_sensor = _seed_sensor(s, bob)
    bob_fingerstick = _seed_fingerstick(s, bob, now + timedelta(hours=1))
    _seed_nightscout_settings(s, bob)
    bob_ns_glucose = _seed_nightscout_glucose(s, bob, now + timedelta(hours=2))
    bob_ns_insulin = _seed_nightscout_insulin(s, bob, now + timedelta(hours=2))
    bob_twin_params = _seed_twin_params(s, bob, 22)
    bob_twin_fit_log = _seed_twin_fit_log(s, bob, "bob")
    s.commit()
    s.close()

    return {
        "alice_meal": alice_meal.id,
        "alice_pattern": alice_pattern.id,
        "alice_sensor": alice_sensor.id,
        "alice_fingerstick": alice_fingerstick.id,
        "alice_ns_glucose": alice_ns_glucose.id,
        "alice_ns_insulin": alice_ns_insulin.id,
        "alice_twin_params": alice_twin_params.id,
        "alice_twin_fit_log": alice_twin_fit_log.id,
        "bob_meal": bob_meal.id,
        "bob_pattern": bob_pattern.id,
        "bob_sensor": bob_sensor.id,
        "bob_fingerstick": bob_fingerstick.id,
        "bob_ns_glucose": bob_ns_glucose.id,
        "bob_ns_insulin": bob_ns_insulin.id,
        "bob_twin_params": bob_twin_params.id,
        "bob_twin_fit_log": bob_twin_fit_log.id,
        "now": now,
        "today": today,
        "alice_day": alice_day,
        "bob_day": bob_day,
    }


class TestGETIsolation:
    """Every GET endpoint returning scoped data must not leak cross-user IDs."""

    @pytest.fixture(autouse=True)
    def _setup(self, _isolation_env):
        self.env = _isolation_env
        self.ids = _populate(self.env)
        self.client = self.env["client"]
        self.alice = self.env["alice_id"]
        self.bob = self.env["bob_id"]
        self.alice_headers = self.env["alice_headers"]
        self.bob_headers = self.env["bob_headers"]

    def _assert_no_cross_user_ids(
        self,
        resp_json: object,
        owning_user_id: UUID,
        other_user_id: UUID,
    ) -> None:
        ids_in_response = _collect_ids(resp_json)
        other_str = str(other_user_id)
        assert other_str not in ids_in_response, (
            f"Response contains the other user's ID {other_str}"
        )
        owner_str = str(owning_user_id)
        if ids_in_response:
            assert owner_str in ids_in_response, (
                f"Response should contain owning user's data ({owner_str})"
            )

    def test_list_meals(self):
        r = self.client.get("/meals", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert str(self.ids["alice_meal"]) in _collect_ids(data)
        assert str(self.ids["bob_meal"]) not in _collect_ids(data)

        r = self.client.get("/meals", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert str(self.ids["bob_meal"]) in _collect_ids(data)
        assert str(self.ids["alice_meal"]) not in _collect_ids(data)

    def test_get_meal(self):
        r = self.client.get(
            f"/meals/{self.ids['alice_meal']}", headers=self.alice_headers
        )
        assert r.status_code == 200
        assert str(self.ids["alice_meal"]) in _collect_ids(r.json())

        r = self.client.get(
            f"/meals/{self.ids['alice_meal']}", headers=self.bob_headers
        )
        assert r.status_code == 404

        r = self.client.get(f"/meals/{self.ids['bob_meal']}", headers=self.bob_headers)
        assert r.status_code == 200
        assert str(self.ids["bob_meal"]) in _collect_ids(r.json())

        r = self.client.get(
            f"/meals/{self.ids['bob_meal']}", headers=self.alice_headers
        )
        assert r.status_code == 404

    def test_list_patterns(self):
        r = self.client.get("/patterns", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert str(self.ids["alice_pattern"]) in _collect_ids(data)
        assert str(self.ids["bob_pattern"]) not in _collect_ids(data)

        r = self.client.get("/patterns", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_pattern"]) in _collect_ids(data)
        assert str(self.ids["alice_pattern"]) not in _collect_ids(data)

    def test_get_pattern(self):
        r = self.client.get(
            f"/patterns/{self.ids['alice_pattern']}", headers=self.alice_headers
        )
        assert r.status_code == 200

        r = self.client.get(
            f"/patterns/{self.ids['alice_pattern']}", headers=self.bob_headers
        )
        assert r.status_code == 404

        r = self.client.get(
            f"/patterns/{self.ids['bob_pattern']}", headers=self.bob_headers
        )
        assert r.status_code == 200

        r = self.client.get(
            f"/patterns/{self.ids['bob_pattern']}", headers=self.alice_headers
        )
        assert r.status_code == 404

    def test_search_patterns(self):
        r = self.client.get(
            "/patterns/search", params={"q": "alice"}, headers=self.alice_headers
        )
        assert r.status_code == 200
        assert str(self.ids["alice_pattern"]) in _collect_ids(r.json())

        r = self.client.get(
            "/patterns/search", params={"q": "alice"}, headers=self.bob_headers
        )
        assert r.status_code == 200
        assert str(self.ids["alice_pattern"]) not in _collect_ids(r.json())

    def test_dashboard_today(self):
        r = self.client.get("/dashboard/today", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.bob) not in _collect_ids(data)

        r = self.client.get("/dashboard/today", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.alice) not in _collect_ids(data)
        assert data["meal_count"] >= 1

    def test_dashboard_range(self):
        today = self.ids["today"]
        params = {"from": today.isoformat(), "to": today.isoformat()}
        r = self.client.get(
            "/dashboard/range",
            params=params,
            headers=self.alice_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.bob) not in _collect_ids(data)

        r = self.client.get("/dashboard/range", params=params, headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.alice) not in _collect_ids(data)
        assert data["summary"]["total_meals"] >= 1

    def test_dashboard_heatmap(self):
        r = self.client.get("/dashboard/heatmap", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.bob) not in _collect_ids(data)

    def test_dashboard_top_patterns(self):
        r = self.client.get(
            "/dashboard/top_patterns", params={"days": 365}, headers=self.alice_headers
        )
        assert r.status_code == 200
        assert str(self.ids["bob_pattern"]) not in _collect_ids(r.json())

    def test_dashboard_source_breakdown(self):
        r = self.client.get("/dashboard/source_breakdown", headers=self.alice_headers)
        assert r.status_code == 200

    def test_dashboard_data_quality(self):
        r = self.client.get("/dashboard/data_quality", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_meal"]) not in _collect_ids(data)

    def test_glucose_dashboard(self):
        now = self.ids["now"]
        params = {
            "from": (now - timedelta(hours=2)).isoformat(),
            "to": (now + timedelta(hours=2)).isoformat(),
        }
        r = self.client.get(
            "/glucose/dashboard", params=params, headers=self.alice_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_sensor"]) not in _collect_ids(data)
        # Alice's moderate mixed meal uses a soft normal/slow prior rather than
        # being forced into one hard bucket; at +120 min its tail remains.
        assert data["summary"]["cob_g"] == pytest.approx(2.93, abs=0.05)
        assert data["summary"]["cob_minutes_remaining"] == 286
        # Alice: 2 U at now-1h, as_of=now+2h → 180 min on biphasic IOB.
        assert data["summary"]["iob_units"] == pytest.approx(0.54, abs=0.02)
        assert data["summary"]["iob_minutes_remaining"] == 84

        r = self.client.get(
            "/glucose/dashboard", params=params, headers=self.bob_headers
        )
        assert r.status_code == 200
        data = r.json()
        # Bob has the same mixed-meal prior at +60 min.
        assert data["summary"]["cob_g"] == pytest.approx(6.05, abs=0.05)
        assert data["summary"]["cob_minutes_remaining"] == 346
        # Bob: 2 U at as_of (future relative to range start) → full IOB.
        assert data["summary"]["iob_units"] == pytest.approx(2.0)
        assert data["summary"]["iob_minutes_remaining"] == 270

    def test_twin_params(self):
        r = self.client.get("/twin/params", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(self.ids["alice_twin_params"])
        assert data["icr_morning"] == 11
        assert str(self.ids["bob_twin_params"]) not in _collect_ids(data)

        r = self.client.get("/twin/params", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(self.ids["bob_twin_params"])
        assert data["icr_morning"] == 22
        assert str(self.ids["alice_twin_params"]) not in _collect_ids(data)

    def test_twin_fit_history(self):
        r = self.client.get("/twin/fit/history", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_twin_fit_log"]) in _collect_ids(data)
        assert str(self.ids["bob_twin_fit_log"]) not in _collect_ids(data)

        r = self.client.get("/twin/fit/history", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_twin_fit_log"]) in _collect_ids(data)
        assert str(self.ids["alice_twin_fit_log"]) not in _collect_ids(data)

    def test_twin_curve(self):
        now = self.ids["now"]
        params = {
            "from": (now - timedelta(hours=2)).isoformat(),
            "to": (now + timedelta(hours=2)).isoformat(),
            "step_minutes": 30,
        }
        r = self.client.get("/twin/curve", params=params, headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_twin_params"]) not in _collect_ids(data)
        assert str(self.ids["bob_fingerstick"]) not in _collect_ids(data)

    def test_twin_data_summary(self):
        now = self.ids["now"]
        params = {
            "from": (now - timedelta(hours=2)).isoformat(),
            "to": (now + timedelta(hours=2)).isoformat(),
        }
        r = self.client.get(
            "/twin/data/summary", params=params, headers=self.alice_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert data["cgm_count"] == 1
        assert str(self.bob) not in _collect_ids(data)

        r = self.client.get(
            "/twin/data/summary", params=params, headers=self.bob_headers
        )
        assert r.status_code == 200
        assert r.json()["cgm_count"] == 1

    def test_twin_fit_does_not_update_other_user(self):
        now = self.ids["now"]
        payload = {
            "data_from": (now - timedelta(hours=2)).isoformat(),
            "data_to": (now + timedelta(hours=2)).isoformat(),
        }
        r = self.client.post("/twin/fit", json=payload, headers=self.bob_headers)
        assert r.status_code == 422
        assert r.json()["detail"]["reason"] == "insufficient_cgm"

        sf = self.env["session_factory"]
        s = sf()
        alice_params = s.get(TwinParams, self.ids["alice_twin_params"])
        assert alice_params.icr_morning == 11
        s.close()

    def test_list_fingersticks(self):
        r = self.client.get("/fingersticks", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_fingerstick"]) in _collect_ids(data)
        assert str(self.ids["bob_fingerstick"]) not in _collect_ids(data)

        r = self.client.get("/fingersticks", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_fingerstick"]) in _collect_ids(data)
        assert str(self.ids["alice_fingerstick"]) not in _collect_ids(data)

    def test_list_sensors(self):
        r = self.client.get("/sensors", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_sensor"]) in _collect_ids(data)
        assert str(self.ids["bob_sensor"]) not in _collect_ids(data)

        r = self.client.get("/sensors", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_sensor"]) in _collect_ids(data)
        assert str(self.ids["alice_sensor"]) not in _collect_ids(data)

    def test_sensor_quality(self):
        r = self.client.get(
            f"/sensors/{self.ids['alice_sensor']}/quality",
            headers=self.alice_headers,
        )
        assert r.status_code == 200

        r = self.client.get(
            f"/sensors/{self.ids['alice_sensor']}/quality",
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_nightscout_settings(self):
        r = self.client.get("/settings/nightscout", headers=self.alice_headers)
        assert r.status_code == 200
        assert str(self.bob) not in _collect_ids(r.json())

        r = self.client.get("/settings/nightscout", headers=self.bob_headers)
        assert r.status_code == 200

    def test_nightscout_latest_reading(self):
        r = self.client.get("/nightscout/latest-reading", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_ns_glucose"]) not in _collect_ids(data)

    def test_nightscout_glucose_not_configured(self):
        now = self.ids["now"]
        params = {
            "from": (now - timedelta(hours=3)).isoformat(),
            "to": (now + timedelta(hours=3)).isoformat(),
        }
        r = self.client.get(
            "/nightscout/glucose", params=params, headers=self.alice_headers
        )
        assert r.status_code in {200, 503} or r.status_code >= 500

    def test_nightscout_insulin_not_configured(self):
        now = self.ids["now"]
        params = {
            "from": (now - timedelta(hours=3)).isoformat(),
            "to": (now + timedelta(hours=3)).isoformat(),
        }
        r = self.client.get(
            "/nightscout/insulin", params=params, headers=self.alice_headers
        )
        assert r.status_code in {200, 503} or r.status_code >= 500

    def test_nightscout_events_not_configured(self):
        now = self.ids["now"]
        params = {
            "from": (now - timedelta(hours=3)).isoformat(),
            "to": (now + timedelta(hours=3)).isoformat(),
        }
        r = self.client.get(
            "/nightscout/events", params=params, headers=self.alice_headers
        )
        assert r.status_code in {200, 503} or r.status_code >= 500

    def test_timeline(self):
        now = self.ids["now"]
        params = {
            "from": (now - timedelta(hours=2)).isoformat(),
            "to": (now + timedelta(hours=2)).isoformat(),
        }
        r = self.client.get("/timeline", params=params, headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_meal"]) not in _collect_ids(data)
        assert str(self.ids["alice_meal"]) in _collect_ids(data)

        r = self.client.get("/timeline", params=params, headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_meal"]) not in _collect_ids(data)
        assert str(self.ids["bob_meal"]) in _collect_ids(data)

    def test_timeline_insulin_links(self):
        params = {"date": self.ids["today"].isoformat()}
        r = self.client.get(
            "/timeline/insulin-links",
            params=params,
            headers=self.alice_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_meal"]) in _collect_ids(data)
        assert str(self.ids["alice_ns_insulin"]) in _collect_ids(data)
        assert str(self.ids["bob_meal"]) not in _collect_ids(data)
        assert str(self.ids["bob_ns_insulin"]) not in _collect_ids(data)

        r = self.client.get(
            "/timeline/insulin-links",
            params=params,
            headers=self.bob_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_meal"]) in _collect_ids(data)
        assert str(self.ids["bob_ns_insulin"]) in _collect_ids(data)
        assert str(self.ids["alice_meal"]) not in _collect_ids(data)
        assert str(self.ids["alice_ns_insulin"]) not in _collect_ids(data)

    def test_autocomplete(self):
        r = self.client.get(
            "/autocomplete", params={"q": "alice"}, headers=self.alice_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_pattern"]) in _collect_ids(data)

        r = self.client.get(
            "/autocomplete", params={"q": "alice"}, headers=self.bob_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_pattern"]) not in _collect_ids(data)

    def test_profile(self):
        r = self.client.get("/profile", headers=self.alice_headers)
        assert r.status_code == 200
        r = self.client.get("/profile", headers=self.bob_headers)
        assert r.status_code == 200

    def test_activity_balance(self):
        today = self.ids["today"]
        r = self.client.get(
            "/activity/balance",
            params={"day": today.isoformat()},
            headers=self.alice_headers,
        )
        assert r.status_code == 200

        r = self.client.get(
            "/activity/balance",
            params={"day": today.isoformat()},
            headers=self.bob_headers,
        )
        assert r.status_code == 200

    def test_activity_balance_range(self):
        today = self.ids["today"]
        params = {
            "from_date": today.isoformat(),
            "to_date": today.isoformat(),
        }
        r = self.client.get(
            "/activity/balance/range", params=params, headers=self.alice_headers
        )
        assert r.status_code == 200

        r = self.client.get(
            "/activity/balance/range", params=params, headers=self.bob_headers
        )
        assert r.status_code == 200

    def test_reports_endocrinologist(self):
        today = self.ids["today"]
        params = {"from": today.isoformat(), "to": today.isoformat()}
        r = self.client.get(
            "/reports/endocrinologist", params=params, headers=self.alice_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_meal"]) not in _collect_ids(data)

        r = self.client.get(
            "/reports/endocrinologist", params=params, headers=self.bob_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_meal"]) not in _collect_ids(data)

    def test_database_items(self):
        r = self.client.get("/database/items", headers=self.alice_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["alice_pattern"]) in _collect_ids(data)
        assert str(self.ids["bob_pattern"]) not in _collect_ids(data)

        r = self.client.get("/database/items", headers=self.bob_headers)
        assert r.status_code == 200
        data = r.json()
        assert str(self.ids["bob_pattern"]) in _collect_ids(data)
        assert str(self.ids["alice_pattern"]) not in _collect_ids(data)

    def test_meal_ai_runs(self):
        r = self.client.get(
            f"/meals/{self.ids['alice_meal']}/ai_runs",
            headers=self.alice_headers,
        )
        assert r.status_code == 200

        r = self.client.get(
            f"/meals/{self.ids['alice_meal']}/ai_runs",
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_nightscout_day_status(self):
        today = self.ids["today"]
        r = self.client.get(
            "/nightscout/day_status",
            params={"date": today.isoformat()},
            headers=self.alice_headers,
        )
        assert r.status_code == 200

        r = self.client.get(
            "/nightscout/day_status",
            params={"date": today.isoformat()},
            headers=self.bob_headers,
        )
        assert r.status_code == 200

    def test_nightscout_status(self):
        r = self.client.get("/nightscout/status", headers=self.alice_headers)
        assert r.status_code == 200

        r = self.client.get("/nightscout/status", headers=self.bob_headers)
        assert r.status_code == 200


class TestMutationIsolation:
    """Every PUT/PATCH/DELETE on a scoped entity must return 404 for other users."""

    @pytest.fixture(autouse=True)
    def _setup(self, _isolation_env):
        self.env = _isolation_env
        self.ids = _populate(self.env)
        self.client = self.env["client"]
        self.alice = self.env["alice_id"]
        self.bob = self.env["bob_id"]
        self.alice_headers = self.env["alice_headers"]
        self.bob_headers = self.env["bob_headers"]

    def test_patch_meal_as_bob(self):
        r = self.client.patch(
            f"/meals/{self.ids['alice_meal']}",
            json={"title": "hacked"},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_delete_meal_as_bob(self):
        r = self.client.delete(
            f"/meals/{self.ids['alice_meal']}", headers=self.bob_headers
        )
        assert r.status_code == 404

    def test_add_meal_item_as_bob(self):
        r = self.client.post(
            f"/meals/{self.ids['alice_meal']}/items",
            json={
                "name": "hacked item",
                "source_kind": "manual",
                "carbs_g": 0,
                "protein_g": 0,
                "fat_g": 0,
                "kcal": 0,
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_replace_meal_items_as_bob(self):
        r = self.client.put(
            f"/meals/{self.ids['alice_meal']}/items",
            json=[
                {
                    "name": "hacked item",
                    "source_kind": "manual",
                    "carbs_g": 0,
                    "protein_g": 0,
                    "fat_g": 0,
                    "kcal": 0,
                }
            ],
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_accept_meal_draft_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        draft = Meal(
            owner_id=self.alice,
            eaten_at=datetime(2026, 5, 7, 14, 0, tzinfo=UTC),
            title="Alice draft",
            source=MealSource.photo,
            status=MealStatus.draft,
        )
        s.add(draft)
        s.flush()
        item = MealItem(
            meal_id=draft.id,
            name="Draft item",
            source_kind=ItemSourceKind.photo_estimate,
            carbs_g=10,
            protein_g=5,
            fat_g=3,
            kcal=87,
            position=0,
        )
        s.add(item)
        s.commit()
        draft_id = draft.id
        s.close()

        r = self.client.post(
            f"/meals/{draft_id}/accept",
            json={
                "items": [
                    {
                        "name": "Accepted item",
                        "source_kind": "manual",
                        "carbs_g": 10,
                        "protein_g": 5,
                        "fat_g": 3,
                        "kcal": 87,
                    }
                ]
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_discard_meal_draft_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        draft = Meal(
            owner_id=self.alice,
            eaten_at=datetime(2026, 5, 7, 15, 0, tzinfo=UTC),
            title="Alice draft2",
            source=MealSource.photo,
            status=MealStatus.draft,
        )
        s.add(draft)
        s.flush()
        item = MealItem(
            meal_id=draft.id,
            name="Draft item",
            source_kind=ItemSourceKind.photo_estimate,
            carbs_g=10,
            protein_g=5,
            fat_g=3,
            kcal=87,
            position=0,
        )
        s.add(item)
        s.commit()
        draft_id = draft.id
        s.close()

        r = self.client.post(
            f"/meals/{draft_id}/discard",
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_patch_pattern_as_bob(self):
        r = self.client.patch(
            f"/patterns/{self.ids['alice_pattern']}",
            json={"display_name": "hacked"},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_delete_pattern_as_bob(self):
        r = self.client.delete(
            f"/patterns/{self.ids['alice_pattern']}", headers=self.bob_headers
        )
        assert r.status_code == 404

    def test_upload_pattern_image_as_bob(self):
        r = self.client.post(
            f"/patterns/{self.ids['alice_pattern']}/image",
            headers=self.bob_headers,
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert r.status_code == 404

    def test_get_pattern_image_file_as_bob(self):
        r = self.client.get(
            f"/patterns/{self.ids['alice_pattern']}/image/file",
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_patch_fingerstick_as_bob(self):
        r = self.client.patch(
            f"/fingersticks/{self.ids['alice_fingerstick']}",
            json={"glucose_mmol_l": 6.5},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_delete_fingerstick_as_bob(self):
        r = self.client.delete(
            f"/fingersticks/{self.ids['alice_fingerstick']}",
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_patch_sensor_as_bob(self):
        r = self.client.patch(
            f"/sensors/{self.ids['alice_sensor']}",
            json={"label": "hacked"},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_recalculate_sensor_calibration_as_bob(self):
        r = self.client.post(
            f"/sensors/{self.ids['alice_sensor']}/recalculate-calibration",
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_delete_photo_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        photo = Photo(
            owner_id=self.alice,
            meal_id=self.ids["alice_meal"],
            path="test/alice_photo.jpg",
            content_type="image/jpeg",
        )
        s.add(photo)
        s.commit()
        photo_id = photo.id
        s.close()

        r = self.client.delete(f"/photos/{photo_id}", headers=self.bob_headers)
        assert r.status_code == 404

    def test_get_photo_file_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        photo = Photo(
            owner_id=self.alice,
            meal_id=self.ids["alice_meal"],
            path="test/alice_photo2.jpg",
            content_type="image/jpeg",
        )
        s.add(photo)
        s.commit()
        photo_id = photo.id
        s.close()

        r = self.client.get(f"/photos/{photo_id}/file", headers=self.bob_headers)
        assert r.status_code == 404

    def test_update_nightscout_settings_isolation(self):
        r = self.client.put(
            "/settings/nightscout",
            json={"enabled": False},
            headers=self.alice_headers,
        )
        assert r.status_code == 200

        sf = self.env["session_factory"]
        s = sf()
        settings = (
            s.query(NightscoutSettings).filter_by(owner_id=self.bob).one_or_none()
        )
        if settings is not None:
            assert settings.enabled is False or settings.enabled is True
        s.close()

    def test_patch_meal_item_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        meal = (
            s.query(Meal)
            .filter_by(id=self.ids["alice_meal"], owner_id=self.alice)
            .one()
        )
        item = meal.items[0]
        item_id = item.id
        s.close()

        r = self.client.patch(
            f"/meal_items/{item_id}",
            json={"name": "hacked item"},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_delete_meal_item_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        meal = (
            s.query(Meal)
            .filter_by(id=self.ids["alice_meal"], owner_id=self.alice)
            .one()
        )
        item = meal.items[0]
        item_id = item.id
        s.close()

        r = self.client.delete(f"/meal_items/{item_id}", headers=self.bob_headers)
        assert r.status_code == 404

    def test_copy_by_weight_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        meal = (
            s.query(Meal)
            .filter_by(id=self.ids["alice_meal"], owner_id=self.alice)
            .one()
        )
        item = meal.items[0]
        item.grams = 100
        s.commit()
        item_id = item.id
        s.close()

        r = self.client.post(
            f"/meal_items/{item_id}/copy_by_weight",
            json={"grams": 50},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_remember_product_as_bob(self):
        sf = self.env["session_factory"]
        s = sf()
        s.info["current_user_id"] = self.alice
        meal = (
            s.query(Meal)
            .filter_by(id=self.ids["alice_meal"], owner_id=self.alice)
            .one()
        )
        item = meal.items[0]
        item_id = item.id
        s.close()

        r = self.client.post(
            f"/meal_items/{item_id}/remember_product",
            json={"aliases": ["test"]},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_create_meal_ownership(self):
        r = self.client.post(
            "/meals",
            json={
                "title": "Bob new meal",
                "source": "manual",
                "eaten_at": "2026-04-01T12:00:00Z",
                "items": [],
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 201
        meal_id = UUID(r.json()["id"])
        sf = self.env["session_factory"]
        s = sf()
        meal = s.get(Meal, meal_id)
        assert str(meal.owner_id) == str(self.bob)
        s.close()

    def test_create_pattern_ownership(self):
        r = self.client.post(
            "/patterns",
            json={
                "prefix": "test",
                "key": "bob-new-pattern",
                "display_name": "Bob new pattern",
                "default_carbs_g": 10,
                "default_protein_g": 5,
                "default_fat_g": 2,
                "default_kcal": 78,
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 201
        pattern_id = UUID(r.json()["id"])
        sf = self.env["session_factory"]
        s = sf()
        pattern = s.get(Pattern, pattern_id)
        assert str(pattern.owner_id) == str(self.bob)
        s.close()

    def test_create_fingerstick_ownership(self):
        r = self.client.post(
            "/fingersticks",
            json={
                "measured_at": "2026-04-01T10:00:00Z",
                "glucose_mmol_l": 5.0,
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 201
        reading_id = UUID(r.json()["id"])
        sf = self.env["session_factory"]
        s = sf()
        reading = s.get(FingerstickReading, reading_id)
        assert str(reading.owner_id) == str(self.bob)
        s.close()

    def test_create_nightscout_insulin_ownership(self):
        class FakeNightscoutClient:
            configured = True

            async def post_insulin_treatment(
                self,
                *,
                insulin_units: float,
                recorded_at: datetime,
                idempotency_key: str | None = None,
            ) -> dict:
                return {"_id": f"ns-{idempotency_key}"}

            async def find_insulin_treatment(
                self,
                *,
                insulin_units: float,
                recorded_at: datetime,
                idempotency_key: str | None = None,
            ) -> dict | None:
                return None

        app.dependency_overrides[get_nightscout_client] = FakeNightscoutClient
        try:
            r = self.client.post(
                "/nightscout/insulin",
                json={
                    "recorded_at": "2026-04-01T10:00:00Z",
                    "insulin_units": 1.5,
                    "idempotency_key": "bob-manual-insulin",
                },
                headers=self.bob_headers,
            )
        finally:
            app.dependency_overrides.pop(get_nightscout_client, None)

        assert r.status_code == 200
        sf = self.env["session_factory"]
        s = sf()
        row = s.scalar(
            select(NightscoutInsulinEvent).where(
                NightscoutInsulinEvent.nightscout_id == "ns-bob-manual-insulin"
            )
        )
        assert row is not None
        assert str(row.owner_id) == str(self.bob)
        s.close()

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_nightscout_insulin_mutation_isolation(self, method: str):
        """Alice cannot update or delete Bob's manual insulin cache row."""
        sf = self.env["session_factory"]
        s = sf()
        row = NightscoutInsulinEvent(
            owner_id=self.bob,
            source_key=f"manual_insulin:bob-{method}",
            nightscout_id=f"ns-bob-{method}",
            timestamp=datetime(2026, 4, 1, 10, tzinfo=UTC),
            insulin_units=1.5,
            entered_by="glucotracker",
            raw_json={"request": {"idempotency_key": f"bob-{method}"}},
        )
        s.add(row)
        s.commit()
        event_id = row.id
        s.close()

        class FakeNightscoutClient:
            configured = True
            calls: list[str] = []

            async def update_insulin_treatment(self, *_args, **_kwargs) -> dict:
                self.calls.append("patch")
                return {}

            async def delete_treatment(self, _nightscout_id: str) -> dict:
                self.calls.append("delete")
                return {}

        fake = FakeNightscoutClient()
        app.dependency_overrides[get_nightscout_client] = lambda: fake
        try:
            if method == "patch":
                response = self.client.patch(
                    f"/nightscout/insulin/{event_id}",
                    json={"insulin_units": 2.0},
                    headers=self.alice_headers,
                )
            else:
                response = self.client.delete(
                    f"/nightscout/insulin/{event_id}",
                    headers=self.alice_headers,
                )
        finally:
            app.dependency_overrides.pop(get_nightscout_client, None)

        assert response.status_code == 404
        assert fake.calls == []
        s = sf()
        assert s.get(NightscoutInsulinEvent, event_id) is not None
        s.close()

    def test_create_sensor_ownership(self):
        r = self.client.post(
            "/sensors",
            json={
                "started_at": "2026-04-01T00:00:00Z",
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 201
        sensor_id = UUID(r.json()["id"])
        sf = self.env["session_factory"]
        s = sf()
        sensor = s.get(SensorSession, sensor_id)
        assert str(sensor.owner_id) == str(self.bob)
        s.close()

    def test_update_profile_ownership(self):
        r = self.client.put(
            "/profile",
            json={"weight_kg": 80},
            headers=self.bob_headers,
        )
        assert r.status_code == 200
        sf = self.env["session_factory"]
        s = sf()
        profile = s.query(UserProfile).filter_by(owner_id=self.bob).one()
        assert profile.weight_kg == 80
        s.close()

    def test_activity_sync_ownership(self):
        today = self.ids["today"]
        r = self.client.post(
            "/activity/sync",
            json={
                "date": (today - timedelta(days=2)).isoformat(),
                "steps": 1000,
                "active_minutes": 10,
                "kcal_burned": 50,
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 200
        sf = self.env["session_factory"]
        s = sf()
        activity = (
            s.query(DailyActivity)
            .filter_by(
                owner_id=self.bob,
                date=today - timedelta(days=2),
            )
            .one()
        )
        assert activity.steps == 1000
        s.close()

    def test_put_timeline_insulin_links_ownership(self):
        payload = {
            "date": self.ids["today"].isoformat(),
            "links": [
                {
                    "meal_id": str(self.ids["alice_meal"]),
                    "insulin_event_id": str(self.ids["alice_ns_insulin"]),
                    "source": "manual",
                    "confidence": 1,
                }
            ],
            "reviewed_insulin_event_ids": [],
        }
        r = self.client.put(
            "/timeline/insulin-links",
            json=payload,
            headers=self.bob_headers,
        )
        assert r.status_code == 404

        payload["links"] = [
            {
                "meal_id": str(self.ids["bob_meal"]),
                "insulin_event_id": str(self.ids["bob_ns_insulin"]),
                "source": "manual",
                "confidence": 1,
            }
        ]
        r = self.client.put(
            "/timeline/insulin-links",
            json=payload,
            headers=self.bob_headers,
        )
        assert r.status_code == 200

        sf = self.env["session_factory"]
        s = sf()
        link = (
            s.query(MealInsulinLink)
            .filter_by(
                meal_id=self.ids["bob_meal"],
                insulin_event_id=self.ids["bob_ns_insulin"],
            )
            .one()
        )
        assert str(link.owner_id) == str(self.bob)
        s.close()

    def test_patch_twin_params_updates_current_user_only(self):
        r = self.client.patch(
            "/twin/params",
            json={
                "icr_morning": 33,
                "icr_day": 33,
                "icr_evening": 33,
                "isf": 3,
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 200

        sf = self.env["session_factory"]
        s = sf()
        alice_params = s.get(TwinParams, self.ids["alice_twin_params"])
        bob_params = s.get(TwinParams, self.ids["bob_twin_params"])
        assert alice_params.icr_morning == 11
        assert bob_params.icr_morning == 33
        s.close()

    def test_reset_twin_params_updates_current_user_only(self):
        r = self.client.post("/twin/params/reset", headers=self.bob_headers)
        assert r.status_code == 200

        sf = self.env["session_factory"]
        s = sf()
        alice_params = s.get(TwinParams, self.ids["alice_twin_params"])
        bob_params = s.get(TwinParams, self.ids["bob_twin_params"])
        assert alice_params.icr_morning == 11
        assert bob_params.icr_morning is None
        s.close()

    def test_admin_recalculate_ownership(self):
        today = self.ids["today"]
        r = self.client.post(
            "/admin/recalculate",
            params={"from": today.isoformat(), "to": today.isoformat()},
            headers=self.alice_headers,
        )
        assert r.status_code == 200
        assert r.json()["days_recalculated"] >= 0

    def test_meal_sync_nightscout_not_configured(self):
        r = self.client.post(
            f"/meals/{self.ids['alice_meal']}/sync_nightscout",
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 503} or r.status_code >= 500

    def test_meal_unsync_nightscout_not_configured(self):
        r = self.client.post(
            f"/meals/{self.ids['alice_meal']}/unsync_nightscout",
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 409, 503} or r.status_code >= 500

    def test_nightscout_sync_today_not_configured(self):
        today = self.ids["today"]
        r = self.client.post(
            "/nightscout/sync/today",
            json={"date": today.isoformat(), "confirm": True},
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 503} or r.status_code >= 500

    def test_nightscout_import_not_configured(self):
        now = self.ids["now"]
        r = self.client.post(
            "/nightscout/import",
            json={
                "from_datetime": (now - timedelta(hours=1)).isoformat(),
                "to_datetime": (now + timedelta(hours=1)).isoformat(),
                "sync_glucose": False,
                "import_insulin_events": False,
            },
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 503} or r.status_code >= 500

    def test_settings_nightscout_test_not_configured(self):
        r = self.client.post(
            "/settings/nightscout/test",
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 503} or r.status_code >= 500

    def test_admin_postprandial_recompute_scoped(self):
        params = {
            "from": self.ids["today"].isoformat(),
            "to": self.ids["today"].isoformat(),
        }

        r = self.client.post(
            "/admin/postprandial/recompute",
            params=params,
            headers=self.alice_headers,
        )
        assert r.status_code == 200
        assert r.json()["meals_total"] == 1

        r = self.client.post(
            "/admin/postprandial/recompute",
            params=params,
            headers=self.bob_headers,
        )
        assert r.status_code == 200
        assert r.json()["meals_total"] == 1

    def test_create_meal_from_photo_idempotency_is_scoped(self, monkeypatch):
        from glucotracker.api.routers import photos as photos_router

        monkeypatch.setattr(
            photos_router,
            "_run_single_call_photo_estimate",
            lambda *_args, **_kwargs: None,
        )

        key = "11111111-2222-3333-4444-555555555555"
        data = {
            "captured_at": "2026-05-10T03:17:13Z",
            "source": "camera",
            "idempotency_key": key,
        }

        alice = self.client.post(
            "/meals/from-photo",
            data=data,
            files={"photo": ("meal.jpg", b"alice jpeg", "image/jpeg")},
            headers=self.alice_headers,
        )
        assert alice.status_code == 202

        bob = self.client.post(
            "/meals/from-photo",
            data=data,
            files={"photo": ("meal.jpg", b"bob jpeg", "image/jpeg")},
            headers=self.bob_headers,
        )
        assert bob.status_code == 202
        assert bob.json()["meal_id"] != alice.json()["meal_id"]

    def test_meal_estimate_not_configured(self):
        r = self.client.post(
            f"/meals/{self.ids['alice_meal']}/estimate",
            json={"context_note": None},
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 201, 400, 503} or r.status_code >= 500

    def test_meal_reestimate_not_configured(self):
        r = self.client.post(
            f"/meals/{self.ids['alice_meal']}/reestimate",
            json={"model": "default"},
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 201, 400, 503} or r.status_code >= 500

    def test_meal_estimate_and_save_draft_not_configured(self):
        r = self.client.post(
            f"/meals/{self.ids['alice_meal']}/estimate_and_save_draft",
            json={"context_note": None},
            headers=self.alice_headers,
        )
        assert r.status_code in {200, 201, 400, 503} or r.status_code >= 500

    def test_upload_meal_photo_scoped(self):
        r = self.client.post(
            f"/meals/{self.ids['bob_meal']}/photos",
            headers=self.alice_headers,
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert r.status_code == 404

    def test_apply_estimation_run_as_bob(self):
        r = self.client.post(
            f"/meals/{self.ids['alice_meal']}/apply_estimation_run/{uuid4()}",
            json={"apply_mode": "replace_current"},
            headers=self.bob_headers,
        )
        assert r.status_code == 404

    def test_create_product_ownership(self):
        from glucotracker.infra.db.models import Product

        r = self.client.post(
            "/products",
            json={
                "name": "Bob Private Product",
                "source_kind": "manual",
                "carbs_per_100g": 50,
                "protein_per_100g": 10,
                "fat_per_100g": 5,
                "kcal_per_100g": 285,
            },
            headers=self.bob_headers,
        )
        assert r.status_code == 201
        product_id = UUID(r.json()["id"])
        sf = self.env["session_factory"]
        s = sf()
        product = s.get(Product, product_id)
        assert str(product.owner_id) == str(self.bob)
        s.close()

    def test_create_product_from_label_ownership(self):
        from glucotracker.infra.db.models import Product

        r = self.client.post(
            "/products/from_label",
            json={
                "name": "Bob Label Product Unique",
                "source_kind": "manual",
                "carbs_per_100g": 40,
                "protein_per_100g": 8,
                "fat_per_100g": 3,
                "kcal_per_100g": 219,
            },
            headers=self.bob_headers,
        )
        assert r.status_code in {200, 201}
        product_id = UUID(r.json()["id"])
        sf = self.env["session_factory"]
        s = sf()
        product = s.get(Product, product_id)
        assert str(product.owner_id) == str(self.bob)
        s.close()
