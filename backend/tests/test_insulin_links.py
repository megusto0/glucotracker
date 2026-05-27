"""Food/insulin link review rules."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    Meal,
    MealInsulinEpisodeSnapshot,
    MealInsulinLink,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    User,
)
from glucotracker.infra.security import hash_password, issue_access_token


def _headers(user_id: UUID, role: UserRole = UserRole.gluco) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, role)}"}


def _seed_user(session: Session, username: str, role: UserRole) -> User:
    user = User(
        username=username,
        password_hash=hash_password("test-password"),
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def _seed_meal(
    session: Session,
    owner_id: UUID,
    title: str,
    eaten_at: datetime,
    *,
    carbs: float = 20,
) -> Meal:
    meal = Meal(
        owner_id=owner_id,
        eaten_at=eaten_at,
        title=title,
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=carbs,
        total_protein_g=5,
        total_fat_g=3,
        total_kcal=120,
    )
    session.add(meal)
    session.flush()
    return meal


def _seed_insulin(
    session: Session,
    owner_id: UUID,
    source_key: str,
    timestamp: datetime,
    *,
    units: float = 2,
    event_type: str = "Correction Bolus",
) -> NightscoutInsulinEvent:
    event = NightscoutInsulinEvent(
        owner_id=owner_id,
        source_key=source_key,
        nightscout_id=source_key,
        timestamp=timestamp,
        insulin_units=units,
        event_type=event_type,
        entered_by="Nightscout",
    )
    session.add(event)
    session.flush()
    return event


def _seed_glucose(
    session: Session,
    owner_id: UUID,
    source_key: str,
    timestamp: datetime,
    value: float,
) -> NightscoutGlucoseEntry:
    entry = NightscoutGlucoseEntry(
        owner_id=owner_id,
        source_key=source_key,
        nightscout_id=source_key,
        timestamp=timestamp,
        value_mmol_l=value,
        source="nightscout",
    )
    session.add(entry)
    session.flush()
    return entry


def test_day_links_relabels_nearby_correction_bolus_as_food_context(
    api_client: TestClient,
) -> None:
    """Nightscout's raw correction label stays raw; backend adds food context."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        first = _seed_meal(
            session,
            owner_id,
            "Сырок глазированный",
            datetime(2026, 5, 20, 12, 0),
            carbs=17,
        )
        second = _seed_meal(
            session,
            owner_id,
            "Ролл с курицей",
            datetime(2026, 5, 20, 12, 20),
            carbs=51,
        )
        insulin = _seed_insulin(
            session,
            owner_id,
            "ns-correction-near-food",
            datetime(2026, 5, 20, 12, 8),
        )
        session.commit()

    response = api_client.get(
        "/timeline/insulin-links",
        params={"date": "2026-05-20"},
    )

    assert response.status_code == 200
    event = response.json()["insulin_events"][0]
    assert event["id"] == str(insulin.id)
    assert event["raw_event_type"] == "Correction Bolus"
    assert event["context_label"] == "food"
    assert event["link_source"] == "auto"
    assert set(event["suggested_meal_ids"]) == {str(first.id), str(second.id)}
    assert event["covers_multiple_food_events"] is True
    assert {
        (link["meal_id"], link["insulin_event_id"], link["source"])
        for link in response.json()["links"]
    } == {
        (str(first.id), str(insulin.id), "auto"),
        (str(second.id), str(insulin.id), "auto"),
    }


