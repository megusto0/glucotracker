"""TDEE calculation tests."""

from datetime import date
from uuid import uuid4

from glucotracker.domain.energy import bmr_mifflin_st_jeor, tdee_from_profile
from glucotracker.infra.db.models import DailyActivity, UserProfile


def _profile() -> UserProfile:
    return UserProfile(
        owner_id=uuid4(),
        weight_kg=70,
        height_cm=175,
        age_years=30,
        sex="male",
        activity_level="moderate",
    )


def test_tdee_uses_health_connect_total_calories_as_full_day_estimate() -> None:
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=2234.6,
        source="health_connect_total",
    )

    assert tdee_from_profile(_profile(), activity) == 2234.6


def test_tdee_adds_active_calorie_sources_to_bmr() -> None:
    profile = _profile()
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=412.5,
        source="health_connect_active",
    )

    expected = bmr_mifflin_st_jeor(70, 175, 30, "male") + 412.5
    assert tdee_from_profile(profile, activity) == round(expected, 1)
