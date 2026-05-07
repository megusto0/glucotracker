"""Tests for database session guardrails."""

from datetime import date

import pytest
from sqlalchemy import text

from glucotracker.infra.db.models import DailyTotal


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
