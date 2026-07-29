"""Automatic meal/snack/correction intent classification."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from glucotracker.api.schemas import GlucoseDashboardPoint
from glucotracker.application.episode_therapy import classify_episode_therapy
from glucotracker.application.episodes import EpisodeComponent
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import Meal, NightscoutInsulinEvent


def _meal(
    at: datetime,
    *,
    carbs: float,
    role: str,
    title: str = "Еда",
) -> Meal:
    return Meal(
        id=uuid4(),
        owner_id=uuid4(),
        eaten_at=at,
        title=title,
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=carbs,
        total_protein_g=4,
        total_fat_g=4,
        total_kcal=carbs * 5,
        derived_categories={"meal_role": role},
    )


def _insulin(at: datetime, *, event_type: str) -> NightscoutInsulinEvent:
    key = f"therapy-{uuid4()}"
    return NightscoutInsulinEvent(
        id=uuid4(),
        owner_id=uuid4(),
        source_key=key,
        nightscout_id=key,
        timestamp=at,
        insulin_units=2,
        event_type=event_type,
        entered_by="Nightscout",
    )


def _point(
    at: datetime,
    *,
    raw: float,
    normalized: float,
) -> GlucoseDashboardPoint:
    return GlucoseDashboardPoint(
        timestamp=at,
        raw_value=raw,
        normalized_value=normalized,
        display_value=normalized,
    )


def test_low_cookie_is_carb_correction_even_when_normalized_is_not_low() -> None:
    at = datetime(2026, 7, 25, 14, 47)
    cookie = _meal(
        at,
        carbs=30,
        role="dessert",
        title="Шоколадное печенье",
    )
    points = [
        _point(at - timedelta(minutes=10), raw=2.6, normalized=4.9),
        _point(at, raw=2.5, normalized=4.8),
        _point(at + timedelta(hours=2), raw=6.0, normalized=8.3),
        _point(at + timedelta(minutes=140), raw=6.7, normalized=9.0),
    ]

    result = classify_episode_therapy(
        EpisodeComponent(meals=[cookie], insulin=[], pairs=[]),
        points,
    )

    assert result.classification == "carb_correction"
    assert result.confidence == "high"
    assert result.suggested_carbs_g == 15.0
    assert result.suggestion_source == "ada_default"
    assert result.glucose_at_start_raw == 2.5
    assert result.glucose_at_start_normalized == 4.8
    assert result.peak_post_event_normalized == 9.0


def test_dessert_at_in_range_glucose_is_snack() -> None:
    at = datetime(2026, 7, 25, 18, 0)
    dessert = _meal(at, carbs=24, role="dessert")

    result = classify_episode_therapy(
        EpisodeComponent(meals=[dessert], insulin=[], pairs=[]),
        [_point(at, raw=5.7, normalized=5.9)],
    )

    assert result.classification == "snack"
    assert result.suggested_carbs_g is None


def test_small_main_meal_during_fast_fall_is_carb_correction() -> None:
    """Food-role metadata must not override an obvious rescue pattern."""
    at = datetime(2026, 7, 25, 12, 30)
    small_meal = _meal(
        at,
        carbs=7,
        role="main_meal",
        title="Омлет с грибами и соусом",
    )
    points = [
        _point(at - timedelta(minutes=20), raw=6.4, normalized=8.7),
        _point(at - timedelta(minutes=10), raw=5.4, normalized=7.7),
        _point(at, raw=4.4, normalized=6.7),
    ]

    result = classify_episode_therapy(
        EpisodeComponent(meals=[small_meal], insulin=[], pairs=[]),
        points,
    )

    assert result.classification == "carb_correction"
    assert result.confidence == "high"
    assert result.suggested_carbs_g == 15.0
    assert "глюкоза быстро снижалась перед едой" in result.reasons
    assert "небольшой приём: 7 г" in result.reasons


def test_main_meal_with_bolus_is_meal() -> None:
    at = datetime(2026, 7, 25, 19, 0)
    meal = _meal(at, carbs=70, role="main_meal")
    bolus = _insulin(at, event_type="Meal Bolus")

    result = classify_episode_therapy(
        EpisodeComponent(meals=[meal], insulin=[bolus], pairs=[]),
        [_point(at, raw=6.0, normalized=6.1)],
    )

    assert result.classification == "meal"
    assert result.confidence == "high"


def test_large_drink_and_dessert_component_is_one_meal() -> None:
    at = datetime(2026, 7, 25, 11, 50)
    drink = _meal(at, carbs=55, role="drink", title="Энергетический напиток")
    dessert = _meal(
        at + timedelta(seconds=15),
        carbs=28,
        role="dessert",
        title="Шоколад",
    )
    bolus = _insulin(at, event_type="Insulin")

    result = classify_episode_therapy(
        EpisodeComponent(meals=[drink, dessert], insulin=[bolus], pairs=[]),
        [_point(at, raw=6.1, normalized=8.4)],
    )

    assert result.classification == "meal"
    assert result.confidence == "high"
    assert "углеводы приёма: 83 г" in result.reasons


def test_insulin_without_food_is_insulin_correction() -> None:
    at = datetime(2026, 7, 25, 20, 0)
    correction = _insulin(at, event_type="Correction Bolus")

    result = classify_episode_therapy(
        EpisodeComponent(meals=[], insulin=[correction], pairs=[]),
        [_point(at, raw=11.0, normalized=10.8)],
    )

    assert result.classification == "insulin_correction"
    assert result.confidence == "high"


def test_food_with_explicit_insulin_correction_is_mixed() -> None:
    at = datetime(2026, 7, 25, 21, 0)
    meal = _meal(at, carbs=50, role="main_meal")
    correction = _insulin(at, event_type="Correction Bolus")

    result = classify_episode_therapy(
        EpisodeComponent(meals=[meal], insulin=[correction], pairs=[]),
        [_point(at, raw=9.0, normalized=9.2)],
    )

    assert result.classification == "mixed"
