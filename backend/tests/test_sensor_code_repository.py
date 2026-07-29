"""Two-user isolation tests for the sensor-code repository."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from glucotracker.domain.auth import UserRole
from glucotracker.domain.sensor_codes import parse_sensor_data_matrix
from glucotracker.infra.db.models import SensorSession, User
from glucotracker.infra.db.repositories.sensor_codes import SensorCodeRepository
from glucotracker.infra.security import hash_password

RAW_CODES = (
    "0106977641010009112606221727062110LOT-A\x1d21SERIAL-A",
    "0106977641010009112606221727062110LOT-B\x1d21SERIAL-B",
)


@pytest.mark.parametrize("acting_index", [0, 1])
def test_repository_never_reads_or_attaches_cross_user_rows(
    api_client,
    acting_index: int,
) -> None:
    """Every repository operation remains scoped to its required user id."""
    session_factory = api_client.app_state["session_factory"]
    alice_id = api_client.app_state["current_user_id"]
    with session_factory() as session:
        bob = User(
            username=f"sensor-code-bob-{uuid4()}",
            password_hash=hash_password("bob-password"),
            role=UserRole.gluco,
        )
        session.add(bob)
        session.commit()
        bob_id = bob.id

    user_ids = (alice_id, bob_id)
    code_ids = []
    sensor_ids = []
    for index, user_id in enumerate(user_ids):
        with session_factory() as session:
            session.info["current_user_id"] = user_id
            sensor = SensorSession(
                owner_id=user_id,
                started_at=datetime(2026, 7, 1 + index),
                expected_life_days=15,
            )
            session.add(sensor)
            session.flush()
            code = SensorCodeRepository(session, user_id).save_code(
                parse_sensor_data_matrix(RAW_CODES[index]),
                scanned_at=datetime(2026, 7, 1 + index, tzinfo=UTC),
                sensor_session_id=None,
            )
            assert code is not None
            code_ids.append(code.id)
            sensor_ids.append(sensor.id)
            session.commit()

    acting_id = user_ids[acting_index]
    other_index = 1 - acting_index
    with session_factory() as session:
        repository = SensorCodeRepository(session, acting_id)
        assert {row.id for row in repository.list_codes()} == {code_ids[acting_index]}
        assert repository.get_code(code_ids[other_index]) is None
        assert repository.get_sensor(sensor_ids[other_index]) is None
        assert (
            repository.attach(code_ids[acting_index], sensor_ids[other_index])
            is None
        )
