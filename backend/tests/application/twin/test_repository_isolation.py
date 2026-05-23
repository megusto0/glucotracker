"""Two-user isolation tests for the twin repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import TwinFitLog, TwinParams, User
from glucotracker.infra.db.repositories.twin import TwinRepository
from glucotracker.infra.security import hash_password


@pytest.mark.parametrize("read_kind", ["params", "logs"])
def test_twin_repository_filters_by_current_user_id(
    api_client: TestClient,
    read_kind: str,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    alice_id = UUID(str(api_client.app_state["current_user_id"]))
    with session_factory() as session:
        bob = User(
            username=f"bob-{uuid4().hex}",
            password_hash=hash_password("bob-pass"),
            role=UserRole.gluco,
        )
        session.add(bob)
        session.flush()
        bob_id = bob.id
        session.add_all(
            [
                TwinParams(owner_id=alice_id, icr_morning=11.0),
                TwinParams(owner_id=bob_id, icr_morning=22.0),
                TwinFitLog(
                    owner_id=alice_id,
                    fit_at=datetime(2026, 5, 1, 8, 0),
                    params_snapshot={"owner": "alice"},
                    method="manual",
                ),
                TwinFitLog(
                    owner_id=bob_id,
                    fit_at=datetime(2026, 5, 1, 9, 0),
                    params_snapshot={"owner": "bob"},
                    method="manual",
                ),
            ]
        )
        session.commit()

    with session_factory() as session:
        alice_repo = TwinRepository(session, alice_id)
        bob_repo = TwinRepository(session, bob_id)

        if read_kind == "params":
            assert alice_repo.get_or_create_params().icr_morning == 11.0
            assert bob_repo.get_or_create_params().icr_morning == 22.0
        else:
            assert alice_repo.list_fit_logs()[0].params_snapshot == {"owner": "alice"}
            assert bob_repo.list_fit_logs()[0].params_snapshot == {"owner": "bob"}
