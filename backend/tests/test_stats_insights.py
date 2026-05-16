"""Stats insight endpoint tests."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.application.stats_insights import (
    BANNED_COPY,
    rendered_template_samples_for_lint,
)
from glucotracker.application.time import local_now
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import ItemSourceKind, MealSource, MealStatus
from glucotracker.infra.db.models import Meal, MealItem, User
from glucotracker.infra.security import hash_password, issue_access_token

EXTRA_BANNED_COPY = ("превышение", "плохо", "цель не достигнута", "нарушение", "опасно")


def _create_user(session: Session, username: str, role: UserRole) -> User:
    user = User(
        username=username,
        password_hash=hash_password(f"{username}-password"),
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def _seed_meals(
    session: Session,
    owner_id: UUID,
    days: int,
    *,
    kcal: float = 1970,
    hour: int = 13,
    fat_g: float = 83,
) -> None:
    today = local_now().date()
    for offset in range(days):
        day = today - timedelta(days=days - offset - 1)
        eaten_at = local_now().replace(
            year=day.year,
            month=day.month,
            day=day.day,
            hour=hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        meal = Meal(
            owner_id=owner_id,
            eaten_at=eaten_at,
            title=f"meal-{offset}",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=240,
            total_protein_g=65,
            total_fat_g=fat_g,
            total_kcal=kcal,
        )
        session.add(meal)
        session.flush()
        session.add(
            MealItem(
                meal_id=meal.id,
                name="обед",
                source_kind=ItemSourceKind.manual,
                carbs_g=240,
                protein_g=65,
                fat_g=fat_g,
                kcal=kcal,
                position=0,
            )
        )
    session.commit()


def _seed_filter_meal(
    session: Session,
    owner_id: UUID,
    title: str,
    *,
    taste_profile: str = "savory",
    meal_window: str = "mid",
    source: MealSource = MealSource.manual,
    confidence: float | None = 0.9,
) -> None:
    meal = Meal(
        owner_id=owner_id,
        eaten_at=local_now(),
        title=title,
        source=source,
        status=MealStatus.accepted,
        total_carbs_g=20,
        total_protein_g=10,
        total_fat_g=5,
        total_kcal=165,
        confidence=confidence,
        ai_categories={"taste_profile": taste_profile},
        derived_categories={"meal_window": meal_window},
    )
    session.add(meal)
    session.flush()
    session.add(
        MealItem(
            meal_id=meal.id,
            name=title,
            source_kind=ItemSourceKind.manual,
            carbs_g=20,
            protein_g=10,
            fat_g=5,
            kcal=165,
            confidence=confidence,
            position=0,
        )
    )


def _auth_headers(user_id: UUID, role: UserRole = UserRole.gluco) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, role)}"}


def test_stats_insights_returns_deterministic_russian_copy(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session = session_factory()
    _seed_meals(session, user_id, 14)
    session.close()

    response = api_client.get(
        "/stats/insights",
        params={"period": "14d", "slot": "stats"},
    )

    assert response.status_code == 200
    insights = response.json()["insights"]
    assert 1 <= len(insights) <= 3
    for insight in insights:
        assert insight["text"]
        assert insight["weight"] in {"primary", "secondary"}
        assert insight["computed_at"]
        assert any("а" <= char.lower() <= "я" for char in insight["text"])
        lowered = insight["text"].casefold()
        assert all(term not in lowered for term in (*BANNED_COPY, *EXTRA_BANNED_COPY))


def test_stats_insights_returns_empty_when_data_is_sparse(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session = session_factory()
    _seed_meals(session, user_id, 2)
    session.close()

    response = api_client.get(
        "/stats/insights",
        params={"period": "14d", "slot": "stats"},
    )

    assert response.status_code == 200
    assert response.json() == {"insights": []}


def test_stats_insights_work_with_thirteen_tracked_days(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session = session_factory()
    today = local_now().date()
    for offset in range(13):
        day = today - timedelta(days=13 - offset)
        kcal = 900 + (offset % 4) * 450
        meal = Meal(
            owner_id=user_id,
            eaten_at=local_now().replace(
                year=day.year,
                month=day.month,
                day=day.day,
                hour=22,
                minute=0,
                second=0,
                microsecond=0,
            ),
            title="repeat-evening-meal",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=40,
            total_protein_g=20,
            total_fat_g=15,
            total_kcal=kcal,
            derived_categories={"meal_window": "late"},
        )
        session.add(meal)
        session.flush()
        session.add(
            MealItem(
                meal_id=meal.id,
                name="repeat-evening-meal",
                source_kind=ItemSourceKind.manual,
                carbs_g=40,
                protein_g=20,
                fat_g=15,
                kcal=kcal,
                position=0,
            )
        )
    session.commit()
    session.close()

    response = api_client.get(
        "/stats/insights",
        params={"period": "14d", "slot": "stats"},
    )

    assert response.status_code == 200
    kinds = {item["kind"] for item in response.json()["insights"]}
    assert "top_repeat_products" in kinds


@pytest.mark.parametrize("role", [UserRole.gluco, UserRole.food])
def test_stats_insights_are_scoped_to_current_user(
    api_client: TestClient,
    role: UserRole,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    session = session_factory()
    alice = _create_user(session, f"alice-{role.value}", role)
    bob = _create_user(session, f"bob-{role.value}", role)
    session.commit()
    alice_id = alice.id
    bob_id = bob.id
    _seed_meals(session, alice_id, 14, kcal=1970)
    _seed_meals(session, bob_id, 14, kcal=900, fat_g=20)
    session.close()

    response = api_client.get(
        "/stats/insights",
        params={"period": "14d", "slot": "stats"},
        headers=_auth_headers(alice_id, role),
    )

    assert response.status_code == 200
    text = " ".join(item["text"] for item in response.json()["insights"])
    assert "1 970" in text
    assert "900" not in text


@pytest.mark.parametrize(
    ("role", "expects_gluco_kind"),
    [(UserRole.gluco, True), (UserRole.food, False)],
)
def test_stats_insights_gate_glucose_kinds_by_role(
    api_client: TestClient,
    role: UserRole,
    expects_gluco_kind: bool,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    session = session_factory()
    user = _create_user(session, f"predictable-{role.value}", role)
    session.commit()
    user_id = user.id
    today = local_now().date()
    for offset in range(14):
        day = today - timedelta(days=13 - offset)
        meal = Meal(
            owner_id=user_id,
            eaten_at=local_now().replace(
                year=day.year,
                month=day.month,
                day=day.day,
                hour=13,
                minute=0,
                second=0,
                microsecond=0,
            ),
            title="йогурт",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=30,
            total_protein_g=12,
            total_fat_g=5,
            total_kcal=213,
            postprandial_response={
                "delta_max": 1.1,
                "glycemic_response": "mild",
                "delayed_peak_likely": False,
            },
        )
        session.add(meal)
        session.flush()
        session.add(
            MealItem(
                meal_id=meal.id,
                name="йогурт",
                source_kind=ItemSourceKind.manual,
                carbs_g=30,
                protein_g=12,
                fat_g=5,
                kcal=213,
                position=0,
            )
        )
    session.commit()
    session.close()

    response = api_client.get(
        "/stats/insights",
        params={"period": "14d", "slot": "stats"},
        headers=_auth_headers(user_id, role),
    )

    assert response.status_code == 200
    kinds = {item["kind"] for item in response.json()["insights"]}
    assert ("meal_predictability" in kinds) is expects_gluco_kind


def test_stats_insight_templates_avoid_forbidden_copy() -> None:
    for text in rendered_template_samples_for_lint():
        lowered = text.casefold()
        assert all(term not in lowered for term in (*BANNED_COPY, *EXTRA_BANNED_COPY))


def test_history_category_filters_use_backend_categories(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    user_id = UUID(str(api_client.app_state["current_user_id"]))
    session = session_factory()
    _seed_filter_meal(
        session,
        user_id,
        "sweet-breakfast",
        taste_profile="sweet",
        meal_window="start",
    )
    _seed_filter_meal(
        session,
        user_id,
        "sweet-evening",
        taste_profile="sweet",
        meal_window="late",
    )
    _seed_filter_meal(session, user_id, "savory-breakfast", meal_window="start")
    _seed_filter_meal(
        session,
        user_id,
        "photo-low",
        source=MealSource.photo,
        confidence=0.42,
    )
    session.commit()
    session.close()

    sweet_breakfast = api_client.get(
        "/meals",
        params={"sweet": True, "breakfast": True, "limit": 20},
    )
    photo_low = api_client.get(
        "/meals",
        params={"photo_only": True, "low_confidence": True, "limit": 20},
    )

    assert sweet_breakfast.status_code == 200
    assert [item["title"] for item in sweet_breakfast.json()["items"]] == [
        "sweet-breakfast"
    ]
    assert photo_low.status_code == 200
    assert [item["title"] for item in photo_low.json()["items"]] == ["photo-low"]
