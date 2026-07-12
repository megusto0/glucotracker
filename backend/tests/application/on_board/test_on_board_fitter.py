"""Focused synthetic tests for retrospective IOB/COB timing fits."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest

from glucotracker.application.on_board import fitter as fitter_module
from glucotracker.application.on_board.fitter import (
    CgmSample,
    CobTimingOverride,
    FitterConfig,
    MealEvent,
    OnBoardTimingModel,
    RapidInsulinEvent,
    RetrospectiveDay,
    fit_on_board_timing,
)
from glucotracker.application.twin.kernels import (
    POPULATION_INSULIN_KERNEL_V2,
    CarbProfileWeights,
    PersonalizedInsulinKernel,
    blend_carb_profile_weights,
    carb_mixture_cumulative_absorbed,
    personalized_insulin_cumulative_absorbed,
)

_PRIOR = CarbProfileWeights(0.2, 0.6, 0.2)
_PERSONAL = PersonalizedInsulinKernel(0.5, 15.0, 70.0)


def _delivered_insulin(
    start: datetime,
    end: datetime,
    event: RapidInsulinEvent,
    kernel: PersonalizedInsulinKernel,
) -> float:
    elapsed_start = max(0.0, (start - event.timestamp).total_seconds() / 60.0)
    elapsed_end = (end - event.timestamp).total_seconds() / 60.0
    return max(
        0.0,
        personalized_insulin_cumulative_absorbed(elapsed_end, kernel)
        - personalized_insulin_cumulative_absorbed(elapsed_start, kernel),
    )


def _delivered_carbs(
    start: datetime,
    end: datetime,
    meal: MealEvent,
    weights: CarbProfileWeights,
) -> float:
    elapsed_start = max(0.0, (start - meal.timestamp).total_seconds() / 60.0)
    elapsed_end = (end - meal.timestamp).total_seconds() / 60.0
    return max(
        0.0,
        carb_mixture_cumulative_absorbed(elapsed_end, weights=weights)
        - carb_mixture_cumulative_absorbed(elapsed_start, weights=weights),
    )


def _iob_days(
    kernel_for_day: Callable[[int], PersonalizedInsulinKernel],
) -> tuple[RetrospectiveDay, ...]:
    days: list[RetrospectiveDay] = []
    for day_index in range(10):
        day_start = datetime(2026, 1, 1) + timedelta(days=day_index)
        insulin = tuple(
            RapidInsulinEvent(
                day_start + timedelta(hours=hour, minutes=(day_index % 3) * 5),
                3.0 + event_index % 2,
            )
            for event_index, hour in enumerate((2, 8, 14, 20))
        )
        meals = tuple(
            MealEvent(
                day_start + timedelta(hours=hour, minutes=(day_index % 2) * 5),
                45.0,
                _PRIOR,
            )
            for hour in (5, 11, 17)
        )
        values = [20.0]
        kernel = kernel_for_day(day_index)
        for index in range(95):
            start = day_start + timedelta(minutes=index * 15 + 7.5)
            end = start + timedelta(minutes=15)
            insulin_activity = -sum(
                event.units * _delivered_insulin(start, end, event, kernel)
                for event in insulin
            )
            meal_activity = sum(
                meal.carbs_g * _delivered_carbs(start, end, meal, _PRIOR)
                for meal in meals
            )
            deterministic_noise = ((index * 13 + day_index * 7) % 11 - 5) * 0.003
            values.append(
                values[-1]
                + 3.0 * insulin_activity
                + 0.25 * meal_activity
                + deterministic_noise
            )
        cgm = tuple(
            CgmSample(day_start + timedelta(minutes=index * 15), value)
            for index, value in enumerate(values)
        )
        days.append(RetrospectiveDay(day_start, cgm, insulin, meals))
    return tuple(days)


def _iob_config() -> FitterConfig:
    return FitterConfig(
        min_meal_events=999,
        fast_weight_candidates=(0.21, 0.5),
        fast_tau_candidates=(15.0, 24.0),
        slow_tau_candidates=(70.0, 158.0),
        insulin_horizon_candidates=(390.0,),
        iob_prior_penalty=0.0001,
    )


def test_large_iob_grid_full_scores_only_screened_finalists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = FitterConfig(
        min_meal_events=999,
        robust_iterations=4,
        iob_screening_robust_iterations=1,
        iob_screening_max_observations=64,
        iob_full_evaluation_limit=3,
        fast_weight_candidates=(0.10, 0.20, 0.35, 0.50),
        fast_tau_candidates=(15.0, 25.0, 45.0),
        slow_tau_candidates=(70.0, 110.0),
        insulin_horizon_candidates=(330.0, 390.0),
    )
    original = fitter_module._training_score
    full_calls = 0
    screening_calls = 0

    def counting_score(
        rows: tuple[fitter_module._RegressionRow, ...],
        settings: FitterConfig,
    ) -> float:
        nonlocal full_calls, screening_calls
        if settings.robust_iterations == config.robust_iterations:
            full_calls += 1
        else:
            screening_calls += 1
        return original(rows, settings)

    monkeypatch.setattr(fitter_module, "_training_score", counting_score)

    fit_on_board_timing(_iob_days(lambda _: _PERSONAL), config=config)

    assert screening_calls > config.iob_full_evaluation_limit
    assert full_calls <= 1 + config.iob_full_evaluation_limit


def test_sparse_or_incomplete_days_preserve_the_exact_fallback() -> None:
    day_start = datetime(2026, 3, 1)
    incomplete = RetrospectiveDay(
        day_start,
        (
            CgmSample(day_start, 6.0),
            CgmSample(day_start + timedelta(hours=23), 7.0),
        ),
    )
    fallback = OnBoardTimingModel(
        insulin_kernel=PersonalizedInsulinKernel(0.3, 30.0, 100.0),
        cob_overrides=(
            CobTimingOverride(
                "category",
                "category:normal:solid",
                CarbProfileWeights(0.1, 0.8, 0.1),
                event_count=9,
                day_count=6,
                learned_weight=0.3,
            ),
        ),
    )

    result = fit_on_board_timing((incomplete,), fallback=fallback)

    assert result.status == "insufficient_data"
    assert result.model == fallback
    assert result.candidate_model is None
    assert dict(result.metrics.excluded_reasons) == {"cgm_gap_too_large": 1}


def test_replacement_set_prunes_cob_scopes_without_current_evidence() -> None:
    keep = CobTimingOverride(
        "category",
        "category:normal:solid",
        CarbProfileWeights(0.1, 0.8, 0.1),
        event_count=12,
        day_count=7,
        learned_weight=0.3,
    )
    stale = CobTimingOverride(
        "exact",
        "pattern:stale-private-hash",
        CarbProfileWeights(0.1, 0.2, 0.7),
        event_count=5,
        day_count=3,
        learned_weight=0.4,
    )
    model = OnBoardTimingModel(
        insulin_kernel=None,
        legacy_dia_minutes=300,
        normal_carb_duration_minutes=210,
        cob_overrides=(keep, stale),
    )

    replacement = fitter_module._retain_eligible_cob_overrides(
        model,
        category_keys=(keep.scope_key,),
        exact_keys=(),
    )

    assert replacement.cob_overrides == (keep,)
    assert replacement.insulin_kernel is None
    assert replacement.legacy_dia_minutes == 300
    assert replacement.normal_carb_duration_minutes == 210


def test_personal_iob_is_selected_on_training_and_accepted_once_on_holdout() -> None:
    result = fit_on_board_timing(
        _iob_days(lambda _index: _PERSONAL),
        config=_iob_config(),
    )

    assert result.status == "accepted"
    assert result.model.insulin_kernel == _PERSONAL
    assert result.metrics.mae_improvement_mmol is not None
    assert result.metrics.mae_improvement_mmol >= 0.10
    assert result.metrics.mae_improvement_fraction is not None
    assert result.metrics.mae_improvement_fraction >= 0.05
    assert set(result.metrics.training_day_starts).isdisjoint(
        result.metrics.holdout_day_starts
    )
    assert max(result.metrics.training_day_starts) < min(
        result.metrics.holdout_day_starts
    )
    assert result.to_mapping()["model"]["insulin_kernel"] == {
        "fast_weight": 0.5,
        "fast_tau_minutes": 15.0,
        "slow_tau_minutes": 70.0,
        "horizon_minutes": 390.0,
    }


def test_chronological_regime_shift_rejects_training_winner_and_keeps_fallback() -> (
    None
):
    days = _iob_days(
        lambda index: _PERSONAL if index < 7 else POPULATION_INSULIN_KERNEL_V2
    )

    result = fit_on_board_timing(days, config=_iob_config())

    assert result.status == "rejected"
    assert result.model.insulin_kernel == POPULATION_INSULIN_KERNEL_V2
    assert result.candidate_model is not None
    assert result.candidate_model.insulin_kernel == _PERSONAL
    assert result.metrics.baseline is not None
    assert result.metrics.candidate is not None
    assert result.metrics.candidate.mae_mmol > result.metrics.baseline.mae_mmol


def test_soft_exact_and_category_cob_candidates_are_shrunken_and_serializable() -> None:
    exact_true = blend_carb_profile_weights(
        _PRIOR,
        CarbProfileWeights(0.0, 0.0, 1.0),
        learned_weight=0.4,
    )
    category_true = blend_carb_profile_weights(
        _PRIOR,
        CarbProfileWeights(1.0, 0.0, 0.0),
        learned_weight=1.0 / 3.0,
    )
    days: list[RetrospectiveDay] = []
    for day_index in range(12):
        day_start = datetime(2026, 2, 1) + timedelta(days=day_index)
        exact_meal = MealEvent(
            day_start + timedelta(hours=3, minutes=(day_index % 3) * 5),
            50.0,
            _PRIOR,
            exact_key="private-pattern-hash",
        )
        category_meal = MealEvent(
            day_start + timedelta(hours=13, minutes=(day_index % 2) * 5),
            50.0,
            _PRIOR,
            category_key="category:fast:liquid",
        )
        values = [7.0]
        for index in range(95):
            start = day_start + timedelta(minutes=index * 15 + 7.5)
            end = start + timedelta(minutes=15)
            activity = exact_meal.carbs_g * _delivered_carbs(
                start, end, exact_meal, exact_true
            ) + category_meal.carbs_g * _delivered_carbs(
                start, end, category_meal, category_true
            )
            values.append(values[-1] + 0.7 * activity - 0.02)
        cgm = tuple(
            CgmSample(day_start + timedelta(minutes=index * 15), value)
            for index, value in enumerate(values)
        )
        days.append(
            RetrospectiveDay(
                day_start,
                cgm,
                meals=(exact_meal, category_meal),
            )
        )

    result = fit_on_board_timing(
        tuple(days),
        config=FitterConfig(
            fast_weight_candidates=(0.17,),
            fast_tau_candidates=(21.0,),
            slow_tau_candidates=(99.0,),
        ),
    )

    assert result.status == "accepted"
    overrides = {
        (item.scope, item.scope_key): item for item in result.model.cob_overrides
    }
    exact = overrides[("exact", "private-pattern-hash")]
    category = overrides[("category", "category:fast:liquid")]
    assert 0.0 < exact.learned_weight <= 0.55
    assert 0.0 < category.learned_weight <= 0.40
    assert _PRIOR.slow < exact.weights.slow < 1.0
    assert _PRIOR.fast < category.weights.fast < 1.0
    serialized = result.to_mapping()["model"]["cob_overrides"]
    assert {item["scope"] for item in serialized} == {"exact", "category"}
    assert all("learned_weight" in item for item in serialized)


def test_fit_config_rejects_non_fifteen_divisible_grids() -> None:
    with pytest.raises(ValueError, match="divisible"):
        FitterConfig(bin_minutes=17)
