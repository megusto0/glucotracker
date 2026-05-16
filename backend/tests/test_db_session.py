"""Tests for database session guardrails."""

from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy import text

from glucotracker.infra.db.models import DailyActivity, DailyTotal


def test_owner_date_models_use_composite_primary_keys() -> None:
    """ORM primary keys must match the forward-only owner scoping migration."""
    assert [column.name for column in inspect(DailyTotal).primary_key] == [
        "owner_id",
        "date",
    ]
    assert [column.name for column in inspect(DailyActivity).primary_key] == [
        "owner_id",
        "date",
    ]


def test_read_only_session_rejects_orm_writes(api_client) -> None:
    session_factory = api_client.app_state["session_factory"]
    session = session_factory()
    session.info["read_only"] = True

    session.add(DailyTotal(date=date(2026, 5, 7)))
    with pytest.raises(RuntimeError, match="Read-only database session"):
        session.flush()

    session.close()


def test_read_only_session_rejects_raw_sql_writes(api_client) -> None:
    session_factory = api_client.app_state["session_factory"]
    session = session_factory()
    session.info["read_only"] = True

    assert session.execute(text("SELECT 1")).scalar_one() == 1
    with pytest.raises(RuntimeError, match="Read-only database session"):
        session.execute(
            text("INSERT INTO daily_totals (date) VALUES (:date)"),
            {"date": "2026-05-07"},
        )

    session.close()