def test_put_day_links_persists_many_to_many_manual_links(
    api_client: TestClient,
) -> None:
    """One insulin event can cover meals and one meal can have insulin events."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        first = _seed_meal(
            session,
            owner_id,
            "Обед",
            datetime(2026, 5, 21, 13, 0),
        )
        second = _seed_meal(
            session,
            owner_id,
            "Десерт",
            datetime(2026, 5, 21, 13, 25),
        )
        first_bolus = _seed_insulin(
            session,
            owner_id,
            "ns-bolus-1",
            datetime(2026, 5, 21, 13, 5),
        )
        second_bolus = _seed_insulin(
            session,
            owner_id,
            "ns-bolus-2",
            datetime(2026, 5, 21, 13, 45),
        )
        session.commit()

    payload = {
        "date": "2026-05-21",
        "reviewed_insulin_event_ids": [
            str(first_bolus.id),
            str(second_bolus.id),
        ],
        "links": [
            {"meal_id": str(first.id), "insulin_event_id": str(first_bolus.id)},
            {"meal_id": str(second.id), "insulin_event_id": str(first_bolus.id)},
            {"meal_id": str(first.id), "insulin_event_id": str(second_bolus.id)},
        ],
    }
    saved = api_client.put("/timeline/insulin-links", json=payload)
    loaded = api_client.get(
        "/timeline/insulin-links",
        params={"date": "2026-05-21"},
    )

    assert saved.status_code == 200
    assert loaded.status_code == 200
    links = loaded.json()["links"]
    assert len(links) == 3
    by_event = {
        event["id"]: event for event in loaded.json()["insulin_events"]
    }
    assert by_event[str(first_bolus.id)]["context_label"] == "manual"
    assert by_event[str(first_bolus.id)]["link_source"] == "manual"
    assert set(by_event[str(first_bolus.id)]["linked_meal_ids"]) == {
        str(first.id),
        str(second.id),
    }
    assert by_event[str(second_bolus.id)]["linked_meal_ids"] == [str(first.id)]
    assert set(loaded.json()["reviewed_insulin_event_ids"]) == {
        str(first_bolus.id),
        str(second_bolus.id),
    }


def test_day_links_include_meal_glucose_anchors(api_client: TestClient) -> None:
    """Meal rows include CGM levels at -30 min and +2 h when data exists."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        meal = _seed_meal(
            session,
            owner_id,
            "Lunch with CGM",
            datetime(2026, 5, 23, 12, 0),
            carbs=44,
        )
        _seed_glucose(
            session,
            owner_id,
            "glucose-before",
            datetime(2026, 5, 23, 11, 30),
            5.4,
        )
        _seed_glucose(
            session,
            owner_id,
            "glucose-after",
            datetime(2026, 5, 23, 14, 0),
            8.1,
        )
        session.commit()

    response = api_client.get(
        "/timeline/insulin-links",
        params={"date": "2026-05-23"},
    )

    assert response.status_code == 200
    meal_row = response.json()["meals"][0]
    assert meal_row["id"] == str(meal.id)
    assert meal_row["glucose_minus_30"] == {
        "value": 5.4,
        "timestamp": "2026-05-23T11:30:00",
        "source": "actual",
    }
    assert meal_row["glucose_plus_2h"] == {
        "value": 8.1,
        "timestamp": "2026-05-23T14:00:00",
        "source": "actual",
    }


