"""Daily retrospective therapy review API tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.application.therapy_review import (
    THERAPY_REVIEW_MODEL_VERSION,
)
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    HealthConnectRecord,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)


def _meal(session, owner_id, at: datetime, carbs: float, title: str) -> Meal:
    row = Meal(
        owner_id=owner_id,
        eaten_at=at,
        title=title,
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=carbs,
        total_protein_g=4,
        total_fat_g=4,
        total_kcal=carbs * 5,
    )
    session.add(row)
    session.flush()
    return row


def _insulin(session, owner_id, at: datetime, units: float) -> None:
    key = f"review-insulin-{uuid4()}"
    session.add(
        NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key=key,
            nightscout_id=key,
            timestamp=at,
            insulin_units=units,
            event_type="Insulin",
            entered_by="test",
        )
    )


def _glucose(session, owner_id, at: datetime, value: float, key: str) -> None:
    session.add(
        NightscoutGlucoseEntry(
            owner_id=owner_id,
            source_key=key,
            timestamp=at,
            value_mmol_l=value,
            value_mg_dl=round(value * 18.0182),
            source="CGM",
        )
    )


def test_daily_review_lists_meal_and_falling_carb_correction(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 25)
    meal_at = day + timedelta(hours=10)
    rescue_at = day + timedelta(hours=12)

    with session_factory() as session:
        meal = _meal(session, owner_id, meal_at, 40, "Обед")
        _insulin(session, owner_id, meal_at, 4)
        for days_ago in (7, 14, 21):
            historical_at = meal_at - timedelta(days=days_ago)
            _meal(session, owner_id, historical_at, 40, "Обед")
            _insulin(session, owner_id, historical_at, 4)

        rescue = _meal(session, owner_id, rescue_at, 7, "Небольшой перекус")
        for index, value in enumerate((6.4, 5.4, 4.4)):
            _glucose(
                session,
                owner_id,
                rescue_at - timedelta(minutes=20 - index * 10),
                value,
                f"review-rescue-pre-{index}",
            )
        _glucose(
            session,
            owner_id,
            rescue_at + timedelta(hours=2),
            5.2,
            "review-rescue-after",
        )
        session.commit()

    response = api_client.get(
        "/glucose/therapy-review",
        params={
            "date": "2026-07-25",
            "target_mmol_l": 6,
            "horizon_minutes": 120,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-07-25"
    assert body["horizon_minutes"] == 120
    assert body["cached"] is False
    assert body["model_version"] == THERAPY_REVIEW_MODEL_VERSION
    by_key = {
        frozenset(item["key"].split("|")): item
        for item in body["items"]
    }
    meal_item = next(
        item
        for key, item in by_key.items()
        if f"m:{meal.id}" in key
    )
    assert meal_item["classification"] == "meal"
    assert meal_item["value_unit"] == "U"
    assert meal_item["actual_value"] == 4.0

    rescue_item = next(
        item
        for key, item in by_key.items()
        if f"m:{rescue.id}" in key
    )
    assert rescue_item["classification"] == "carb_correction"
    assert rescue_item["value_unit"] == "g"
    assert rescue_item["actual_value"] == 7.0
    assert rescue_item["calculated_value"] == 15.0
    assert rescue_item["glucose_start_normalized"] == 4.4
    assert rescue_item["glucose_after_normalized"] == 5.2
    assert rescue_item["adjusted_actual_value"] == 10.2
    assert rescue_item["adjustment_status"] == "ready"

    cached_response = api_client.get(
        "/glucose/therapy-review",
        params={
            "date": "2026-07-25",
            "target_mmol_l": 6,
            "horizon_minutes": 120,
        },
    )
    assert cached_response.status_code == 200
    cached_body = cached_response.json()
    assert cached_body["cached"] is True
    assert cached_body["computed_at"] == body["computed_at"]
    assert cached_body["items"] == body["items"]

    refreshed_response = api_client.get(
        "/glucose/therapy-review",
        params={
            "date": "2026-07-25",
            "target_mmol_l": 6,
            "horizon_minutes": 120,
            "force_recalculate": True,
        },
    )
    assert refreshed_response.status_code == 200
    assert refreshed_response.json()["cached"] is False


def _review(api_client: TestClient, day: str = "2026-07-25") -> dict:
    response = api_client.get(
        "/glucose/therapy-review",
        params={"date": day, "target_mmol_l": 6, "horizon_minutes": 120},
    )
    assert response.status_code == 200
    return response.json()


def test_todays_review_is_cached_until_something_it_reads_changes(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The open day used to recompute on every request; now only on new data."""
    monkeypatch.setattr(
        "glucotracker.application.time.local_now",
        lambda: datetime(2026, 7, 25, 18),
    )
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 25)
    with session_factory() as session:
        _meal(session, owner_id, day + timedelta(hours=9), 40, "Завтрак")
        session.commit()

    first = _review(api_client)
    assert first["cached"] is False

    second = _review(api_client)
    assert second["cached"] is True
    assert second["computed_at"] == first["computed_at"]

    with session_factory() as session:
        _glucose(
            session,
            owner_id,
            day + timedelta(hours=11),
            7.4,
            "review-fingerprint-cgm",
        )
        session.commit()

    after_new_data = _review(api_client)
    assert after_new_data["cached"] is False
    assert after_new_data["computed_at"] != first["computed_at"]


