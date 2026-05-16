"""User schedule and day-anchor history endpoint tests."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.application.time import local_now
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import ItemSourceKind, MealSource, MealStatus
from glucotracker.infra.db.models import Meal, MealItem, User
from glucotracker.infra.security import hash_password, issue_access_token


def _auth_headers(user_id: UUID, role: UserRole = UserRole.gluco) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, role)}"}


def _seed_anchor_meals(session: Session, owner_id: UUID) -> None:
    today = local_now().date()
    for offset in range(8):
        day = today - timedelta(days=7 - offset)
        eaten_at = local_now().replace(
            year=day.year,
            month=day.month,
            day=day.day,
            hour=6,
            minute=30,
            second=0,
            microsecond=0,
        )
        meal = Meal(
            owner_id=owner_id,
            eaten_at=eaten_at,
            title=f"breakfast-{offset}",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=20,
            total_protein_g=10,
            total_fat_g=5,
            total_kcal=165,
        )
        session.add(meal)
        session.flush()
        session.add(
            MealItem(
                meal_id=meal.id,
                name="breakfast",
                source_kind=ItemSourceKind.manual,
                carbs_g=20,
                protein_g=10,
                fat_g=5,
                kcal=165,
                position=0,
            )
        )
    session.commit()


def test_schedule_override_and_history_are_scoped(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session = session_factory()
    other = User(
        username="schedule-other",
        password_hash=hash_password("schedule-other-password"),
        role=UserRole.gluco,
    )
    session.add(other)
    session.flush()
    other_id = other.id
    _seed_anchor_meals(session, user_id)
    session.close()

    put_response = api_client.put(
        "/me/schedule/override",
        json={"anchor_minutes": 420},
    )
    other_response = api_client.put(
        "/me/schedule/override",
        json={"anchor_minutes": 600},
        headers=_auth_headers(other_id),
    )
    get_response = api_client.get("/me/schedule")

    assert put_response.status_code == 200
    assert put_response.json()["user_override_minutes"] == 420
    assert put_response.json()["windows"][0]["start_minute"] == 420
    assert put_response.json()["history"][0]["basis"] == "user_override"
    assert other_response.status_code == 200
    assert other_response.json()["user_override_minutes"] == 600
    assert get_response.status_code == 200
    assert get_response.json()["user_override_minutes"] == 420


def test_schedule_read_persists_learned_anchor_when_missing(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session = session_factory()
    _seed_anchor_meals(session, user_id)
    user = session.get(User, user_id)
    assert user is not None
    assert user.day_anchor_weekday_minutes is None
    assert user.day_anchor_basis is None
    session.close()

    response = api_client.get("/me/schedule")

    assert response.status_code == 200
    body = response.json()
    assert body["basis"] == "weighted_7d"
    assert body["anchor_weekday_minutes"] == 390
    assert body["effective_anchor_minutes"] == 390
    assert body["windows"][0]["start_minute"] == 390


def test_schedule_non_typical_period_crud(api_client: TestClient) -> None:
    today = local_now().date()
    create_response = api_client.post(
        "/me/schedule/non-typical-periods",
        json={
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=2)).isoformat(),
            "note": "trip",
        },
    )

    assert create_response.status_code == 201
    period_id = create_response.json()["id"]

    get_response = api_client.get("/me/schedule")
    assert [row["id"] for row in get_response.json()["non_typical_periods"]] == [
        period_id
    ]

    delete_response = api_client.delete(f"/me/schedule/non-typical-periods/{period_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
