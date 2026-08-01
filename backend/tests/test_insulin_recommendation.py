"""Historical insulin recommendation API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    User,
)
from glucotracker.infra.db.repositories.twin import TwinRepository
from glucotracker.infra.security import hash_password, issue_access_token


def _meal(
    session: Session,
    owner_id: UUID,
    eaten_at: datetime,
    carbs: float,
    *,
    title: str = "Приём",
    kcal: float | None = None,
) -> Meal:
    row = Meal(
        owner_id=owner_id,
        eaten_at=eaten_at,
        title=title,
        source=MealSource.photo,
        status=MealStatus.accepted,
        total_carbs_g=carbs,
        total_protein_g=8,
        total_fat_g=6,
        total_kcal=kcal if kcal is not None else carbs * 5,
    )
    session.add(row)
    session.flush()
    return row


def _insulin(
    session: Session,
    owner_id: UUID,
    timestamp: datetime,
    units: float,
    *,
    event_type: str = "Meal Bolus",
) -> NightscoutInsulinEvent:
    key = f"recommendation-{uuid4()}"
    row = NightscoutInsulinEvent(
        owner_id=owner_id,
        source_key=key,
        nightscout_id=key,
        timestamp=timestamp,
        insulin_units=units,
        event_type=event_type,
        entered_by="Nightscout",
    )
    session.add(row)
    session.flush()
    return row


def _headers(user_id: UUID, role: UserRole) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, role)}"}


def test_recommendation_scales_historical_episode_median_for_group(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 19, 0)
    with session_factory() as session:
        target_a = _meal(session, owner_id, target_at, 20, title="Салат")
        target_b = _meal(
            session,
            owner_id,
            target_at + timedelta(minutes=5),
            40,
            title="Паста",
        )
        for days_ago, units in ((7, 3.0), (14, 3.2), (21, 2.8), (28, 3.1)):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 30)
            _insulin(session, owner_id, occurred_at, units)
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target_a.id), str(target_b.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["target_carbs_g"] == 60.0
    assert body["recommended_units"] == 6.1
    assert body["range_low_units"] == 5.9
    assert body["range_high_units"] == 6.2
    assert body["matched_episode_count"] == 4
    assert body["confidence"] == "low"
    assert body["method_version"] == "historical-episode-median-v2"


def test_recommendation_reports_insufficient_history(api_client: TestClient) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 9, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        occurred_at = target_at - timedelta(days=7)
        _meal(session, owner_id, occurred_at, 40)
        _insulin(session, owner_id, occurred_at, 4)
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_history"
    assert response.json()["recommended_units"] is None
    assert response.json()["matched_episode_count"] == 1


def test_recommendation_excludes_explicit_correction_boluses(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 13, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4)
            _insulin(
                session,
                owner_id,
                occurred_at + timedelta(minutes=1),
                2,
                event_type="Correction Bolus",
            )
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["recommended_units"] == 4.0


def test_recommendation_does_not_reattribute_late_explicit_corrections(
    api_client: TestClient,
) -> None:
    """A labelled correction never becomes a meal-dose training label."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 13, 0)
    correction_only_meal_ids: set[str] = set()
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            historical = _meal(session, owner_id, occurred_at, 40)
            correction_only_meal_ids.add(str(historical.id))
            _insulin(
                session,
                owner_id,
                occurred_at + timedelta(hours=2),
                8,
                event_type="Correction Bolus",
            )
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    matched_meal_ids = {
        meal_id for match in body["matches"] for meal_id in match["meal_ids"]
    }
    assert correction_only_meal_ids.isdisjoint(matched_meal_ids)


def test_recommendation_adds_rising_glucose_correction_without_own_bolus_iob(
    api_client: TestClient,
) -> None:
    """Total is meal plus correction; the recorded meal bolus is not prior IOB."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 13, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        _insulin(session, owner_id, target_at, 6.5)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4)
        for index, value in enumerate((8.0, 8.5, 9.0, 9.5)):
            timestamp = target_at - timedelta(minutes=15 - index * 5)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"recommendation-cgm-{index}",
                    timestamp=timestamp,
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 2.0
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={
            "meal_ids": [str(target.id)],
            "correction_target_mmol_l": 6.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommended_units"] == 4.0
    assert body["correction_status"] == "ready"
    assert body["correction_glucose_mmol_l"] == 9.5
    assert body["correction_projected_glucose_mmol_l"] == 11.0
    assert body["correction_trend_mmol_l_per_min"] == 0.1
    assert body["correction_iob_units"] == 0.0
    assert body["correction_units"] == 2.5
    assert body["total_recommended_units"] == 6.5


def test_recommendation_replaces_auto_fitted_isf_at_constraint_boundary(
    api_client: TestClient,
) -> None:
    """A boundary-clamped automatic ISF uses the explicit app fallback."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 13, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4)
        for index, value in enumerate((8.0, 8.5, 9.0, 9.5)):
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"boundary-isf-cgm-{index}",
                    timestamp=target_at
                    - timedelta(minutes=15 - index * 5),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 0.2
        params.last_fit_method = "least_squares"
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={
            "meal_ids": [str(target.id)],
            "correction_target_mmol_l": 6.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommended_units"] == 4.0
    assert body["correction_status"] == "ready"
    assert body["correction_isf_mmol_l_per_unit"] == 2.8
    assert body["correction_isf_source"] == "default"
    assert body["correction_units"] == 1.8
    assert body["total_recommended_units"] == 5.8


def test_recommendation_never_reads_another_users_meal(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        other = User(
            username=f"recommendation-other-{uuid4().hex}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        foreign_meal = _meal(
            session,
            other.id,
            datetime(2026, 7, 20, 12, 0),
            50,
            title="Чужой приём",
        )
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(foreign_meal.id)]},
    )

    assert response.status_code == 404
    assert "Чужой" not in response.text