def test_a_late_import_invalidates_an_already_stored_day(
    api_client: TestClient,
) -> None:
    """A closed day used to stay stale until the model version moved."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 25)
    with session_factory() as session:
        _meal(session, owner_id, day + timedelta(hours=9), 40, "Завтрак")
        session.commit()

    assert len(_review(api_client)["items"]) == 1
    assert _review(api_client)["cached"] is True

    with session_factory() as session:
        _insulin(session, owner_id, day + timedelta(hours=19), 3.0)
        session.commit()

    late = _review(api_client)
    assert late["cached"] is False
    assert len(late["items"]) == 2


def _curve(session, owner_id, start: datetime, values: list[float]) -> None:
    """Write one CGM reading every ten minutes from ``start``."""
    for index, value in enumerate(values):
        _glucose(
            session,
            owner_id,
            start + timedelta(minutes=10 * index),
            value,
            f"curve-{start.isoformat()}-{index}",
        )


def test_a_spike_that_lands_on_target_is_not_reported_as_a_clean_episode(
    api_client: TestClient,
) -> None:
    """Reported 2026-08-04: pancakes peaked at 13.1 and ended at 5.3, so the
    hindsight adjustment called the dose optimal and said nothing about the
    two hours spent above the high band."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 25)
    meal_at = day + timedelta(hours=12)
    with session_factory() as session:
        _meal(session, owner_id, meal_at, 62, "Панкейки")
        _insulin(session, owner_id, meal_at, 8.5)
        _curve(
            session,
            owner_id,
            meal_at,
            [6.2, 8.0, 10.4, 12.3, 13.1, 12.4, 10.8, 8.9, 7.1, 6.0, 5.6, 5.4, 5.3],
        )
        session.commit()

    item = _review(api_client)["items"][0]

    assert item["peak_mmol_l"] == 13.1
    assert item["peak_after_minutes"] == 40
    assert item["outcome_quality"] == "spike"
    assert item["minutes_above_high"] >= 40
    # The endpoint is on target, so the total dose is not what went wrong.
    assert item["glucose_after_normalized"] == 5.3
    assert any("вопрос ко времени укола" in note for note in item["notes"])
    assert len(item["trajectory"]) == 13


def test_a_dose_that_caused_a_hypo_is_never_told_to_go_higher(
    api_client: TestClient,
) -> None:
    """A dip to 3.4 that recovers by the horizon used to read as zero error,
    and the upward adjustment then asked for more insulin."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 25)
    meal_at = day + timedelta(hours=9)
    with session_factory() as session:
        _meal(session, owner_id, meal_at, 40, "Завтрак")
        _insulin(session, owner_id, meal_at, 6.0)
        _curve(
            session,
            owner_id,
            meal_at,
            [7.0, 6.1, 5.2, 4.3, 3.6, 3.4, 3.9, 4.8, 5.6, 6.3, 6.8, 7.2, 7.4],
        )
        session.commit()

    item = _review(api_client)["items"][0]

    assert item["nadir_mmol_l"] == 3.4
    assert item["outcome_quality"] == "low"
    assert item["minutes_below_low"] >= 20
    # Ending at 7.4 against a target of 6.0 would otherwise add ~0.5 U.
    assert item["glucose_after_normalized"] == 7.4
    assert item["adjusted_actual_value"] == item["actual_value"]
    assert any("провал до 3.4" in note for note in item["notes"])


def test_a_flat_landing_keeps_the_ordinary_adjustment(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 25)
    meal_at = day + timedelta(hours=9)
    with session_factory() as session:
        _meal(session, owner_id, meal_at, 40, "Завтрак")
        _insulin(session, owner_id, meal_at, 4.0)
        _curve(
            session,
            owner_id,
            meal_at,
            [6.0, 6.4, 7.1, 7.6, 7.9, 7.8, 7.5, 7.2, 7.0, 6.9, 6.8, 6.8, 6.9],
        )
        session.commit()

    item = _review(api_client)["items"][0]

    assert item["outcome_quality"] == "in_range"
    assert item["minutes_above_high"] == 0
    assert item["minutes_below_low"] == 0
    # 4.0 + (6.9 − 6.0) / ISF, with nothing on the path to override it.
    assert item["adjusted_actual_value"] > item["actual_value"]


def test_review_reports_sleep_and_marks_the_meal_that_followed_it(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    day = datetime(2026, 7, 25)
    with session_factory() as session:
        _meal(session, owner_id, day + timedelta(hours=9), 40, "Завтрак")
        _meal(session, owner_id, day + timedelta(hours=20), 60, "Ужин")
        session.add(
            HealthConnectRecord(
                owner_id=owner_id,
                record_id="review-sleep",
                record_type="SleepSessionRecord",
                start_time=datetime(2026, 7, 25, 0, 0, tzinfo=UTC),
                end_time=datetime(2026, 7, 25, 6, 0, tzinfo=UTC),
                payload={},
            )
        )
        session.commit()

    body = _review(api_client)
    assert [state["kind"] for state in body["body_states"]] == ["sleep"]
    sleep = body["body_states"][0]
    assert sleep["source"] == "recorded"
    assert sleep["confidence"] == "high"
    assert sleep["total_minutes"] == 360
    contexts = [item["body_context"] for item in body["items"]]
    assert contexts == [["after_sleep"], []]
