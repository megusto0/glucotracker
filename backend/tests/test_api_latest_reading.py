"""Tests for the nightscout latest-reading endpoint and glucose sync scenarios."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


def _insert_glucose_entry(session: Session, **overrides) -> None:
    owner_id = session.info["current_user_id"]
    defaults = {
        "id": uuid4().hex,
        "owner_id": owner_id.hex,
        "source_key": f"test-{datetime.now(UTC).isoformat()}",
        "nightscout_id": None,
        "timestamp": datetime.now(UTC),
        "value_mmol_l": 6.5,
        "value_mg_dl": 117,
        "trend": "Flat",
        "source": "test",
        "raw_json": "{}",
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    params = ", ".join(f":{k}" for k in defaults.keys())
    session.execute(
        text(f"INSERT INTO nightscout_glucose_entries ({cols}) VALUES ({params})"),
        defaults,
    )
    session.commit()


def _insert_sensor(session: Session, **overrides) -> str:
    sensor_id = overrides.get("id", str(uuid4()))
    owner_id = session.info["current_user_id"]
    defaults = {
        "id": sensor_id,
        "owner_id": owner_id.hex,
        "source": "manual",
        "vendor": "Test",
        "model": "Test",
        "label": "Test Sensor",
        "started_at": datetime.now(UTC) - timedelta(days=5),
        "ended_at": None,
        "expected_life_days": 15,
        "notes": None,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    params = ", ".join(f":{k}" for k in defaults.keys())
    session.execute(
        text(f"INSERT INTO sensor_sessions ({cols}) VALUES ({params})"),
        defaults,
    )
    session.commit()
    return sensor_id


class TestLatestReadingEndpoint:
    def test_returns_empty_when_no_entries(self, api_client):
        response = api_client.get("/nightscout/latest-reading")
        assert response.status_code == 200
        data = response.json()
        assert data["timestamp"] is None
        assert data["value_mmol_l"] is None
        assert data["trend"] is None
        assert data["sensor_id"] is None
        assert data["total_entries"] == 0

    def test_returns_latest_entry(self, api_client, db_engine):
        session_factory = api_client.app_state["session_factory"]
        session = session_factory()

        ts1 = datetime.now(UTC) - timedelta(minutes=10)
        ts2 = datetime.now(UTC) - timedelta(minutes=5)
        _insert_glucose_entry(
            session, source_key="key-1", timestamp=ts1, value_mmol_l=5.5
        )
        _insert_glucose_entry(
            session,
            source_key="key-2",
            timestamp=ts2,
            value_mmol_l=6.8,
            trend="FortyFiveUp",
        )
        session.close()

        response = api_client.get("/nightscout/latest-reading")
        assert response.status_code == 200
        data = response.json()
        assert data["timestamp"] is not None
        assert abs(data["value_mmol_l"] - 6.8) < 0.01
        assert data["trend"] == "FortyFiveUp"
        assert data["total_entries"] == 2

    def test_returns_sensor_id_when_active(self, api_client, db_engine):
        session_factory = api_client.app_state["session_factory"]
        session = session_factory()

        sensor_start = datetime.now(UTC) - timedelta(days=2)
        reading_ts = datetime.now(UTC) - timedelta(minutes=5)
        sensor_id = _insert_sensor(session, started_at=sensor_start)
        _insert_glucose_entry(
            session, source_key="key-s", timestamp=reading_ts, value_mmol_l=7.2
        )
        session.close()

        response = api_client.get("/nightscout/latest-reading")
        assert response.status_code == 200
        data = response.json()
        assert data["sensor_id"] == sensor_id


class TestSyncScenarios:
    def test_normal_update_cycle(self, api_client, db_engine):
        session_factory = api_client.app_state["session_factory"]
        session = session_factory()

        sensor_start = datetime.now(UTC) - timedelta(days=2)
        _insert_sensor(session, started_at=sensor_start)

        for i in range(5):
            ts = datetime.now(UTC) - timedelta(minutes=(5 - i) * 5)
            _insert_glucose_entry(
                session,
                source_key=f"key-{i}",
                timestamp=ts,
                value_mmol_l=5.5 + i * 0.3,
            )

        session.close()

        response = api_client.get("/nightscout/latest-reading")
        data = response.json()
        assert data["total_entries"] == 5
        assert data["timestamp"] is not None

    def test_data_delay_no_recent_entries(self, api_client, db_engine):
        session_factory = api_client.app_state["session_factory"]
        session = session_factory()

        old_ts = datetime.now(UTC) - timedelta(hours=2)
        _insert_glucose_entry(
            session, source_key="old-1", timestamp=old_ts, value_mmol_l=6.0
        )
        session.close()

        response = api_client.get("/nightscout/latest-reading")
        data = response.json()
        assert data["total_entries"] == 1
        ts = datetime.fromisoformat(data["timestamp"])
        assert ts < datetime.now(UTC) - timedelta(minutes=30)

    def test_sensor_change_detection(self, api_client, db_engine):
        session_factory = api_client.app_state["session_factory"]
        session = session_factory()

        old_sensor_start = datetime.now(UTC) - timedelta(days=20)
        new_sensor_start = datetime.now(UTC) - timedelta(days=2)
        _insert_sensor(
            session,
            started_at=old_sensor_start,
            ended_at=datetime.now(UTC) - timedelta(days=5),
            label="Old Sensor",
        )
        new_sensor_id = _insert_sensor(
            session, started_at=new_sensor_start, label="New Sensor"
        )

        old_ts = datetime.now(UTC) - timedelta(days=7)
        new_ts = datetime.now(UTC) - timedelta(minutes=5)
        _insert_glucose_entry(
            session, source_key="old-key", timestamp=old_ts, value_mmol_l=5.0
        )
        _insert_glucose_entry(
            session, source_key="new-key", timestamp=new_ts, value_mmol_l=6.5
        )
        session.close()

        response = api_client.get("/nightscout/latest-reading")
        data = response.json()
        assert data["sensor_id"] == new_sensor_id

    def test_multiple_entries_same_timestamp(self, api_client, db_engine):
        session_factory = api_client.app_state["session_factory"]
        session = session_factory()

        ts = datetime.now(UTC) - timedelta(minutes=5)
        _insert_glucose_entry(
            session, source_key="dup-1", timestamp=ts, value_mmol_l=6.0
        )
        _insert_glucose_entry(
            session, source_key="dup-2", timestamp=ts, value_mmol_l=6.1
        )
        session.close()

        response = api_client.get("/nightscout/latest-reading")
        data = response.json()
        assert data["total_entries"] == 2
        assert data["value_mmol_l"] in [6.0, 6.1]
