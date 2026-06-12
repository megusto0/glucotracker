"""Unified meal/insulin episode grouping rules."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.insulin_links import InsulinLinkDayService
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    Meal,
    MealInsulinEpisodeSnapshot,
    NightscoutInsulinEvent,
    User,
)
from glucotracker.infra.security import hash_password, issue_access_token


def _headers(user_id: UUID, role: UserRole = UserRole.gluco) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, role)}"}


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


def test_episodes_group_many_meals_and_insulin_into_one(
    api_client: TestClient,
) -> None:
    """Two dishes plus their bolus is one episode; the bolus anchors nearby."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        nuggets = _seed_meal(
            session,
            owner_id,
            "Наггетсы",
            datetime(2026, 5, 20, 19, 12),
            carbs=24,
        )
        roll = _seed_meal(
            session,
            owner_id,
            "Воппер Ролл",
            datetime(2026, 5, 20, 19, 13),
            carbs=34,
        )
        bolus = _seed_insulin(
            session,
            owner_id,
            "ns-evening-bolus",
            datetime(2026, 5, 20, 19, 12),
            units=12,
        )
        session.commit()

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
    )

    assert response.status_code == 200
    episodes = response.json()["episodes"]
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["kind"] == "food"
    assert set(episode["meal_ids"]) == {str(nuggets.id), str(roll.id)}
    assert episode["total_carbs_g"] == 58.0
    assert episode["total_insulin_units"] == 12.0
    event = episode["insulin"][0]
    assert event["id"] == str(bolus.id)
    assert event["kind"] == "food"
    assert event["anchor_meal_id"] == str(nuggets.id)


def test_episodes_standalone_insulin_is_correction(api_client: TestClient) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        _seed_meal(
            session,
            owner_id,
            "Завтрак",
            datetime(2026, 5, 20, 9, 0),
        )
        correction = _seed_insulin(
            session,
            owner_id,
            "ns-lone-correction",
            datetime(2026, 5, 20, 15, 0),
            units=1.5,
        )
        session.commit()

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
    )

    assert response.status_code == 200
    episodes = response.json()["episodes"]
    kinds = {episode["kind"] for episode in episodes}
    assert kinds == {"food_only", "correction"}
    lone = next(e for e in episodes if e["kind"] == "correction")
    assert lone["meal_ids"] == []
    event = lone["insulin"][0]
    assert event["id"] == str(correction.id)
    assert event["kind"] == "correction"
    assert event["anchor_meal_id"] is None


def test_episodes_are_scoped_to_current_user(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        other = User(
            username="episode-other",
            password_hash=hash_password("episode-other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        other_id = other.id
        _seed_meal(
            session,
            other_id,
            "Чужой обед",
            datetime(2026, 5, 20, 13, 0),
        )
        session.commit()

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
    )

    assert response.status_code == 200
    assert response.json()["episodes"] == []
    assert "Чужой" not in response.text


def test_episodes_are_glucose_gated_for_food_users(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        food_user = User(
            username="episode-food-user",
            password_hash=hash_password("episode-food-password"),
            role=UserRole.food,
        )
        session.add(food_user)
        session.commit()
        food_user_id = food_user.id

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
        headers=_headers(food_user_id, UserRole.food),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "feature_disabled",
        "feature": "glucose",
    }


def test_materialize_day_persists_snapshots_without_manual_review(
    api_client: TestClient,
) -> None:
    """The worker path fills the export tables with auto-grouped episodes."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        _seed_meal(
            session,
            owner_id,
            "Суп с фрикадельками",
            datetime(2026, 5, 20, 4, 54),
            carbs=35,
        )
        _seed_insulin(
            session,
            owner_id,
            "ns-soup-bolus",
            datetime(2026, 5, 20, 4, 53),
            units=3,
        )
        session.commit()

    with session_factory() as session:
        InsulinLinkDayService(session, owner_id).materialize_day(date(2026, 5, 20))

    with session_factory() as session:
        snapshots = list(
            session.scalars(
                select(MealInsulinEpisodeSnapshot).where(
                    MealInsulinEpisodeSnapshot.owner_id == owner_id,
                    MealInsulinEpisodeSnapshot.date == date(2026, 5, 20),
                )
            )
        )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.kind == "food"
    assert snapshot.total_carbs_g == 35.0
    assert snapshot.total_insulin_units == 3.0
    assert len(snapshot.meal_ids_json) == 1
    assert len(snapshot.insulin_event_ids_json) == 1