def test_put_day_links_persists_episode_snapshots_by_user(
    api_client: TestClient,
) -> None:
    """Saved episode snapshots are scoped by owner and include CGM anchors."""
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        alice = _seed_user(session, "alice-episode", UserRole.gluco)
        bob = _seed_user(session, "bob-episode", UserRole.gluco)
        alice_meal = _seed_meal(
            session,
            alice.id,
            "Alice lunch",
            datetime(2026, 5, 24, 12, 0),
        )
        bob_meal = _seed_meal(
            session,
            bob.id,
            "Bob lunch",
            datetime(2026, 5, 24, 12, 0),
        )
        alice_insulin = _seed_insulin(
            session,
            alice.id,
            "alice-episode-insulin",
            datetime(2026, 5, 24, 12, 5),
        )
        bob_insulin = _seed_insulin(
            session,
            bob.id,
            "bob-episode-insulin",
            datetime(2026, 5, 24, 12, 5),
        )
        _seed_glucose(
            session,
            alice.id,
            "alice-before",
            datetime(2026, 5, 24, 11, 30),
            5.2,
        )
        _seed_glucose(
            session,
            alice.id,
            "alice-after",
            datetime(2026, 5, 24, 14, 0),
            7.6,
        )
        _seed_glucose(
            session,
            bob.id,
            "bob-before",
            datetime(2026, 5, 24, 11, 30),
            6.1,
        )
        _seed_glucose(
            session,
            bob.id,
            "bob-after",
            datetime(2026, 5, 24, 14, 0),
            9.3,
        )
        session.commit()

    for user, meal, insulin in (
        (alice, alice_meal, alice_insulin),
        (bob, bob_meal, bob_insulin),
    ):
        response = api_client.put(
            "/timeline/insulin-links",
            json={
                "date": "2026-05-24",
                "links": [
                    {
                        "meal_id": str(meal.id),
                        "insulin_event_id": str(insulin.id),
                        "source": "manual",
                        "confidence": 1,
                    }
                ],
                "reviewed_insulin_event_ids": [str(insulin.id)],
            },
            headers=_headers(user.id),
        )
        assert response.status_code == 200

    with session_factory() as session:
        snapshots = session.query(MealInsulinEpisodeSnapshot).all()

    assert len(snapshots) == 2
    by_owner = {snapshot.owner_id: snapshot for snapshot in snapshots}
    assert by_owner[alice.id].title == "Alice lunch"
    assert by_owner[alice.id].meal_ids_json == [str(alice_meal.id)]
    assert by_owner[alice.id].insulin_event_ids_json == [str(alice_insulin.id)]
    assert by_owner[alice.id].glucose_minus_30_mmol_l == 5.2
    assert by_owner[alice.id].glucose_plus_2h_mmol_l == 7.6
    assert by_owner[bob.id].title == "Bob lunch"
    assert by_owner[bob.id].meal_ids_json == [str(bob_meal.id)]
    assert by_owner[bob.id].insulin_event_ids_json == [str(bob_insulin.id)]
    assert by_owner[bob.id].glucose_minus_30_mmol_l == 6.1
    assert by_owner[bob.id].glucose_plus_2h_mmol_l == 9.3


@pytest.mark.parametrize(
    ("viewer", "expected_title", "expected_before"),
    [("alice", "Alice scoped lunch", 5.2), ("bob", "Bob scoped lunch", 6.1)],
)
def test_put_day_links_episode_snapshots_are_scoped_to_viewer(
    api_client: TestClient,
    viewer: str,
    expected_title: str,
    expected_before: float,
) -> None:
    """Snapshot replacement writes only the authenticated user's episodes."""
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        alice = _seed_user(session, "alice-snapshot-scope", UserRole.gluco)
        bob = _seed_user(session, "bob-snapshot-scope", UserRole.gluco)
        alice_meal = _seed_meal(
            session,
            alice.id,
            "Alice scoped lunch",
            datetime(2026, 5, 25, 12, 0),
        )
        bob_meal = _seed_meal(
            session,
            bob.id,
            "Bob scoped lunch",
            datetime(2026, 5, 25, 12, 0),
        )
        alice_insulin = _seed_insulin(
            session,
            alice.id,
            "alice-scoped-insulin",
            datetime(2026, 5, 25, 12, 5),
        )
        bob_insulin = _seed_insulin(
            session,
            bob.id,
            "bob-scoped-insulin",
            datetime(2026, 5, 25, 12, 5),
        )
        _seed_glucose(
            session,
            alice.id,
            "alice-scoped-before",
            datetime(2026, 5, 25, 11, 30),
            5.2,
        )
        _seed_glucose(
            session,
            bob.id,
            "bob-scoped-before",
            datetime(2026, 5, 25, 11, 30),
            6.1,
        )
        session.commit()

    selected_user = alice if viewer == "alice" else bob
    selected_meal = alice_meal if viewer == "alice" else bob_meal
    selected_insulin = alice_insulin if viewer == "alice" else bob_insulin

    response = api_client.put(
        "/timeline/insulin-links",
        json={
            "date": "2026-05-25",
            "links": [
                {
                    "meal_id": str(selected_meal.id),
                    "insulin_event_id": str(selected_insulin.id),
                    "source": "manual",
                    "confidence": 1,
                }
            ],
            "reviewed_insulin_event_ids": [str(selected_insulin.id)],
        },
        headers=_headers(selected_user.id),
    )

    assert response.status_code == 200
    with session_factory() as session:
        snapshots = session.query(MealInsulinEpisodeSnapshot).all()

    assert len(snapshots) == 1
    assert snapshots[0].owner_id == selected_user.id
    assert snapshots[0].title == expected_title
    assert snapshots[0].glucose_minus_30_mmol_l == expected_before


