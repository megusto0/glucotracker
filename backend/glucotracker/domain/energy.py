"""BMR and TDEE calculations from user profile and activity data."""

from __future__ import annotations

from glucotracker.infra.db.models import DailyActivity, UserProfile

ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

STEPS_MULTIPLIER_RANGES: list[tuple[int, float]] = [
    (0, 1.2),
    (3000, 1.3),
    (5000, 1.375),
    (7500, 1.5),
    (10000, 1.55),
    (12500, 1.7),
    (15000, 1.8),
]

FLEX_HR_OFFSET = 15
INTENSITY_MOVE_THRESHOLD = 20
KCAL_PER_MIN_CAP = 18.0
NO_MOVE_FACTOR = 0.35
STRIDE_M = 0.72
WALKING_KCAL_PER_KM_FACTOR = 0.6


def bmr_mifflin_st_jeor(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    sex: str,
) -> float:
    if sex == "male":
        return 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age_years + 5.0
    return 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age_years - 161.0


def activity_multiplier_from_steps(steps: int) -> float:
    multiplier = ACTIVITY_MULTIPLIERS["sedentary"]
    for threshold, mult in STEPS_MULTIPLIER_RANGES:
        if steps >= threshold:
            multiplier = mult
    return multiplier


def keypoint_kcal_per_min(
    hr: int,
    weight_kg: float,
    age_years: int,
    sex: str,
) -> float:
    if sex == "male":
        return (age_years * 0.2017 + weight_kg * 0.1988 + hr * 0.6309 - 55.0969) / 4.184
    return (age_years * 0.2017 + weight_kg * 0.1293 + hr * 0.6309 - 20.4022) / 4.184


def steps_kcal(steps: int, weight_kg: float) -> float:
    distance_km = steps * STRIDE_M / 1000
    return weight_kg * distance_km * WALKING_KCAL_PER_KM_FACTOR


def estimate_active_kcal_hybrid(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    sex: str,
    hr_rest: float | None,
    total_steps: int,
    hr_active_minutes: int,
    hr_no_move_minutes: int,
    avg_active_hr: float | None,
    kcal_hr_active_raw: float,
    kcal_no_move_hr_raw: float,
) -> dict:
    if hr_rest is None or hr_rest <= 0:
        hr_rest = 60.0

    bmr = bmr_mifflin_st_jeor(weight_kg, height_cm, age_years, sex)
    bmr_per_min = bmr / 1440.0
    flex_hr = hr_rest + FLEX_HR_OFFSET

    kcal_from_steps = steps_kcal(total_steps, weight_kg)

    if avg_active_hr is not None and avg_active_hr >= flex_hr:
        hr_active = min(kcal_hr_active_raw, hr_active_minutes * KCAL_PER_MIN_CAP)
    else:
        hr_active = 0.0

    no_move_active = kcal_no_move_hr_raw * NO_MOVE_FACTOR

    if hr_active > 0:
        active_kcal = max(hr_active, kcal_from_steps)
        sources = ["hr"]
        if kcal_from_steps > hr_active:
            active_kcal = kcal_from_steps
            sources = ["steps"]
    elif kcal_from_steps > 0:
        active_kcal = kcal_from_steps
        sources = ["steps"]
    elif no_move_active > 0:
        active_kcal = no_move_active
        sources = ["hr_no_move"]
    else:
        active_kcal = 0.0
        sources = []

    confidence = "low"
    if hr_active_minutes > 30 and total_steps > 1000:
        confidence = "medium"
    if hr_active_minutes > 60 and kcal_from_steps > 50:
        confidence = "high"

    return {
        "bmr": round(bmr, 1),
        "active_kcal": round(active_kcal, 1),
        "tdee": round(bmr + active_kcal, 1),
        "kcal_hr_active": round(hr_active, 1),
        "kcal_steps": round(kcal_from_steps, 1),
        "kcal_no_move_hr": round(no_move_active, 1),
        "confidence": confidence,
        "sources": sources,
        "flex_hr": round(flex_hr, 1),
        "hr_rest": round(hr_rest, 1),
    }


def tdee_from_profile(
    profile: UserProfile,
    activity: DailyActivity | None = None,
) -> float | None:
    if (
        profile.weight_kg is None
        or profile.height_cm is None
        or profile.age_years is None
        or profile.sex not in ("male", "female")
    ):
        return None

    base_bmr = bmr_mifflin_st_jeor(
        profile.weight_kg,
        profile.height_cm,
        profile.age_years,
        profile.sex,
    )

    if activity and activity.kcal_burned > 0:
        return round(base_bmr + activity.kcal_burned, 1)

    if activity and activity.steps > 0:
        multiplier = activity_multiplier_from_steps(activity.steps)
    else:
        multiplier = ACTIVITY_MULTIPLIERS.get(profile.activity_level, 1.55)

    return round(base_bmr * multiplier, 1)


def kcal_balance(
    kcal_in: float,
    profile: UserProfile,
    activity: DailyActivity | None = None,
) -> float | None:
    tdee = tdee_from_profile(profile, activity)
    if tdee is None:
        return None
    return round(kcal_in - tdee, 1)
