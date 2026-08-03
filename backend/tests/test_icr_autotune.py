"""Per-daypart ICR proposals from how meals actually landed."""

from __future__ import annotations

from datetime import datetime, timedelta

from glucotracker.application.icr_autotune import (
    MAX_LOOSEN_FRACTION,
    MAX_TIGHTEN_FRACTION,
    MIN_EPISODES,
    IcrEpisode,
    implied_icr,
    propose,
    weighted_median,
)

AT = datetime(2026, 8, 3, 12, 41)


def _episodes(count: int, ratio: float, carbs: float = 60.0) -> list[IcrEpisode]:
    return [
        IcrEpisode(
            occurred_at=AT - timedelta(days=index),
            carbs_g=carbs,
            units=carbs / ratio,
            outcome_mmol_l=6.0,
            implied_icr=ratio,
        )
        for index in range(count)
    ]


def test_an_episode_that_finished_high_implies_a_tighter_ratio() -> None:
    # 2026-08-03 breakfast: 62 g on 8.5 U landed at 13.0 against a 6.0 target.
    ratio = implied_icr(
        carbs_g=62.0,
        units=8.5,
        outcome_mmol_l=13.0,
        target_mmol_l=6.0,
        isf=2.6,
    )

    assert ratio is not None
    # 8.5 + (13.0 - 6.0) / 2.6 = 11.2 U would have landed on target.
    assert 5.0 < ratio < 6.0
    assert ratio < 62.0 / 8.5


def test_an_episode_that_finished_low_implies_a_looser_ratio() -> None:
    ratio = implied_icr(
        carbs_g=39.0,
        units=7.3,
        outcome_mmol_l=4.7,
        target_mmol_l=6.0,
        isf=2.6,
    )

    assert ratio is not None
    assert ratio > 39.0 / 7.3


def test_no_ratio_where_the_arithmetic_has_no_meaning() -> None:
    # Small snack, below the evidence floor.
    assert implied_icr(
        carbs_g=8.0, units=1.0, outcome_mmol_l=6.0, target_mmol_l=6.0, isf=2.6
    ) is None
    # An outcome so low that no positive dose explains it.
    assert implied_icr(
        carbs_g=60.0, units=1.0, outcome_mmol_l=2.0, target_mmol_l=6.0, isf=2.6
    ) is None
    # A ratio outside the trusted bounds is not evidence.
    assert implied_icr(
        carbs_g=60.0, units=30.0, outcome_mmol_l=6.0, target_mmol_l=6.0, isf=2.6
    ) is None


def test_larger_meals_carry_more_weight() -> None:
    # One big meal at 6 outvotes two small ones at 12.
    assert weighted_median([(12.0, 20.0), (6.0, 200.0), (12.0, 20.0)]) == 6.0


def test_too_few_episodes_produces_no_number() -> None:
    proposal = propose(
        daypart="morning",
        episodes=_episodes(MIN_EPISODES - 1, 5.5),
        current_icr=8.0,
    )

    assert proposal.proposed_icr is None
    assert proposal.confidence == "none"
    assert proposal.note


def test_tightening_is_capped_harder_than_loosening() -> None:
    tighten = propose(
        daypart="morning", episodes=_episodes(30, 4.0), current_icr=8.0
    )
    loosen = propose(
        daypart="evening", episodes=_episodes(30, 20.0), current_icr=10.0
    )

    # The measured ratios are far away in both directions; one proposal may
    # move a quarter, the other only a tenth.
    assert tighten.proposed_icr == round(8.0 * (1 - MAX_TIGHTEN_FRACTION), 1)
    assert loosen.proposed_icr == round(10.0 * (1 + MAX_LOOSEN_FRACTION), 1)
    assert tighten.capped and loosen.capped


def test_a_thin_history_moves_only_part_of_the_way() -> None:
    thin = propose(daypart="day", episodes=_episodes(8, 6.0), current_icr=9.3)
    full = propose(daypart="day", episodes=_episodes(20, 6.0), current_icr=9.3)

    assert thin.proposed_icr is not None and full.proposed_icr is not None
    # Both move toward 6.0, the thin one less so.
    assert full.proposed_icr < thin.proposed_icr < 9.3


def test_an_unset_ratio_is_proposed_directly() -> None:
    proposal = propose(
        daypart="morning", episodes=_episodes(10, 5.5), current_icr=None
    )

    assert proposal.proposed_icr == 5.5
    assert proposal.confidence == "low"


def test_the_reported_day_moves_both_slots_the_right_way() -> None:
    """Breakfast asks for tighter, evening for looser, from 2026-08-03."""
    morning = propose(
        daypart="morning", episodes=_episodes(12, 5.5, carbs=62.0), current_icr=8.0
    )
    evening = propose(
        daypart="evening", episodes=_episodes(12, 11.5, carbs=39.0), current_icr=10.0
    )

    assert morning.proposed_icr < 8.0
    assert evening.proposed_icr > 10.0
    assert morning.estimated_icr == 5.5
    assert evening.estimated_icr == 11.5
