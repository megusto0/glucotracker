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


def test_low_raw_reading_alone_is_not_a_rescue() -> None:
    """A raw 2.5 that calibrates to 4.8 is an ordinary in-range dessert.

    This used to classify on min(raw, normalized) so that a deeply low raw
    reading won regardless, on the reasoning that an alarm should err low.
    That is right for an alarm and wrong for a label: this sensor runs 1.0-2.8
    mmol/L under true glucose, so the +2.3 seen here is the expected offset and
    nothing about the moment was low. Every such plate was being filed as a
    rescue. Both raw figures stay in the response; only the judgement changed.
    """
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

    assert result.classification == "snack"
    assert result.glucose_at_start_raw == 2.5
    assert result.glucose_at_start_normalized == 4.8
    assert result.peak_post_event_normalized == 9.0


def test_low_calibrated_glucose_before_food_is_a_rescue() -> None:
    """The same shape, but the calibrated value is the one below range."""
    at = datetime(2026, 7, 25, 14, 47)
    cookie = _meal(
        at,
        carbs=30,
        role="dessert",
        title="Шоколадное печенье",
    )
    points = [
        _point(at - timedelta(minutes=10), raw=1.4, normalized=3.7),
        _point(at, raw=1.2, normalized=3.4),
        _point(at + timedelta(hours=2), raw=6.0, normalized=8.3),
        _point(at + timedelta(minutes=140), raw=6.7, normalized=9.0),
    ]

    result = classify_episode_therapy(
        EpisodeComponent(meals=[cookie], insulin=[], pairs=[]),
        points,
    )

    assert result.classification == "carb_correction"
    assert result.suggested_carbs_g == 15.0
    assert result.suggestion_source == "ada_default"


def test_sitting_in_progress_is_not_called_a_rescue() -> None:
    """Food at a genuine low, no bolus yet — a lunch that has not been dosed.

    The user photographs dish by dish and doses at the end, so "no insulin" is
    not evidence until a bolus would no longer be attributed to the sitting.
    Only the timing differs between the two calls below; the trace is low
    enough either way, which is what leaves the settling rule visible.
    """
    at = datetime(2026, 7, 25, 13, 0)
    plate = _meal(at, carbs=25, role="main")
    points = [
        _point(at - timedelta(minutes=20), raw=1.6, normalized=4.2),
        _point(at, raw=1.2, normalized=3.7),
    ]
    component = EpisodeComponent(meals=[plate], insulin=[], pairs=[])

    fresh = classify_episode_therapy(
        component,
        points,
        now=at + timedelta(minutes=10),
    )
    settled = classify_episode_therapy(
        component,
        points,
        now=at + timedelta(hours=3),
    )

    assert fresh.classification == "meal"
    assert settled.classification == "carb_correction"


def test_dessert_at_in_range_glucose_is_snack() -> None:
    at = datetime(2026, 7, 25, 18, 0)
    dessert = _meal(at, carbs=24, role="dessert")

    result = classify_episode_therapy(
        EpisodeComponent(meals=[dessert], insulin=[], pairs=[]),
        [_point(at, raw=5.7, normalized=5.9)],
    )

    assert result.classification == "snack"
    assert result.suggested_carbs_g is None


def test_small_meal_during_a_fall_toward_range_is_not_a_rescue() -> None:
    """A steep slope is not a low, and this one lands nowhere near one.

    This case used to classify as a rescue on the reasoning that food-role
    metadata must not override an obvious rescue pattern — but the pattern was
    only a slope. Coming down from 8.7 to 6.7 is what every meal does after its
    peak, so an omelette eaten during the descent was filed as hypo treatment,
    which is where the diary's spurious orange rows came from. The rule now
    reads the trough instead of extrapolating the slope: nothing here went below
    6.7, so nothing was rescued.
    """
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

    assert result.classification == "meal"
    assert result.suggested_carbs_g is None


def test_the_same_fall_reaching_a_low_is_a_rescue() -> None:
    """Identical food and slope, carried three mmol/L lower.

    The pair with the test above is the point: what separates the two is where
    glucose ended up, not how fast it was moving or what the plate was called.
    """
    at = datetime(2026, 7, 25, 12, 30)
    small_meal = _meal(
        at,
        carbs=7,
        role="main_meal",
        title="Омлет с грибами и соусом",
    )
    points = [
        _point(at - timedelta(minutes=20), raw=3.4, normalized=5.7),
        _point(at - timedelta(minutes=10), raw=2.4, normalized=4.7),
        _point(at, raw=1.4, normalized=3.7),
    ]

    result = classify_episode_therapy(
        EpisodeComponent(meals=[small_meal], insulin=[], pairs=[]),
        points,
    )

    assert result.classification == "carb_correction"
    assert result.suggested_carbs_g == 15.0
    assert "глюкоза быстро снижалась перед едой" in result.reasons
    assert "небольшой приём: 7 г" in result.reasons


def test_a_rescue_without_cgm_cover_is_not_guessed() -> None:
    """No calibrated glucose around the plate means no hypo label.

    A gap in the trace is the one case where the old rule and the new one would
    both like to say something, and the honest answer is that whether a low
    happened is unknown. Unknown must not render as an orange row.
    """
    at = datetime(2026, 7, 25, 3, 40)
    juice = _meal(at, carbs=12, role="drink", title="Сок яблочный")

    result = classify_episode_therapy(
        EpisodeComponent(meals=[juice], insulin=[], pairs=[]),
        [_point(at - timedelta(hours=2), raw=1.1, normalized=3.4)],
    )

    assert result.classification == "snack"


def test_juice_at_a_night_low_that_turned_around_is_a_confident_rescue() -> None:
    """The mockup's own episode: 12 g of juice against a 3.6 at 01:05."""
    at = datetime(2026, 8, 6, 1, 5)
    juice = _meal(at, carbs=12, role="drink", title="Сок яблочный")
    juice.total_protein_g = 0
    juice.total_fat_g = 0
    juice.ai_categories = {"taste_profile": "drink_sweet"}
    points = [
        _point(at - timedelta(minutes=5), raw=1.3, normalized=3.7),
        _point(at, raw=1.2, normalized=3.6),
        _point(at + timedelta(minutes=20), raw=2.0, normalized=4.4),
        _point(at + timedelta(minutes=55), raw=5.5, normalized=7.9),
    ]

    result = classify_episode_therapy(
        EpisodeComponent(meals=[juice], insulin=[], pairs=[]),
        points,
    )

    assert result.classification == "carb_correction"
    assert result.confidence == "high"
    assert result.trough_normalized == 3.6
    assert {item.code for item in result.evidence} >= {
        "low_before_food",
        "small_portion",
        "no_bolus",
        "fast_carbs",
        "lean_portion",
        "reversed",
    }


def test_food_dosed_with_a_bolus_at_a_low_is_not_a_rescue() -> None:
    """Eating at 3.7 and dosing for it is a meal begun low, not treatment."""
    at = datetime(2026, 7, 25, 13, 0)
    plate = _meal(at, carbs=28, role="main_meal")
    bolus = _insulin(at + timedelta(minutes=5), event_type="Meal Bolus")
    points = [
        _point(at - timedelta(minutes=10), raw=1.5, normalized=4.0),
        _point(at, raw=1.2, normalized=3.7),
    ]

    result = classify_episode_therapy(
        EpisodeComponent(meals=[plate], insulin=[bolus], pairs=[]),
        points,
    )

    assert result.classification == "meal"


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
