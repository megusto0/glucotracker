"""Absorption and action kernels for the digital twin estimator.

Insulin IOB uses a data-calibrated biphasic cumulative action curve derived
from isolated-bolus CGM drop-rate integration (historical user log):

- ~12% of action by 30 min
- ~25% by 60 min
- ~35% by 90 min   (front-loaded, but not "most")
- ~60% by 180 min
- ~78% by 270 min
- tail to ~360 min for full delivery

IOB remaining = 1 - cumulative absorbed. Activity (for BG effect) is the
time-derivative of cumulative absorption, peak-normalized to 1.0 so peak
amplitude stays ``units * isf`` for the twin estimator.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from glucotracker.application.twin.estimator import EstimatorParams

# Cumulative fraction of total pharmacodynamic effect delivered by time t.
# Source: mean of isolated-bolus CGM activity integrals (n≈26), horizon 360 min.
_INSULIN_CUM_ABSORBED_KNOTS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (30.0, 0.12),
    (60.0, 0.25),
    (90.0, 0.35),
    (120.0, 0.45),
    (150.0, 0.54),
    (180.0, 0.60),
    (210.0, 0.65),
    (240.0, 0.73),
    (270.0, 0.78),
    (300.0, 0.87),
    (330.0, 0.93),
    (360.0, 1.0),
)

_REFERENCE_DIA_MIN = 360.0
_IOB_EPSILON = 0.02


# Carbohydrate absorption profiles from historical CGM reactions
# (admin2 log, low nearby insulin, pure_carb vs high fat/protein meals).
#
# pure_carb / energy drinks: peak rise often ~40–100 min, frequently back
# toward baseline by ~2 h when not stacked with more food/insulin.
# high fat/protein: slower early rise + prolonged / second-wave elevation
# out to 4–6 h (chocolate, glazirovannyi syrok, heavy mixed plates).
#
# Values = cumulative fraction of meal carb *effect* delivered by time t.
_CARB_PROFILE_KNOTS: dict[str, tuple[tuple[float, float], ...]] = {
    # Liquid sugar / pure carbs (energy drink, gel, sweet tea).
    # ~50% by ~40–50 min, ~70% by 60, ~90% by 90, done ~2 h.
    "fast": (
        (0.0, 0.0),
        (20.0, 0.22),
        (40.0, 0.50),
        (60.0, 0.70),
        (90.0, 0.88),
        (120.0, 1.0),
    ),
    # Fruit, potato, moderate mixed plates.
    "normal": (
        (0.0, 0.0),
        (30.0, 0.15),
        (60.0, 0.35),
        (90.0, 0.52),
        (120.0, 0.68),
        (150.0, 0.80),
        (180.0, 0.90),
        (240.0, 1.0),
    ),
    # High fat/protein (egg salad, chocolate, burgers): long dual-wave tail.
    "slow": (
        (0.0, 0.0),
        (30.0, 0.08),
        (60.0, 0.18),
        (90.0, 0.30),
        (120.0, 0.40),
        (180.0, 0.55),
        (240.0, 0.70),
        (300.0, 0.85),
        (360.0, 0.94),
        (420.0, 1.0),
    ),
}

_CARB_PROFILE_DURATION: dict[str, int] = {
    "fast": 120,
    "normal": 240,
    "slow": 420,
}

_COB_EPSILON = 0.02


def classify_carb_profile(
    *,
    carbs_g: float,
    protein_g: float = 0.0,
    fat_g: float = 0.0,
    fiber_g: float = 0.0,
) -> str:
    """Classify meal absorption speed from macros (display / COB / twin).

    Examples from real logs:
    - Energy drink ~54 g carbs, 0/0/0 → ``fast``
    - Egg/veg salad ~14.5 g carbs, 12.5 p, 16.2 f → ``slow``
    """
    carbs = max(0.0, float(carbs_g or 0.0))
    protein = max(0.0, float(protein_g or 0.0))
    fat = max(0.0, float(fat_g or 0.0))
    fiber = max(0.0, float(fiber_g or 0.0))
    if carbs <= 0:
        return "normal"

    # Pure sugar liquids / candy: almost only carbs, negligible fiber.
    if fat + protein < 2.0 and fiber < 1.5 and carbs >= 8.0:
        return "fast"

    fat_ratio = fat / carbs
    protein_ratio = protein / carbs
    fiber_ratio = fiber / carbs
    slow_score = 0
    if fat_ratio >= 0.8:
        slow_score += 3
    elif fat_ratio >= 0.4:
        slow_score += 2
    elif fat_ratio >= 0.2:
        slow_score += 1
    # High absolute fat (chocolate, burger) prolongs even at moderate ratio.
    if fat >= 15.0 and fat_ratio >= 0.45:
        slow_score += 1
    if protein_ratio >= 0.6:
        slow_score += 2
    elif protein_ratio >= 0.3:
        slow_score += 1
    if fiber_ratio >= 0.08:
        slow_score += 1

    if slow_score >= 3:
        return "slow"
    # Low-fat solids with little protein/fiber still absorb quickly (juice-like),
    # but whole starch with fiber stays normal.
    if slow_score == 0 and fat + protein < 5.0 and fiber < 1.0:
        return "fast"
    return "normal"


def carb_absorption_duration_minutes(
    *,
    carbs_g: float,
    protein_g: float = 0.0,
    fat_g: float = 0.0,
    fiber_g: float = 0.0,
    default_minutes: int | None = None,
) -> int:
    """Return COB duration for a meal; ``default_minutes`` overrides ``normal``."""
    profile = classify_carb_profile(
        carbs_g=carbs_g,
        protein_g=protein_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
    )
    if profile == "normal" and default_minutes is not None and default_minutes > 0:
        return int(default_minutes)
    return _CARB_PROFILE_DURATION[profile]


def carb_cumulative_absorbed(
    dt_min: float,
    *,
    duration_min: int,
    profile: str = "normal",
) -> float:
    """Fraction of meal carb effect delivered by ``dt_min`` in ``[0, 1]``."""
    if dt_min <= 0 or duration_min <= 0:
        return 0.0
    if dt_min >= duration_min:
        return 1.0
    knots = _CARB_PROFILE_KNOTS.get(profile) or _CARB_PROFILE_KNOTS["normal"]
    ref_end = knots[-1][0]
    scale = ref_end / float(duration_min)
    f_t = _interp_knots(dt_min * scale, knots)
    f_end = _interp_knots(min(duration_min * scale, ref_end), knots)
    if f_end <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, f_t / f_end))


def carb_cob_remaining_fraction(
    dt_min: float,
    *,
    duration_min: int,
    profile: str = "normal",
) -> float:
    """Remaining COB fraction for a meal (1 at t=0)."""
    if dt_min <= 0:
        return 1.0
    if duration_min <= 0 or dt_min >= duration_min:
        return 0.0
    return max(
        0.0,
        1.0
        - carb_cumulative_absorbed(
            dt_min,
            duration_min=duration_min,
            profile=profile,
        ),
    )


def carb_minutes_remaining(
    dt_min: float,
    *,
    duration_min: int,
    profile: str = "normal",
) -> int:
    """Minutes until COB residual is negligible."""
    if duration_min <= 0 or dt_min >= duration_min:
        return 0
    if dt_min <= 0:
        return int(duration_min)
    lo = max(0.0, dt_min)
    hi = float(duration_min)
    for _ in range(32):
        mid = 0.5 * (lo + hi)
        if (
            carb_cob_remaining_fraction(
                mid,
                duration_min=duration_min,
                profile=profile,
            )
            <= _COB_EPSILON
        ):
            hi = mid
        else:
            lo = mid
    return int(max(0.0, hi - dt_min) + 0.999)


def carb_effect(dt_min: float, grams: float, icr: float, duration_min: int) -> float:
    """Return bilinear carbohydrate absorption effect in mmol/L.

    Peak amplitude is ``grams / icr``. Callers that know meal macros should prefer
    :func:`carb_effect_for_meal` for fast/slow timing.
    """
    if dt_min <= 0 or dt_min >= duration_min or grams <= 0 or icr <= 0:
        return 0.0

    first = duration_min / 3
    second = (duration_min * 2) / 3
    if dt_min <= first:
        shape = dt_min / first
    elif dt_min <= second:
        shape = 1.0
    else:
        shape = (duration_min - dt_min) / (duration_min - second)
    return (grams / icr) * max(0.0, min(shape, 1.0))


def carb_effect_for_meal(
    dt_min: float,
    *,
    carbs_g: float,
    icr: float,
    protein_g: float = 0.0,
    fat_g: float = 0.0,
    fiber_g: float = 0.0,
    default_duration_minutes: int | None = None,
) -> float:
    """Meal-aware carb effect: profile timing, peak amplitude still grams/icr."""
    if carbs_g <= 0 or icr <= 0:
        return 0.0
    profile = classify_carb_profile(
        carbs_g=carbs_g,
        protein_g=protein_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
    )
    duration = carb_absorption_duration_minutes(
        carbs_g=carbs_g,
        protein_g=protein_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        default_minutes=default_duration_minutes,
    )
    if dt_min <= 0 or dt_min >= duration:
        return 0.0
    activity = _carb_activity_shape(dt_min, duration_min=duration, profile=profile)
    return (carbs_g / icr) * activity


def _interp_knots(t: float, knots: tuple[tuple[float, float], ...]) -> float:
    if t <= 0:
        return 0.0
    if t >= knots[-1][0]:
        return float(knots[-1][1])
    for idx in range(1, len(knots)):
        t1, f1 = knots[idx]
        t0, f0 = knots[idx - 1]
        if t <= t1:
            if t1 <= t0:
                return float(f1)
            ratio = (t - t0) / (t1 - t0)
            return float(f0 + (f1 - f0) * ratio)
    return float(knots[-1][1])


def _carb_activity_shape(
    dt_min: float,
    *,
    duration_min: int,
    profile: str,
) -> float:
    if dt_min <= 0 or duration_min <= 0 or dt_min >= duration_min:
        return 0.0
    peak = _carb_peak_activity(duration_min, profile)
    if peak <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, _carb_raw_activity(dt_min, duration_min, profile) / peak))


def _carb_raw_activity(dt_min: float, duration_min: int, profile: str) -> float:
    eps = 2.5
    f0 = carb_cumulative_absorbed(
        max(0.0, dt_min - eps),
        duration_min=duration_min,
        profile=profile,
    )
    f1 = carb_cumulative_absorbed(
        dt_min + eps,
        duration_min=duration_min,
        profile=profile,
    )
    return max(0.0, (f1 - f0) / (2.0 * eps))


@lru_cache(maxsize=64)
def _carb_peak_activity(duration_min: int, profile: str) -> float:
    if duration_min <= 0:
        return 1.0
    peak = 0.0
    for t in range(0, duration_min + 1, 5):
        if 0 < t < duration_min:
            peak = max(peak, _carb_raw_activity(float(t), duration_min, profile))
    return peak if peak > 1e-12 else 1.0


def insulin_cumulative_absorbed(dt_min: float, dia_min: int) -> float:
    """Return fraction of total insulin action delivered by ``dt_min`` in ``[0, 1]``.

    The empirical shape is defined on a 0–360 min reference horizon and rescaled
    so that cumulative absorption reaches 1.0 exactly at ``dia_min``.
    """
    if dt_min <= 0 or dia_min <= 0:
        return 0.0
    if dt_min >= dia_min:
        return 1.0

    # Map query time into the reference curve, then renormalize by F(dia).
    scale = _REFERENCE_DIA_MIN / float(dia_min)
    ref_t = dt_min * scale
    ref_dia_t = float(dia_min) * scale  # == REFERENCE_DIA when dia==360
    f_t = _interp_cum(ref_t)
    f_dia = _interp_cum(min(ref_dia_t, _REFERENCE_DIA_MIN))
    if f_dia <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, f_t / f_dia))


def insulin_iob_remaining_fraction(dt_min: float, dia_min: int) -> float:
    """Return fraction of the bolus still active (IOB / dose) at ``dt_min``."""
    if dt_min <= 0:
        return 1.0
    if dia_min <= 0 or dt_min >= dia_min:
        return 0.0
    return max(0.0, 1.0 - insulin_cumulative_absorbed(dt_min, dia_min))


def insulin_minutes_remaining(dt_min: float, dia_min: int) -> int:
    """Return approximate minutes until IOB falls below a small residual."""
    if dia_min <= 0 or dt_min >= dia_min:
        return 0
    if dt_min <= 0:
        return int(dia_min)

    # Binary search the first time remaining fraction <= epsilon.
    lo = max(0.0, dt_min)
    hi = float(dia_min)
    for _ in range(32):
        mid = 0.5 * (lo + hi)
        if insulin_iob_remaining_fraction(mid, dia_min) <= _IOB_EPSILON:
            hi = mid
        else:
            lo = mid
    remaining = max(0.0, hi - dt_min)
    return int(remaining + 0.999)  # ceil


def insulin_activity_shape(dt_min: float, dia_min: int) -> float:
    """Return peak-normalized insulin activity at ``dt_min`` (max ≈ 1)."""
    if dt_min <= 0 or dia_min <= 0 or dt_min >= dia_min:
        return 0.0
    peak = _peak_activity(int(dia_min))
    if peak <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, _raw_activity(dt_min, dia_min) / peak))


def insulin_effect(dt_min: float, units: float, isf: float, dia_min: int) -> float:
    """Return data-shaped insulin action effect in mmol/L (positive).

    Peak amplitude remains ``units * isf`` so twin ISF semantics stay stable;
    only the time course is biphasic / front-loaded with a long tail.
    """
    if dt_min <= 0 or dt_min >= dia_min or units <= 0 or isf <= 0 or dia_min <= 0:
        return 0.0
    return units * isf * insulin_activity_shape(dt_min, dia_min)


def icr_at(ts: datetime, params: EstimatorParams) -> float:
    """Return the active ICR by minutes from local midnight."""
    minutes = ts.hour * 60 + ts.minute
    if minutes < params.day_start_minutes:
        return params.icr_morning
    if minutes < params.evening_start_minutes:
        return params.icr_day
    return params.icr_evening


def _interp_cum(t: float) -> float:
    """Piecewise-linear interpolate the reference cumulative absorption curve."""
    if t <= 0:
        return 0.0
    knots = _INSULIN_CUM_ABSORBED_KNOTS
    if t >= knots[-1][0]:
        return 1.0
    for idx in range(1, len(knots)):
        t1, f1 = knots[idx]
        t0, f0 = knots[idx - 1]
        if t <= t1:
            if t1 <= t0:
                return f1
            ratio = (t - t0) / (t1 - t0)
            return f0 + (f1 - f0) * ratio
    return 1.0


def _raw_activity(dt_min: float, dia_min: int) -> float:
    """Finite-difference of cumulative absorbed (action rate, unnormalized)."""
    # Half-window large enough for stable piecewise slopes, small vs DIA.
    eps = 2.5
    f0 = insulin_cumulative_absorbed(max(0.0, dt_min - eps), dia_min)
    f1 = insulin_cumulative_absorbed(dt_min + eps, dia_min)
    return max(0.0, (f1 - f0) / (2.0 * eps))


@lru_cache(maxsize=64)
def _peak_activity(dia_min: int) -> float:
    """Max raw activity over the DIA (cached per duration)."""
    if dia_min <= 0:
        return 1.0
    peak = 0.0
    # Sample at knot-scaled times plus a fine grid early where the peak lives.
    samples = {0.0, float(dia_min)}
    scale = float(dia_min) / _REFERENCE_DIA_MIN
    for t_ref, _ in _INSULIN_CUM_ABSORBED_KNOTS:
        samples.add(t_ref * scale)
    for t in range(0, min(dia_min, 180) + 1, 5):
        samples.add(float(t))
    for t in samples:
        if 0.0 < t < dia_min:
            peak = max(peak, _raw_activity(t, dia_min))
    return peak if peak > 1e-12 else 1.0
