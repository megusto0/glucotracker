"""Personal historical short-horizon glucose forecasting.

The predictor is display-only. It learns glucose deltas from the owner's own
chronological CGM history and augments the recent CGM shape with meal, insulin,
heart-rate, activity, and sleep context.

The learned short-horizon changes use raw CGM differences within one sensor.
Display starts from the calibrated anchor and keeps that anchor's correction
fixed over the forecast. Later fingerstick calibration cannot rewrite training
features or target deltas. Absolute-level holdout diagnostics remain descriptive
and depend on the calibration available at the fitting cutoff.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil, cos, pi, sin
from typing import Any, Literal
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import (
    GlucosePredictionAuditCalibration,
    GlucosePredictionInputs,
    GlucosePredictionModel,
    GlucosePredictionPoint,
    GlucosePredictionResponse,
)
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.glucose_normalization import (
    GlucoseNormalizationService,
)
from glucotracker.application.glucose_visibility import visible_glucose_filter
from glucotracker.application.on_board.classification import is_rapid_insulin_event
from glucotracker.application.time import (
    local_wall_time,
    utc_instant_from_local_wall,
)
from glucotracker.application.twin.kernels import (
    POPULATION_INSULIN_KERNEL_V2,
    CarbProfileWeights,
    PersonalizedInsulinKernel,
    carb_mixture_activity_rate,
    carb_mixture_cob_remaining_fraction,
    carb_profile_prior_weights,
    personalized_insulin_activity_rate,
    personalized_insulin_iob_remaining_fraction,
)
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import (
    HealthConnectRecord,
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    utc_now,
)
from glucotracker.infra.db.repositories.glucose_prediction_audit import (
    EvaluatedForecastPoint,
    GlucosePredictionAuditRepository,
)
from glucotracker.infra.db.repositories.on_board import OnBoardRepository

MODEL_VERSION = "personal_causal_residual_v9"
MODEL_ALGORITHM = "causal_known_input_residual_conformal"
AUDIT_CALIBRATION_SOURCE_VERSIONS = (MODEL_VERSION,)
AUDIT_CALIBRATION_LOOKBACK_DAYS = 7
AUDIT_CALIBRATION_MIN_HORIZON_MINUTES = 30
AUDIT_CALIBRATION_MIN_POINTS = 48
AUDIT_CALIBRATION_FULL_STRENGTH_POINTS = 180
# Candidates above 1.0 let the audit expand an under-confident forecast, not just
# damp it toward persistence. A one-sided grid could only ever shrink further.
AUDIT_CALIBRATION_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
AUDIT_CALIBRATION_CORRECTION_CAP_MMOL = 0.5
AUDIT_CALIBRATION_MIN_MAE_IMPROVEMENT = 0.005
TRAINING_DAYS = 45
TRAINING_STRIDE_POINTS = 3
MIN_TRAINING_ROWS = 240
MIN_VALIDATION_ROWS = 48
MIN_TEST_ROWS = 48
MAX_CGM_MATCH_SECONDS = 8 * 60
SCENARIO_TAU_CANDIDATES = (15.0, 30.0, 45.0, 60.0)
SCENARIO_MOMENTUM_WEIGHTS = np.linspace(0.25, 1.5, 6)
SCENARIO_CARB_WEIGHTS = np.asarray((0.0, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2))
SCENARIO_INSULIN_WEIGHTS = np.asarray((0.25, 0.5, 1.0, 1.5, 2.0, 3.0))
SHAPE_BLEND_CANDIDATES = (0.0, 0.25, 0.5, 0.75)
SHAPE_BLEND_SCORE_TOLERANCE = 0.005
# The Huber delta used to be 0.8 mmol/L, below a typical 60-90 minute move, so
# every stage effectively optimized L1 and returned the conditional median. On a
# mostly-flat CGM that median is near zero, and the forecast collapsed toward
# persistence (measured: predicted moves were ~30% of actual moves at 90 min).
# A delta above the usual excursion keeps the estimate near the conditional mean
# while still clipping genuine artefacts such as compression lows.
HUBER_DELTA_MMOL = 3.0
SHAPE_LIGHTGBM_PARAMS: dict[str, int | float | str] = {
    "objective": "huber",
    "metric": "l2",
    "alpha": HUBER_DELTA_MMOL,
    "verbosity": -1,
    "num_threads": 2,
    "lambda_l2": 2.0,
    "lambda_l1": 0.2,
    "seed": 42,
    "learning_rate": 0.025,
    "num_leaves": 5,
    "max_depth": 3,
    "min_data_in_leaf": 60,
}
SHAPE_LIGHTGBM_ROUNDS = 180
# Interval from real quantile regression, then conformalized on the holdout, in
# place of a max() over two independent q80 residual estimates (which is not a
# quantile of anything and over-covered badly at long horizons).
INTERVAL_QUANTILES = (0.1, 0.9)
INTERVAL_TARGET_COVERAGE = 0.8
QUANTILE_LIGHTGBM_PARAMS: dict[str, int | float | str] = {
    "objective": "quantile",
    "metric": "quantile",
    "verbosity": -1,
    "num_threads": 2,
    "lambda_l2": 2.0,
    "seed": 42,
    "learning_rate": 0.05,
    "num_leaves": 5,
    "max_depth": 3,
    "min_data_in_leaf": 60,
}
QUANTILE_LIGHTGBM_ROUNDS = 150
MIN_CONFORMAL_ROWS = 30
MIN_CI_HALF_WIDTH_MMOL = 0.25
SHAPE_FEATURE_NAMES = [
    "glucose_delta_5m",
    "glucose_delta_15m",
    "glucose_delta_30m",
    "glucose_delta_60m",
    "glucose_delta_90m",
    "glucose_volatility_30m",
    "glucose_range_30m",
    "carbs_30m",
    "carbs_120m",
    "carbs_240m",
    "insulin_60m",
    "insulin_180m",
    "insulin_300m",
    "heart_rate_over_rest",
    "active_kcal_60m",
    "active_kcal_180m",
    "exercise_minutes_60m",
    "exercise_minutes_180m",
    "asleep",
    "sleep_hours_24h",
    "hour_sin",
    "hour_cos",
    "sensor_age_days",
    "heart_rate_available",
    "heart_rate_age_minutes",
    "activity_available",
    "activity_age_minutes",
    "sleep_available",
    "sleep_age_minutes",
]
SCENARIO_FEATURE_NAMES = [
    "cob_remaining_g",
    "known_carb_absorption_over_horizon_g",
    "iob_remaining_units",
    "known_insulin_action_over_horizon_units",
    *SHAPE_FEATURE_NAMES,
]
FEATURE_NAMES = [
    "glucose_now",
    "glucose_delta_5m",
    "glucose_delta_15m",
    "glucose_delta_30m",
    "glucose_delta_60m",
    "glucose_delta_90m",
    "glucose_volatility_30m",
    "glucose_range_30m",
    "glucose_mean_30m",
    "glucose_mean_60m",
    "carbs_30m",
    "carbs_120m",
    "carbs_240m",
    "insulin_60m",
    "insulin_180m",
    "insulin_300m",
    "cob_remaining_g",
    "carb_absorption_next_30m_g",
    "carb_absorption_rate_g_per_min",
    "iob_remaining_units",
    "insulin_action_next_30m_units",
    "insulin_action_rate_units_per_min",
    "minutes_since_carbs",
    "minutes_since_insulin",
    "heart_rate_now",
    "heart_rate_over_rest",
    "heart_rate_mean_30m",
    "heart_rate_mean_180m",
    "active_kcal_60m",
    "active_kcal_180m",
    "exercise_minutes_60m",
    "exercise_minutes_180m",
    "asleep",
    "sleep_hours_24h",
    "hour_sin",
    "hour_cos",
    "sensor_age_days",
    "heart_rate_available",
    "heart_rate_age_minutes",
    "activity_available",
    "activity_age_minutes",
    "sleep_available",
    "sleep_age_minutes",
]


@dataclass(frozen=True)
class _GlucoseSample:
    """One calibrated CGM reading.

    ``value`` is the normalized value the model learns and displays; ``raw`` is
    kept so the prospective audit can stay in the raw space its history uses.
    """

    timestamp: datetime
    value: float
    raw: float = 0.0
    bias: float = 0.0
    sensor_age_days: float | None = None
    is_normalized: bool = False
    sensor_session_id: UUID | None = None


@dataclass(frozen=True)
class _Interval:
    start: datetime
    end: datetime
    available_at: datetime | None = None


@dataclass(frozen=True)
class _CarbEvent:
    timestamp: datetime
    grams: float
    weights: CarbProfileWeights
    available_at: datetime | None = None


@dataclass(frozen=True)
class _InsulinDose:
    timestamp: datetime
    units: float
    available_at: datetime | None = None


class _Series:
    """Sorted timestamp/value series with efficient rolling windows."""

    def __init__(
        self,
        entries: list[tuple[datetime, float]],
        *,
        aggregate: Literal["mean", "sum"] = "mean",
        availability: dict[datetime, datetime] | None = None,
    ) -> None:
        collapsed: dict[datetime, list[float]] = {}
        for timestamp, value in entries:
            collapsed.setdefault(_as_utc(timestamp), []).append(float(value))
        ordered = sorted(
            (
                timestamp,
                sum(values) if aggregate == "sum" else sum(values) / len(values),
            )
            for timestamp, values in collapsed.items()
        )
        self.timestamps = [entry[0] for entry in ordered]
        self.values = [entry[1] for entry in ordered]
        self.availability = availability or {}
        self._tree_size = 1 << max(0, (len(self.timestamps) - 1).bit_length())
        self._available_tree = [float("inf")] * (2 * self._tree_size)
        if self.availability:
            for index, timestamp in enumerate(self.timestamps):
                self._available_tree[self._tree_size + index] = self.availability.get(
                    timestamp, timestamp
                ).timestamp()
            for node in range(self._tree_size - 1, 0, -1):
                self._available_tree[node] = min(
                    self._available_tree[2 * node], self._available_tree[2 * node + 1]
                )
        self.prefix = [0.0]
        for value in self.values:
            self.prefix.append(self.prefix[-1] + value)

    def window(
        self, end: datetime, minutes: int, *, known_at: datetime | None = None
    ) -> list[float]:
        end = _as_utc(end)
        start = end - timedelta(minutes=minutes)
        left = bisect_left(self.timestamps, start)
        right = bisect_right(self.timestamps, end)
        cutoff = _as_utc(known_at or end)
        return [
            self.values[i]
            for i in range(left, right)
            if self.availability.get(self.timestamps[i], self.timestamps[i]) <= cutoff
        ]

    def window_sum(
        self, end: datetime, minutes: int, *, known_at: datetime | None = None
    ) -> float:
        if self.availability:
            return sum(self.window(end, minutes, known_at=known_at))
        end = _as_utc(end)
        start = end - timedelta(minutes=minutes)
        left = bisect_left(self.timestamps, start)
        right = bisect_right(self.timestamps, end)
        return self.prefix[right] - self.prefix[left]

    def window_mean(
        self, end: datetime, minutes: int, *, known_at: datetime | None = None
    ) -> float | None:
        values = self.window(end, minutes, known_at=known_at)
        return sum(values) / len(values) if values else None

    def _latest_visible_index(self, at: datetime, known_at: datetime) -> int:
        right = bisect_right(self.timestamps, at) - 1
        if not self.availability or right < 0:
            return right
        cutoff = _as_utc(known_at).timestamp()

        def search(node: int, lo: int, hi: int) -> int:
            if lo > right or self._available_tree[node] > cutoff:
                return -1
            if lo == hi:
                return lo
            middle = (lo + hi) // 2
            found = search(node * 2 + 1, middle + 1, hi)
            return found if found >= 0 else search(node * 2, lo, middle)

        return search(1, 0, self._tree_size - 1)

    def latest(
        self, at: datetime, max_age_minutes: int, *, known_at: datetime | None = None
    ) -> float | None:
        at = _as_utc(at)
        index = self._latest_visible_index(at, known_at or at)
        if index < 0:
            return None
        if at - self.timestamps[index] > timedelta(minutes=max_age_minutes):
            return None
        return self.values[index]

    def minutes_since(
        self, at: datetime, cap_minutes: int, *, known_at: datetime | None = None
    ) -> float:
        at = _as_utc(at)
        index = self._latest_visible_index(at, known_at or at)
        if index < 0:
            return float(cap_minutes)
        age = (at - self.timestamps[index]).total_seconds() / 60.0
        return max(0.0, min(float(cap_minutes), age))


@dataclass(frozen=True)
class _FeatureContext:
    glucose: list[_GlucoseSample]
    glucose_times: list[datetime]
    carbs: _Series
    insulin: _Series
    carb_events: list[_CarbEvent]
    insulin_events: list[_InsulinDose]
    food_intervention_times: list[datetime]
    insulin_intervention_times: list[datetime]
    insulin_kernel: PersonalizedInsulinKernel
    heart_rate: _Series
    resting_heart_rate: _Series
    active_kcal: _Series
    exercise: list[_Interval]
    sleep: list[_Interval]
    default_resting_hr: float


@dataclass(frozen=True)
class _TreeFit:
    boosters: list[Any]


@dataclass(frozen=True)
class _QuantileFit:
    """Per-quantile, per-horizon boosters bounding the forecast delta."""

    boosters: dict[float, list[Any]]


@dataclass(frozen=True)
class _KnownInputEffects:
    momentum_slope: np.ndarray
    absorbed_carbs: np.ndarray
    delivered_insulin: np.ndarray


@dataclass(frozen=True)
class _AuditCalibration:
    """Conservative adjustment learned from already observed outcomes."""

    sample_count: int = 0
    weight: float = 1.0
    correction_mmol_l: float = 0.0
    empirical_q80_mmol_l: float | None = None
    base_mae_mmol_l: float | None = None
    calibrated_mae_mmol_l: float | None = None


@dataclass(frozen=True)
class _FittedHistory:
    selected_tau: float
    shape_blend: float
    coefficients: np.ndarray
    shape: _TreeFit
    quantiles: _QuantileFit
    conformal_scale: np.ndarray
    validation_mae: float
    baseline_mae: float
    post_meal_metrics: dict[str, Any]
    critical_metrics: dict[str, Any]


def _train_history(
    x: np.ndarray,
    y: np.ndarray,
    eligibility: np.ndarray,
    row_times: list[datetime],
    horizons: list[int],
    known_effects: _KnownInputEffects,
    train_end: int,
    calibration_end: int,
) -> _FittedHistory:
    test_x = x[calibration_end:]
    test_y = y[calibration_end:]
    test_eligibility = eligibility[calibration_end:]
    selected_tau = _select_scenario_tau(
        known_effects,
        y,
        eligibility,
        horizons,
        train_end,
        calibration_end,
    )
    evaluation_design = _scenario_design(
        known_effects,
        horizons,
        selected_tau,
    )
    shape_x = _shape_features(x)
    selection_coefficients = _fit_scenario_coefficients(
        evaluation_design[:train_end],
        y[:train_end],
        eligibility[:train_end],
    )
    selection_kinetic_predictions = _predict_known_input_scenario(
        evaluation_design[train_end:calibration_end],
        selection_coefficients,
    )
    selection_shape_fit = _fit_shape_models(
        shape_x[:train_end],
        evaluation_design[:train_end],
        y[:train_end]
        - _predict_known_input_scenario(
            evaluation_design[:train_end], selection_coefficients
        ),
        eligibility[:train_end],
    )
    selection_shape_predictions = selection_kinetic_predictions + _predict_shape_models(
        selection_shape_fit,
        shape_x[train_end:calibration_end],
        evaluation_design[train_end:calibration_end],
    )
    shape_blend = _select_shape_blend(
        selection_kinetic_predictions,
        selection_shape_predictions,
        y[train_end:calibration_end],
        eligibility[train_end:calibration_end],
    )
    evaluation_coefficients = _fit_scenario_coefficients(
        evaluation_design[:calibration_end],
        y[:calibration_end],
        eligibility[:calibration_end],
    )
    validation_kinetic_predictions = _predict_known_input_scenario(
        evaluation_design[calibration_end:],
        evaluation_coefficients,
    )
    evaluation_shape_fit = _fit_shape_models(
        shape_x[:calibration_end],
        evaluation_design[:calibration_end],
        y[:calibration_end]
        - _predict_known_input_scenario(
            evaluation_design[:calibration_end], evaluation_coefficients
        ),
        eligibility[:calibration_end],
    )
    validation_shape_predictions = (
        validation_kinetic_predictions
        + _predict_shape_models(
            evaluation_shape_fit,
            shape_x[calibration_end:],
            evaluation_design[calibration_end:],
        )
    )
    validation_predictions = _blend_scenario_predictions(
        validation_kinetic_predictions,
        validation_shape_predictions,
        shape_blend,
    )
    evaluation_quantile_fit = _fit_quantile_models(
        shape_x[:calibration_end],
        evaluation_design[:calibration_end],
        y[:calibration_end],
        eligibility[:calibration_end],
    )
    validation_quantiles = _predict_quantile_models(
        evaluation_quantile_fit,
        shape_x[calibration_end:],
        evaluation_design[calibration_end:],
    )
    conformal_scale = _conformal_interval_scale(
        validation_quantiles[INTERVAL_QUANTILES[0]],
        validation_quantiles[INTERVAL_QUANTILES[1]],
        validation_predictions,
        test_y,
        test_eligibility,
    )
    validation_errors = np.abs(validation_predictions - test_y)
    validation_mae_by_horizon = _masked_mean_by_horizon(
        validation_errors,
        test_eligibility,
    )
    baseline_mae_by_horizon = _masked_mean_by_horizon(
        np.abs(test_y),
        test_eligibility,
    )
    validation_mae = float(validation_mae_by_horizon[-1])
    baseline_mae = float(baseline_mae_by_horizon[-1])
    post_meal_metrics = _post_meal_validation_metrics(
        test_x,
        test_y,
        validation_predictions,
        test_eligibility,
    )
    critical_metrics = _critical_validation_metrics(
        test_x,
        test_y,
        validation_predictions,
        test_eligibility,
    )

    final_coefficients = _fit_scenario_coefficients(
        evaluation_design,
        y,
        eligibility,
    )
    final_shape_fit = _fit_shape_models(
        shape_x,
        evaluation_design,
        y - _predict_known_input_scenario(evaluation_design, final_coefficients),
        eligibility,
    )
    final_quantile_fit = _fit_quantile_models(
        shape_x,
        evaluation_design,
        y,
        eligibility,
    )
    return _FittedHistory(
        selected_tau,
        shape_blend,
        final_coefficients,
        final_shape_fit,
        final_quantile_fit,
        conformal_scale,
        validation_mae,
        baseline_mae,
        post_meal_metrics,
        critical_metrics,
    )


class GlucosePredictionService:
    """Train and run a current-user 90-minute research forecast."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        if user_id is None:
            raise ValueError("GlucosePredictionService requires user_id")
        self.session = session
        self.user_id = user_id
        self.as_of = utc_now()
        self.input_provenance: dict[str, Any] = {}

    def predict(
        self,
        *,
        mode: Literal["raw", "normalized"] = "normalized",
        horizon_minutes: int = 90,
        step_minutes: int = 5,
        as_of: datetime | None = None,
    ) -> GlucosePredictionResponse:
        self.as_of = _as_utc(as_of or utc_now())
        horizon_minutes = max(step_minutes, min(90, horizon_minutes))
        horizons = list(range(step_minutes, horizon_minutes + 1, step_minutes))
        glucose = self._glucose_history(horizon_minutes)
        now = self.as_of
        notes = [
            "Исследовательский прогноз; не использовать для расчёта инсулина.",
        ]
        if not glucose:
            return self._empty_response(
                mode=mode,
                horizon_minutes=horizon_minutes,
                step_minutes=step_minutes,
                notes=[*notes, "Нет доступных данных CGM."],
            )

        anchor = glucose[-1]
        context = self._feature_context(glucose, anchor.timestamp)
        rows, targets, row_times, eligibility_rows = self._training_matrix(
            context,
            horizons,
        )
        if len(rows) < MIN_TRAINING_ROWS + MIN_VALIDATION_ROWS + MIN_TEST_ROWS:
            return self._empty_response(
                mode=mode,
                horizon_minutes=horizon_minutes,
                step_minutes=step_minutes,
                anchor=anchor,
                sample_count=len(rows),
                day_count=len({timestamp.date() for timestamp in row_times}),
                notes=[
                    *notes,
                    "Недостаточно непрерывных исторических окон для обучения.",
                ],
            )

        x = np.asarray(rows, dtype=np.float64)
        y = np.asarray(targets, dtype=np.float64)
        eligibility = np.asarray(eligibility_rows, dtype=bool)
        train_end, calibration_end = _chronological_day_splits(row_times)
        eligibility = _purge_overlapping_targets(
            row_times, horizons, eligibility, (train_end, calibration_end)
        )
        if (
            int(eligibility[:train_end].sum(axis=0).min()) < MIN_TRAINING_ROWS
            or int(eligibility[train_end:calibration_end].sum(axis=0).min())
            < MIN_VALIDATION_ROWS
            or int(eligibility[calibration_end:].sum(axis=0).min()) < MIN_TEST_ROWS
        ):
            return self._empty_response(
                mode=mode,
                horizon_minutes=horizon_minutes,
                step_minutes=step_minutes,
                anchor=anchor,
                sample_count=int(eligibility[:, -1].sum()),
                day_count=len(
                    {
                        timestamp.date()
                        for timestamp, eligible in zip(
                            row_times,
                            eligibility[:, -1],
                            strict=True,
                        )
                        if eligible
                    }
                ),
                notes=[
                    *notes,
                    "Недостаточно окон без новых приёмов пищи или инсулина.",
                ],
            )

        known_effects = _known_input_effects(context, x, row_times, horizons)
        from glucotracker.application.glucose_prediction_model_store import (
            fitted_history,
        )

        fit = fitted_history(
            self.user_id,
            x,
            y,
            eligibility,
            row_times,
            horizons,
            known_effects,
            train_end,
            calibration_end,
        )
        selected_tau = fit.selected_tau
        shape_blend = fit.shape_blend
        final_coefficients = fit.coefficients
        final_shape_fit = fit.shape
        final_quantile_fit = fit.quantiles
        conformal_scale = fit.conformal_scale
        validation_mae = fit.validation_mae
        baseline_mae = fit.baseline_mae
        post_meal_metrics = fit.post_meal_metrics
        critical_metrics = fit.critical_metrics

        try:
            current_features, coverage = _features_at(
                context, anchor.timestamp, known_at=now
            )
        except ValueError:
            return self._empty_response(
                mode=mode,
                horizon_minutes=horizon_minutes,
                step_minutes=step_minutes,
                anchor=anchor,
                sample_count=len(rows),
                day_count=len({timestamp.date() for timestamp in row_times}),
                notes=[
                    *notes,
                    "В последних данных CGM есть разрыв; прогноз временно недоступен.",
                ],
            )
        self.input_provenance = {
            "as_of": now.isoformat(),
            "anchor_bias": anchor.bias,
            "anchor_is_normalized": anchor.is_normalized,
            "features": dict(zip(FEATURE_NAMES, current_features, strict=True)),
        }
        current_x = np.asarray([current_features], dtype=np.float64)
        current_effects = _known_input_effects(
            context,
            current_x,
            [anchor.timestamp],
            horizons,
            known_at=now,
        )
        current_design = _scenario_design(
            current_effects,
            horizons,
            selected_tau,
        )
        current_kinetic_predictions = _predict_known_input_scenario(
            current_design,
            final_coefficients,
        )
        current_shape_predictions = current_kinetic_predictions + _predict_shape_models(
            final_shape_fit,
            _shape_features(current_x),
            current_design,
        )
        predicted_deltas = _blend_scenario_predictions(
            current_kinetic_predictions,
            current_shape_predictions,
            shape_blend,
        )[0]
        current_quantiles = _predict_quantile_models(
            final_quantile_fit,
            _shape_features(current_x),
            current_design,
        )
        interval_half_low, interval_half_high = _interval_half_widths(
            current_quantiles[INTERVAL_QUANTILES[0]][0],
            current_quantiles[INTERVAL_QUANTILES[1]][0],
            predicted_deltas,
            conformal_scale,
        )
        audit_calibration = self._audit_calibration(anchor, horizons)
        eligible_sample_count = int(eligibility[:, -1].sum())
        eligible_days = {
            timestamp.date()
            for timestamp, eligible in zip(
                row_times,
                eligibility[:, -1],
                strict=True,
            )
            if eligible
        }
        model_confidence = _model_confidence(
            sample_count=eligible_sample_count,
            day_count=len(eligible_days),
            validation_mae=validation_mae,
            baseline_mae=baseline_mae,
        )
        notes.extend(
            [
                "Сценарий: после последней точки не добавляются еда или инсулин.",
                "Учтены уже записанные углеводы, инсулин и исторически "
                "похожая форма CGM.",
                "Абсолютный уровень глюкозы исключён из модели формы, "
                "чтобы не тянуть прогноз к норме.",
                "Окна с новыми последующими записями исключены из обучения и holdout.",
            ]
        )
        if post_meal_metrics["count"]:
            notes.append(
                "После еды holdout MAE на 90 минут: "
                f"{post_meal_metrics['mae_90']:.2f} ммоль/л "
                f"({post_meal_metrics['count']} окон)."
            )

        display_anchor = anchor.value if mode == "normalized" else anchor.raw
        anchor_age_minutes = max(
            0.0,
            (now - anchor.timestamp).total_seconds() / 60.0,
        )
        if not anchor.is_normalized:
            notes.append(
                "Для текущего сенсора нет калибровки по замерам из пальца; "
                "прогноз на шкале CGM."
            )
        if not coverage["health"]:
            notes.append(
                "Свежие данные браслета недоступны; это учтено как отсутствие данных."
            )
        if anchor_age_minutes > 15:
            notes.append("Последняя точка CGM старше 15 минут; confidence снижен.")

        points: list[GlucosePredictionPoint] = []
        base_prediction_by_horizon: dict[int, float] = {}
        base_confidence = {"high": 0.82, "medium": 0.64, "low": 0.44}[model_confidence]
        freshness = max(0.25, 1.0 - max(0.0, anchor_age_minutes - 10) / 120)
        # The model now works entirely in the normalized space, so the raw series
        # reported for the prospective audit is reconstructed from the anchor bias.
        bias = anchor.bias
        for index, horizon in enumerate(horizons):
            base_delta = float(predicted_deltas[index])
            base_prediction_by_horizon[horizon] = round(
                _clamp_glucose(anchor.raw + base_delta),
                2,
            )
            calibration = audit_calibration[horizon]
            delta = calibration.weight * base_delta + calibration.correction_mmol_l
            raw_value = _clamp_glucose(anchor.raw + delta)
            normalized_value = _clamp_glucose(raw_value + bias)
            display_value = normalized_value if mode == "normalized" else raw_value
            half_low = max(
                MIN_CI_HALF_WIDTH_MMOL,
                float(interval_half_low[index]),
                calibration.empirical_q80_mmol_l or 0.0,
            )
            half_high = max(
                MIN_CI_HALF_WIDTH_MMOL,
                float(interval_half_high[index]),
                calibration.empirical_q80_mmol_l or 0.0,
            )
            confidence = base_confidence * freshness * (1.0 - 0.35 * horizon / 90)
            points.append(
                GlucosePredictionPoint(
                    timestamp=local_wall_time(
                        anchor.timestamp + timedelta(minutes=horizon)
                    ),
                    horizon_minutes=horizon,
                    raw_value=round(raw_value, 2),
                    raw_ci_low=round(_clamp_glucose(raw_value - half_low), 2),
                    raw_ci_high=round(_clamp_glucose(raw_value + half_high), 2),
                    normalized_value=(
                        round(normalized_value, 2) if anchor.is_normalized else None
                    ),
                    display_value=round(display_value, 2),
                    ci_low=round(_clamp_glucose(display_value - half_low), 2),
                    ci_high=round(_clamp_glucose(display_value + half_high), 2),
                    confidence=round(max(0.0, min(1.0, confidence)), 3),
                    band=_glucose_band(display_value),
                )
            )

        calibrated_horizons = [
            horizon
            for horizon, calibration in audit_calibration.items()
            if calibration.weight < 0.999 or abs(calibration.correction_mmol_l) >= 0.005
        ]
        if calibrated_horizons:
            notes.append(
                "Горизонты "
                f"{min(calibrated_horizons)}–{max(calibrated_horizons)} мин "
                "скорректированы только по уже завершённым прогнозам "
                "текущего сенсора."
            )

        return GlucosePredictionResponse(
            generated_at=now,
            anchor_timestamp=local_wall_time(anchor.timestamp),
            anchor_value=round(display_anchor, 2),
            raw_anchor_value=round(anchor.raw, 2),
            horizon_minutes=horizon_minutes,
            step_minutes=step_minutes,
            mode=mode,
            points=points,
            model=GlucosePredictionModel(
                version=MODEL_VERSION,
                algorithm=MODEL_ALGORITHM,
                forecast_assumption="no_new_food_or_insulin",
                training_from=local_wall_time(row_times[0]),
                training_to=local_wall_time(row_times[-1]),
                sample_count=eligible_sample_count,
                day_count=len(eligible_days),
                validation_mae_mmol=round(validation_mae, 3),
                baseline_mae_mmol=round(baseline_mae, 3),
                validation_post_meal_count=post_meal_metrics["count"],
                validation_post_meal_mae_30_mmol=post_meal_metrics["mae_30"],
                validation_post_meal_mae_60_mmol=post_meal_metrics["mae_60"],
                validation_post_meal_mae_90_mmol=post_meal_metrics["mae_90"],
                validation_post_meal_baseline_mae_90_mmol=(
                    post_meal_metrics["baseline_mae_90"]
                ),
                validation_low_count=critical_metrics["low_count"],
                validation_low_mae_mmol=critical_metrics["low_mae"],
                validation_low_miss_pct=critical_metrics["low_miss_pct"],
                validation_high_count=critical_metrics["high_count"],
                validation_high_mae_mmol=critical_metrics["high_mae"],
                validation_high_miss_pct=critical_metrics["high_miss_pct"],
                confidence=model_confidence,
                features_used=SCENARIO_FEATURE_NAMES,
                feature_coverage=coverage,
                audit_calibration_by_horizon=[
                    GlucosePredictionAuditCalibration(
                        horizon_minutes=horizon,
                        base_prediction_mmol_l=base_prediction_by_horizon[horizon],
                        sample_count=calibration.sample_count,
                        weight=round(calibration.weight, 3),
                        correction_mmol_l=round(
                            calibration.correction_mmol_l,
                            3,
                        ),
                        historical_mae_mmol_l=(
                            round(calibration.calibrated_mae_mmol_l, 3)
                            if calibration.calibrated_mae_mmol_l is not None
                            else None
                        ),
                    )
                    for horizon, calibration in audit_calibration.items()
                ],
                audit_calibration_source_versions=list(
                    AUDIT_CALIBRATION_SOURCE_VERSIONS
                ),
            ),
            inputs=_prediction_inputs(context, anchor.timestamp, known_at=now),
            notes=notes,
        )

    def _audit_calibration(
        self,
        anchor: _GlucoseSample,
        horizons: list[int],
    ) -> dict[int, _AuditCalibration]:
        sensors = GlucoseDashboardService(
            self.session,
            self.user_id,
        ).list_sensors()
        active_sensor = next(
            (
                sensor
                for sensor in sensors
                if sensor.ended_at is None
                and utc_instant_from_local_wall(sensor.started_at) <= anchor.timestamp
            ),
            None,
        )
        if active_sensor is None:
            return {horizon: _AuditCalibration() for horizon in horizons}

        sensor_started_at = utc_instant_from_local_wall(active_sensor.started_at)
        since = max(
            sensor_started_at,
            anchor.timestamp - timedelta(days=AUDIT_CALIBRATION_LOOKBACK_DAYS),
        )
        samples = GlucosePredictionAuditRepository(
            self.session,
            self.user_id,
        ).evaluated_base_points(
            since=since,
            before=anchor.timestamp,
            model_versions=AUDIT_CALIBRATION_SOURCE_VERSIONS,
        )
        return _fit_audit_calibration(samples, horizons)

    def _glucose_history(self, horizon_minutes: int) -> list[_GlucoseSample]:
        """Return the calibrated training series, oldest first."""
        newest = self.session.scalar(
            select(NightscoutGlucoseEntry)
            .where(
                NightscoutGlucoseEntry.owner_id == self.user_id,
                NightscoutGlucoseEntry.timestamp <= self.as_of,
                NightscoutGlucoseEntry.created_at <= self.as_of,
                visible_glucose_filter(self.user_id),
            )
            .order_by(NightscoutGlucoseEntry.timestamp.desc())
            .limit(1)
        )
        if newest is None:
            return []
        newest_at = _as_utc(newest.timestamp)
        newest_local = local_wall_time(newest_at)
        training_from = utc_instant_from_local_wall(
            datetime.combine(
                newest_local.date() - timedelta(days=TRAINING_DAYS),
                datetime.min.time(),
            )
        )
        samples = GlucoseNormalizationService(self.session, self.user_id).series(
            training_from,
            newest_at,
            as_of=self.as_of,
        )
        return [
            _GlucoseSample(
                timestamp=sample.timestamp,
                value=sample.normalized_mmol_l,
                raw=sample.raw_mmol_l,
                bias=sample.bias_mmol_l,
                sensor_age_days=sample.sensor_age_days,
                is_normalized=sample.is_normalized,
                sensor_session_id=sample.sensor_session_id,
            )
            for sample in samples
            if 1.5 <= sample.raw_mmol_l <= 30
        ]

    def _feature_context(
        self,
        glucose: list[_GlucoseSample],
        anchor: datetime,
    ) -> _FeatureContext:
        training_from = glucose[0].timestamp - timedelta(hours=6)
        carbs = self._carb_events(training_from, anchor)
        insulin = self._insulin_events(training_from, anchor)
        food_intervention_times = self._food_intervention_times(
            training_from,
            anchor,
        )
        insulin_intervention_times = self._insulin_intervention_times(
            training_from,
            anchor,
        )
        health = self._health_records(training_from, anchor)
        heart_rate, resting_hr, active_kcal, exercise, sleep = _health_series(health)
        default_resting_hr = 60.0
        insulin_kernel = POPULATION_INSULIN_KERNEL_V2
        iob_fit = OnBoardRepository(self.session, self.user_id).get_active_fit(
            "iob",
            "rapid",
        )
        if iob_fit is not None and _as_utc(iob_fit.fitted_at) <= self.as_of:
            try:
                insulin_kernel = PersonalizedInsulinKernel.from_mapping(
                    iob_fit.params_json
                )
            except ValueError:
                pass
        return _FeatureContext(
            glucose=glucose,
            glucose_times=[sample.timestamp for sample in glucose],
            carbs=_Series(
                [(event.timestamp, event.grams) for event in carbs],
                aggregate="sum",
                availability={
                    event.timestamp: event.available_at or event.timestamp
                    for event in carbs
                },
            ),
            insulin=_Series(
                [(event.timestamp, event.units) for event in insulin],
                aggregate="sum",
                availability={
                    event.timestamp: event.available_at or event.timestamp
                    for event in insulin
                },
            ),
            carb_events=carbs,
            insulin_events=insulin,
            food_intervention_times=food_intervention_times,
            insulin_intervention_times=insulin_intervention_times,
            insulin_kernel=insulin_kernel,
            heart_rate=heart_rate,
            resting_heart_rate=resting_hr,
            active_kcal=active_kcal,
            exercise=exercise,
            sleep=sleep,
            default_resting_hr=default_resting_hr,
        )

    def _carb_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[_CarbEvent]:
        local_from = local_wall_time(from_datetime)
        local_to = local_wall_time(to_datetime)
        rows = self.session.scalars(
            select(Meal)
            .where(
                Meal.owner_id == self.user_id,
                Meal.updated_at <= self.as_of,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= local_from,
                Meal.eaten_at <= local_to,
                Meal.total_carbs_g > 0,
            )
            .order_by(Meal.eaten_at.asc())
        ).all()
        return [
            _CarbEvent(
                timestamp=utc_instant_from_local_wall(row.eaten_at),
                grams=float(row.total_carbs_g),
                available_at=_as_utc(row.updated_at),
                weights=carb_profile_prior_weights(
                    carbs_g=float(row.total_carbs_g),
                    protein_g=float(row.total_protein_g),
                    fat_g=float(row.total_fat_g),
                    fiber_g=float(row.total_fiber_g),
                ),
            )
            for row in rows
        ]

    def _insulin_events(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[_InsulinDose]:
        rows = self.session.scalars(
            select(NightscoutInsulinEvent)
            .where(
                NightscoutInsulinEvent.owner_id == self.user_id,
                NightscoutInsulinEvent.updated_at <= self.as_of,
                NightscoutInsulinEvent.timestamp >= from_datetime,
                NightscoutInsulinEvent.timestamp <= to_datetime,
                NightscoutInsulinEvent.insulin_units.is_not(None),
                NightscoutInsulinEvent.insulin_units > 0,
            )
            .order_by(NightscoutInsulinEvent.timestamp.asc())
        ).all()
        seen: set[str] = set()
        events: list[_InsulinDose] = []
        for row in rows:
            if not is_rapid_insulin_event(
                insulin_type=row.insulin_type,
                event_type=row.event_type,
            ):
                continue
            timestamp = _as_utc(row.timestamp)
            units = float(row.insulin_units or 0)
            key = (row.nightscout_id or "").strip() or (
                f"{int(timestamp.timestamp())}:{units:.3f}:{row.event_type or ''}"
            )
            if key in seen:
                continue
            seen.add(key)
            events.append(_InsulinDose(timestamp, units, _as_utc(row.updated_at)))
        return events

    def _food_intervention_times(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[datetime]:
        rows = self.session.scalars(
            select(Meal.eaten_at)
            .where(
                Meal.owner_id == self.user_id,
                Meal.updated_at <= self.as_of,
                Meal.status == MealStatus.accepted,
                Meal.eaten_at >= local_wall_time(from_datetime),
                Meal.eaten_at <= local_wall_time(to_datetime),
            )
            .order_by(Meal.eaten_at.asc())
        ).all()
        return [utc_instant_from_local_wall(timestamp) for timestamp in rows]

    def _insulin_intervention_times(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[datetime]:
        rows = self.session.scalars(
            select(NightscoutInsulinEvent.timestamp)
            .where(
                NightscoutInsulinEvent.owner_id == self.user_id,
                NightscoutInsulinEvent.updated_at <= self.as_of,
                NightscoutInsulinEvent.timestamp >= from_datetime,
                NightscoutInsulinEvent.timestamp <= to_datetime,
                NightscoutInsulinEvent.insulin_units.is_not(None),
                NightscoutInsulinEvent.insulin_units > 0,
            )
            .order_by(NightscoutInsulinEvent.timestamp.asc())
        ).all()
        return [_as_utc(timestamp) for timestamp in rows]

    def _health_records(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[HealthConnectRecord]:
        # Some imported index columns contain a double-applied zone offset.
        # Query with padding, then trust absolute instants inside each payload.
        record_types = {
            "HeartRateRecord",
            "RestingHeartRateRecord",
            "ActiveCaloriesBurnedRecord",
            "ExerciseSessionRecord",
            "SleepSessionRecord",
        }
        return list(
            self.session.scalars(
                select(HealthConnectRecord)
                .where(
                    HealthConnectRecord.owner_id == self.user_id,
                    HealthConnectRecord.record_type.in_(record_types),
                    HealthConnectRecord.updated_at <= self.as_of,
                    HealthConnectRecord.start_time
                    >= from_datetime - timedelta(hours=12),
                    HealthConnectRecord.start_time <= to_datetime + timedelta(hours=12),
                )
                .order_by(HealthConnectRecord.start_time.asc())
            )
        )

    def _training_matrix(
        self,
        context: _FeatureContext,
        horizons: list[int],
    ) -> tuple[
        list[list[float]],
        list[list[float]],
        list[datetime],
        list[list[bool]],
    ]:
        rows: list[list[float]] = []
        targets: list[list[float]] = []
        row_times: list[datetime] = []
        eligibility: list[list[bool]] = []
        current_local_day = local_wall_time(context.glucose[-1].timestamp).date()
        for index in range(6, len(context.glucose)):
            anchor = context.glucose[index]
            if local_wall_time(anchor.timestamp).date() >= current_local_day:
                break
            five_minute_slot = int(anchor.timestamp.timestamp() // (5 * 60))
            if five_minute_slot % TRAINING_STRIDE_POINTS != 0:
                continue
            target_end = anchor.timestamp + timedelta(minutes=horizons[-1])
            # No target (including CGM matching tolerance) may enter the current day.
            day_start = utc_instant_from_local_wall(
                datetime.combine(current_local_day, datetime.min.time())
            )
            if target_end + timedelta(seconds=MAX_CGM_MATCH_SECONDS) >= day_start:
                break
            try:
                features, _ = _features_at(context, anchor.timestamp)
            except ValueError:
                continue
            target_values: list[float] = []
            target_eligibility: list[bool] = []
            food_start = bisect_right(
                context.food_intervention_times,
                anchor.timestamp,
            )
            insulin_start = bisect_right(
                context.insulin_intervention_times,
                anchor.timestamp,
            )
            for horizon in horizons:
                target_timestamp = anchor.timestamp + timedelta(minutes=horizon)
                future = _nearest_glucose(
                    context,
                    target_timestamp,
                    raw=True,
                )
                if future is None:
                    break
                future_index = min(
                    bisect_left(context.glucose_times, target_timestamp),
                    len(context.glucose) - 1,
                )
                if (
                    context.glucose[future_index].sensor_session_id
                    != anchor.sensor_session_id
                ):
                    break
                target_values.append(future - (anchor.raw or anchor.value))
                target_eligibility.append(
                    bisect_right(
                        context.food_intervention_times,
                        target_timestamp,
                    )
                    == food_start
                    and bisect_right(
                        context.insulin_intervention_times,
                        target_timestamp,
                    )
                    == insulin_start
                )
            if len(target_values) != len(horizons):
                continue
            rows.append(features)
            targets.append(target_values)
            row_times.append(anchor.timestamp)
            eligibility.append(target_eligibility)
        return rows, targets, row_times, eligibility

    def _empty_response(
        self,
        *,
        mode: Literal["raw", "normalized"],
        horizon_minutes: int,
        step_minutes: int,
        notes: list[str],
        anchor: _GlucoseSample | None = None,
        sample_count: int = 0,
        day_count: int = 0,
    ) -> GlucosePredictionResponse:
        return GlucosePredictionResponse(
            generated_at=utc_now(),
            anchor_timestamp=(
                local_wall_time(anchor.timestamp) if anchor is not None else None
            ),
            anchor_value=anchor.value if anchor is not None else None,
            raw_anchor_value=anchor.raw if anchor is not None else None,
            horizon_minutes=horizon_minutes,
            step_minutes=step_minutes,
            mode=mode,
            points=[],
            model=GlucosePredictionModel(
                version=MODEL_VERSION,
                algorithm=MODEL_ALGORITHM,
                forecast_assumption="no_new_food_or_insulin",
                sample_count=sample_count,
                day_count=day_count,
                confidence="none",
                features_used=SCENARIO_FEATURE_NAMES,
                feature_coverage={},
            ),
            inputs=GlucosePredictionInputs(),
            notes=notes,
        )


def _fit_audit_calibration(
    samples: list[EvaluatedForecastPoint],
    horizons: list[int],
) -> dict[int, _AuditCalibration]:
    """Choose a correction on older days; accept it only on two later days.

    The repository enforces outcome availability. Overlapping target windows
    are purged at this additional selection boundary. Days have equal weight
    so frequent polling cannot by itself justify a correction.
    """
    result: dict[int, _AuditCalibration] = {}
    for horizon in horizons:
        points = sorted(
            (p for p in samples if p.horizon_minutes == horizon),
            key=lambda p: p.anchor_timestamp,
        )
        count = len(points)
        result[horizon] = _AuditCalibration(sample_count=count)
        days = sorted({local_wall_time(p.anchor_timestamp).date() for p in points})
        if horizon < AUDIT_CALIBRATION_MIN_HORIZON_MINUTES or len(days) < 5:
            continue
        validation_day = days[-2]
        cutoff = utc_instant_from_local_wall(
            datetime.combine(validation_day, datetime.min.time())
        )
        train = [
            p
            for p in points
            if p.anchor_timestamp
            + timedelta(minutes=horizon, seconds=MAX_CGM_MATCH_SECONDS)
            < cutoff
        ]
        holdout = [p for p in points if p.anchor_timestamp >= cutoff]
        if (
            len(train) < AUDIT_CALIBRATION_MIN_POINTS
            or len(holdout) < MIN_CONFORMAL_ROWS
        ):
            continue

        def arrays(rows: list[EvaluatedForecastPoint]):
            anchors = np.asarray([p.anchor_value_mmol_l for p in rows])
            deltas = np.asarray([p.base_predicted_value_mmol_l for p in rows]) - anchors
            actual = np.asarray([p.actual_value_mmol_l for p in rows])
            dates = np.asarray(
                [local_wall_time(p.anchor_timestamp).date() for p in rows]
            )
            return anchors, deltas, actual, dates

        def daily_mae(errors: np.ndarray, dates: np.ndarray) -> float:
            return float(np.mean([np.mean(errors[dates == day]) for day in set(dates)]))

        anchors, deltas, actual, dates = arrays(train)
        candidates = []
        for weight in AUDIT_CALIBRATION_WEIGHTS:
            residual = actual - (anchors + weight * deltas)
            correction = float(
                np.clip(
                    np.median(
                        [np.median(residual[dates == day]) for day in set(dates)]
                    ),
                    -AUDIT_CALIBRATION_CORRECTION_CAP_MMOL,
                    AUDIT_CALIBRATION_CORRECTION_CAP_MMOL,
                )
            )
            errors = np.abs(residual - correction)
            candidates.append(
                (daily_mae(errors, dates), abs(weight - 1), weight, correction)
            )
        _, _, best_weight, best_correction = min(candidates)
        strength = min(
            1.0,
            len(train) / AUDIT_CALIBRATION_FULL_STRENGTH_POINTS,
            len(set(dates)) / 5.0,
        )
        weight = 1.0 + strength * (best_weight - 1.0)
        correction = strength * best_correction
        anchors, deltas, actual, dates = arrays(holdout)
        base_errors = np.abs(actual - (anchors + deltas))
        errors = np.abs(actual - (anchors + weight * deltas + correction))
        base_mae = daily_mae(base_errors, dates)
        calibrated_mae = daily_mae(errors, dates)
        # Both later days must avoid regression; an average win alone is weak evidence.
        accepted = (
            calibrated_mae <= base_mae - AUDIT_CALIBRATION_MIN_MAE_IMPROVEMENT
            and all(
                float(np.mean(errors[dates == day] - base_errors[dates == day])) <= 0
                for day in set(dates)
            )
        )
        if not accepted:
            weight, correction, errors, calibrated_mae = 1.0, 0.0, base_errors, base_mae
        result[horizon] = _AuditCalibration(
            sample_count=count,
            weight=weight,
            correction_mmol_l=correction,
            empirical_q80_mmol_l=float(np.quantile(errors, 0.8)),
            base_mae_mmol_l=base_mae,
            calibrated_mae_mmol_l=calibrated_mae,
        )
    return result


def _features_at(
    context: _FeatureContext,
    timestamp: datetime,
    *,
    known_at: datetime | None = None,
) -> tuple[list[float], dict[str, bool]]:
    current = _nearest_glucose(context, timestamp, raw=True)
    normalized_current = _nearest_glucose(context, timestamp)
    five = _nearest_glucose(context, timestamp - timedelta(minutes=5), raw=True)
    fifteen = _nearest_glucose(context, timestamp - timedelta(minutes=15), raw=True)
    thirty = _nearest_glucose(context, timestamp - timedelta(minutes=30), raw=True)
    sixty = _nearest_glucose(context, timestamp - timedelta(minutes=60), raw=True)
    ninety = _nearest_glucose(context, timestamp - timedelta(minutes=90), raw=True)
    if current is None or five is None or fifteen is None or thirty is None:
        raise ValueError("CGM lookback is incomplete")

    recent_start = bisect_left(context.glucose_times, timestamp - timedelta(minutes=30))
    recent_end = bisect_right(context.glucose_times, timestamp)
    if (
        len(
            {
                sample.sensor_session_id
                for sample in context.glucose[recent_start:recent_end]
            }
        )
        > 1
    ):
        raise ValueError("CGM lookback crosses a sensor replacement")
    recent_values = [
        (sample.raw or sample.value)
        for sample in context.glucose[recent_start:recent_end]
    ]
    volatility = float(np.std(recent_values)) if len(recent_values) >= 2 else 0.0
    glucose_range = (
        float(max(recent_values) - min(recent_values))
        if len(recent_values) >= 2
        else 0.0
    )
    recent_60_start = bisect_left(
        context.glucose_times,
        timestamp - timedelta(minutes=60),
    )
    recent_60_values = [
        (sample.raw or sample.value)
        for sample in context.glucose[recent_60_start:recent_end]
    ]
    mean_30 = float(np.mean(recent_values)) if recent_values else current
    mean_60 = float(np.mean(recent_60_values)) if recent_60_values else mean_30
    sixty = sixty if sixty is not None else mean_60
    ninety = ninety if ninety is not None else sixty
    cob, carb_next_30, carb_rate = _carb_kinetics(context, timestamp, known_at=known_at)
    iob, insulin_next_30, insulin_rate = _insulin_kinetics(
        context, timestamp, known_at=known_at
    )

    resting_hr = context.resting_heart_rate.latest(
        timestamp, 36 * 60, known_at=known_at
    )
    resting_hr = resting_hr or context.default_resting_hr
    hr_now = context.heart_rate.latest(timestamp, 15, known_at=known_at)
    observed_hr_mean_30 = context.heart_rate.window_mean(
        timestamp, 30, known_at=known_at
    )
    observed_hr_mean_180 = context.heart_rate.window_mean(
        timestamp, 180, known_at=known_at
    )
    hr_mean_30 = observed_hr_mean_30
    hr_mean_180 = observed_hr_mean_180
    effective_hr = hr_now or hr_mean_30 or hr_mean_180 or resting_hr
    hr_mean_30 = hr_mean_30 or effective_hr
    hr_mean_180 = hr_mean_180 or resting_hr
    active_kcal_60 = context.active_kcal.window_sum(timestamp, 60, known_at=known_at)
    active_kcal_180 = context.active_kcal.window_sum(timestamp, 180, known_at=known_at)
    exercise_minutes = _interval_overlap_minutes(
        context.exercise,
        timestamp - timedelta(minutes=180),
        timestamp,
        known_at=known_at,
    )
    exercise_minutes_60 = _interval_overlap_minutes(
        context.exercise,
        timestamp - timedelta(minutes=60),
        timestamp,
        known_at=known_at,
    )
    asleep = _is_inside(context.sleep, timestamp, known_at=known_at)
    sleep_hours = (
        _interval_overlap_minutes(
            context.sleep,
            timestamp - timedelta(hours=24),
            timestamp,
            known_at=known_at,
        )
        / 60.0
    )
    local = local_wall_time(timestamp)
    hour = local.hour + local.minute / 60.0
    angle = 2 * pi * hour / 24.0

    hr_age = context.heart_rate.minutes_since(timestamp, 24 * 60, known_at=known_at)
    activity_age = context.active_kcal.minutes_since(
        timestamp, 24 * 60, known_at=known_at
    )
    known_sleep = [
        i
        for i in context.sleep
        if (i.available_at or i.end) <= (known_at or timestamp) and i.end <= timestamp
    ]
    sleep_age = (
        min(
            48 * 60.0,
            (timestamp - max(i.end for i in known_sleep)).total_seconds() / 60,
        )
        if known_sleep
        else 48 * 60.0
    )
    coverage = {
        "heart_rate": hr_now is not None or observed_hr_mean_30 is not None,
        "activity": bool(context.active_kcal.window(timestamp, 180, known_at=known_at))
        or exercise_minutes > 0,
        "sleep": sleep_hours > 0,
    }
    coverage["health"] = any(coverage.values())
    return (
        [
            normalized_current,
            current - five,
            current - fifteen,
            current - thirty,
            current - sixty,
            current - ninety,
            volatility,
            glucose_range,
            mean_30,
            mean_60,
            context.carbs.window_sum(timestamp, 30, known_at=known_at),
            context.carbs.window_sum(timestamp, 120, known_at=known_at),
            context.carbs.window_sum(timestamp, 240, known_at=known_at),
            context.insulin.window_sum(timestamp, 60, known_at=known_at),
            context.insulin.window_sum(timestamp, 180, known_at=known_at),
            context.insulin.window_sum(timestamp, 300, known_at=known_at),
            cob,
            carb_next_30,
            carb_rate,
            iob,
            insulin_next_30,
            insulin_rate,
            context.carbs.minutes_since(timestamp, 480, known_at=known_at),
            context.insulin.minutes_since(timestamp, 480, known_at=known_at),
            effective_hr,
            effective_hr - resting_hr,
            hr_mean_30,
            hr_mean_180,
            active_kcal_60,
            active_kcal_180,
            exercise_minutes_60,
            exercise_minutes,
            1.0 if asleep else 0.0,
            sleep_hours,
            sin(angle),
            cos(angle),
            _sensor_age_at(context, timestamp),
            float(coverage["heart_rate"]),
            hr_age,
            float(coverage["activity"]),
            activity_age,
            float(coverage["sleep"]),
            sleep_age,
        ],
        coverage,
    )


def _sensor_age_at(context: _FeatureContext, timestamp: datetime) -> float:
    """Return sensor age in days at a timestamp, 0.0 when unknown.

    Sensor age is a real regime variable: before a sensor has stable fingerstick
    coverage its bias is unresolved, and forecasts made then were measurably
    worse than persistence. Exposing it lets the model separate those windows
    instead of averaging them into the rest of the history.
    """
    index = bisect_right(context.glucose_times, timestamp) - 1
    if index < 0:
        index = 0
    age = context.glucose[index].sensor_age_days
    return float(age) if age is not None else 0.0


def _prediction_inputs(
    context: _FeatureContext,
    timestamp: datetime,
    *,
    known_at: datetime | None = None,
) -> GlucosePredictionInputs:
    resting = context.resting_heart_rate.latest(timestamp, 36 * 60, known_at=known_at)
    resting = resting or context.default_resting_hr
    heart_rate = context.heart_rate.latest(timestamp, 15, known_at=known_at)
    if heart_rate is None:
        heart_rate = context.heart_rate.window_mean(timestamp, 30, known_at=known_at)
    cob, carb_next_30, _ = _carb_kinetics(context, timestamp, known_at=known_at)
    iob, insulin_next_30, _ = _insulin_kinetics(context, timestamp, known_at=known_at)
    return GlucosePredictionInputs(
        carbs_g_4h=round(
            context.carbs.window_sum(timestamp, 240, known_at=known_at), 1
        ),
        cob_remaining_g=round(cob, 1),
        carb_absorption_next_30m_g=round(carb_next_30, 1),
        insulin_units_5h=round(
            context.insulin.window_sum(timestamp, 300, known_at=known_at), 2
        ),
        iob_remaining_units=round(iob, 2),
        insulin_action_next_30m_units=round(insulin_next_30, 2),
        heart_rate_bpm=round(heart_rate, 1) if heart_rate is not None else None,
        resting_heart_rate_bpm=round(resting, 1),
        active_kcal_3h=round(
            context.active_kcal.window_sum(timestamp, 180, known_at=known_at), 1
        ),
        exercise_minutes_3h=round(
            _interval_overlap_minutes(
                context.exercise,
                timestamp - timedelta(minutes=180),
                timestamp,
                known_at=known_at,
            ),
            1,
        ),
        asleep=_is_inside(context.sleep, timestamp, known_at=known_at),
        sleep_hours_24h=round(
            _interval_overlap_minutes(
                context.sleep,
                timestamp - timedelta(hours=24),
                timestamp,
                known_at=known_at,
            )
            / 60.0,
            2,
        ),
    )


def _carb_kinetics(
    context: _FeatureContext,
    timestamp: datetime,
    *,
    known_at: datetime | None = None,
) -> tuple[float, float, float]:
    remaining = 0.0
    absorbed_next_30 = 0.0
    activity_rate = 0.0
    for event in reversed(context.carb_events):
        if event.available_at is not None and event.available_at > (
            known_at or timestamp
        ):
            continue
        elapsed = (timestamp - event.timestamp).total_seconds() / 60.0
        if elapsed < 0:
            continue
        if elapsed > 420:
            break
        fraction_now = carb_mixture_cob_remaining_fraction(
            elapsed,
            weights=event.weights,
            normal_duration_minutes=240,
        )
        fraction_later = carb_mixture_cob_remaining_fraction(
            elapsed + 30,
            weights=event.weights,
            normal_duration_minutes=240,
        )
        remaining += event.grams * fraction_now
        absorbed_next_30 += event.grams * max(0.0, fraction_now - fraction_later)
        activity_rate += event.grams * carb_mixture_activity_rate(
            elapsed,
            weights=event.weights,
            normal_duration_minutes=240,
        )
    return remaining, absorbed_next_30, activity_rate


def _insulin_kinetics(
    context: _FeatureContext,
    timestamp: datetime,
    *,
    known_at: datetime | None = None,
) -> tuple[float, float, float]:
    remaining = 0.0
    action_next_30 = 0.0
    activity_rate = 0.0
    horizon = context.insulin_kernel.horizon_minutes
    for event in reversed(context.insulin_events):
        if event.available_at is not None and event.available_at > (
            known_at or timestamp
        ):
            continue
        elapsed = (timestamp - event.timestamp).total_seconds() / 60.0
        if elapsed < 0:
            continue
        if elapsed > horizon:
            break
        fraction_now = personalized_insulin_iob_remaining_fraction(
            elapsed,
            context.insulin_kernel,
        )
        fraction_later = personalized_insulin_iob_remaining_fraction(
            elapsed + 30,
            context.insulin_kernel,
        )
        remaining += event.units * fraction_now
        action_next_30 += event.units * max(0.0, fraction_now - fraction_later)
        activity_rate += event.units * personalized_insulin_activity_rate(
            elapsed,
            context.insulin_kernel,
        )
    return remaining, action_next_30, activity_rate


def _health_series(
    records: list[HealthConnectRecord],
) -> tuple[_Series, _Series, _Series, list[_Interval], list[_Interval]]:
    heart_rate: list[tuple[datetime, float]] = []
    resting_hr: list[tuple[datetime, float]] = []
    active_kcal: list[tuple[datetime, float]] = []
    exercise: list[_Interval] = []
    sleep: list[_Interval] = []
    availability = {
        kind: {}
        for kind in (
            "HeartRateRecord",
            "RestingHeartRateRecord",
            "ActiveCaloriesBurnedRecord",
        )
    }
    for record in records:
        available = getattr(record, "updated_at", None) or getattr(
            record, "created_at", None
        )
        available = _as_utc(available) if available else None
        observation_availability = availability.get(record.record_type, {})
        payload = record.payload or {}
        if record.record_type == "HeartRateRecord":
            for sample in payload.get("samples") or []:
                timestamp = _payload_datetime(sample.get("time"))
                bpm = _number(sample.get("beatsPerMinute"))
                if timestamp is not None and bpm is not None and 25 <= bpm <= 240:
                    heart_rate.append((timestamp, bpm))
                    observation_availability[timestamp] = max(
                        observation_availability.get(timestamp, timestamp),
                        available or timestamp,
                    )
        elif record.record_type == "RestingHeartRateRecord":
            timestamp = _payload_datetime(payload.get("time"))
            bpm = _number(payload.get("beatsPerMinute"))
            if timestamp is not None and bpm is not None and 25 <= bpm <= 160:
                resting_hr.append((timestamp, bpm))
                observation_availability[timestamp] = max(
                    observation_availability.get(timestamp, timestamp),
                    available or timestamp,
                )
        elif record.record_type == "ActiveCaloriesBurnedRecord":
            timestamp = _payload_datetime(payload.get("endTime"))
            energy = payload.get("energy") or {}
            kcal = _number(energy.get("kilocalories"))
            if timestamp is not None and kcal is not None and 0 <= kcal <= 5000:
                active_kcal.append((timestamp, kcal))
                observation_availability[timestamp] = max(
                    observation_availability.get(timestamp, timestamp),
                    available or timestamp,
                )
        elif record.record_type == "ExerciseSessionRecord":
            interval = _payload_interval(payload)
            if interval is not None:
                exercise.append(
                    _Interval(interval.start, interval.end, available or interval.end)
                )
        elif record.record_type == "SleepSessionRecord":
            interval = _payload_interval(payload)
            if interval is not None:
                sleep.append(
                    _Interval(interval.start, interval.end, available or interval.end)
                )
    return (
        _Series(heart_rate, availability=availability["HeartRateRecord"]),
        _Series(resting_hr, availability=availability["RestingHeartRateRecord"]),
        _Series(active_kcal, availability=availability["ActiveCaloriesBurnedRecord"]),
        sorted(exercise, key=lambda i: i.start),
        sorted(sleep, key=lambda i: i.start),
    )


def _known_input_effects(
    context: _FeatureContext,
    x: np.ndarray,
    row_times: list[datetime],
    horizons: list[int],
    *,
    known_at: datetime | None = None,
) -> _KnownInputEffects:
    """Calculate effects only from food and insulin known at each anchor."""
    momentum_slope = (
        0.65 * x[:, FEATURE_NAMES.index("glucose_delta_5m")] / 5
        + 0.35 * x[:, FEATURE_NAMES.index("glucose_delta_15m")] / 15
    )
    absorbed_carbs = np.zeros((len(x), len(horizons)), dtype=np.float64)
    delivered_insulin = np.zeros((len(x), len(horizons)), dtype=np.float64)
    insulin_horizon = context.insulin_kernel.horizon_minutes

    for row_index, timestamp in enumerate(row_times):
        known_carbs: list[tuple[_CarbEvent, float]] = []
        for event in reversed(context.carb_events):
            if event.available_at is not None and event.available_at > (
                known_at or timestamp
            ):
                continue
            elapsed = (timestamp - event.timestamp).total_seconds() / 60.0
            if elapsed < 0:
                continue
            if elapsed > 420:
                break
            known_carbs.append((event, elapsed))

        known_insulin: list[tuple[_InsulinDose, float]] = []
        for event in reversed(context.insulin_events):
            if event.available_at is not None and event.available_at > (
                known_at or timestamp
            ):
                continue
            elapsed = (timestamp - event.timestamp).total_seconds() / 60.0
            if elapsed < 0:
                continue
            if elapsed > insulin_horizon:
                break
            known_insulin.append((event, elapsed))

        for horizon_index, horizon in enumerate(horizons):
            for event, elapsed in known_carbs:
                remaining_now = carb_mixture_cob_remaining_fraction(
                    elapsed,
                    weights=event.weights,
                    normal_duration_minutes=240,
                )
                remaining_later = carb_mixture_cob_remaining_fraction(
                    elapsed + horizon,
                    weights=event.weights,
                    normal_duration_minutes=240,
                )
                absorbed_carbs[row_index, horizon_index] += event.grams * max(
                    0.0,
                    remaining_now - remaining_later,
                )
            for event, elapsed in known_insulin:
                remaining_now = personalized_insulin_iob_remaining_fraction(
                    elapsed,
                    context.insulin_kernel,
                )
                remaining_later = personalized_insulin_iob_remaining_fraction(
                    elapsed + horizon,
                    context.insulin_kernel,
                )
                delivered_insulin[row_index, horizon_index] += event.units * max(
                    0.0,
                    remaining_now - remaining_later,
                )

    return _KnownInputEffects(
        momentum_slope=momentum_slope,
        absorbed_carbs=absorbed_carbs,
        delivered_insulin=delivered_insulin,
    )


def _scenario_design(
    effects: _KnownInputEffects,
    horizons: list[int],
    tau_minutes: float,
) -> np.ndarray:
    momentum = np.column_stack(
        [
            effects.momentum_slope
            * tau_minutes
            * (1.0 - np.exp(-horizon / tau_minutes))
            for horizon in horizons
        ]
    )
    return np.stack(
        [momentum, effects.absorbed_carbs, effects.delivered_insulin],
        axis=2,
    )


def _huber_score(residual: np.ndarray, delta: float = HUBER_DELTA_MMOL) -> float:
    """Return mean Huber loss: quadratic within ``delta``, linear beyond it.

    Selecting on mean absolute error drives every estimate to the conditional
    median, which on a mostly-flat CGM is a near-flat forecast. Huber keeps the
    quadratic pull toward the conditional mean for ordinary excursions and only
    degrades to L1 for outliers such as compression lows and sensor jumps.
    """
    magnitude = np.abs(residual)
    quadratic = np.minimum(magnitude, delta)
    linear = magnitude - quadratic
    return float(np.mean(0.5 * quadratic**2 + delta * linear))


def _fit_scenario_coefficients(
    design: np.ndarray,
    targets: np.ndarray,
    eligibility: np.ndarray,
) -> np.ndarray:
    """Fit sign-constrained personal effects using a small robust grid."""
    coefficients = np.zeros((targets.shape[1], 3), dtype=np.float64)
    for horizon_index in range(targets.shape[1]):
        use = eligibility[:, horizon_index]
        values = design[use, horizon_index]
        actual = targets[use, horizon_index]
        best_score: float | None = None
        best_coefficients: tuple[float, float, float] | None = None
        for momentum_weight in SCENARIO_MOMENTUM_WEIGHTS:
            for carb_weight in SCENARIO_CARB_WEIGHTS:
                for insulin_weight in SCENARIO_INSULIN_WEIGHTS:
                    estimate = (
                        momentum_weight * values[:, 0]
                        + carb_weight * values[:, 1]
                        - insulin_weight * values[:, 2]
                    )
                    score = _huber_score(estimate - actual)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_coefficients = (
                            float(momentum_weight),
                            float(carb_weight),
                            float(insulin_weight),
                        )
        assert best_coefficients is not None
        coefficients[horizon_index] = best_coefficients
    return coefficients


def _predict_known_input_scenario(
    design: np.ndarray,
    coefficients: np.ndarray,
) -> np.ndarray:
    # Smoothing happens once, in the blend. Applying it here as well damped the
    # kinetic branch twice and flattened exactly the excursions worth showing.
    return (
        design[:, :, 0] * coefficients[:, 0]
        + design[:, :, 1] * coefficients[:, 1]
        - design[:, :, 2] * coefficients[:, 2]
    )


def _shape_features(x: np.ndarray) -> np.ndarray:
    """Return dynamic context without an absolute glucose-level feature."""
    return x[:, [FEATURE_NAMES.index(name) for name in SHAPE_FEATURE_NAMES]]


def _shape_horizon_features(
    shape_x: np.ndarray,
    scenario_design: np.ndarray,
    horizon_index: int,
) -> np.ndarray:
    return np.column_stack(
        [shape_x, scenario_design[:, horizon_index, :]],
    )


def _fit_shape_models(
    shape_x: np.ndarray,
    scenario_design: np.ndarray,
    targets: np.ndarray,
    eligibility: np.ndarray,
) -> _TreeFit:
    """Learn no-intervention curve shape without glucose-level mean reversion."""
    import lightgbm as lgb

    boosters: list[Any] = []
    for horizon_index in range(targets.shape[1]):
        use = eligibility[:, horizon_index]
        features = _shape_horizon_features(
            shape_x,
            scenario_design,
            horizon_index,
        )
        dataset = lgb.Dataset(
            features[use],
            label=targets[use, horizon_index],
            free_raw_data=True,
        )
        boosters.append(
            lgb.train(
                SHAPE_LIGHTGBM_PARAMS,
                dataset,
                num_boost_round=SHAPE_LIGHTGBM_ROUNDS,
            )
        )
    return _TreeFit(boosters)


def _fit_quantile_models(
    shape_x: np.ndarray,
    scenario_design: np.ndarray,
    targets: np.ndarray,
    eligibility: np.ndarray,
) -> _QuantileFit:
    """Learn the lower and upper delta quantiles that bound the forecast."""
    import lightgbm as lgb

    boosters: dict[float, list[Any]] = {}
    for quantile in INTERVAL_QUANTILES:
        params = {**QUANTILE_LIGHTGBM_PARAMS, "alpha": quantile}
        horizon_boosters: list[Any] = []
        for horizon_index in range(targets.shape[1]):
            use = eligibility[:, horizon_index]
            features = _shape_horizon_features(
                shape_x,
                scenario_design,
                horizon_index,
            )
            dataset = lgb.Dataset(
                features[use],
                label=targets[use, horizon_index],
                free_raw_data=True,
            )
            horizon_boosters.append(
                lgb.train(
                    params,
                    dataset,
                    num_boost_round=QUANTILE_LIGHTGBM_ROUNDS,
                )
            )
        boosters[quantile] = horizon_boosters
    return _QuantileFit(boosters)


def _predict_quantile_models(
    fit: _QuantileFit,
    shape_x: np.ndarray,
    scenario_design: np.ndarray,
) -> dict[float, np.ndarray]:
    return {
        quantile: np.column_stack(
            [
                booster.predict(
                    _shape_horizon_features(
                        shape_x,
                        scenario_design,
                        horizon_index,
                    )
                )
                for horizon_index, booster in enumerate(boosters)
            ]
        )
        for quantile, boosters in fit.boosters.items()
    }


def _conformal_interval_scale(
    lower: np.ndarray,
    upper: np.ndarray,
    center: np.ndarray,
    targets: np.ndarray,
    eligibility: np.ndarray,
) -> np.ndarray:
    """Return the per-horizon factor that lifts holdout coverage to nominal.

    Quantile regression alone under-covers on small personal histories. Scaling
    each side by the empirical coverage quantile of the normalized conformity
    score restores the stated level without assuming a residual distribution.
    """
    scales = np.ones(targets.shape[1], dtype=np.float64)
    for index in range(targets.shape[1]):
        use = eligibility[:, index]
        if int(use.sum()) < MIN_CONFORMAL_ROWS:
            continue
        half_low = np.maximum(center[use, index] - lower[use, index], 1e-6)
        half_high = np.maximum(upper[use, index] - center[use, index], 1e-6)
        residual = targets[use, index] - center[use, index]
        # Conformity score: how many half-widths away the outcome landed.
        score = np.where(residual < 0, -residual / half_low, residual / half_high)
        level = min(
            1.0,
            INTERVAL_TARGET_COVERAGE * (1.0 + 1.0 / int(use.sum())),
        )
        scales[index] = max(0.5, min(4.0, float(np.quantile(score, level))))
    return scales


def _predict_shape_models(
    fit: _TreeFit,
    shape_x: np.ndarray,
    scenario_design: np.ndarray,
) -> np.ndarray:
    return np.column_stack(
        [
            booster.predict(
                _shape_horizon_features(
                    shape_x,
                    scenario_design,
                    horizon_index,
                )
            )
            for horizon_index, booster in enumerate(fit.boosters)
        ]
    )


def _blend_scenario_predictions(
    kinetic: np.ndarray,
    shape: np.ndarray,
    shape_weight: float,
) -> np.ndarray:
    return _smooth_forecast_matrix(
        (1.0 - shape_weight) * kinetic + shape_weight * shape
    )


def _select_shape_blend(
    kinetic: np.ndarray,
    shape: np.ndarray,
    targets: np.ndarray,
    eligibility: np.ndarray,
) -> float:
    scores: dict[float, float] = {}
    for weight in SHAPE_BLEND_CANDIDATES:
        predictions = _blend_scenario_predictions(kinetic, shape, weight)
        residual = predictions - targets
        scores[weight] = float(
            np.mean(
                [
                    _huber_score(residual[eligibility[:, index], index])
                    for index in range(residual.shape[1])
                ]
            )
        )
    best_score = min(scores.values())
    tolerance = max(1e-6, best_score * SHAPE_BLEND_SCORE_TOLERANCE)
    return max(
        weight for weight, score in scores.items() if score <= best_score + tolerance
    )


def _select_scenario_tau(
    effects: _KnownInputEffects,
    targets: np.ndarray,
    eligibility: np.ndarray,
    horizons: list[int],
    train_end: int,
    calibration_end: int,
) -> float:
    best_score: float | None = None
    best_tau = SCENARIO_TAU_CANDIDATES[0]
    for tau_minutes in SCENARIO_TAU_CANDIDATES:
        design = _scenario_design(effects, horizons, tau_minutes)
        coefficients = _fit_scenario_coefficients(
            design[:train_end],
            targets[:train_end],
            eligibility[:train_end],
        )
        predictions = _predict_known_input_scenario(
            design[train_end:calibration_end],
            coefficients,
        )
        residual = predictions - targets[train_end:calibration_end]
        window = eligibility[train_end:calibration_end]
        score = float(
            np.mean(
                [
                    _huber_score(residual[window[:, index], index])
                    for index in range(residual.shape[1])
                ]
            )
        )
        if best_score is None or score < best_score:
            best_score = score
            best_tau = tau_minutes
    return best_tau


def _masked_mean_by_horizon(
    values: np.ndarray,
    eligibility: np.ndarray,
) -> np.ndarray:
    return np.asarray(
        [
            float(np.mean(values[eligibility[:, index], index]))
            for index in range(values.shape[1])
        ],
        dtype=np.float64,
    )


def _interval_half_widths(
    lower_delta: np.ndarray,
    upper_delta: np.ndarray,
    center_delta: np.ndarray,
    conformal_scale: np.ndarray,
    *,
    minimum: float = MIN_CI_HALF_WIDTH_MMOL,
) -> tuple[np.ndarray, np.ndarray]:
    """Return conformalized lower/upper half-widths around the central forecast.

    The band is deliberately asymmetric: a rise driven by absorbing carbs and a
    fall driven by active insulin do not carry the same uncertainty, and a
    symmetric half-width had to cover the worse side on both.
    """
    half_low = np.maximum(center_delta - lower_delta, minimum) * conformal_scale
    half_high = np.maximum(upper_delta - center_delta, minimum) * conformal_scale
    return (
        np.maximum(half_low, minimum),
        np.maximum(half_high, minimum),
    )


def _purge_overlapping_targets(
    row_times: list[datetime],
    horizons: list[int],
    eligibility: np.ndarray,
    boundaries: tuple[int, ...],
) -> np.ndarray:
    result = eligibility.copy()
    for boundary in boundaries:
        cutoff = row_times[boundary]
        for row in range(boundary - 1, -1, -1):
            at = row_times[row]
            if (
                at + timedelta(minutes=max(horizons), seconds=MAX_CGM_MATCH_SECONDS)
                < cutoff
            ):
                break
            for column, horizon in enumerate(horizons):
                if (
                    at + timedelta(minutes=horizon, seconds=MAX_CGM_MATCH_SECONDS)
                    >= cutoff
                ):
                    result[row, column] = False
    return result


def _chronological_day_splits(row_times: list[datetime]) -> tuple[int, int]:
    days = sorted({local_wall_time(timestamp).date() for timestamp in row_times})
    evaluation_days = max(3, ceil(len(days) * 0.2))
    if len(days) >= evaluation_days * 2 + 1:
        calibration_day = days[-2 * evaluation_days]
        test_day = days[-evaluation_days]
        train_end = next(
            index
            for index, timestamp in enumerate(row_times)
            if local_wall_time(timestamp).date() >= calibration_day
        )
        calibration_end = next(
            index
            for index, timestamp in enumerate(row_times)
            if local_wall_time(timestamp).date() >= test_day
        )
        if (
            train_end >= MIN_TRAINING_ROWS
            and calibration_end - train_end >= MIN_VALIDATION_ROWS
            and len(row_times) - calibration_end >= MIN_TEST_ROWS
        ):
            return train_end, calibration_end

    train_end = max(MIN_TRAINING_ROWS, int(len(row_times) * 0.6))
    calibration_end = max(
        train_end + MIN_VALIDATION_ROWS,
        int(len(row_times) * 0.8),
    )
    calibration_end = min(calibration_end, len(row_times) - MIN_TEST_ROWS)
    return train_end, calibration_end


def _nearest_glucose(
    context: _FeatureContext,
    timestamp: datetime,
    *,
    raw: bool = False,
) -> float | None:
    index = bisect_left(context.glucose_times, timestamp)
    candidates = []
    if index < len(context.glucose):
        candidates.append(context.glucose[index])
    if index > 0:
        candidates.append(context.glucose[index - 1])
    if not candidates:
        return None
    nearest = min(
        candidates,
        key=lambda sample: abs((sample.timestamp - timestamp).total_seconds()),
    )
    if abs((nearest.timestamp - timestamp).total_seconds()) > MAX_CGM_MATCH_SECONDS:
        return None
    return (nearest.raw or nearest.value) if raw else nearest.value


def _model_confidence(
    *,
    sample_count: int,
    day_count: int,
    validation_mae: float,
    baseline_mae: float,
) -> Literal["low", "medium", "high"]:
    improvement = 1.0 - validation_mae / max(baseline_mae, 0.05)
    if (
        sample_count >= 1200
        and day_count >= 14
        and validation_mae <= 1.5
        and improvement >= 0.08
    ):
        return "high"
    if (
        sample_count >= 500
        and day_count >= 7
        and validation_mae <= 2.2
        and improvement >= 0.02
    ):
        return "medium"
    return "low"


def _smooth_forecast(values: np.ndarray) -> np.ndarray:
    if len(values) < 3:
        return values.copy()
    result = values.copy()
    for index in range(1, len(values) - 1):
        result[index] = (
            values[index - 1] + 2 * values[index] + values[index + 1]
        ) / 4.0
    return result


def _smooth_forecast_matrix(values: np.ndarray) -> np.ndarray:
    return np.vstack([_smooth_forecast(row) for row in values])


def _critical_validation_metrics(
    x: np.ndarray,
    targets: np.ndarray,
    predictions: np.ndarray,
    eligibility: np.ndarray | None = None,
) -> dict[str, Any]:
    if eligibility is None:
        eligibility = np.ones(targets.shape, dtype=bool)
    actual = x[:, 0] + targets[:, -1]
    predicted = x[:, 0] + predictions[:, -1]

    def metrics(
        mask: np.ndarray,
        *,
        low: bool,
    ) -> tuple[int, float | None, float | None]:
        count = int(mask.sum())
        if count == 0:
            return 0, None, None
        mae = float(np.mean(np.abs(predictions[mask, -1] - targets[mask, -1])))
        misses = predicted[mask] >= 3.9 if low else predicted[mask] <= 10.0
        return count, round(mae, 3), round(float(np.mean(misses) * 100), 1)

    eligible = eligibility[:, -1]
    low_count, low_mae, low_miss = metrics(
        eligible & (actual < 3.9),
        low=True,
    )
    high_count, high_mae, high_miss = metrics(
        eligible & (actual > 10.0),
        low=False,
    )
    return {
        "low_count": low_count,
        "low_mae": low_mae,
        "low_miss_pct": low_miss,
        "high_count": high_count,
        "high_mae": high_mae,
        "high_miss_pct": high_miss,
    }


def _post_meal_validation_metrics(
    x: np.ndarray,
    targets: np.ndarray,
    predictions: np.ndarray,
    eligibility: np.ndarray | None = None,
) -> dict[str, int | float | None]:
    """Measure holdout error where carbs were recorded in the prior two hours."""
    if eligibility is None:
        eligibility = np.ones(targets.shape, dtype=bool)
    post_meal = x[:, FEATURE_NAMES.index("carbs_120m")] > 0
    count = int((post_meal & eligibility[:, -1]).sum())
    if count == 0:
        return {
            "count": 0,
            "mae_30": None,
            "mae_60": None,
            "mae_90": None,
            "baseline_mae_90": None,
        }

    def mae_at(minutes: int) -> float:
        index = minutes // 5 - 1
        mask = post_meal & eligibility[:, index]
        return round(
            float(np.mean(np.abs(predictions[mask, index] - targets[mask, index]))),
            3,
        )

    return {
        "count": count,
        "mae_30": mae_at(30),
        "mae_60": mae_at(60),
        "mae_90": mae_at(90),
        "baseline_mae_90": round(
            float(np.mean(np.abs(targets[post_meal & eligibility[:, -1], -1]))),
            3,
        ),
    }


def _payload_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _payload_interval(payload: dict[str, Any]) -> _Interval | None:
    start = _payload_datetime(payload.get("startTime"))
    end = _payload_datetime(payload.get("endTime"))
    if start is None or end is None or end <= start:
        return None
    if end - start > timedelta(hours=24):
        return None
    return _Interval(start, end)


def _merge_intervals(intervals: list[_Interval]) -> list[_Interval]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: item.start)
    merged = [ordered[0]]
    for interval in ordered[1:]:
        previous = merged[-1]
        if interval.start <= previous.end:
            merged[-1] = _Interval(previous.start, max(previous.end, interval.end))
        else:
            merged.append(interval)
    return merged


def _interval_overlap_minutes(
    intervals: list[_Interval],
    start: datetime,
    end: datetime,
    *,
    known_at: datetime | None = None,
) -> float:
    intervals = _merge_intervals(
        [
            i
            for i in intervals
            if i.available_at is None or i.available_at <= (known_at or end)
        ]
    )
    start = _as_utc(start)
    end = _as_utc(end)
    seconds = 0.0
    for interval in intervals:
        if interval.end <= start:
            continue
        if interval.start >= end:
            break
        seconds += max(
            0.0,
            (min(interval.end, end) - max(interval.start, start)).total_seconds(),
        )
    return seconds / 60.0


def _is_inside(
    intervals: list[_Interval], timestamp: datetime, *, known_at: datetime | None = None
) -> bool:
    timestamp = _as_utc(timestamp)
    return any(
        interval.start <= timestamp <= interval.end
        and (
            interval.available_at is None
            or interval.available_at <= (known_at or timestamp)
        )
        for interval in intervals
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _clamp_glucose(value: float) -> float:
    return max(2.0, min(22.0, value))


def _glucose_band(value: float) -> Literal["low", "in_range", "high"]:
    if value < 3.9:
        return "low"
    if value > 10.0:
        return "high"
    return "in_range"
