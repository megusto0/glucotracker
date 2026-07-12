"""Focused tests for personalized IOB and soft-mixture COB kernels."""

from __future__ import annotations

from itertools import pairwise

import pytest

from glucotracker.application.twin.kernels import (
    POPULATION_INSULIN_KERNEL_V2,
    CarbProfileWeights,
    PersonalizedInsulinKernel,
    blend_carb_profile_weights,
    carb_cob_remaining_fraction,
    carb_effect_for_meal,
    carb_mixture_cob_remaining_fraction,
    carb_mixture_cumulative_absorbed,
    carb_mixture_minutes_remaining,
    carb_profile_prior_weights,
    insulin_iob_remaining_fraction,
    personalized_insulin_activity_rate,
    personalized_insulin_cumulative_absorbed,
    personalized_insulin_iob_remaining_fraction,
    personalized_insulin_minutes_remaining,
)


def test_kernel_parameter_mappings_round_trip_and_validate() -> None:
    insulin = PersonalizedInsulinKernel.from_mapping(
        {
            "fast_weight": 0.25,
            "fast_tau_minutes": 35,
            "slow_tau_minutes": 110,
        }
    )
    assert PersonalizedInsulinKernel.from_mapping(insulin.to_mapping()) == insulin

    weights = CarbProfileWeights.from_mapping({"fast": 1, "normal": 2, "slow": 1})
    assert weights == CarbProfileWeights(fast=0.25, normal=0.5, slow=0.25)
    assert CarbProfileWeights.from_mapping(weights.to_mapping()) == weights

    with pytest.raises(ValueError):
        PersonalizedInsulinKernel(0.5, 120, 60)
    with pytest.raises(ValueError):
        PersonalizedInsulinKernel.from_mapping({"fast_weight": 0.5})
    with pytest.raises(ValueError):
        CarbProfileWeights(0, 0, 0)
    with pytest.raises(ValueError):
        CarbProfileWeights(float("inf"), 1, 0)
    with pytest.raises(ValueError):
        CarbProfileWeights(-1, 1, 1)


def test_population_analytic_kernel_approximates_legacy_knots() -> None:
    # The final legacy knot is a hard cutoff. The smooth model tracks the fitted
    # curve before that discontinuity and then decays naturally.
    for elapsed in (30, 60, 90, 120, 180, 240, 270, 300, 330):
        legacy = insulin_iob_remaining_fraction(elapsed, 360)
        analytic = personalized_insulin_iob_remaining_fraction(
            elapsed,
            POPULATION_INSULIN_KERNEL_V2,
        )
        assert analytic == pytest.approx(legacy, abs=0.06)


def test_personalized_insulin_survival_is_monotone_with_exact_activity() -> None:
    parameters = PersonalizedInsulinKernel(0.3, 35, 105)
    remaining = [
        personalized_insulin_iob_remaining_fraction(elapsed, parameters)
        for elapsed in range(0, 721, 5)
    ]
    assert personalized_insulin_iob_remaining_fraction(-5, parameters) == 1.0
    assert personalized_insulin_cumulative_absorbed(-5, parameters) == 0.0
    assert personalized_insulin_activity_rate(-5, parameters) == 0.0
    assert remaining[0] == 1.0
    assert all(left >= right for left, right in pairwise(remaining))
    assert remaining[-1] < 0.01

    elapsed = 123.0
    epsilon = 0.001
    finite_difference = (
        personalized_insulin_cumulative_absorbed(elapsed + epsilon, parameters)
        - personalized_insulin_cumulative_absorbed(elapsed - epsilon, parameters)
    ) / (2.0 * epsilon)
    assert personalized_insulin_activity_rate(
        elapsed,
        parameters,
    ) == pytest.approx(finite_difference, rel=1e-7)


def test_personalized_insulin_minutes_use_residual_horizon() -> None:
    parameters = PersonalizedInsulinKernel(0.2, 25, 90)
    horizon = personalized_insulin_minutes_remaining(0, parameters)
    assert personalized_insulin_iob_remaining_fraction(horizon, parameters) <= 0.02
    assert personalized_insulin_iob_remaining_fraction(horizon - 1, parameters) > 0.02
    assert personalized_insulin_minutes_remaining(60, parameters) == horizon - 60
    assert personalized_insulin_minutes_remaining(horizon, parameters) == 0
    assert personalized_insulin_minutes_remaining(-10, parameters) == horizon
    assert personalized_insulin_iob_remaining_fraction(10_000, parameters) < 1e-20
    assert personalized_insulin_minutes_remaining(10_000, parameters) == 0


