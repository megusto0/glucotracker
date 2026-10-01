"""Tests for the sensor auto-rollover guarantee."""

from datetime import datetime, timedelta

from sqlalchemy import select

from glucotracker.application.sensor_lifecycle import (
    SENSOR_ROLLOVER_NOTE,
    rollover_expired_sensor_sessions,
)
from glucotracker.infra.db.models import (
    NightscoutGlucoseEntry,
    SensorSession,
    utc_now,
)
from glucotracker.infra.db.repositories.sensor_codes import _as_utc


def _add_glucose(session, owner_id, timestamp: datetime) -> None:
    session.add(
        NightscoutGlucoseEntry(
            owner_id=owner_id,
            source_key=f"rollover-{timestamp.isoformat()}",
            timestamp=timestamp,
            value_mmol_l=5.0,
        )
    )


def _sensors(session, owner_id):
    return session.scalars(
        select(SensorSession)
        .where(SensorSession.owner_id == owner_id)
        .order_by(SensorSession.started_at.asc())
    ).all()


def test_rollover_finishes_at_last_point_before_new_stream(api_client) -> None:
    """An expired sensor ends on the last point of its own stream."""
    session_factory = api_client.app_state["session_factory"]
    owner_id = api_client.app_state["current_user_id"]
    now = utc_now()
    started = now - timedelta(days=16)
    cutoff = started + timedelta(days=15)
    new_first = cutoff + timedelta(hours=6)

    with session_factory() as session:
        session.add(
            SensorSession(
                owner_id=owner_id,
                source="auto_cgm",
                started_at=started,
                expected_life_days=15,
            )
        )
        for timestamp in (
            started,
            cutoff,
            new_first,
            new_first + timedelta(minutes=5),
        ):
            _add_glucose(session, owner_id, timestamp)
        session.commit()

    with session_factory() as session:
        assert rollover_expired_sensor_sessions(session) == 1

    with session_factory() as session:
        sensors = _sensors(session, owner_id)
        assert len(sensors) == 2
        old, new = sensors
        assert old.ended_at is not None
        assert _as_utc(old.ended_at) == cutoff
        assert SENSOR_ROLLOVER_NOTE in (old.notes or "")
        assert new.ended_at is None
        assert _as_utc(new.started_at) == new_first
        assert new.source == "auto_cgm"


def test_rollover_ignores_outages_before_the_expected_life(api_client) -> None:
    """A signal loss inside the sensor life does not finish the session."""
    session_factory = api_client.app_state["session_factory"]
    owner_id = api_client.app_state["current_user_id"]
    now = utc_now()
    started = now - timedelta(days=16)
    cutoff = started + timedelta(days=15)
    outage = started + timedelta(days=10)
    new_first = cutoff + timedelta(hours=3)

    with session_factory() as session:
        session.add(
            SensorSession(
                owner_id=owner_id,
                source="auto_cgm",
                started_at=started,
                expected_life_days=15,
            )
        )
        for timestamp in (
            started,
            outage,
            outage + timedelta(hours=1),
            cutoff,
            new_first,
            new_first + timedelta(minutes=5),
        ):
            _add_glucose(session, owner_id, timestamp)
        session.commit()

    with session_factory() as session:
        assert rollover_expired_sensor_sessions(session) == 1

    with session_factory() as session:
        old = _sensors(session, owner_id)[0]
        assert _as_utc(old.ended_at) == cutoff


def test_rollover_splits_a_continuous_stream_at_the_life_boundary(
    api_client,
) -> None:
    """Without a stream gap the session still ends on the life boundary."""
    session_factory = api_client.app_state["session_factory"]
    owner_id = api_client.app_state["current_user_id"]
    now = utc_now()
    started = now - timedelta(days=16)
    cutoff = started + timedelta(days=15)

    readings = [started]
    moment = cutoff - timedelta(hours=1)
    while moment <= cutoff + timedelta(hours=1):
        readings.append(moment)
        moment += timedelta(minutes=10)

    with session_factory() as session:
        session.add(
            SensorSession(
                owner_id=owner_id,
                source="auto_cgm",
                started_at=started,
                expected_life_days=15,
            )
        )
        for timestamp in readings:
            _add_glucose(session, owner_id, timestamp)
        session.commit()

    with session_factory() as session:
        assert rollover_expired_sensor_sessions(session) == 1

    with session_factory() as session:
        old, new = _sensors(session, owner_id)
        assert _as_utc(old.ended_at) <= cutoff
        assert _as_utc(old.ended_at) >= cutoff - timedelta(minutes=10)
        assert new.ended_at is None
        assert _as_utc(new.started_at) > cutoff
        assert _as_utc(new.started_at) == _as_utc(old.ended_at) + timedelta(minutes=10)


def test_rollover_leaves_a_fresh_sensor_alone(api_client) -> None:
    """A sensor inside its expected life is never touched."""
    session_factory = api_client.app_state["session_factory"]
    owner_id = api_client.app_state["current_user_id"]
    now = utc_now()
    started = now - timedelta(days=3)

    with session_factory() as session:
        session.add(
            SensorSession(
                owner_id=owner_id,
                source="auto_cgm",
                started_at=started,
                expected_life_days=15,
            )
        )
        _add_glucose(session, owner_id, started)
        _add_glucose(session, owner_id, now)
        session.commit()

    with session_factory() as session:
        assert rollover_expired_sensor_sessions(session) == 0

    with session_factory() as session:
        sensors = _sensors(session, owner_id)
        assert len(sensors) == 1
        assert sensors[0].ended_at is None


def test_rollover_can_be_scoped_to_one_user(api_client) -> None:
    """The one-off fix only touches the requested owner."""
    from uuid import uuid4

    from glucotracker.domain.auth import UserRole
    from glucotracker.infra.db.models import User
    from glucotracker.infra.security import hash_password

    session_factory = api_client.app_state["session_factory"]
    owner_id = api_client.app_state["current_user_id"]
    now = utc_now()
    started = now - timedelta(days=16)
    cutoff = started + timedelta(days=15)

    with session_factory() as session:
        other = User(
            username=f"rollover-other-{uuid4()}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        other_id = other.id
        for uid in (owner_id, other_id):
            session.add(
                SensorSession(
                    owner_id=uid,
                    source="auto_cgm",
                    started_at=started,
                    expected_life_days=15,
                )
            )
            _add_glucose(session, uid, started)
            _add_glucose(session, uid, cutoff)
            _add_glucose(session, uid, cutoff + timedelta(hours=2))
        session.commit()

    with session_factory() as session:
        assert rollover_expired_sensor_sessions(session, user_id=owner_id) == 1

    with session_factory() as session:
        assert _sensors(session, owner_id)[0].ended_at is not None
        assert _sensors(session, other_id)[0].ended_at is None
