"""Historical insulin recommendation API tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.application.glucose_prediction import MODEL_VERSION
from glucotracker.application.insulin_recommendation import (
    _hr_sample_instant,
    _hr_trough_ended_within_window,
)
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    GlucosePredictionPointAudit,
    GlucosePredictionRun,
    HealthConnectRecord,
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
    assert body["method_version"] == "historical-episode-median-v3"


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
                    timestamp=target_at - timedelta(minutes=15 - index * 5),
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
    assert body["method_version"] == "historical-episode-median-v3"


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
    # With no history the ratio is the whole answer, and it has to say so.
    assert body["icr_g_per_unit"] == 10.0
    assert body["icr_daypart"] == "day"
    assert body["icr_dose_units"] == 4.0
    assert body["history_weight"] == 0.0
    assert body["history_median_units"] is None
    assert body["implied_icr_g_per_unit"] == 10.0


def test_the_food_half_is_stored_and_the_correction_is_not(
    api_client: TestClient,
) -> None:
    """The expensive half is the stable one. Rebuilding 180 days of history on
    every request is waste; reusing a correction would be dangerous."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 12, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4.0)
        session.commit()

    payload = {"meal_ids": [str(target.id)]}
    first = api_client.post(
        "/glucose/insulin-recommendation",
        json=payload,
    ).json()
    second = api_client.post(
        "/glucose/insulin-recommendation",
        json=payload,
    ).json()

    assert first["meal_from_cache"] is False
    assert second["meal_from_cache"] is True
    assert second["meal_computed_at"] is not None
    # The food half is identical; nothing about it depends on the moment.
    assert second["recommended_units"] == first["recommended_units"]
    assert second["matched_episode_count"] == first["matched_episode_count"]

    # Editing the meal must not serve the estimate made for the old one.
    with session_factory() as session:
        meal = session.get(Meal, target.id)
        meal.total_carbs_g = 80.0
        session.commit()

    after_edit = api_client.post(
        "/glucose/insulin-recommendation",
        json=payload,
    ).json()
    assert after_edit["meal_from_cache"] is False
    assert after_edit["target_carbs_g"] == 80.0


def test_late_sleep_sync_recomputes_the_first_after_sleep_food_cache(
    api_client: TestClient,
) -> None:
    """A meal can gain its sleep context after the watch finishes syncing."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 3, 12, 41)
    target_utc = target_at.replace(tzinfo=UTC)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 62.0)
        _meal(session, owner_id, target_at - timedelta(hours=11), 30.0)
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = 8.0
        params.icr_day = 9.3
        params.icr_evening = 10.0
        params.last_fit_method = "manual"
        session.commit()

    payload = {"meal_ids": [str(target.id)]}
    before_sleep = api_client.post(
        "/glucose/insulin-recommendation",
        json=payload,
    ).json()
    assert before_sleep["icr_after_sleep"] is False

    with session_factory() as session:
        _sleep(
            session,
            owner_id,
            start=target_utc - timedelta(hours=9),
            end=target_utc - timedelta(hours=1),
        )
        session.commit()

    after_sleep = api_client.post(
        "/glucose/insulin-recommendation",
        json=payload,
    ).json()
    assert after_sleep["meal_from_cache"] is False
    assert after_sleep["icr_after_sleep"] is True

    cached = api_client.post(
        "/glucose/insulin-recommendation",
        json=payload,
    ).json()
    assert cached["meal_from_cache"] is True
    assert cached["icr_after_sleep"] is True


def test_recommendation_reports_how_history_and_the_ratio_were_blended(
    api_client: TestClient,
) -> None:
    """The client shows its working, so both halves have to reach it."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 12, 0)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21, 28):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 5.0)
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 10.0
        session.commit()

    body = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    ).json()

    assert body["status"] == "ready"
    assert body["history_median_units"] == 5.0
    assert body["icr_dose_units"] == 4.0
    weight = body["history_weight"]
    assert 0.0 < weight < 1.0
    # The headline must be exactly the blend it reports, or the working lies.
    assert body["recommended_units"] == pytest.approx(
        round(weight * 5.0 + (1.0 - weight) * 4.0, 1),
        abs=0.05,
    )
    assert body["implied_icr_g_per_unit"] == pytest.approx(
        round(40.0 / body["recommended_units"], 1),
        abs=0.05,
    )


