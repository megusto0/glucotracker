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
    observed_steps_kcal = 70 * (500 * 0.72 / 1000) * 0.6

    assert tdee_from_profile(
        profile,
        activity,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    ) == round(bmr * 1.2 + observed_steps_kcal, 1)


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


def test_tdee_rejected_health_connect_total_keeps_observed_active_kcal() -> None:
    profile = _profile()
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=300,
        steps=0,
        kcal_hr_active=120,
        source="health_connect_total",
    )

    bmr = bmr_mifflin_st_jeor(70, 175, 30, "male")

    assert tdee_from_profile(
        profile,
        activity,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    ) == round(bmr * 1.2 + 120, 1)


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


def test_tdee_adds_heart_rate_effort_when_the_device_total_is_basal_only() -> None:
    """A basal-only Health Connect total no longer hides a four-hour ride."""
    profile = _profile()
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=1400,
        steps=5000,
        source="health_connect_total",
    )

    bmr = bmr_mifflin_st_jeor(70, 175, 30, "male")
    walking = 70 * (1000 * 0.72 / 1000) * 0.6

    assert tdee_from_profile(
        profile,
        activity,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        effort_kcal=1800,
        effort_steps=4000,
    ) == round(bmr * 1.2 + walking + 1800, 1)


def test_tdee_adds_effort_to_a_sedentary_base_without_any_device_figure() -> None:
    profile = _profile()
    bmr = bmr_mifflin_st_jeor(70, 175, 30, "male")

    assert tdee_from_profile(profile, None, effort_kcal=250) == round(
        bmr * 1.2 + 250,
        1,
    )


def test_a_real_device_total_already_contains_the_effort() -> None:
    activity = DailyActivity(
        owner_id=uuid4(),
        date=date(2026, 5, 5),
        kcal_burned=3400,
        source="health_connect_total",
    )

    assert tdee_from_profile(_profile(), activity, effort_kcal=1500) == 3400


def test_keytel_female_equation_uses_its_own_coefficients() -> None:
    from glucotracker.domain.energy import keypoint_kcal_per_min

    # Keytel 2005 without VO2max: -20.4022 + 0.4472 HR - 0.1263 kg + 0.074 age, kJ/min.
    expected = (-20.4022 + 0.4472 * 140 - 0.1263 * 60 + 0.074 * 30) / 4.184
    assert abs(keypoint_kcal_per_min(140, 60, 30, "female") - expected) < 1e-9