def test_recommendation_is_glucose_gated(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        food_user = User(
            username=f"recommendation-food-{uuid4().hex}",
            password_hash=hash_password("food-password"),
            role=UserRole.food,
        )
        session.add(food_user)
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(uuid4())]},
        headers=_headers(food_user.id, UserRole.food),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "feature_disabled",
            "feature": "glucose",
        },
    }


def test_recommendation_reattributes_deferred_bolus_from_later_meal(
    api_client: TestClient,
) -> None:
    """Late bolus sitting on the next snack trains the earlier food episode."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 14, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 50, title="Цель")
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            # Large meal without in-window insulin.
            _meal(session, owner_id, occurred_at, 50, title="Без болюса")
            # Next snack carries the real bolus ~2h later.
            _meal(
                session,
                owner_id,
                occurred_at + timedelta(minutes=120),
                8,
                title="Позже",
            )
            _insulin(
                session,
                owner_id,
                occurred_at + timedelta(minutes=120),
                5.0,
            )
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["recommended_units"] == 5.0
    assert body["matched_episode_count"] == 3
    assert body["matches"][0]["deferred_insulin_units"] == 5.0
    assert body["method_version"] == "historical-episode-median-v2"


def test_recommendation_prefers_in_range_plus_2h_outcomes(
    api_client: TestClient,
) -> None:
    """Episodes that land high at +2h are down-weighted vs in-range ones."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 12, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        # Three in-range outcomes at 3.0 U.
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 3.0)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"outcome-good-{days_ago}",
                    timestamp=occurred_at + timedelta(hours=2),
                    value_mmol_l=7.0,
                    value_mg_dl=round(7.0 * 18.0182),
                    source="CGM",
                )
            )
        # One high outcome at 8.0 U — should not dominate.
        high_at = target_at - timedelta(days=28)
        _meal(session, owner_id, high_at, 40)
        _insulin(session, owner_id, high_at, 8.0)
        session.add(
            NightscoutGlucoseEntry(
                owner_id=owner_id,
                source_key="outcome-high",
                timestamp=high_at + timedelta(hours=2),
                value_mmol_l=14.0,
                value_mg_dl=round(14.0 * 18.0182),
                source="CGM",
            )
        )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 2.0
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    # Weighted toward the in-range 3U cluster, not the 8U high spike.
    assert body["recommended_units"] == 3.0
    weights = {
        round(m["insulin_units"], 1): m["outcome_weight"] for m in body["matches"]
    }
    assert weights[3.0] == 1.0
    assert weights[8.0] == 0.15
    high_match = next(m for m in body["matches"] if m["insulin_units"] == 8.0)
    assert high_match["scaled_units"] == 10.0


def test_recommendation_zeros_dose_when_premeal_low(
    api_client: TestClient,
) -> None:
    """Low/falling pre-meal glucose zeroes the actionable recommendation."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 13, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4)
        for index, value in enumerate((3.6, 3.5, 3.4, 3.3)):
            timestamp = target_at - timedelta(minutes=15 - index * 5)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"low-cgm-{index}",
                    timestamp=timestamp,
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 2.0
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={
            "meal_ids": [str(target.id)],
            "correction_target_mmol_l": 6.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "low_or_falling"
    assert body["correction_status"] == "low_or_falling"
    assert body["recommended_units"] is None
    assert body["range_low_units"] is None
    assert body["range_high_units"] is None
    assert body["total_recommended_units"] is None


def test_recommendation_falls_back_to_icr_without_history(
    api_client: TestClient,
) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 12, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = 10.0
        params.icr_day = 10.0
        params.icr_evening = 10.0
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["recommended_units"] == 4.0
    assert body["confidence"] == "low"
    assert body["matched_episode_count"] == 0


def test_recommendation_corrects_near_low_outcomes_downward(
    api_client: TestClient,
) -> None:
    """An episode that finished just above hypo lowers its own scaled dose.

    Before, only high outcomes adjusted a dose and sub-3.9 outcomes were
    dropped, so nothing could ever pull the estimate down.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 12, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21, 28):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4.0)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"outcome-near-low-{days_ago}",
                    timestamp=occurred_at + timedelta(hours=2),
                    value_mmol_l=4.2,
                    value_mg_dl=round(4.2 * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 2.0
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    # (4.2 - 5.0) / 2.0 = -0.4 U on an identical 40 g meal.
    assert body["recommended_units"] == 3.6
    for match in body["matches"]:
        assert match["scaled_units"] == 3.6


def test_recommendation_keeps_in_range_outcomes_unchanged(
    api_client: TestClient,
) -> None:
    """Comfortable outcomes are copied as-is, with no residual either way."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 12, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21, 28):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4.0)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"outcome-in-range-{days_ago}",
                    timestamp=occurred_at + timedelta(hours=2),
                    value_mmol_l=6.5,
                    value_mg_dl=round(6.5 * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 2.0
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommended_units"] == 4.0
    for match in body["matches"]:
        assert match["outcome_weight"] == 1.0
        assert match["scaled_units"] == 4.0


def test_recommendation_still_drops_very_low_outcomes(
    api_client: TestClient,
) -> None:
    """A rescued episode teaches no ratio and stays excluded."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 12, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21, 28):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 9.0)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"outcome-very-low-{days_ago}",
                    timestamp=occurred_at + timedelta(hours=2),
                    value_mmol_l=2.6,
                    value_mg_dl=round(2.6 * 18.0182),
                    source="CGM",
                )
            )
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_history"
    assert body["matches"] == []
