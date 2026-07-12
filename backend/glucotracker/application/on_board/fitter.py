"""Robust retrospective fitting of display-only IOB and COB timing.

The fitter deliberately estimates *timing shapes only*.  Insulin sensitivity and
carbohydrate response are nuisance regression coefficients and are never exposed
as dose, bolus, correction, or treatment advice.  Raw CGM remains immutable: the
only preprocessing is deterministic 15-minute median downsampling.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import ceil, isfinite, sqrt
from statistics import median
from typing import Literal

from glucotracker.application.twin.kernels import (
    POPULATION_INSULIN_KERNEL_V2,
    CarbProfileWeights,
    PersonalizedInsulinKernel,
    blend_carb_profile_weights,
    carb_mixture_cumulative_absorbed,
    insulin_cumulative_absorbed,
    personalized_insulin_cumulative_absorbed,
)

MODEL_VERSION = "on-board-timing-v2"
FitStatus = Literal["accepted", "rejected", "insufficient_data"]
FitConfidence = Literal["none", "low", "medium", "high"]
CobScope = Literal["exact", "category"]


@dataclass(frozen=True, slots=True)
class CgmSample:
    """One unmodified raw CGM observation in mmol/L."""

    timestamp: datetime
    glucose_mmol_l: float

    def __post_init__(self) -> None:
        if not isfinite(self.glucose_mmol_l) or self.glucose_mmol_l <= 0.0:
            raise ValueError("CGM glucose must be finite and positive")


@dataclass(frozen=True, slots=True)
class RapidInsulinEvent:
    """A pre-classified rapid bolus; basal/extended insulin must not enter here."""

    timestamp: datetime
    units: float

    def __post_init__(self) -> None:
        if not isfinite(self.units) or self.units <= 0.0:
            raise ValueError("rapid insulin units must be finite and positive")


@dataclass(frozen=True, slots=True)
class MealEvent:
    """A meal with its feature prior and privacy-safe personalization scopes."""

    timestamp: datetime
    carbs_g: float
    prior_weights: CarbProfileWeights
    exact_key: str | None = None
    category_key: str | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.carbs_g) or self.carbs_g <= 0.0:
            raise ValueError("meal carbohydrates must be finite and positive")
        if self.exact_key is not None and not self.exact_key.strip():
            raise ValueError("exact_key must be non-empty when supplied")
        if self.category_key is not None and not self.category_key.strip():
            raise ValueError("category_key must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class RetrospectiveDay:
    """One local-wall day of raw observations and already-scoped events.

    All timestamps must use the same clock convention as ``day_start``.  The
    application service is responsible for converting imported UTC instants to
    the user's local-wall clock before constructing this value.
    """

    day_start: datetime
    cgm: tuple[CgmSample, ...]
    rapid_insulin: tuple[RapidInsulinEvent, ...] = ()
    meals: tuple[MealEvent, ...] = ()

    def __post_init__(self) -> None:
        expected_awareness = self.day_start.tzinfo is not None
        timestamps = (
            *(sample.timestamp for sample in self.cgm),
            *(event.timestamp for event in self.rapid_insulin),
            *(meal.timestamp for meal in self.meals),
        )
        if any(
            (timestamp.tzinfo is not None) != expected_awareness
            for timestamp in timestamps
        ):
            raise ValueError(
                "all retrospective timestamps must share timezone awareness"
            )


@dataclass(frozen=True, slots=True)
class CobTimingOverride:
    """One shrunken personal COB mixture for an exact or category scope."""

    scope: CobScope
    scope_key: str
    weights: CarbProfileWeights
    event_count: int
    day_count: int
    learned_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.scope not in {"exact", "category"}:
            raise ValueError("unknown COB override scope")
        if not self.scope_key:
            raise ValueError("COB override scope_key is required")
        if self.event_count < 0 or self.day_count < 0:
            raise ValueError("COB evidence counts must be non-negative")
        if not isfinite(self.learned_weight) or not 0.0 <= self.learned_weight <= 1.0:
            raise ValueError("COB learned_weight must be between 0 and 1")

    def to_mapping(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "scope_key": self.scope_key,
            "weights": self.weights.to_mapping(),
            "event_count": self.event_count,
            "day_count": self.day_count,
            "learned_weight": self.learned_weight,
        }


@dataclass(frozen=True, slots=True)
class OnBoardTimingModel:
    """Serializable timing model; exact meal overrides take precedence."""

    insulin_kernel: PersonalizedInsulinKernel | None = POPULATION_INSULIN_KERNEL_V2
    legacy_dia_minutes: int = 270
    normal_carb_duration_minutes: int = 240
    cob_overrides: tuple[CobTimingOverride, ...] = ()
    model_version: str = MODEL_VERSION

    def __post_init__(self) -> None:
        if self.legacy_dia_minutes <= 0:
            raise ValueError("legacy_dia_minutes must be positive")
        if self.normal_carb_duration_minutes <= 0:
            raise ValueError("normal_carb_duration_minutes must be positive")
        seen: set[tuple[CobScope, str]] = set()
        for override in self.cob_overrides:
            identity = (override.scope, override.scope_key)
            if identity in seen:
                raise ValueError("duplicate COB override scope")
            seen.add(identity)

    def weights_for(self, meal: MealEvent) -> CarbProfileWeights:
        exact = {
            override.scope_key: override.weights
            for override in self.cob_overrides
            if override.scope == "exact"
        }
        category = {
            override.scope_key: override.weights
            for override in self.cob_overrides
            if override.scope == "category"
        }
        if meal.exact_key is not None and meal.exact_key in exact:
            return exact[meal.exact_key]
        if meal.category_key is not None and meal.category_key in category:
            return category[meal.category_key]
        return meal.prior_weights

    def to_mapping(self) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "insulin_kernel": (
                self.insulin_kernel.to_mapping()
                if self.insulin_kernel is not None
                else None
            ),
            "legacy_dia_minutes": self.legacy_dia_minutes,
            "normal_carb_duration_minutes": self.normal_carb_duration_minutes,
            "cob_overrides": [item.to_mapping() for item in self.cob_overrides],
        }


@dataclass(frozen=True, slots=True)
class ErrorMetrics:
    """Held-out one-step glucose errors in mmol/L."""

    mae_mmol: float
    median_day_mae_mmol: float
    p90_abs_error_mmol: float
    day_mae_mmol: tuple[tuple[str, float], ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "mae_mmol": self.mae_mmol,
            "median_day_mae_mmol": self.median_day_mae_mmol,
            "p90_abs_error_mmol": self.p90_abs_error_mmol,
            "day_mae_mmol": dict(self.day_mae_mmol),
        }


@dataclass(frozen=True, slots=True)
class FitMetrics:
    """Audit data needed to persist or explain a retrospective decision."""

    complete_day_count: int
    excluded_day_count: int
    training_day_starts: tuple[str, ...]
    holdout_day_starts: tuple[str, ...]
    training_sample_count: int
    holdout_sample_count: int
    rapid_insulin_event_count: int
    rapid_insulin_day_count: int
    meal_event_count: int
    meal_day_count: int
    baseline: ErrorMetrics | None = None
    candidate: ErrorMetrics | None = None
    mae_improvement_mmol: float | None = None
    mae_improvement_fraction: float | None = None
    median_improvement_mmol: float | None = None
    median_improvement_fraction: float | None = None
    excluded_reasons: tuple[tuple[str, int], ...] = ()

    def to_mapping(self) -> dict[str, object]:
        return {
            "complete_day_count": self.complete_day_count,
            "excluded_day_count": self.excluded_day_count,
            "training_day_starts": list(self.training_day_starts),
            "holdout_day_starts": list(self.holdout_day_starts),
            "training_sample_count": self.training_sample_count,
            "holdout_sample_count": self.holdout_sample_count,
            "rapid_insulin_event_count": self.rapid_insulin_event_count,
            "rapid_insulin_day_count": self.rapid_insulin_day_count,
            "meal_event_count": self.meal_event_count,
            "meal_day_count": self.meal_day_count,
            "baseline": self.baseline.to_mapping() if self.baseline else None,
            "candidate": self.candidate.to_mapping() if self.candidate else None,
            "mae_improvement_mmol": self.mae_improvement_mmol,
            "mae_improvement_fraction": self.mae_improvement_fraction,
            "median_improvement_mmol": self.median_improvement_mmol,
            "median_improvement_fraction": self.median_improvement_fraction,
            "excluded_reasons": dict(self.excluded_reasons),
        }


@dataclass(frozen=True, slots=True)
class OnBoardFitResult:
    """Accepted model or the unchanged fallback on sparse/rejected evidence."""

    status: FitStatus
    reason: str
    model: OnBoardTimingModel
    metrics: FitMetrics
    confidence: FitConfidence = "none"
    candidate_model: OnBoardTimingModel | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "confidence": self.confidence,
            "model": self.model.to_mapping(),
            "candidate_model": (
                self.candidate_model.to_mapping() if self.candidate_model else None
            ),
            "metrics": self.metrics.to_mapping(),
        }


@dataclass(frozen=True, slots=True)
class FitterConfig:
    """Conservative, deterministic gates and bounded candidate grids."""

    bin_minutes: int = 15
    day_minutes: int = 24 * 60
    min_day_span_minutes: int = 20 * 60
    min_day_coverage_fraction: float = 0.80
    max_cgm_gap_minutes: int = 30
    min_training_days: int = 6
    min_holdout_days: int = 2
    holdout_fraction: float = 0.25
    min_training_samples: int = 300
    min_holdout_samples: int = 100
    min_rapid_events: int = 8
    min_rapid_event_days: int = 5
    min_meal_events: int = 8
    min_meal_event_days: int = 5
    min_exact_scope_events: int = 4
    min_exact_scope_days: int = 3
    min_category_scope_events: int = 8
    min_category_scope_days: int = 5
    max_category_scopes: int = 12
    max_exact_scopes: int = 16
    insulin_lookback_minutes: int = 12 * 60
    meal_lookback_minutes: int = 8 * 60
    huber_delta_mmol: float = 0.60
    ridge_strength: float = 0.50
    robust_iterations: int = 20
    min_absolute_improvement_mmol: float = 0.10
    min_relative_improvement: float = 0.05
    p90_worsening_guard_mmol: float = 0.05
    per_day_worsening_guard_mmol: float = 0.15
    scope_min_training_improvement_mmol: float = 0.002
    iob_prior_penalty: float = 0.004
    cob_prior_penalty: float = 0.008
    iob_screening_max_observations: int = 768
    iob_screening_robust_iterations: int = 2
    iob_full_evaluation_limit: int = 16
    category_max_learned_weight: float = 0.40
    exact_max_learned_weight: float = 0.55
    category_shrinkage_events: float = 16.0
    exact_shrinkage_events: float = 12.0
    fast_weight_candidates: tuple[float, ...] = (0.10, 0.20, 0.35, 0.50)
    fast_tau_candidates: tuple[float, ...] = (15.0, 25.0, 35.0, 45.0, 60.0)
    slow_tau_candidates: tuple[float, ...] = (70.0, 90.0, 110.0, 140.0, 180.0)
    insulin_horizon_candidates: tuple[float, ...] = (330.0, 360.0, 390.0, 420.0)

    def __post_init__(self) -> None:
        if self.bin_minutes <= 0 or self.day_minutes <= 0:
            raise ValueError("time-grid values must be positive")
        if self.day_minutes % self.bin_minutes:
            raise ValueError("day_minutes must be divisible by bin_minutes")
        if not 0.0 < self.min_day_coverage_fraction <= 1.0:
            raise ValueError("day coverage fraction must be in (0, 1]")
        if not 0.0 < self.holdout_fraction < 1.0:
            raise ValueError("holdout_fraction must be in (0, 1)")
        if self.min_training_days < 1 or self.min_holdout_days < 1:
            raise ValueError("training and holdout day gates must be positive")
        if self.robust_iterations < 1 or self.huber_delta_mmol <= 0.0:
            raise ValueError("robust fit parameters must be positive")
        if self.ridge_strength < 0.0:
            raise ValueError("ridge_strength must be non-negative")
        if (
            self.iob_screening_max_observations < 1
            or self.iob_screening_robust_iterations < 1
            or self.iob_full_evaluation_limit < 1
        ):
            raise ValueError("IOB screening limits must be positive")


@dataclass(frozen=True, slots=True)
class _PreparedDay:
    day_start: datetime
    points: tuple[tuple[datetime, float], ...]
    rapid_insulin: tuple[RapidInsulinEvent, ...]
    meals: tuple[MealEvent, ...]


@dataclass(frozen=True, slots=True)
class _Observation:
    day_key: str
    start: datetime
    end: datetime
    glucose_change: float


@dataclass(frozen=True, slots=True)
class _RegressionRow:
    day_key: str
    target: float
    insulin_activity: float
    meal_activity: float


@dataclass(frozen=True, slots=True)
class _RegressionModel:
    intercept: float
    insulin_coefficient: float
    meal_coefficient: float
    insulin_scale: float
    meal_scale: float

    def predict(self, row: _RegressionRow) -> float:
        return (
            self.intercept
            + self.insulin_coefficient * row.insulin_activity / self.insulin_scale
            + self.meal_coefficient * row.meal_activity / self.meal_scale
        )


def fit_on_board_timing(
    days: tuple[RetrospectiveDay, ...] | list[RetrospectiveDay],
    *,
    fallback: OnBoardTimingModel | None = None,
    config: FitterConfig | None = None,
) -> OnBoardFitResult:
    """Fit personal IOB/COB timing with a chronological, day-disjoint holdout.

    Candidate selection sees training days only.  The holdout is used once for
    the acceptance gates; a rejected result returns ``fallback`` unchanged.
    """
    settings = config or FitterConfig()
    baseline_model = fallback or OnBoardTimingModel()
    prepared, excluded = _prepare_days(days, settings)
    split = _chronological_split(prepared, settings)
    if split is None:
        metrics = _empty_metrics(prepared, excluded)
        return OnBoardFitResult(
            status="insufficient_data",
            reason="not_enough_complete_days_for_day_disjoint_holdout",
            model=baseline_model,
            metrics=metrics,
        )

    training_days, holdout_days = split
    training_observations = _observations(training_days, settings)
    holdout_observations = _observations(holdout_days, settings)
    training_rapid = tuple(
        event for day in training_days for event in day.rapid_insulin
    )
    training_meals = tuple(meal for day in training_days for meal in day.meals)
    all_rapid = tuple(event for day in prepared for event in day.rapid_insulin)
    all_meals = tuple(meal for day in prepared for meal in day.meals)
    base_metrics = _metrics_shell(
        prepared,
        excluded,
        training_days,
        holdout_days,
        training_observations,
        holdout_observations,
        training_rapid,
        training_meals,
    )
    if (
        len(training_observations) < settings.min_training_samples
        or len(holdout_observations) < settings.min_holdout_samples
    ):
        return OnBoardFitResult(
            status="insufficient_data",
            reason="not_enough_downsampled_cgm_intervals",
            model=baseline_model,
            metrics=base_metrics,
        )

    rapid_days = _event_day_count(training_days, "rapid")
    meal_days = _event_day_count(training_days, "meal")
    iob_eligible = (
        len(training_rapid) >= settings.min_rapid_events
        and rapid_days >= settings.min_rapid_event_days
    )
    cob_eligible = (
        len(training_meals) >= settings.min_meal_events
        and meal_days >= settings.min_meal_event_days
    )
    if not iob_eligible and not cob_eligible:
        return OnBoardFitResult(
            status="insufficient_data",
            reason="not_enough_rapid_insulin_or_meal_evidence",
            model=baseline_model,
            metrics=base_metrics,
        )

    baseline_training_rows = _build_rows(
        training_observations,
        all_rapid,
        all_meals,
        baseline_model,
        settings,
    )
    selected = baseline_model
    if iob_eligible:
        selected = _select_iob_kernel(
            selected,
            training_observations,
            all_rapid,
            baseline_training_rows,
            settings,
        )
    if cob_eligible:
        selected = _select_cob_overrides(
            selected,
            training_days,
            training_observations,
            all_rapid,
            all_meals,
            settings,
        )

    candidate_training_rows = _build_rows(
        training_observations,
        all_rapid,
        all_meals,
        selected,
        settings,
    )
    baseline_regression = _fit_robust(baseline_training_rows, settings)
    candidate_regression = _fit_robust(candidate_training_rows, settings)
    baseline_holdout_rows = _build_rows(
        holdout_observations,
        all_rapid,
        all_meals,
        baseline_model,
        settings,
    )
    candidate_holdout_rows = _build_rows(
        holdout_observations,
        all_rapid,
        all_meals,
        selected,
        settings,
    )
    baseline_errors = _error_metrics(baseline_holdout_rows, baseline_regression)
    candidate_errors = _error_metrics(candidate_holdout_rows, candidate_regression)
    metrics = _with_validation_metrics(base_metrics, baseline_errors, candidate_errors)

    if selected == baseline_model:
        return OnBoardFitResult(
            status="rejected",
            reason="training_search_did_not_improve_the_fallback",
            model=baseline_model,
            candidate_model=selected,
            metrics=metrics,
        )
    accepted, reason = _passes_holdout_gates(
        baseline_errors, candidate_errors, settings
    )
    if not accepted:
        return OnBoardFitResult(
            status="rejected",
            reason=reason,
            model=baseline_model,
            candidate_model=selected,
            metrics=metrics,
        )
    return OnBoardFitResult(
        status="accepted",
        reason="held_out_errors_improved",
        model=selected,
        candidate_model=selected,
        metrics=metrics,
        confidence=_confidence(metrics, settings),
    )


def _prepare_days(
    days: tuple[RetrospectiveDay, ...] | list[RetrospectiveDay],
    config: FitterConfig,
) -> tuple[tuple[_PreparedDay, ...], dict[str, int]]:
    prepared: list[_PreparedDay] = []
    reasons: dict[str, int] = {}
    seen_starts: set[datetime] = set()
    expected_bins = config.day_minutes // config.bin_minutes
    minimum_bins = ceil(expected_bins * config.min_day_coverage_fraction)
    for day in sorted(days, key=lambda item: item.day_start):
        if day.day_start in seen_starts:
            reasons["duplicate_day_start"] = reasons.get("duplicate_day_start", 0) + 1
            continue
        seen_starts.add(day.day_start)
        day_end = day.day_start + timedelta(minutes=config.day_minutes)
        samples = sorted(
            (
                sample
                for sample in day.cgm
                if day.day_start <= sample.timestamp < day_end
            ),
            key=lambda sample: sample.timestamp,
        )
        if len(samples) < 2:
            reasons["too_few_raw_cgm_samples"] = (
                reasons.get("too_few_raw_cgm_samples", 0) + 1
            )
            continue
        span = (samples[-1].timestamp - samples[0].timestamp).total_seconds() / 60.0
        if span < config.min_day_span_minutes:
            reasons["incomplete_day_span"] = reasons.get("incomplete_day_span", 0) + 1
            continue
        max_gap = max(
            (right.timestamp - left.timestamp).total_seconds() / 60.0
            for left, right in zip(samples, samples[1:], strict=False)
        )
        if max_gap > config.max_cgm_gap_minutes:
            reasons["cgm_gap_too_large"] = reasons.get("cgm_gap_too_large", 0) + 1
            continue
        bins: dict[int, list[float]] = {}
        for sample in samples:
            elapsed = (sample.timestamp - day.day_start).total_seconds() / 60.0
            index = int(elapsed // config.bin_minutes)
            bins.setdefault(index, []).append(sample.glucose_mmol_l)
        if len(bins) < minimum_bins:
            reasons["insufficient_cgm_coverage"] = (
                reasons.get("insufficient_cgm_coverage", 0) + 1
            )
            continue
        points = tuple(
            (
                day.day_start
                + timedelta(
                    minutes=index * config.bin_minutes + config.bin_minutes / 2
                ),
                float(median(values)),
            )
            for index, values in sorted(bins.items())
        )
        prepared.append(
            _PreparedDay(
                day_start=day.day_start,
                points=points,
                rapid_insulin=tuple(
                    sorted(
                        (
                            event
                            for event in day.rapid_insulin
                            if day.day_start <= event.timestamp < day_end
                        ),
                        key=lambda item: item.timestamp,
                    )
                ),
                meals=tuple(
                    sorted(
                        (
                            meal
                            for meal in day.meals
                            if day.day_start <= meal.timestamp < day_end
                        ),
                        key=lambda item: item.timestamp,
                    )
                ),
            )
        )
    return tuple(prepared), reasons


def _chronological_split(
    days: tuple[_PreparedDay, ...],
    config: FitterConfig,
) -> tuple[tuple[_PreparedDay, ...], tuple[_PreparedDay, ...]] | None:
    required = config.min_training_days + config.min_holdout_days
    if len(days) < required:
        return None
    holdout_count = max(
        config.min_holdout_days, ceil(len(days) * config.holdout_fraction)
    )
    holdout_count = min(holdout_count, len(days) - config.min_training_days)
    if holdout_count < config.min_holdout_days:
        return None
    training = days[:-holdout_count]
    holdout = days[-holdout_count:]
    if not training or not holdout or training[-1].day_start >= holdout[0].day_start:
        return None
    return training, holdout


def _observations(
    days: tuple[_PreparedDay, ...],
    config: FitterConfig,
) -> tuple[_Observation, ...]:
    observations: list[_Observation] = []
    expected_delta = timedelta(minutes=config.bin_minutes)
    for day in days:
        day_key = day.day_start.isoformat()
        for (start, glucose_start), (end, glucose_end) in zip(
            day.points, day.points[1:], strict=False
        ):
            if end - start != expected_delta:
                continue
            observations.append(
                _Observation(
                    day_key=day_key,
                    start=start,
                    end=end,
                    glucose_change=glucose_end - glucose_start,
                )
            )
    return tuple(observations)


def _build_rows(
    observations: tuple[_Observation, ...],
    rapid_events: tuple[RapidInsulinEvent, ...],
    meals: tuple[MealEvent, ...],
    model: OnBoardTimingModel,
    config: FitterConfig,
) -> tuple[_RegressionRow, ...]:
    rapid_sorted = tuple(sorted(rapid_events, key=lambda item: item.timestamp))
    meal_sorted = tuple(sorted(meals, key=lambda item: item.timestamp))
    rapid_times = tuple(item.timestamp for item in rapid_sorted)
    meal_times = tuple(item.timestamp for item in meal_sorted)
    exact = {
        item.scope_key: item.weights
        for item in model.cob_overrides
        if item.scope == "exact"
    }
    categories = {
        item.scope_key: item.weights
        for item in model.cob_overrides
        if item.scope == "category"
    }
    rows: list[_RegressionRow] = []
    for observation in observations:
        rapid_start = bisect_left(
            rapid_times,
            observation.end - timedelta(minutes=config.insulin_lookback_minutes),
        )
        rapid_end = bisect_left(rapid_times, observation.end)
        insulin_activity = 0.0
        for event in rapid_sorted[rapid_start:rapid_end]:
            start_elapsed = max(
                0.0,
                (observation.start - event.timestamp).total_seconds() / 60.0,
            )
            end_elapsed = (observation.end - event.timestamp).total_seconds() / 60.0
            if model.insulin_kernel is None:
                delivered = insulin_cumulative_absorbed(
                    end_elapsed,
                    model.legacy_dia_minutes,
                ) - insulin_cumulative_absorbed(
                    start_elapsed,
                    model.legacy_dia_minutes,
                )
            else:
                delivered = personalized_insulin_cumulative_absorbed(
                    end_elapsed, model.insulin_kernel
                ) - personalized_insulin_cumulative_absorbed(
                    start_elapsed, model.insulin_kernel
                )
            insulin_activity -= event.units * max(0.0, delivered)

        meal_start = bisect_left(
            meal_times,
            observation.end - timedelta(minutes=config.meal_lookback_minutes),
        )
        meal_end = bisect_left(meal_times, observation.end)
        meal_activity = 0.0
        for meal in meal_sorted[meal_start:meal_end]:
            weights = meal.prior_weights
            if meal.category_key is not None:
                weights = categories.get(meal.category_key, weights)
            if meal.exact_key is not None:
                weights = exact.get(meal.exact_key, weights)
            start_elapsed = max(
                0.0,
                (observation.start - meal.timestamp).total_seconds() / 60.0,
            )
            end_elapsed = (observation.end - meal.timestamp).total_seconds() / 60.0
            delivered = carb_mixture_cumulative_absorbed(
                end_elapsed,
                weights=weights,
                normal_duration_minutes=model.normal_carb_duration_minutes,
            ) - carb_mixture_cumulative_absorbed(
                start_elapsed,
                weights=weights,
                normal_duration_minutes=model.normal_carb_duration_minutes,
            )
            meal_activity += meal.carbs_g * max(0.0, delivered)
        rows.append(
            _RegressionRow(
                day_key=observation.day_key,
                target=observation.glucose_change,
                insulin_activity=insulin_activity,
                meal_activity=meal_activity,
            )
        )
    return tuple(rows)


def _select_iob_kernel(
    model: OnBoardTimingModel,
    observations: tuple[_Observation, ...],
    rapid_events: tuple[RapidInsulinEvent, ...],
    baseline_rows: tuple[_RegressionRow, ...],
    config: FitterConfig,
) -> OnBoardTimingModel:
    fallback = model.insulin_kernel
    prior = fallback or POPULATION_INSULIN_KERNEL_V2
    best_kernel = fallback
    best_score = _training_score(baseline_rows, config)
    candidates = _iob_candidates(prior, config)
    finalists = candidates
    if len(candidates) > config.iob_full_evaluation_limit + 1:
        # Screen every bounded-grid candidate on an evenly spaced subset with
        # only a few IRLS iterations. This can only remove candidates: every
        # finalist is still rescored on all training rows with the full robust
        # settings before the unchanged future-day holdout gates are applied.
        indexes = _evenly_spaced_indexes(
            len(observations),
            config.iob_screening_max_observations,
        )
        screening_observations = tuple(observations[index] for index in indexes)
        screening_template = tuple(baseline_rows[index] for index in indexes)
        screening_config = replace(
            config,
            robust_iterations=min(
                config.robust_iterations,
                config.iob_screening_robust_iterations,
            ),
        )
        ranked: list[tuple[float, PersonalizedInsulinKernel]] = []
        for candidate in candidates:
            rows = _build_iob_candidate_rows(
                screening_observations,
                rapid_events,
                screening_template,
                candidate,
                config,
            )
            ranked.append(
                (
                    _training_score(rows, screening_config)
                    + config.iob_prior_penalty * _iob_distance(candidate, prior),
                    candidate,
                )
            )
        ranked.sort(key=lambda item: (item[0], _iob_kernel_sort_key(item[1])))
        finalists = tuple(
            candidate
            for _, candidate in ranked
            if fallback is None or candidate != fallback
        )[: config.iob_full_evaluation_limit]

    for candidate in finalists:
        if fallback is not None and candidate == fallback:
            continue
        rows = _build_iob_candidate_rows(
            observations,
            rapid_events,
            baseline_rows,
            candidate,
            config,
        )
        score = _training_score(
            rows, config
        ) + config.iob_prior_penalty * _iob_distance(candidate, prior)
        if score < best_score - 1e-12:
            best_score = score
            best_kernel = candidate
    return OnBoardTimingModel(
        insulin_kernel=best_kernel,
        legacy_dia_minutes=model.legacy_dia_minutes,
        normal_carb_duration_minutes=model.normal_carb_duration_minutes,
        cob_overrides=model.cob_overrides,
        model_version=model.model_version,
    )


def _build_iob_candidate_rows(
    observations: tuple[_Observation, ...],
    rapid_events: tuple[RapidInsulinEvent, ...],
    template_rows: tuple[_RegressionRow, ...],
    kernel: PersonalizedInsulinKernel,
    config: FitterConfig,
) -> tuple[_RegressionRow, ...]:
    """Replace only the insulin feature while reusing invariant meal rows."""
    if len(observations) != len(template_rows):
        raise ValueError("IOB candidate rows require an aligned template")
    rapid_sorted = tuple(sorted(rapid_events, key=lambda item: item.timestamp))
    rapid_times = tuple(item.timestamp for item in rapid_sorted)
    cumulative_cache: dict[float, float] = {0.0: 0.0}

    def cumulative(elapsed: float) -> float:
        cached = cumulative_cache.get(elapsed)
        if cached is None:
            cached = personalized_insulin_cumulative_absorbed(elapsed, kernel)
            cumulative_cache[elapsed] = cached
        return cached

    rows: list[_RegressionRow] = []
    for observation, template in zip(observations, template_rows, strict=True):
        rapid_start = bisect_left(
            rapid_times,
            observation.end - timedelta(minutes=config.insulin_lookback_minutes),
        )
        rapid_end = bisect_left(rapid_times, observation.end)
        insulin_activity = 0.0
        for event in rapid_sorted[rapid_start:rapid_end]:
            start_elapsed = max(
                0.0,
                (observation.start - event.timestamp).total_seconds() / 60.0,
            )
            end_elapsed = (observation.end - event.timestamp).total_seconds() / 60.0
            delivered = cumulative(end_elapsed) - cumulative(start_elapsed)
            insulin_activity -= event.units * max(0.0, delivered)
        rows.append(
            _RegressionRow(
                day_key=template.day_key,
                target=template.target,
                insulin_activity=insulin_activity,
                meal_activity=template.meal_activity,
            )
        )
    return tuple(rows)


def _evenly_spaced_indexes(count: int, limit: int) -> tuple[int, ...]:
    """Return deterministic indexes spanning the full chronological range."""
    if count <= 0:
        return ()
    if count <= limit:
        return tuple(range(count))
    if limit == 1:
        return (count // 2,)
    return tuple(round(index * (count - 1) / (limit - 1)) for index in range(limit))


def _iob_kernel_sort_key(
    kernel: PersonalizedInsulinKernel,
) -> tuple[float, float, float, float]:
    return (
        kernel.fast_weight,
        kernel.fast_tau_minutes,
        kernel.slow_tau_minutes,
        kernel.horizon_minutes,
    )


def _iob_candidates(
    fallback: PersonalizedInsulinKernel,
    config: FitterConfig,
) -> tuple[PersonalizedInsulinKernel, ...]:
    candidates = {fallback}
    for weight in config.fast_weight_candidates:
        for fast_tau in config.fast_tau_candidates:
            for slow_tau in config.slow_tau_candidates:
                for horizon in config.insulin_horizon_candidates:
                    if fast_tau <= slow_tau < horizon:
                        candidates.add(
                            PersonalizedInsulinKernel(
                                fast_weight=weight,
                                fast_tau_minutes=fast_tau,
                                slow_tau_minutes=slow_tau,
                                horizon_minutes=horizon,
                            )
                        )
    return tuple(
        sorted(
            candidates,
            key=_iob_kernel_sort_key,
        )
    )


def _iob_distance(
    candidate: PersonalizedInsulinKernel,
    fallback: PersonalizedInsulinKernel,
) -> float:
    return (
        ((candidate.fast_weight - fallback.fast_weight) / 0.35) ** 2
        + ((candidate.fast_tau_minutes - fallback.fast_tau_minutes) / 45.0) ** 2
        + ((candidate.slow_tau_minutes - fallback.slow_tau_minutes) / 90.0) ** 2
        + ((candidate.horizon_minutes - fallback.horizon_minutes) / 120.0) ** 2
    ) / 4.0


def _select_cob_overrides(
    model: OnBoardTimingModel,
    training_days: tuple[_PreparedDay, ...],
    observations: tuple[_Observation, ...],
    rapid_events: tuple[RapidInsulinEvent, ...],
    meals: tuple[MealEvent, ...],
    config: FitterConfig,
) -> OnBoardTimingModel:
    category_evidence = _scope_evidence(training_days, "category")
    exact_evidence = _scope_evidence(training_days, "exact")
    category_keys = _eligible_scope_keys(
        category_evidence,
        minimum_events=config.min_category_scope_events,
        minimum_days=config.min_category_scope_days,
        limit=config.max_category_scopes,
    )
    exact_keys = _eligible_scope_keys(
        exact_evidence,
        minimum_events=config.min_exact_scope_events,
        minimum_days=config.min_exact_scope_days,
        limit=config.max_exact_scopes,
    )
    selected = _retain_eligible_cob_overrides(
        model,
        category_keys=category_keys,
        exact_keys=exact_keys,
    )
    for scope, keys, evidence in (
        ("category", category_keys, category_evidence),
        ("exact", exact_keys, exact_evidence),
    ):
        for key in keys:
            scoped_meals = evidence[key][2]
            selected = _select_one_cob_scope(
                selected,
                scope,
                key,
                scoped_meals,
                observations,
                rapid_events,
                meals,
                config,
                event_count=evidence[key][0],
                day_count=evidence[key][1],
            )
    return selected


def _retain_eligible_cob_overrides(
    model: OnBoardTimingModel,
    *,
    category_keys: tuple[str, ...],
    exact_keys: tuple[str, ...],
) -> OnBoardTimingModel:
    """Drop scopes without current evidence before fitting a replacement set."""
    eligible_scopes = {
        *(("category", key) for key in category_keys),
        *(("exact", key) for key in exact_keys),
    }
    return OnBoardTimingModel(
        insulin_kernel=model.insulin_kernel,
        legacy_dia_minutes=model.legacy_dia_minutes,
        normal_carb_duration_minutes=model.normal_carb_duration_minutes,
        cob_overrides=tuple(
            override
            for override in model.cob_overrides
            if (override.scope, override.scope_key) in eligible_scopes
        ),
        model_version=model.model_version,
    )


def _select_one_cob_scope(
    model: OnBoardTimingModel,
    scope: CobScope,
    key: str,
    scoped_meals: tuple[MealEvent, ...],
    observations: tuple[_Observation, ...],
    rapid_events: tuple[RapidInsulinEvent, ...],
    all_meals: tuple[MealEvent, ...],
    config: FitterConfig,
    *,
    event_count: int,
    day_count: int,
) -> OnBoardTimingModel:
    current_rows = _build_rows(observations, rapid_events, all_meals, model, config)
    current_score = _training_score(current_rows, config)
    prior = _mean_weights(tuple(model.weights_for(meal) for meal in scoped_meals))
    if scope == "category":
        learned_weight = min(
            config.category_max_learned_weight,
            event_count / (event_count + config.category_shrinkage_events),
        )
    else:
        learned_weight = min(
            config.exact_max_learned_weight,
            event_count / (event_count + config.exact_shrinkage_events),
        )
    best_model = model
    best_score = current_score
    for learned in _cob_simplex_candidates():
        weights = blend_carb_profile_weights(
            prior,
            learned,
            learned_weight=learned_weight,
        )
        candidate = _replace_override(
            model,
            CobTimingOverride(
                scope=scope,
                scope_key=key,
                weights=weights,
                event_count=event_count,
                day_count=day_count,
                learned_weight=learned_weight,
            ),
        )
        rows = _build_rows(observations, rapid_events, all_meals, candidate, config)
        distance = sum(
            (weights.for_profile(profile) - prior.for_profile(profile)) ** 2
            for profile in ("fast", "normal", "slow")
        )
        score = _training_score(rows, config) + config.cob_prior_penalty * distance
        if score < best_score - config.scope_min_training_improvement_mmol:
            best_score = score
            best_model = candidate
    return best_model


def _replace_override(
    model: OnBoardTimingModel,
    replacement: CobTimingOverride,
) -> OnBoardTimingModel:
    overrides = [
        item
        for item in model.cob_overrides
        if (item.scope, item.scope_key) != (replacement.scope, replacement.scope_key)
    ]
    overrides.append(replacement)
    overrides.sort(key=lambda item: (item.scope, item.scope_key))
    return OnBoardTimingModel(
        insulin_kernel=model.insulin_kernel,
        legacy_dia_minutes=model.legacy_dia_minutes,
        normal_carb_duration_minutes=model.normal_carb_duration_minutes,
        cob_overrides=tuple(overrides),
        model_version=model.model_version,
    )


def _cob_simplex_candidates() -> tuple[CarbProfileWeights, ...]:
    values = (0.0, 0.25, 0.50, 0.75, 1.0)
    candidates: list[CarbProfileWeights] = []
    for fast in values:
        for normal in values:
            slow = 1.0 - fast - normal
            if slow < -1e-12 or all(abs(slow - value) > 1e-12 for value in values):
                continue
            candidates.append(CarbProfileWeights(fast, normal, max(0.0, slow)))
    return tuple(
        sorted(candidates, key=lambda item: (item.fast, item.normal, item.slow))
    )


def _scope_evidence(
    days: tuple[_PreparedDay, ...],
    scope: CobScope,
) -> dict[str, tuple[int, int, tuple[MealEvent, ...]]]:
    meals_by_key: dict[str, list[MealEvent]] = {}
    days_by_key: dict[str, set[str]] = {}
    for day in days:
        day_key = day.day_start.isoformat()
        for meal in day.meals:
            key = meal.exact_key if scope == "exact" else meal.category_key
            if key is None:
                continue
            meals_by_key.setdefault(key, []).append(meal)
            days_by_key.setdefault(key, set()).add(day_key)
    return {
        key: (len(values), len(days_by_key[key]), tuple(values))
        for key, values in meals_by_key.items()
    }


def _eligible_scope_keys(
    evidence: dict[str, tuple[int, int, tuple[MealEvent, ...]]],
    *,
    minimum_events: int,
    minimum_days: int,
    limit: int,
) -> tuple[str, ...]:
    eligible = [
        (key, counts[0], counts[1])
        for key, counts in evidence.items()
        if counts[0] >= minimum_events and counts[1] >= minimum_days
    ]
    eligible.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return tuple(key for key, _, _ in eligible[:limit])


def _mean_weights(weights: tuple[CarbProfileWeights, ...]) -> CarbProfileWeights:
    if not weights:
        return CarbProfileWeights(0.2, 0.6, 0.2)
    count = len(weights)
    return CarbProfileWeights(
        sum(item.fast for item in weights) / count,
        sum(item.normal for item in weights) / count,
        sum(item.slow for item in weights) / count,
    )


def _training_score(rows: tuple[_RegressionRow, ...], config: FitterConfig) -> float:
    regression = _fit_robust(rows, config)
    residuals = [row.target - regression.predict(row) for row in rows]
    if not residuals:
        return float("inf")
    return sum(
        _huber_loss(value, config.huber_delta_mmol) for value in residuals
    ) / len(residuals)


def _fit_robust(
    rows: tuple[_RegressionRow, ...],
    config: FitterConfig,
) -> _RegressionModel:
    if not rows:
        return _RegressionModel(0.0, 0.0, 0.0, 1.0, 1.0)
    insulin_scale = max(
        1e-6, sqrt(sum(row.insulin_activity**2 for row in rows) / len(rows))
    )
    meal_scale = max(1e-6, sqrt(sum(row.meal_activity**2 for row in rows) / len(rows)))
    design = [
        (1.0, row.insulin_activity / insulin_scale, row.meal_activity / meal_scale)
        for row in rows
    ]
    targets = [row.target for row in rows]
    weights = [1.0] * len(rows)
    beta = [median(targets), 0.0, 0.0]
    for _ in range(config.robust_iterations):
        updated = _weighted_ridge_solution(
            design,
            targets,
            weights,
            ridge=config.ridge_strength,
        )
        # Signed feature construction means both physiological amplitudes must
        # be non-negative.  They remain nuisance values and are not serialized.
        updated[1] = max(0.0, updated[1])
        updated[2] = max(0.0, updated[2])
        total_weight = sum(weights)
        if total_weight > 0.0:
            updated[0] = (
                sum(
                    weight * (target - updated[1] * x[1] - updated[2] * x[2])
                    for x, target, weight in zip(design, targets, weights, strict=True)
                )
                / total_weight
            )
        residuals = [
            target
            - sum(
                value * coefficient
                for value, coefficient in zip(x, updated, strict=True)
            )
            for x, target in zip(design, targets, strict=True)
        ]
        new_weights = [
            1.0
            if abs(residual) <= config.huber_delta_mmol
            else config.huber_delta_mmol / abs(residual)
            for residual in residuals
        ]
        if (
            max(abs(left - right) for left, right in zip(beta, updated, strict=True))
            < 1e-8
        ):
            beta = updated
            break
        beta = updated
        weights = new_weights
    return _RegressionModel(
        intercept=beta[0],
        insulin_coefficient=beta[1],
        meal_coefficient=beta[2],
        insulin_scale=insulin_scale,
        meal_scale=meal_scale,
    )


def _weighted_ridge_solution(
    design: list[tuple[float, float, float]],
    targets: list[float],
    weights: list[float],
    *,
    ridge: float,
) -> list[float]:
    matrix = [[0.0] * 3 for _ in range(3)]
    vector = [0.0] * 3
    for x, target, weight in zip(design, targets, weights, strict=True):
        for row in range(3):
            vector[row] += weight * x[row] * target
            for column in range(3):
                matrix[row][column] += weight * x[row] * x[column]
    matrix[0][0] += 1e-9
    matrix[1][1] += ridge
    matrix[2][2] += ridge
    return _solve_3x3(matrix, vector)


def _solve_3x3(matrix: list[list[float]], vector: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    for pivot in range(3):
        best = max(range(pivot, 3), key=lambda row: abs(augmented[row][pivot]))
        augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
        divisor = augmented[pivot][pivot]
        if abs(divisor) < 1e-12:
            augmented[pivot][pivot] = 1e-12
            divisor = 1e-12
        augmented[pivot] = [value / divisor for value in augmented[pivot]]
        for row in range(3):
            if row == pivot:
                continue
            factor = augmented[row][pivot]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(
                    augmented[row], augmented[pivot], strict=True
                )
            ]
    return [augmented[index][3] for index in range(3)]


def _huber_loss(residual: float, delta: float) -> float:
    magnitude = abs(residual)
    if magnitude <= delta:
        return 0.5 * residual * residual
    return delta * (magnitude - 0.5 * delta)


def _error_metrics(
    rows: tuple[_RegressionRow, ...],
    regression: _RegressionModel,
) -> ErrorMetrics:
    absolute = [abs(row.target - regression.predict(row)) for row in rows]
    if not absolute:
        return ErrorMetrics(0.0, 0.0, 0.0, ())
    by_day: dict[str, list[float]] = {}
    for row, error in zip(rows, absolute, strict=True):
        by_day.setdefault(row.day_key, []).append(error)
    day_mae = tuple(
        (key, sum(values) / len(values)) for key, values in sorted(by_day.items())
    )
    return ErrorMetrics(
        mae_mmol=sum(absolute) / len(absolute),
        median_day_mae_mmol=median(value for _, value in day_mae),
        p90_abs_error_mmol=_percentile(absolute, 0.90),
        day_mae_mmol=day_mae,
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    portion = position - lower
    return ordered[lower] * (1.0 - portion) + ordered[upper] * portion


def _passes_holdout_gates(
    baseline: ErrorMetrics,
    candidate: ErrorMetrics,
    config: FitterConfig,
) -> tuple[bool, str]:
    mae_gain = baseline.mae_mmol - candidate.mae_mmol
    median_gain = baseline.median_day_mae_mmol - candidate.median_day_mae_mmol
    mae_fraction = mae_gain / baseline.mae_mmol if baseline.mae_mmol > 1e-12 else 0.0
    median_fraction = (
        median_gain / baseline.median_day_mae_mmol
        if baseline.median_day_mae_mmol > 1e-12
        else 0.0
    )
    if mae_gain < config.min_absolute_improvement_mmol or median_gain < (
        config.min_absolute_improvement_mmol
    ):
        return False, "held_out_absolute_improvement_below_gate"
    if mae_fraction < config.min_relative_improvement or median_fraction < (
        config.min_relative_improvement
    ):
        return False, "held_out_relative_improvement_below_gate"
    if candidate.p90_abs_error_mmol > (
        baseline.p90_abs_error_mmol + config.p90_worsening_guard_mmol
    ):
        return False, "held_out_tail_error_worsened"
    baseline_days = dict(baseline.day_mae_mmol)
    for day_key, candidate_mae in candidate.day_mae_mmol:
        if candidate_mae > (
            baseline_days[day_key] + config.per_day_worsening_guard_mmol
        ):
            return False, "held_out_day_worsened"
    return True, "accepted"


def _metrics_shell(
    prepared: tuple[_PreparedDay, ...],
    excluded: dict[str, int],
    training_days: tuple[_PreparedDay, ...],
    holdout_days: tuple[_PreparedDay, ...],
    training_observations: tuple[_Observation, ...],
    holdout_observations: tuple[_Observation, ...],
    training_rapid: tuple[RapidInsulinEvent, ...],
    training_meals: tuple[MealEvent, ...],
) -> FitMetrics:
    return FitMetrics(
        complete_day_count=len(prepared),
        excluded_day_count=sum(excluded.values()),
        training_day_starts=tuple(day.day_start.isoformat() for day in training_days),
        holdout_day_starts=tuple(day.day_start.isoformat() for day in holdout_days),
        training_sample_count=len(training_observations),
        holdout_sample_count=len(holdout_observations),
        rapid_insulin_event_count=len(training_rapid),
        rapid_insulin_day_count=_event_day_count(training_days, "rapid"),
        meal_event_count=len(training_meals),
        meal_day_count=_event_day_count(training_days, "meal"),
        excluded_reasons=tuple(sorted(excluded.items())),
    )


def _empty_metrics(
    prepared: tuple[_PreparedDay, ...],
    excluded: dict[str, int],
) -> FitMetrics:
    return FitMetrics(
        complete_day_count=len(prepared),
        excluded_day_count=sum(excluded.values()),
        training_day_starts=(),
        holdout_day_starts=(),
        training_sample_count=0,
        holdout_sample_count=0,
        rapid_insulin_event_count=0,
        rapid_insulin_day_count=0,
        meal_event_count=0,
        meal_day_count=0,
        excluded_reasons=tuple(sorted(excluded.items())),
    )


def _with_validation_metrics(
    base: FitMetrics,
    baseline: ErrorMetrics,
    candidate: ErrorMetrics,
) -> FitMetrics:
    mae_gain = baseline.mae_mmol - candidate.mae_mmol
    median_gain = baseline.median_day_mae_mmol - candidate.median_day_mae_mmol
    return FitMetrics(
        complete_day_count=base.complete_day_count,
        excluded_day_count=base.excluded_day_count,
        training_day_starts=base.training_day_starts,
        holdout_day_starts=base.holdout_day_starts,
        training_sample_count=base.training_sample_count,
        holdout_sample_count=base.holdout_sample_count,
        rapid_insulin_event_count=base.rapid_insulin_event_count,
        rapid_insulin_day_count=base.rapid_insulin_day_count,
        meal_event_count=base.meal_event_count,
        meal_day_count=base.meal_day_count,
        baseline=baseline,
        candidate=candidate,
        mae_improvement_mmol=mae_gain,
        mae_improvement_fraction=(
            mae_gain / baseline.mae_mmol if baseline.mae_mmol > 1e-12 else 0.0
        ),
        median_improvement_mmol=median_gain,
        median_improvement_fraction=(
            median_gain / baseline.median_day_mae_mmol
            if baseline.median_day_mae_mmol > 1e-12
            else 0.0
        ),
        excluded_reasons=base.excluded_reasons,
    )


def _event_day_count(
    days: tuple[_PreparedDay, ...], kind: Literal["rapid", "meal"]
) -> int:
    if kind == "rapid":
        return sum(bool(day.rapid_insulin) for day in days)
    return sum(bool(day.meals) for day in days)


def _confidence(metrics: FitMetrics, config: FitterConfig) -> FitConfidence:
    gain = metrics.mae_improvement_fraction or 0.0
    if metrics.complete_day_count >= 28 and gain >= 0.15:
        return "high"
    if metrics.complete_day_count >= 14 and gain >= 0.10:
        return "medium"
    if gain >= config.min_relative_improvement:
        return "low"
    return "none"
