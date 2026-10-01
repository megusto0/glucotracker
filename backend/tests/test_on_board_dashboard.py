"""Dashboard regressions for display-only personalized IOB and COB reads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from glucotracker.application.twin.kernels import (
    PersonalizedInsulinKernel,
    insulin_iob_remaining_fraction,
    personalized_insulin_iob_remaining_fraction,
)
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import ItemSourceKind, MealSource, MealStatus
from glucotracker.infra.db.models import Meal, MealItem, NightscoutInsulinEvent, User
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.security import hash_password, issue_access_token


def _auth_headers(user_id: UUID) -> dict[str, str]:
    token = issue_access_token(user_id, UserRole.gluco)
    return {"Authorization": f"Bearer {token}"}


def _dashboard(
    api_client: TestClient,
    *,
    from_datetime: datetime,
    to_datetime: datetime,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    response = api_client.get(
        "/glucose/dashboard",
        params={
            "from": from_datetime.isoformat(),
            "to": to_datetime.isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _add_insulin_event(
    *,
    owner_id: UUID,
    timestamp: datetime,
    units: float,
    event_type: str | None,
    insulin_type: str | None,
    marker: str,
) -> NightscoutInsulinEvent:
    return NightscoutInsulinEvent(
        owner_id=owner_id,
        source_key=f"on-board-dashboard-{marker}-{uuid4()}",
        timestamp=timestamp,
        insulin_units=units,
        event_type=event_type,
        insulin_type=insulin_type,
        notes=marker,
    )


def test_slow_meal_outside_chart_range_still_contributes_cob(
    api_client: TestClient,
) -> None:
    """A 420-minute COB lookback is independent of the visible chart range."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    as_of = datetime(2026, 7, 12, 12, 0)
    meal = Meal(
        owner_id=owner_id,
        eaten_at=as_of - timedelta(minutes=390),
        title="High-fat mixed meal",
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=40,
        total_protein_g=25,
        total_fat_g=40,
        total_fiber_g=5,
        total_kcal=620,
    )

    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add(meal)
        session.commit()

    body = _dashboard(
        api_client,
        from_datetime=as_of - timedelta(hours=2),
        to_datetime=as_of,
    )
    summary = body["summary"]

    assert body["food_events"] == []
    assert summary["cob_g"] > 0
    assert summary["cob_minutes_remaining"] > 0
    assert summary["cob_model_source"] == "macro_prior"


