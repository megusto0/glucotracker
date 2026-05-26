"""TDEE calculation tests."""

from datetime import UTC, date, datetime
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


def test_tdee_projects_same_day_health_connect_total_to_full_day_estimate() -> None:
    profile = _profile()
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=1000,
        source="health_connect_total",
    )

    bmr = bmr_mifflin_st_jeor(70, 175, 30, "male")

    assert tdee_from_profile(
        profile,
        activity,
        now=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
    ) == round(1000 + bmr * 0.5, 1)


def test_tdee_rejects_implausibly_low_past_health_connect_total() -> None:
    profile = _profile()
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=300,
        steps=500,
        source="health_connect_total",
    )

    bmr = bmr_mifflin_st_jeor(70, 175, 30, "male")

    assert tdee_from_profile(
        profile,
        activity,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    ) == round(bmr * 1.2, 1)


def test_tdee_rejects_low_health_connect_total_without_steps_as_sedentary() -> None:
    profile = _profile()
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=300,
        steps=0,
        source="health_connect_total",
    )

    bmr = bmr_mifflin_st_jeor(70, 175, 30, "male")

    assert tdee_from_profile(
        profile,
        activity,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    ) == round(bmr * 1.2, 1)


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