def test_empty_manual_review_suppresses_auto_links(api_client: TestClient) -> None:
    """A reviewed insulin event can intentionally remain unlinked."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        meal = _seed_meal(
            session,
            owner_id,
            "Перекус",
            datetime(2026, 5, 21, 16, 0),
        )
        insulin = _seed_insulin(
            session,
            owner_id,
            "ns-reviewed-empty",
            datetime(2026, 5, 21, 16, 5),
        )
        session.commit()

    auto = api_client.get(
        "/timeline/insulin-links",
        params={"date": "2026-05-21"},
    )
    saved = api_client.put(
        "/timeline/insulin-links",
        json={
            "date": "2026-05-21",
            "reviewed_insulin_event_ids": [str(insulin.id)],
            "links": [],
        },
    )
    loaded = api_client.get(
        "/timeline/insulin-links",
        params={"date": "2026-05-21"},
    )

    assert auto.status_code == 200
    assert auto.json()["links"] == [
        {
            "meal_id": str(meal.id),
            "insulin_event_id": str(insulin.id),
            "source": "auto",
            "confidence": 0.9,
            "note": None,
        }
    ]
    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["links"] == []
    assert loaded.json()["reviewed_insulin_event_ids"] == [str(insulin.id)]
    event = loaded.json()["insulin_events"][0]
    assert event["link_source"] == "manual"
    assert event["context_label"] == "correction"


@pytest.mark.parametrize(
    ("viewer", "expected_title"),
    [("alice", "Alice meal"), ("bob", "Bob meal")],
)
def test_day_links_are_scoped_by_user(
    api_client: TestClient,
    viewer: str,
    expected_title: str,
) -> None:
    """The scoped repository returns only the current user's reviewed links."""
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        alice = _seed_user(session, "alice-links", UserRole.gluco)
        bob = _seed_user(session, "bob-links", UserRole.gluco)
        alice_meal = _seed_meal(
            session,
            alice.id,
            "Alice meal",
            datetime(2026, 5, 22, 11, 0),
        )
        bob_meal = _seed_meal(
            session,
            bob.id,
            "Bob meal",
            datetime(2026, 5, 22, 11, 0),
        )
        alice_insulin = _seed_insulin(
            session,
            alice.id,
            "alice-insulin",
            datetime(2026, 5, 22, 11, 5),
        )
        bob_insulin = _seed_insulin(
            session,
            bob.id,
            "bob-insulin",
            datetime(2026, 5, 22, 11, 5),
        )
        session.add(
            MealInsulinLink(
                owner_id=alice.id,
                meal_id=alice_meal.id,
                insulin_event_id=alice_insulin.id,
            )
        )
        session.add(
            MealInsulinLink(
                owner_id=bob.id,
                meal_id=bob_meal.id,
                insulin_event_id=bob_insulin.id,
            )
        )
        session.commit()
        viewer_user = alice if viewer == "alice" else bob

    response = api_client.get(
        "/timeline/insulin-links",
        params={"date": "2026-05-22"},
        headers=_headers(viewer_user.id),
    )

    assert response.status_code == 200
    data = response.json()
    assert [meal["title"] for meal in data["meals"]] == [expected_title]
    assert len(data["insulin_events"]) == 1
    assert len(data["links"]) == 1


def test_day_links_are_glucose_gated_for_food_users(api_client: TestClient) -> None:
    """Food users must not receive insulin/glucose review responses."""
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        food_user = _seed_user(session, "food-links", UserRole.food)
        session.commit()

    response = api_client.get(
        "/timeline/insulin-links",
        params={"date": "2026-05-22"},
        headers=_headers(food_user.id, UserRole.food),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "feature_disabled",
        "feature": "glucose",
    }