def test_only_rapid_bolus_contributes_iob_but_all_events_remain_markers(
    api_client: TestClient,
) -> None:
    """Legacy rapid boluses stay eligible; unmodeled deliveries remain visible."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    as_of = datetime(2026, 7, 12, 12, 0)
    event_at = as_of.replace(tzinfo=UTC)
    events = [
        _add_insulin_event(
            owner_id=owner_id,
            timestamp=event_at,
            units=2,
            event_type="Bolus",
            insulin_type=None,
            marker="legacy-rapid",
        ),
        _add_insulin_event(
            owner_id=owner_id,
            timestamp=event_at,
            units=5,
            event_type="Temp Basal",
            insulin_type=None,
            marker="temp-basal",
        ),
        _add_insulin_event(
            owner_id=owner_id,
            timestamp=event_at,
            units=6,
            event_type="Insulin",
            insulin_type="Lantus",
            marker="long-acting",
        ),
        _add_insulin_event(
            owner_id=owner_id,
            timestamp=event_at,
            units=7,
            event_type="Combo Bolus",
            insulin_type="NovoRapid",
            marker="combo",
        ),
    ]
    events[0].source_key = "manual_insulin:dashboard-editable"
    events[0].entered_by = "glucotracker"
    events[0].nightscout_id = "dashboard-editable"

    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add_all(events)
        session.commit()

    body = _dashboard(
        api_client,
        from_datetime=as_of - timedelta(hours=2),
        to_datetime=as_of,
    )
    summary = body["summary"]
    by_marker = {event["notes"]: event for event in body["insulin_events"]}

    assert set(by_marker) == {
        "legacy-rapid",
        "temp-basal",
        "long-acting",
        "combo",
    }
    assert by_marker["legacy-rapid"]["insulin_type"] is None
    assert by_marker["legacy-rapid"]["id"] == str(events[0].id)
    assert by_marker["legacy-rapid"]["editable"] is True
    assert by_marker["temp-basal"]["insulin_type"] is None
    assert by_marker["temp-basal"]["editable"] is False
    assert by_marker["long-acting"]["insulin_type"] == "Lantus"
    assert by_marker["combo"]["insulin_type"] == "NovoRapid"
    assert summary["iob_units"] == pytest.approx(2.0)
    assert summary["iob_minutes_remaining"] == 270
    assert summary["iob_model_source"] == "population"


def test_personalized_iob_fit_is_owner_scoped_on_dashboard(
    api_client: TestClient,
) -> None:
    """One user's active fit cannot change another user's IOB calculation."""
    alice_id = UUID(str(api_client.app_state["current_user_id"]))
    as_of = datetime(2026, 7, 12, 12, 0)
    elapsed_minutes = 60
    event_at = (as_of - timedelta(minutes=elapsed_minutes)).replace(tzinfo=UTC)
    parameters = PersonalizedInsulinKernel(
        fast_weight=0.9,
        fast_tau_minutes=10,
        slow_tau_minutes=20,
    )

    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        bob = User(
            username=f"on-board-bob-{uuid4().hex}",
            password_hash=hash_password("bob-pass"),
            role=UserRole.gluco,
        )
        session.add(bob)
        session.flush()
        bob_id = bob.id
        session.add_all(
            [
                _add_insulin_event(
                    owner_id=alice_id,
                    timestamp=event_at,
                    units=2,
                    event_type="Bolus",
                    insulin_type=None,
                    marker="alice-bolus",
                ),
                _add_insulin_event(
                    owner_id=bob_id,
                    timestamp=event_at,
                    units=2,
                    event_type="Bolus",
                    insulin_type=None,
                    marker="bob-bolus",
                ),
            ]
        )
        OnBoardRepository(session, alice_id).add_fit(
            kind="iob",
            scope_key="rapid",
            model_version="on-board-v2",
            params_json=parameters.to_mapping(),
            metrics_json={"validation": "leave-one-day-out"},
            training_from=None,
            training_to=None,
            sample_count=20,
            day_count=12,
            validation_mae_mmol=0.5,
            baseline_mae_mmol=0.8,
            confidence="high",
            status="accepted",
            activate=True,
        )
        session.commit()

    chart_from = as_of - timedelta(hours=2)
    alice = _dashboard(
        api_client,
        from_datetime=chart_from,
        to_datetime=as_of,
        headers=_auth_headers(alice_id),
    )
    bob = _dashboard(
        api_client,
        from_datetime=chart_from,
        to_datetime=as_of,
        headers=_auth_headers(bob_id),
    )
    alice_summary = alice["summary"]
    bob_summary = bob["summary"]
    expected_alice = round(
        2
        * personalized_insulin_iob_remaining_fraction(
            elapsed_minutes,
            parameters,
        ),
        2,
    )
    expected_bob = round(
        2 * insulin_iob_remaining_fraction(elapsed_minutes, 270),
        2,
    )

    assert [event["notes"] for event in alice["insulin_events"]] == ["alice-bolus"]
    assert [event["notes"] for event in bob["insulin_events"]] == ["bob-bolus"]
    assert alice_summary["iob_units"] == expected_alice
    assert bob_summary["iob_units"] == expected_bob
    assert alice_summary["iob_units"] != bob_summary["iob_units"]
    assert alice_summary["iob_model_source"] == "personalized"
    assert alice_summary["iob_model_confidence"] == "high"
    assert bob_summary["iob_model_source"] == "population"
    assert bob_summary["iob_model_confidence"] == "none"


def test_dashboard_exposes_each_meal_item_as_a_separate_food_marker(
    api_client: TestClient,
) -> None:
    """A multi-item meal is one COB episode but separate chart food markers."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    as_of = datetime(2026, 9, 21, 9, 0)
    meal = Meal(
        owner_id=owner_id,
        eaten_at=as_of - timedelta(minutes=50),
        title="Restaurant order",
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=133,
        total_protein_g=49.7,
        total_fat_g=71,
        total_fiber_g=4,
        total_kcal=1381,
        items=[
            MealItem(
                name="Картофель Фри",
                carbs_g=41,
                protein_g=3.9,
                fat_g=16,
                fiber_g=4,
                kcal=330,
                source_kind=ItemSourceKind.manual,
                position=0,
            ),
            MealItem(
                name="Фреш Маффин",
                carbs_g=34,
                protein_g=18,
                fat_g=18,
                kcal=368,
                source_kind=ItemSourceKind.manual,
                position=1,
            ),
            MealItem(
                name="Маффин с яйцом и свиной котлетой",
                carbs_g=26,
                protein_g=25,
                fat_g=25,
                kcal=434,
                source_kind=ItemSourceKind.manual,
                position=2,
            ),
            MealItem(
                name="Пирожок Вишневый",
                carbs_g=32,
                protein_g=2.8,
                fat_g=12,
                kcal=249,
                source_kind=ItemSourceKind.manual,
                position=3,
            ),
        ],
    )
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add(meal)
        session.commit()

    body = _dashboard(
        api_client, from_datetime=as_of - timedelta(hours=2), to_datetime=as_of
    )
    food_events = body["food_events"]

    assert len(food_events) == 4
    assert [event["title"] for event in food_events] == [
        "Картофель Фри",
        "Фреш Маффин",
        "Маффин с яйцом и свиной котлетой",
        "Пирожок Вишневый",
    ]
    assert [event["carbs_g"] for event in food_events] == [41, 34, 26, 32]
    assert {event["meal_id"] for event in food_events} == {str(meal.id)}
    assert sum(event["carbs_g"] for event in food_events) == pytest.approx(133)
    assert body["summary"]["cob_g"] > 0