def test_the_first_meal_after_sleep_reports_the_tightened_ratio(
    api_client: TestClient,
) -> None:
    """Applying the factor silently would leave the shown ratio contradicting
    the shown dose."""
    body = _first_meal_case(api_client, with_sleep=True, gap_hours=11)

    assert body["icr_after_sleep"] is True
    assert body["icr_configured_g_per_unit"] == 9.3
    # Configured stays reportable next to what was actually applied.
    assert body["icr_g_per_unit"] == pytest.approx(9.3 * 7.1 / 8.7, abs=0.01)


def test_first_after_sleep_factor_survives_the_history_blend(
    api_client: TestClient,
) -> None:
    """Personal matches must not cancel the measured after-sleep factor."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 3, 12, 41)
    target_utc = target_at.replace(tzinfo=UTC)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40.0)
        _meal(session, owner_id, target_at - timedelta(hours=11), 30.0)
        for days_ago in (7, 14, 21, 28):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40.0)
            _insulin(session, owner_id, occurred_at, 4.0)
        _sleep(
            session,
            owner_id,
            start=target_utc - timedelta(hours=9),
            end=target_utc - timedelta(hours=1),
        )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 10.0
        params.last_fit_method = "manual"
        session.commit()

    body = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    ).json()

    assert body["icr_after_sleep"] is True
    assert body["history_median_units"] == pytest.approx(
        round(4.0 / (7.1 / 8.7), 1),
        abs=0.05,
    )
    assert body["recommended_units"] == pytest.approx(
        round(
            body["history_weight"] * body["history_median_units"]
            + (1.0 - body["history_weight"]) * body["icr_dose_units"],
            1,
        ),
        abs=0.05,
    )
    assert body["recommended_units"] >= 4.8


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


def test_correction_uses_the_forecast_when_glucose_is_in_range_but_falling(
    api_client: TestClient,
) -> None:
    """The case a flat reading hides: 8.0 now, but heading down to 5.6.

    The linear trend over the last 20 minutes is flat here, so without the
    forecast the correction would dose as if 8.0 were stable.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 7, 20, 13, 0)
    anchor_utc = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 40)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 40)
            _insulin(session, owner_id, occurred_at, 4)
        # Flat CGM: a straight-line projection sees no movement at all.
        for index in range(4):
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"flat-cgm-{index}",
                    timestamp=target_at - timedelta(minutes=15 - index * 5),
                    value_mmol_l=8.0,
                    value_mg_dl=round(8.0 * 18.0182),
                    source="CGM",
                )
            )
        run = GlucosePredictionRun(
            owner_id=owner_id,
            generated_at=anchor_utc,
            anchor_timestamp=anchor_utc,
            anchor_value_mmol_l=8.0,
            model_version=MODEL_VERSION,
            algorithm="test",
            horizon_minutes=90,
            step_minutes=5,
            model_json={},
            inputs_json={},
            notes_json=[],
        )
        run.points = [
            GlucosePredictionPointAudit(
                owner_id=owner_id,
                target_timestamp=anchor_utc + timedelta(minutes=60),
                horizon_minutes=60,
                predicted_value_mmol_l=5.6,
                ci_low_mmol_l=4.4,
                ci_high_mmol_l=6.8,
                confidence=0.6,
                predicted_band="in_range",
                evaluation_status="pending",
            )
        ]
        session.add(run)
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
    assert body["correction_glucose_mmol_l"] == 8.0
    assert body["correction_trend_mmol_l_per_min"] == 0.0
    # Flat trend would have projected 8.0 and asked for (8.0-6.0)/2.0 = 1.0 U.
    assert body["correction_projected_glucose_mmol_l"] == 5.6
    assert body["correction_status"] == "not_needed"
    assert body["correction_units"] == 0.0
    # Meal dose is unchanged; only the correction component responds.
    assert body["recommended_units"] == 4.0
    assert body["total_recommended_units"] == 4.0


