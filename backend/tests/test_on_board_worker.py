"""Periodic personalized on-board fit worker tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from glucotracker.application.on_board.service import OnBoardFitService
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import OnBoardModelFit, User
from glucotracker.workers.on_board_fit import OnBoardFitWorker


@dataclass(frozen=True, slots=True)
class _RecordedRun:
    recorded_fit_count: int = 1


def _add_user(api_client: TestClient, role: UserRole) -> UUID:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        user = User(
            username=f"on-board-worker-{role.value}-{uuid4().hex}",
            password_hash="hash",
            role=role,
        )
        session.add(user)
        session.commit()
        return UUID(str(user.id))


def _record_fit(service: OnBoardFitService, marker: str) -> _RecordedRun:
    service.repository.add_fit(
        kind="iob",
        scope_key="rapid",
        model_version="on-board-v2-worker-test",
        params_json={"marker": marker},
        metrics_json={},
        training_from=None,
        training_to=None,
        sample_count=1,
        day_count=1,
        validation_mae_mmol=0.5,
        baseline_mae_mmol=0.7,
        confidence="low",
        status="accepted",
        activate=True,
    )
    return _RecordedRun()


@pytest.mark.asyncio
async def test_worker_loop_offloads_synchronous_fit_from_event_loop(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = OnBoardFitWorker(api_client.app_state["session_factory"])
    offloaded: list[object] = []

    async def fake_to_thread(function: object, *args: object, **kwargs: object) -> None:
        offloaded.append(function)
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    with pytest.raises(asyncio.CancelledError):
        await worker.run_forever()

    assert offloaded == [worker.run_once]


def test_worker_fits_gluco_users_only(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    first_gluco_id = UUID(str(api_client.app_state["current_user_id"]))
    second_gluco_id = _add_user(api_client, UserRole.gluco)
    food_id = _add_user(api_client, UserRole.food)
    called_user_ids: list[UUID] = []

    def fake_fit_recent(service: OnBoardFitService) -> _RecordedRun:
        called_user_ids.append(service.user_id)
        return _record_fit(service, str(service.user_id))

    monkeypatch.setattr(OnBoardFitService, "fit_recent", fake_fit_recent)

    touched = OnBoardFitWorker(session_factory).run_once(force=True)

    assert touched == 2
    assert set(called_user_ids) == {first_gluco_id, second_gluco_id}
    assert food_id not in called_user_ids
    with session_factory() as session:
        rows = list(session.scalars(select(OnBoardModelFit)))
        assert {row.owner_id for row in rows} == {
            first_gluco_id,
            second_gluco_id,
        }


def test_worker_rolls_back_one_user_and_continues_with_the_next(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    failed_user_id = UUID(str(api_client.app_state["current_user_id"]))
    successful_user_id = _add_user(api_client, UserRole.gluco)
    called_user_ids: list[UUID] = []

    def fake_fit_recent(service: OnBoardFitService) -> _RecordedRun:
        called_user_ids.append(service.user_id)
        run = _record_fit(service, str(service.user_id))
        if service.user_id == failed_user_id:
            raise RuntimeError("user-specific fit failure")
        return run

    monkeypatch.setattr(OnBoardFitService, "fit_recent", fake_fit_recent)

    touched = OnBoardFitWorker(session_factory).run_once(force=True)

    assert touched == 1
    assert set(called_user_ids) == {failed_user_id, successful_user_id}
    with session_factory() as session:
        rows = list(session.scalars(select(OnBoardModelFit)))
        assert len(rows) == 1
        assert rows[0].owner_id == successful_user_id
        assert rows[0].params_json == {"marker": str(successful_user_id)}


def test_worker_skips_recent_attempt_but_force_reruns_it(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    called_user_ids: list[UUID] = []

    def fake_fit_recent(service: OnBoardFitService) -> _RecordedRun:
        called_user_ids.append(service.user_id)
        return _record_fit(service, f"attempt-{len(called_user_ids)}")

    monkeypatch.setattr(OnBoardFitService, "fit_recent", fake_fit_recent)
    worker = OnBoardFitWorker(session_factory)

    assert worker.run_once() == 1
    with session_factory() as session:
        latest = session.scalar(
            select(OnBoardModelFit).where(OnBoardModelFit.owner_id == owner_id)
        )
        assert latest is not None
        latest.fitted_at = datetime.now(UTC) - timedelta(hours=23)
        session.commit()

    assert worker.run_once() == 0
    assert worker.run_once(force=True) == 1
    assert called_user_ids == [owner_id, owner_id]

    with session_factory() as session:
        rows = list(
            session.scalars(
                select(OnBoardModelFit).where(OnBoardModelFit.owner_id == owner_id)
            )
        )
        assert len(rows) == 2
        assert sum(row.active for row in rows) == 1
