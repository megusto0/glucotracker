"""Owner-isolation and activation tests for personalized IOB/COB fits."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import OnBoardModelFit, User
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.security import hash_password


def _add_fit(
    repository: OnBoardRepository,
    *,
    marker: str,
    status: str = "accepted",
    activate: bool = True,
) -> OnBoardModelFit:
    return repository.add_fit(
        kind="iob",
        scope_key="rapid",
        model_version="on-board-v2",
        params_json={"marker": marker},
        metrics_json={},
        training_from=None,
        training_to=None,
        sample_count=20,
        day_count=12,
        validation_mae_mmol=0.6,
        baseline_mae_mmol=0.8,
        confidence="medium",
        status=status,  # type: ignore[arg-type]
        activate=activate,
    )


def _add_cob_fit(
    repository: OnBoardRepository,
    *,
    scope_key: str,
    marker: str,
) -> OnBoardModelFit:
    return repository.add_fit(
        kind="cob",
        scope_key=scope_key,
        model_version="on-board-v2",
        params_json={"marker": marker},
        metrics_json={},
        training_from=None,
        training_to=None,
        sample_count=12,
        day_count=8,
        validation_mae_mmol=0.6,
        baseline_mae_mmol=0.8,
        confidence="medium",
        status="accepted",
        activate=True,
    )


def test_on_board_repository_requires_user_id(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]

    with session_factory() as session:
        with pytest.raises(
            ValueError,
            match="OnBoardRepository requires user_id",
        ):
            OnBoardRepository(session, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("read_method", ["get", "list"])
def test_active_fit_reads_and_activation_are_owner_scoped(
    api_client: TestClient,
    read_method: str,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    alice_id = UUID(str(api_client.app_state["current_user_id"]))

    with session_factory() as session:
        bob = User(
            username=f"bob-on-board-{uuid4().hex}",
            password_hash=hash_password("bob-pass"),
            role=UserRole.gluco,
        )
        session.add(bob)
        session.flush()
        bob_id = bob.id

        alice_repository = OnBoardRepository(session, alice_id)
        bob_repository = OnBoardRepository(session, bob_id)
        alice_old = _add_fit(alice_repository, marker="alice-old")
        bob_active = _add_fit(bob_repository, marker="bob-active")
        alice_new = _add_fit(alice_repository, marker="alice-new")
        session.commit()

        if read_method == "get":
            alice_result = alice_repository.get_active_fit("iob", "rapid")
            bob_result = bob_repository.get_active_fit("iob", "rapid")
        else:
            alice_result = alice_repository.list_active_fits("iob")[0]
            bob_result = bob_repository.list_active_fits("iob")[0]

        assert alice_result is not None
        assert bob_result is not None
        assert alice_result.id == alice_new.id
        assert bob_result.id == bob_active.id
        assert alice_result.owner_id == alice_id
        assert bob_result.owner_id == bob_id

        session.refresh(alice_old)
        session.refresh(bob_active)
        assert alice_old.active is False
        assert bob_active.active is True


def test_rejected_fit_does_not_replace_active_fit(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))

    with session_factory() as session:
        repository = OnBoardRepository(session, owner_id)
        accepted = _add_fit(repository, marker="accepted")
        rejected = _add_fit(
            repository,
            marker="rejected",
            status="rejected",
            activate=True,
        )
        session.commit()

        active = repository.get_active_fit("iob", "rapid")
        persisted_rejected = session.scalar(
            select(OnBoardModelFit).where(OnBoardModelFit.id == rejected.id)
        )

        assert active is not None
        assert active.id == accepted.id
        assert accepted.active is True
        assert persisted_rejected is not None
        assert persisted_rejected.status == "rejected"
        assert persisted_rejected.active is False


@pytest.mark.parametrize(
    ("replacement_scopes", "expected_keep_active", "expected_deactivated"),
    [
        ({"category:slow:solid"}, True, 1),
        (set(), False, 2),
    ],
)
def test_cob_scope_retirement_is_owner_scoped_and_preserves_history(
    api_client: TestClient,
    replacement_scopes: set[str],
    expected_keep_active: bool,
    expected_deactivated: int,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    alice_id = UUID(str(api_client.app_state["current_user_id"]))

    with session_factory() as session:
        bob = User(
            username=f"bob-cob-retirement-{uuid4().hex}",
            password_hash=hash_password("bob-pass"),
            role=UserRole.gluco,
        )
        session.add(bob)
        session.flush()

        alice_repository = OnBoardRepository(session, alice_id)
        bob_repository = OnBoardRepository(session, bob.id)
        alice_keep = _add_cob_fit(
            alice_repository,
            scope_key="category:slow:solid",
            marker="alice-keep",
        )
        alice_stale = _add_cob_fit(
            alice_repository,
            scope_key="pattern:stale",
            marker="alice-stale",
        )
        alice_iob = _add_fit(alice_repository, marker="alice-iob")
        bob_stale = _add_cob_fit(
            bob_repository,
            scope_key="pattern:stale",
            marker="bob-stale",
        )

        deactivated = alice_repository.deactivate_cob_scopes_except(
            replacement_scopes,
        )
        session.commit()

        for row in (alice_keep, alice_stale, alice_iob, bob_stale):
            session.refresh(row)
        all_rows = list(session.scalars(select(OnBoardModelFit)))

    assert deactivated == expected_deactivated
    assert alice_keep.active is expected_keep_active
    assert alice_stale.active is False
    assert alice_iob.active is True
    assert bob_stale.active is True
    assert {row.id for row in all_rows}.issuperset(
        {alice_keep.id, alice_stale.id, alice_iob.id, bob_stale.id}
    )
