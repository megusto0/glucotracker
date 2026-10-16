"""A frozen alternative to the meal estimate, recorded but never shown.

The production meal estimate has no bias on this owner's history but misses by
about 2.5 U either way. A backtest of 657 past sittings
(`ml-labs/response-attribution/REPORT.md` §6) found part of the miss
predictable from what is known at the plate: glucose climbing into the meal,
meal size (history doses are scaled linearly with carbohydrate, which is wrong
at the edges), fat per gram of carbohydrate, and the first meal after sleep.
Together they cut the error from 2.56 to 2.37 U in a time-ordered check, with a
90% interval of −0.02…+0.40 — suggestive, not proven.

So the correction is not applied. Its coefficients were fitted once, on
everything up to 2026-10-01, and frozen here; every recommendation stores what
it would have said beside what was actually recommended. Sittings after the
freeze are then a clean prospective test of a model that never saw them. The
dose a user sees does not change, and nothing here reaches the API response.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log

SHADOW_MODEL_VERSION = "meal-residual-shadow-v1"
#: Every sitting after this moment is out of sample for the coefficients below.
SHADOW_FROZEN_AT = "2026-10-01"

# residual U = intercept + Σ coefficient · feature, fitted with ISF 2.6 on 184
# sittings without further food for three hours; label = all insulin the meal
# received plus the four-hour glucose change divided by ISF.
_INTERCEPT = 3.976
_TREND_PER_30_MIN = 0.513
_LOG_CARBS = -1.133
_FAT_PER_CARB = 3.276
_AFTER_SLEEP = -2.207

#: Features outside the range they were fitted on are clamped to it.
_TREND_LIMIT_MMOL_L = 3.0
_MIN_CARBS_G = 10.0
_MAX_CARBS_G = 200.0
_MAX_FAT_PER_CARB = 1.5
#: The fitted residual reached ±3 U on its own data; beyond that is
#: extrapolation, which a shadow record should not pretend to know.
_MAX_RESIDUAL_UNITS = 3.0


@dataclass(frozen=True)
class ShadowMealEstimate:
    """What the frozen alternative would have recommended for the food."""

    model_version: str
    frozen_at: str
    production_meal_units: float
    residual_units: float
    shadow_meal_units: float
    trend_mmol_l_per_30_min: float
    trend_missing: bool
    carbs_g: float
    fat_per_carb: float
    after_sleep: bool


def shadow_meal_estimate(
    *,
    production_meal_units: float | None,
    carbs_g: float,
    fat_g: float,
    trend_mmol_l_per_min: float | None,
    after_sleep: bool,
) -> ShadowMealEstimate | None:
    """Return the shadow estimate, or None when there is no production one."""
    if (
        production_meal_units is None
        or not isfinite(production_meal_units)
        or carbs_g <= 0
    ):
        return None
    trend_missing = trend_mmol_l_per_min is None or not isfinite(trend_mmol_l_per_min)
    trend = 0.0 if trend_missing else float(trend_mmol_l_per_min) * 30.0
    trend = max(-_TREND_LIMIT_MMOL_L, min(_TREND_LIMIT_MMOL_L, trend))
    carbs = max(_MIN_CARBS_G, min(_MAX_CARBS_G, carbs_g))
    fat_per_carb = max(0.0, min(_MAX_FAT_PER_CARB, max(0.0, fat_g) / carbs_g))
    residual = (
        _INTERCEPT
        + _TREND_PER_30_MIN * trend
        + _LOG_CARBS * log(carbs)
        + _FAT_PER_CARB * fat_per_carb
        + (_AFTER_SLEEP if after_sleep else 0.0)
    )
    residual = max(-_MAX_RESIDUAL_UNITS, min(_MAX_RESIDUAL_UNITS, residual))
    return ShadowMealEstimate(
        model_version=SHADOW_MODEL_VERSION,
        frozen_at=SHADOW_FROZEN_AT,
        production_meal_units=round(production_meal_units, 2),
        residual_units=round(residual, 2),
        shadow_meal_units=round(max(0.0, production_meal_units + residual), 1),
        trend_mmol_l_per_30_min=round(trend, 2),
        trend_missing=trend_missing,
        carbs_g=round(carbs_g, 1),
        fat_per_carb=round(fat_per_carb, 3),
        after_sleep=after_sleep,
    )