def test_fast_fall_from_a_safe_level_does_not_hide_the_meal_dose(
    api_client: TestClient,
) -> None:
    """Reported 2026-08-02: 76 g about to be eaten at 8.8 falling 4.0/h.

    Rate alone used to withhold everything, including the meal component, even
    though the fall lands near 5.8 and the food outweighs it several times over.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 2, 20, 26)
    with session_factory() as session:
        target_a = _meal(session, owner_id, target_at, 28.5, title="Картофель")
        target_b = _meal(
            session,
            owner_id,
            target_at + timedelta(minutes=8),
            47.5,
            title="Орешки",
        )
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 76.0)
            _insulin(session, owner_id, occurred_at, 8.0)
        # 9.8 -> 8.8 over 15 minutes: -0.067 mmol/L per minute.
        for index, value in enumerate((9.8, 9.4, 9.1, 8.8)):
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"fast-fall-{index}",
                    timestamp=target_at - timedelta(minutes=15 - index * 5),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 2.6
        session.commit()

    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={
            "meal_ids": [str(target_a.id), str(target_b.id)],
            "correction_target_mmol_l": 6.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["recommended_units"] is not None
    assert body["correction_status"] != "low_or_falling"
    assert body["total_recommended_units"] is not None


def test_the_same_fall_from_a_low_level_still_withholds_everything(
    api_client: TestClient,
) -> None:
    """5.0 falling at the same rate lands near 2.0, so nothing is shown."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 2, 20, 26)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 76.0)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 76.0)
            _insulin(session, owner_id, occurred_at, 8.0)
        for index, value in enumerate((6.0, 5.6, 5.3, 5.0)):
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"low-fall-{index}",
                    timestamp=target_at - timedelta(minutes=15 - index * 5),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.isf = 2.6
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
    assert body["correction_status"] == "low_or_falling"
    assert body["status"] == "low_or_falling"
    assert body["recommended_units"] is None
    assert body["total_recommended_units"] is None


def _sleep(session, owner_id, *, start, end) -> None:
    """A Health Connect sleep session, as the sync writes it."""
    session.add(
        HealthConnectRecord(
            owner_id=owner_id,
            record_id=f"sleep-{start.isoformat()}",
            record_type="SleepSessionRecord",
            start_time=start,
            end_time=end,
            payload={
                "startTime": start.isoformat().replace("+00:00", "Z"),
                "endTime": end.isoformat().replace("+00:00", "Z"),
            },
        )
    )


def _hr_trough(
    session,
    owner_id,
    *,
    target_utc: datetime,
    trough_start: datetime,
    trough_end: datetime,
) -> None:
    """Heart-rate samples at 45 bpm across the trough, 75 bpm elsewhere."""
    at = target_utc - timedelta(hours=24)
    while at < target_utc:
        bpm = 45 if trough_start <= at <= trough_end else 75
        session.add(
            HealthConnectRecord(
                owner_id=owner_id,
                record_id=f"hr-{at.isoformat()}-{bpm}",
                record_type="HeartRateRecord",
                start_time=at,
                end_time=at,
                payload={"samples": [{"beatsPerMinute": bpm}]},
            )
        )
        at += timedelta(minutes=5)