def test_soft_prior_uses_liquid_identity_and_macro_tail_signals() -> None:
    drink = carb_profile_prior_weights(
        carbs_g=54,
        is_liquid=True,
        is_sweetened=True,
    )
    same_macros_as_solid = carb_profile_prior_weights(
        carbs_g=54,
        is_liquid=False,
    )
    slow_mixed = carb_profile_prior_weights(
        carbs_g=14.5,
        protein_g=12.5,
        fat_g=16.2,
        fiber_g=1.5,
        is_liquid=False,
    )

    assert drink.dominant_profile == "fast"
    assert same_macros_as_solid.dominant_profile == "normal"
    assert drink.fast > same_macros_as_solid.fast
    assert slow_mixed.dominant_profile == "slow"


def test_reviewed_hint_and_learned_weights_update_without_hard_override() -> None:
    prior = carb_profile_prior_weights(carbs_g=45, is_liquid=False)
    hinted = carb_profile_prior_weights(
        carbs_g=45,
        is_liquid=False,
        profile_hint="slow",
    )
    learned = CarbProfileWeights(fast=0.05, normal=0.15, slow=0.8)
    posterior = blend_carb_profile_weights(prior, learned, learned_weight=0.75)

    assert hinted.slow > prior.slow
    assert prior.slow < posterior.slow < learned.slow
    assert sum(posterior.to_mapping().values()) == pytest.approx(1.0)


def test_one_hot_cob_mixture_matches_legacy_basis() -> None:
    fast = CarbProfileWeights(fast=1, normal=0, slow=0)
    slow = CarbProfileWeights(fast=0, normal=0, slow=1)
    for elapsed in (0, 30, 60, 90, 120):
        assert carb_mixture_cob_remaining_fraction(
            elapsed,
            weights=fast,
        ) == pytest.approx(
            carb_cob_remaining_fraction(
                elapsed,
                duration_min=120,
                profile="fast",
            )
        )
    for elapsed in (0, 60, 120, 240, 360, 420):
        assert carb_mixture_cob_remaining_fraction(
            elapsed,
            weights=slow,
        ) == pytest.approx(
            carb_cob_remaining_fraction(
                elapsed,
                duration_min=420,
                profile="slow",
            )
        )


def test_cob_mixture_boundaries_are_stable() -> None:
    weights = CarbProfileWeights(fast=0.2, normal=0.6, slow=0.2)
    horizon = carb_mixture_minutes_remaining(0, weights=weights)

    assert carb_mixture_cumulative_absorbed(-5, weights=weights) == 0.0
    assert carb_mixture_cob_remaining_fraction(-5, weights=weights) == 1.0
    assert carb_mixture_minutes_remaining(-5, weights=weights) == horizon
    assert carb_mixture_cumulative_absorbed(10_000, weights=weights) == 1.0
    assert carb_mixture_cob_remaining_fraction(10_000, weights=weights) == 0.0
    assert carb_mixture_minutes_remaining(10_000, weights=weights) == 0


def test_soft_cob_mixture_is_convex_and_effect_remains_dose_proportional() -> None:
    weights = CarbProfileWeights(fast=0.25, normal=0.5, slow=0.25)
    elapsed = 120
    cumulative = carb_mixture_cumulative_absorbed(elapsed, weights=weights)
    fast = carb_mixture_cumulative_absorbed(
        elapsed,
        weights=CarbProfileWeights(1, 0, 0),
    )
    slow = carb_mixture_cumulative_absorbed(
        elapsed,
        weights=CarbProfileWeights(0, 0, 1),
    )
    assert slow < cumulative < fast

    small = carb_effect_for_meal(
        60,
        carbs_g=30,
        icr=10,
        profile_weights=weights,
    )
    large = carb_effect_for_meal(
        60,
        carbs_g=60,
        icr=10,
        profile_weights=weights,
    )
    assert large == pytest.approx(small * 2)

    horizon = carb_mixture_minutes_remaining(0, weights=weights)
    assert carb_mixture_cob_remaining_fraction(horizon, weights=weights) <= 0.02
    assert carb_mixture_minutes_remaining(horizon, weights=weights) == 0
