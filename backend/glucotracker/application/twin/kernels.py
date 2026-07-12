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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from math import ceil, exp, isfinite
from typing import TYPE_CHECKING, Literal

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

# Canonical query/lookback horizon for callers that may encounter any profile.
MAX_CARB_ABSORPTION_MINUTES = max(_CARB_PROFILE_DURATION.values())

_COB_EPSILON = 0.02

CarbProfile = Literal["fast", "normal", "slow"]


@dataclass(frozen=True, slots=True)
class PersonalizedInsulinKernel:
    """Validated parameters for a personalized smooth insulin-action kernel.

    Each component is a second-order Erlang distribution. Its survival function
    is ``exp(-t / tau) * (1 + t / tau)`` and its action rate is the exact
    derivative of the corresponding cumulative distribution. The mixture is
    deliberately small (four fitted values) so retrospective fits can shrink
    safely toward a population prior instead of overfitting individual days.
    """

    fast_weight: float
    fast_tau_minutes: float
    slow_tau_minutes: float
    horizon_minutes: float = 390.0

    def __post_init__(self) -> None:
        values = (
            self.fast_weight,
            self.fast_tau_minutes,
            self.slow_tau_minutes,
            self.horizon_minutes,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("insulin kernel parameters must be finite")
        if not 0.0 <= self.fast_weight <= 1.0:
            raise ValueError("fast_weight must be between 0 and 1")
        if self.fast_tau_minutes <= 0.0 or self.slow_tau_minutes <= 0.0:
            raise ValueError("insulin time constants must be positive")
        if self.fast_tau_minutes > self.slow_tau_minutes:
            raise ValueError("fast_tau_minutes must not exceed slow_tau_minutes")
        if not 240.0 <= self.horizon_minutes <= 720.0:
            raise ValueError("horizon_minutes must be between 240 and 720")
        if self.slow_tau_minutes >= self.horizon_minutes:
            raise ValueError("slow_tau_minutes must be below horizon_minutes")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> PersonalizedInsulinKernel:
        """Parse persisted JSON-like parameters through the same validation."""
        try:
            return cls(
                fast_weight=float(value["fast_weight"]),
                fast_tau_minutes=float(value["fast_tau_minutes"]),
                slow_tau_minutes=float(value["slow_tau_minutes"]),
                horizon_minutes=float(value.get("horizon_minutes", 390.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid personalized insulin kernel mapping") from exc

    def to_mapping(self) -> dict[str, float]:
        """Return a stable JSON-serializable representation."""
        return {
            "fast_weight": self.fast_weight,
            "fast_tau_minutes": self.fast_tau_minutes,
            "slow_tau_minutes": self.slow_tau_minutes,
            "horizon_minutes": self.horizon_minutes,
        }


@dataclass(frozen=True, slots=True)
class CarbProfileWeights:
    """Normalized soft membership of the fast/normal/slow COB basis curves."""

    fast: float
    normal: float
    slow: float

    def __post_init__(self) -> None:
        values = (self.fast, self.normal, self.slow)
        if not all(isfinite(value) and value >= 0.0 for value in values):
            raise ValueError("carb profile weights must be finite and non-negative")
        total = sum(values)
        if total <= 0.0:
            raise ValueError("at least one carb profile weight must be positive")
        object.__setattr__(self, "fast", self.fast / total)
        object.__setattr__(self, "normal", self.normal / total)
        object.__setattr__(self, "slow", self.slow / total)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> CarbProfileWeights:
        """Parse persisted JSON-like mixture weights and normalize them."""
        try:
            return cls(
                fast=float(value["fast"]),
                normal=float(value["normal"]),
                slow=float(value["slow"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid carb profile weights mapping") from exc

    def to_mapping(self) -> dict[str, float]:
        """Return a stable JSON-serializable representation."""
        return {
            "fast": self.fast,
            "normal": self.normal,
            "slow": self.slow,
        }

    def for_profile(self, profile: CarbProfile) -> float:
        """Return the normalized weight for one basis profile."""
        return float(getattr(self, profile))

    @property
    def dominant_profile(self) -> CarbProfile:
        """Return the largest-weight profile for compact legacy displays."""
        return max(
            ("fast", "normal", "slow"),
            key=lambda profile: self.for_profile(profile),
        )


# Least-squares approximation of the legacy 360-minute population-of-one knots.
# It intentionally stays an explicit opt-in; legacy callers keep their exact
# piecewise curve unless a stored personalized model is selected.
POPULATION_INSULIN_KERNEL_V2 = PersonalizedInsulinKernel(
    fast_weight=0.21,
    fast_tau_minutes=24.0,
    slow_tau_minutes=158.0,
    horizon_minutes=390.0,
)


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


def carb_profile_prior_weights(
    *,
    carbs_g: float,
    protein_g: float = 0.0,
    fat_g: float = 0.0,
    fiber_g: float = 0.0,
    is_liquid: bool | None = None,
    is_sweetened: bool | None = None,
    profile_hint: CarbProfile | None = None,
) -> CarbProfileWeights:
    """Build soft COB basis weights from meal features.

    The result is a prior, not a final retrospective fit. ``profile_hint`` is an
    optional categorical signal derived by a caller from product identity or a
    reviewed meal class; this module intentionally does not guess from titles.
    Explicit liquid/solid information prevents low-fat solid starches from being
    treated exactly like sugar drinks. Every result retains non-zero support for
    all three basis curves so later personal evidence can update it smoothly.
    """
    if profile_hint is not None and profile_hint not in _CARB_PROFILE_KNOTS:
        raise ValueError(f"unknown carb profile hint: {profile_hint}")

    carbs = max(0.0, float(carbs_g or 0.0))
    protein = max(0.0, float(protein_g or 0.0))
    fat = max(0.0, float(fat_g or 0.0))
    fiber = max(0.0, float(fiber_g or 0.0))

    # Pseudo-counts encode a conservative normal-meal population prior.
    evidence = {"fast": 1.0, "normal": 3.0, "slow": 1.0}
    if carbs <= 0.0:
        evidence["normal"] += 12.0
    else:
        fat_ratio = fat / carbs
        protein_ratio = protein / carbs
        fiber_ratio = fiber / carbs
        nearly_pure_carb = fat + protein < 2.0 and fiber < 1.5 and carbs >= 8.0

        if nearly_pure_carb:
            if is_liquid is False:
                # A known solid needs a normal/starch prior, even when macros are
                # sparse. A reviewed identity hint can still override this.
                evidence["fast"] += 1.0
                evidence["normal"] += 4.0
            else:
                evidence["fast"] += 3.0

        slow_score = 0
        if fat_ratio >= 0.8:
            slow_score += 3
        elif fat_ratio >= 0.4:
            slow_score += 2
        elif fat_ratio >= 0.2:
            slow_score += 1
        if fat >= 15.0 and fat_ratio >= 0.45:
            slow_score += 1
        if protein_ratio >= 0.6:
            slow_score += 2
        elif protein_ratio >= 0.3:
            slow_score += 1
        if fiber_ratio >= 0.08:
            slow_score += 1

        if slow_score >= 3:
            evidence["slow"] += float(slow_score)
        elif slow_score > 0:
            evidence["normal"] += 1.0
            evidence["slow"] += float(slow_score)

        if is_liquid is True:
            if fat + protein < 5.0:
                evidence["fast"] += 4.0
            else:
                evidence["normal"] += 2.0
        elif is_liquid is False and not nearly_pure_carb:
            evidence["normal"] += 1.0

        if is_sweetened is True:
            evidence["fast" if is_liquid is True else "normal"] += 2.0

    if profile_hint is not None:
        evidence[profile_hint] += 8.0

    return CarbProfileWeights(**evidence)


def blend_carb_profile_weights(
    prior: CarbProfileWeights,
    learned: CarbProfileWeights,
    *,
    learned_weight: float,
) -> CarbProfileWeights:
    """Shrink personal retrospective weights toward the meal-feature prior."""
    if not isfinite(learned_weight) or not 0.0 <= learned_weight <= 1.0:
        raise ValueError("learned_weight must be between 0 and 1")
    prior_weight = 1.0 - learned_weight
    return CarbProfileWeights(
        fast=prior.fast * prior_weight + learned.fast * learned_weight,
        normal=prior.normal * prior_weight + learned.normal * learned_weight,
        slow=prior.slow * prior_weight + learned.slow * learned_weight,
    )


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


def carb_mixture_cumulative_absorbed(
    dt_min: float,
    *,
    weights: CarbProfileWeights,
    normal_duration_minutes: int | None = None,
    duration_scale: float = 1.0,
) -> float:
    """Cumulative absorbed fraction for a soft mixture of COB basis curves."""
    durations = _carb_mixture_durations(
        normal_duration_minutes=normal_duration_minutes,
        duration_scale=duration_scale,
    )
    if dt_min <= 0.0:
        return 0.0
    cumulative = sum(
        weights.for_profile(profile)
        * carb_cumulative_absorbed(
            dt_min,
            duration_min=duration,
            profile=profile,
        )
        for profile, duration in durations
    )
    return max(0.0, min(1.0, cumulative))


def carb_mixture_cob_remaining_fraction(
    dt_min: float,
    *,
    weights: CarbProfileWeights,
    normal_duration_minutes: int | None = None,
    duration_scale: float = 1.0,
) -> float:
    """Remaining COB fraction for a soft mixture of basis curves."""
    if dt_min <= 0.0:
        return 1.0
    return max(
        0.0,
        1.0
        - carb_mixture_cumulative_absorbed(
            dt_min,
            weights=weights,
            normal_duration_minutes=normal_duration_minutes,
            duration_scale=duration_scale,
        ),
    )


def carb_mixture_activity_rate(
    dt_min: float,
    *,
    weights: CarbProfileWeights,
    normal_duration_minutes: int | None = None,
    duration_scale: float = 1.0,
) -> float:
    """Exact piecewise action rate (absorbed fraction/min) of a COB mixture."""
    durations = _carb_mixture_durations(
        normal_duration_minutes=normal_duration_minutes,
        duration_scale=duration_scale,
    )
    if dt_min <= 0.0:
        return 0.0
    return max(
        0.0,
        sum(
            weights.for_profile(profile)
            * _carb_profile_activity_rate(dt_min, duration, profile)
            for profile, duration in durations
        ),
    )


def carb_mixture_activity_shape(
    dt_min: float,
    *,
    weights: CarbProfileWeights,
    normal_duration_minutes: int | None = None,
    duration_scale: float = 1.0,
) -> float:
    """Peak-normalized action rate for a soft COB mixture."""
    durations = _carb_mixture_durations(
        normal_duration_minutes=normal_duration_minutes,
        duration_scale=duration_scale,
    )
    if dt_min <= 0.0 or dt_min >= max(duration for _, duration in durations):
        return 0.0
    peak = _carb_mixture_peak_activity(weights, durations)
    if peak <= 1e-12:
        return 0.0
    return max(
        0.0,
        min(
            1.0,
            carb_mixture_activity_rate(
                dt_min,
                weights=weights,
                normal_duration_minutes=normal_duration_minutes,
                duration_scale=duration_scale,
            )
            / peak,
        ),
    )


def carb_mixture_minutes_remaining(
    dt_min: float,
    *,
    weights: CarbProfileWeights,
    normal_duration_minutes: int | None = None,
    duration_scale: float = 1.0,
    residual_fraction: float = _COB_EPSILON,
) -> int:
    """Minutes until the cached COB-mixture residual reaches a threshold."""
    durations = _carb_mixture_durations(
        normal_duration_minutes=normal_duration_minutes,
        duration_scale=duration_scale,
    )
    horizon = _carb_mixture_active_horizon(
        weights,
        durations,
        _validated_residual_fraction(residual_fraction),
    )
    if dt_min <= 0.0:
        return ceil(horizon)
    if dt_min >= horizon:
        return 0
    return ceil(horizon - dt_min)


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
    profile_weights: CarbProfileWeights | None = None,
    duration_scale: float = 1.0,
) -> float:
    """Meal-aware carb effect; optional soft weights enable the V2 kernel."""
    if carbs_g <= 0 or icr <= 0:
        return 0.0
    if profile_weights is not None:
        activity = carb_mixture_activity_shape(
            dt_min,
            weights=profile_weights,
            normal_duration_minutes=default_duration_minutes,
            duration_scale=duration_scale,
        )
        return (carbs_g / icr) * activity
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


def _carb_mixture_durations(
    *,
    normal_duration_minutes: int | None,
    duration_scale: float,
) -> tuple[tuple[CarbProfile, int], ...]:
    if not isfinite(duration_scale) or duration_scale <= 0.0:
        raise ValueError("duration_scale must be finite and positive")
    normal_duration = _CARB_PROFILE_DURATION["normal"]
    if normal_duration_minutes is not None:
        if normal_duration_minutes <= 0:
            raise ValueError("normal_duration_minutes must be positive")
        normal_duration = int(normal_duration_minutes)
    base_durations = {
        **_CARB_PROFILE_DURATION,
        "normal": normal_duration,
    }
    return tuple(
        (profile, max(1, round(base_durations[profile] * duration_scale)))
        for profile in ("fast", "normal", "slow")
    )


def _carb_profile_activity_rate(
    dt_min: float,
    duration_min: int,
    profile: CarbProfile,
) -> float:
    if dt_min <= 0.0 or duration_min <= 0 or dt_min >= duration_min:
        return 0.0
    knots = _CARB_PROFILE_KNOTS[profile]
    scale = knots[-1][0] / float(duration_min)
    ref_t = dt_min * scale
    for idx in range(1, len(knots)):
        t1, f1 = knots[idx]
        t0, f0 = knots[idx - 1]
        if ref_t < t1 or idx == len(knots) - 1:
            if t1 <= t0:
                return 0.0
            return max(0.0, ((f1 - f0) / (t1 - t0)) * scale)
    return 0.0


@lru_cache(maxsize=256)
def _carb_mixture_peak_activity(
    weights: CarbProfileWeights,
    durations: tuple[tuple[CarbProfile, int], ...],
) -> float:
    # A weighted sum of piecewise-linear cumulative profiles has a constant
    # derivative between the union of all scaled knots. Evaluate one midpoint
    # from every interval to obtain the exact global peak without a fine grid.
    boundaries = {0.0}
    for profile, duration in durations:
        ref_end = _CARB_PROFILE_KNOTS[profile][-1][0]
        boundaries.update(
            ref_t * duration / ref_end for ref_t, _ in _CARB_PROFILE_KNOTS[profile]
        )
    ordered = sorted(boundaries)
    peak = 0.0
    for index in range(1, len(ordered)):
        start = ordered[index - 1]
        end = ordered[index]
        midpoint = 0.5 * (start + end)
        peak = max(
            peak,
            sum(
                weights.for_profile(profile)
                * _carb_profile_activity_rate(midpoint, duration, profile)
                for profile, duration in durations
            ),
        )
    return peak if peak > 1e-12 else 1.0


@lru_cache(maxsize=512)
def _carb_mixture_active_horizon(
    weights: CarbProfileWeights,
    durations: tuple[tuple[CarbProfile, int], ...],
    residual_fraction: float,
) -> float:
    lo = 0.0
    hi = float(max(duration for _, duration in durations))
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        remaining = 1.0 - sum(
            weights.for_profile(profile)
            * carb_cumulative_absorbed(
                mid,
                duration_min=duration,
                profile=profile,
            )
            for profile, duration in durations
        )
        if remaining <= residual_fraction:
            hi = mid
        else:
            lo = mid
    return hi


def personalized_insulin_iob_remaining_fraction(
    dt_min: float,
    parameters: PersonalizedInsulinKernel,
) -> float:
    """Smooth personalized IOB survival fraction.

    The analytic mixture is truncated and renormalized at its validated
    practical horizon, so a fitted rapid-insulin curve cannot grow an
    implausibly long tail merely to absorb unrelated baseline drift.
    """
    if dt_min <= 0.0:
        return 1.0
    if dt_min >= parameters.horizon_minutes:
        return 0.0
    fast = _erlang2_survival(dt_min, parameters.fast_tau_minutes)
    slow = _erlang2_survival(dt_min, parameters.slow_tau_minutes)
    raw_remaining = (
        parameters.fast_weight * fast + (1.0 - parameters.fast_weight) * slow
    )
    horizon_remaining = _raw_personalized_insulin_survival(
        parameters.horizon_minutes,
        parameters,
    )
    delivered_at_horizon = 1.0 - horizon_remaining
    if delivered_at_horizon <= 1e-12:
        return 0.0
    remaining = (raw_remaining - horizon_remaining) / delivered_at_horizon
    return max(0.0, min(1.0, remaining))


def personalized_insulin_cumulative_absorbed(
    dt_min: float,
    parameters: PersonalizedInsulinKernel,
) -> float:
    """Cumulative action fraction paired with the personalized IOB survival."""
    if dt_min <= 0.0:
        return 0.0
    return max(
        0.0,
        min(
            1.0,
            1.0 - personalized_insulin_iob_remaining_fraction(dt_min, parameters),
        ),
    )


def personalized_insulin_activity_rate(
    dt_min: float,
    parameters: PersonalizedInsulinKernel,
) -> float:
    """Exact personalized action density in absorbed fraction per minute."""
    if dt_min <= 0.0 or dt_min >= parameters.horizon_minutes:
        return 0.0
    fast = _erlang2_activity_rate(dt_min, parameters.fast_tau_minutes)
    slow = _erlang2_activity_rate(dt_min, parameters.slow_tau_minutes)
    raw_rate = max(
        0.0,
        parameters.fast_weight * fast + (1.0 - parameters.fast_weight) * slow,
    )
    delivered_at_horizon = 1.0 - _raw_personalized_insulin_survival(
        parameters.horizon_minutes,
        parameters,
    )
    if delivered_at_horizon <= 1e-12:
        return 0.0
    return raw_rate / delivered_at_horizon


def personalized_insulin_activity_shape(
    dt_min: float,
    parameters: PersonalizedInsulinKernel,
) -> float:
    """Peak-normalized version of the exact personalized action density."""
    if dt_min <= 0.0:
        return 0.0
    peak = _personalized_insulin_peak_activity(parameters)
    if peak <= 1e-12:
        return 0.0
    return max(
        0.0,
        min(1.0, personalized_insulin_activity_rate(dt_min, parameters) / peak),
    )


def personalized_insulin_minutes_remaining(
    dt_min: float,
    parameters: PersonalizedInsulinKernel,
    *,
    residual_fraction: float = _IOB_EPSILON,
) -> int:
    """Minutes until personalized IOB reaches a cached residual threshold."""
    horizon = _personalized_insulin_active_horizon(
        parameters,
        _validated_residual_fraction(residual_fraction),
    )
    if dt_min <= 0.0:
        return ceil(horizon)
    if dt_min >= horizon:
        return 0
    return ceil(horizon - dt_min)


def personalized_insulin_effect(
    dt_min: float,
    units: float,
    isf: float,
    parameters: PersonalizedInsulinKernel,
) -> float:
    """Peak-scaled informational effect using a personalized action shape."""
    if dt_min <= 0.0 or units <= 0.0 or isf <= 0.0:
        return 0.0
    return units * isf * personalized_insulin_activity_shape(dt_min, parameters)


def _erlang2_survival(dt_min: float, tau_minutes: float) -> float:
    scaled = dt_min / tau_minutes
    return exp(-scaled) * (1.0 + scaled)


def _erlang2_activity_rate(dt_min: float, tau_minutes: float) -> float:
    scaled = dt_min / tau_minutes
    return scaled * exp(-scaled) / tau_minutes


def _erlang2_activity_derivative(dt_min: float, tau_minutes: float) -> float:
    scaled = dt_min / tau_minutes
    return exp(-scaled) * (1.0 - scaled) / (tau_minutes * tau_minutes)


def _raw_personalized_insulin_survival(
    dt_min: float,
    parameters: PersonalizedInsulinKernel,
) -> float:
    return parameters.fast_weight * _erlang2_survival(
        dt_min,
        parameters.fast_tau_minutes,
    ) + (1.0 - parameters.fast_weight) * _erlang2_survival(
        dt_min,
        parameters.slow_tau_minutes,
    )


def _personalized_insulin_activity_derivative(
    dt_min: float,
    parameters: PersonalizedInsulinKernel,
) -> float:
    return parameters.fast_weight * _erlang2_activity_derivative(
        dt_min, parameters.fast_tau_minutes
    ) + (1.0 - parameters.fast_weight) * _erlang2_activity_derivative(
        dt_min, parameters.slow_tau_minutes
    )


@lru_cache(maxsize=256)
def _personalized_insulin_peak_activity(
    parameters: PersonalizedInsulinKernel,
) -> float:
    # Every component derivative is positive before fast_tau and negative after
    # slow_tau. Scan that bounded interval for sign changes, then refine every
    # stationary point; this remains robust when a wide mixture is bimodal.
    lo = parameters.fast_tau_minutes
    hi = parameters.slow_tau_minutes
    candidates = {lo, hi}
    if hi > lo:
        ratio = hi / lo
        points = sorted(
            {lo + (hi - lo) * index / 256.0 for index in range(257)}
            | {lo * ratio ** (index / 256.0) for index in range(257)}
        )
        left = points[0]
        left_value = _personalized_insulin_activity_derivative(left, parameters)
        for right in points[1:]:
            right_value = _personalized_insulin_activity_derivative(
                right,
                parameters,
            )
            if left_value == 0.0:
                candidates.add(left)
            elif right_value == 0.0 or left_value * right_value < 0.0:
                root_lo = left
                root_hi = right
                for _ in range(48):
                    midpoint = 0.5 * (root_lo + root_hi)
                    mid_value = _personalized_insulin_activity_derivative(
                        midpoint,
                        parameters,
                    )
                    if left_value * mid_value <= 0.0:
                        root_hi = midpoint
                    else:
                        root_lo = midpoint
                        left_value = mid_value
                candidates.add(0.5 * (root_lo + root_hi))
            left = right
            left_value = right_value
    peak = max(
        personalized_insulin_activity_rate(candidate, parameters)
        for candidate in candidates
    )
    return peak if peak > 1e-12 else 1.0


@lru_cache(maxsize=512)
def _personalized_insulin_active_horizon(
    parameters: PersonalizedInsulinKernel,
    residual_fraction: float,
) -> float:
    lo = 0.0
    hi = parameters.horizon_minutes
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        if personalized_insulin_iob_remaining_fraction(mid, parameters) <= (
            residual_fraction
        ):
            hi = mid
        else:
            lo = mid
    return hi


def _validated_residual_fraction(value: float) -> float:
    if not isfinite(value) or not 0.0 < value < 1.0:
        raise ValueError("residual_fraction must be between 0 and 1")
    return float(value)


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