def _first_meal_case(
    api_client: TestClient,
    *,
    with_sleep: bool,
    gap_hours: int,
    hr_trough: tuple[int, int] | None = None,
):
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 3, 12, 41)
    target_utc = datetime(2026, 8, 3, 12, 41, tzinfo=UTC)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 62.0, title="Панкейки")
        _meal(session, owner_id, target_at - timedelta(hours=gap_hours), 30.0)
        _insulin(session, owner_id, target_at - timedelta(hours=gap_hours), 3.0)
        if with_sleep:
            _sleep(
                session,
                owner_id,
                start=target_utc - timedelta(hours=9),
                end=target_utc - timedelta(hours=1),
            )
        if hr_trough is not None:
            start_hours, end_hours = hr_trough
            _hr_trough(
                session,
                owner_id,
                target_utc=target_utc,
                trough_start=target_utc - timedelta(hours=start_hours),
                trough_end=target_utc - timedelta(hours=end_hours),
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = 8.0
        params.icr_day = 9.3
        params.icr_evening = 10.0
        params.last_fit_method = "manual"
        session.commit()
    response = api_client.post(
        "/glucose/insulin-recommendation",
        json={"meal_ids": [str(target.id)]},
    )
    assert response.status_code == 200
    return response.json()


def test_first_meal_after_recorded_sleep_gets_a_tighter_ratio(
    api_client: TestClient,
) -> None:
    """Measured over 75 days: a gap of 7 h implies 7.1 g/U against 8.7.

    Those episodes ran from 06:00 to 20:00 with a median at 14:00, so the clock
    cannot stand in for the effect — this one is at 12:41, inside the configured
    "day" slot, exactly like the 2026-08-03 breakfast that peaked at 13.0.
    """
    body = _first_meal_case(api_client, with_sleep=True, gap_hours=11)

    assert body["status"] == "ready"
    assert body["recommended_units"] > 62.0 / 9.3
    assert 7.5 <= body["recommended_units"] <= 8.8


def test_a_long_gap_without_recorded_sleep_changes_nothing(
    api_client: TestClient,
) -> None:
    """An unlogged meal looks like a long gap, and must not raise the dose."""
    body = _first_meal_case(api_client, with_sleep=False, gap_hours=11)

    assert abs(body["recommended_units"] - 62.0 / 9.3) < 0.2


def test_sleep_without_a_long_gap_changes_nothing(api_client: TestClient) -> None:
    body = _first_meal_case(api_client, with_sleep=True, gap_hours=3)

    assert abs(body["recommended_units"] - 62.0 / 9.3) < 0.2


def test_hr_trough_ending_just_before_meal_gets_a_tighter_ratio(
    api_client: TestClient,
) -> None:
    """No sleep session is synced, but the low-HR trough ended 2 h before the
    meal — the fallback wake signal stands in for the sleep record."""
    body = _first_meal_case(
        api_client,
        with_sleep=False,
        gap_hours=11,
        hr_trough=(11, 2),
    )

    assert body["status"] == "ready"
    assert body["recommended_units"] > 62.0 / 9.3
    assert 7.5 <= body["recommended_units"] <= 8.8


def test_hr_trough_ending_too_long_before_meal_changes_nothing(
    api_client: TestClient,
) -> None:
    """The trough ended 8 h before the meal, outside the 6 h window."""
    body = _first_meal_case(
        api_client,
        with_sleep=False,
        gap_hours=11,
        hr_trough=(17, 8),
    )

    assert abs(body["recommended_units"] - 62.0 / 9.3) < 0.2


def test_hr_trough_does_not_override_a_missing_long_gap(
    api_client: TestClient,
) -> None:
    """A trough ending near a meal is irrelevant without the 7 h meal gap."""
    body = _first_meal_case(
        api_client,
        with_sleep=False,
        gap_hours=3,
        hr_trough=(11, 2),
    )

    assert abs(body["recommended_units"] - 62.0 / 9.3) < 0.2


def _trough_samples(
    *,
    target: datetime,
    trough_start: datetime,
    trough_end: datetime,
    low: int = 45,
    high: int = 75,
) -> list[tuple[datetime, int]]:
    samples = []
    at = target - timedelta(hours=24)
    while at < target:
        bpm = low if trough_start <= at <= trough_end else high
        samples.append((at, bpm))
        at += timedelta(minutes=5)
    return samples


def test_hr_trough_accepts_a_trough_that_ended_inside_the_window() -> None:
    target = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    samples = _trough_samples(
        target=target,
        trough_start=datetime(2026, 8, 3, 2, 0, tzinfo=UTC),
        trough_end=datetime(2026, 8, 3, 11, 0, tzinfo=UTC),
    )

    assert _hr_trough_ended_within_window(samples, target)


def test_hr_trough_rejects_a_trough_that_ended_too_long_ago() -> None:
    target = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
    samples = _trough_samples(
        target=target,
        trough_start=datetime(2026, 8, 3, 2, 0, tzinfo=UTC),
        trough_end=datetime(2026, 8, 3, 11, 0, tzinfo=UTC),
    )

    assert not _hr_trough_ended_within_window(samples, target)


def test_hr_trough_survives_noise_inside_the_trough() -> None:
    """A single above-threshold minute is a sensor spike, not an awakening."""
    target = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    samples = _trough_samples(
        target=target,
        trough_start=datetime(2026, 8, 3, 2, 0, tzinfo=UTC),
        trough_end=datetime(2026, 8, 3, 11, 0, tzinfo=UTC),
    )
    for hh, mm in ((3, 30), (5, 15), (7, 45)):
        samples.append((datetime(2026, 8, 3, hh, mm, tzinfo=UTC), 75))
        samples.append((datetime(2026, 8, 3, hh, mm + 1, tzinfo=UTC), 75))

    assert _hr_trough_ended_within_window(samples, target)


def test_hr_trough_rejects_a_short_trough() -> None:
    """A 1 h dip cannot stand in for a night of sleep."""
    target = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    samples = _trough_samples(
        target=target,
        trough_start=datetime(2026, 8, 3, 10, 30, tzinfo=UTC),
        trough_end=datetime(2026, 8, 3, 11, 30, tzinfo=UTC),
    )

    assert not _hr_trough_ended_within_window(samples, target)


def test_hr_trough_rejects_a_monotone_window() -> None:
    """All-low (or all-high) data must not read as a trough."""
    target = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    samples = _trough_samples(
        target=target,
        trough_start=datetime(2026, 8, 3, 2, 0, tzinfo=UTC),
        trough_end=datetime(2026, 8, 3, 11, 0, tzinfo=UTC),
        low=75,
        high=75,
    )

    assert not _hr_trough_ended_within_window(samples, target)


def test_hr_sample_instant_reapplies_the_wall_clock_offset() -> None:
    row = HealthConnectRecord(
        owner_id=uuid4(),
        record_id="hr-offset",
        record_type="HeartRateRecord",
        start_time=datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
        end_time=datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
        payload={"startZoneOffset": "+04:00"},
    )
    sample = {"beatsPerMinute": 60, "time": "2026-08-03T02:00:00Z"}

    assert _hr_sample_instant(sample, row) == datetime(2026, 8, 3, 6, 0, tzinfo=UTC)


def test_hr_sample_instant_falls_back_to_row_start_time() -> None:
    row = HealthConnectRecord(
        owner_id=uuid4(),
        record_id="hr-fallback",
        record_type="HeartRateRecord",
        start_time=datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
        end_time=datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
        payload={},
    )
    sample = {"beatsPerMinute": 60}

    assert _hr_sample_instant(sample, row) == datetime(2026, 8, 3, 6, 0, tzinfo=UTC)


def test_surplus_insulin_never_reduces_the_new_meal(api_client: TestClient) -> None:
    """IOB may reduce a correction, but never the food half of a new bolus.

    Reported twice in the UI: a perfectly ordinary new plate showed a non-zero
    food estimate and a zero total because old IOB was silently subtracted from
    the food. That IOB belongs to the earlier episode; without an explicit
    correction need there is no justified deduction from the new plate.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 3, 17, 33)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 24.0, title="Пирожок")
        # A covered meal an hour earlier: most of its carbohydrate is gone,
        # most of its insulin is not.
        _meal(session, owner_id, target_at - timedelta(hours=1), 113.0)
        _insulin(session, owner_id, target_at - timedelta(hours=1), 10.8)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 24.0)
            _insulin(session, owner_id, occurred_at, 2.6)
        for index, value in enumerate((6.0, 6.0, 6.0, 6.0)):
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"surplus-cgm-{index}",
                    timestamp=target_at - timedelta(minutes=15 - index * 5),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 9.3
        params.isf = 2.6
        params.last_fit_method = "manual"
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
    assert body["correction_status"] == "not_needed"
    assert body["correction_excess_iob_units"] > 0
    # The food half remains the food half. Free IOB is correction context, not a
    # hidden negative meal term.
    assert body["recommended_units"] is not None
    assert body["total_recommended_units"] == body["recommended_units"]


def test_no_surplus_when_insulin_is_committed_to_carbs_still_absorbing(
    api_client: TestClient,
) -> None:
    """A large meal just eaten leaves nothing spare, however big the IOB."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 3, 17, 33)
    with session_factory() as session:
        target = _meal(session, owner_id, target_at, 24.0)
        # A separate earlier episode with enough carbohydrate still on board to
        # commit every remaining unit of its own bolus.
        _meal(session, owner_id, target_at - timedelta(minutes=90), 220.0)
        _insulin(session, owner_id, target_at - timedelta(minutes=90), 11.0)
        for days_ago in (7, 14, 21):
            occurred_at = target_at - timedelta(days=days_ago)
            _meal(session, owner_id, occurred_at, 24.0)
            _insulin(session, owner_id, occurred_at, 2.6)
        for index, value in enumerate((7.0, 7.0, 7.0, 7.0)):
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"committed-cgm-{index}",
                    timestamp=target_at - timedelta(minutes=15 - index * 5),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 9.3
        params.isf = 2.6
        params.last_fit_method = "manual"
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
    assert body["correction_prior_cob_g"] > 70
    assert body["correction_excess_iob_units"] == 0.0
    assert body["correction_iob_units"] > 0
    # IOB committed to COB cannot erase a glucose correction as well.
    gross = (
        body["correction_projected_glucose_mmol_l"] - body["correction_target_mmol_l"]
    ) / body["correction_isf_mmol_l_per_unit"]
    assert abs(body["correction_units"] - round(gross * 10) / 10) < 0.11
