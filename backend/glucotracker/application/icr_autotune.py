"""Estimate a per-daypart ICR from how meals actually landed.

A single ratio cannot fit this owner. Measured on 2026-08-03: 62 g at breakfast
took 8.5 U given twenty minutes early and still peaked at 13.0, implying roughly
5.5 g/U; that evening 39 g took 7.3 U and did not move the curve at all,
implying about 11. The configured 8.0 / 9.3 / 10.0 splits the day in the right
direction but with a quarter of the spread the outcomes ask for.

For each completed food episode the ratio that would have landed on target is

    ideal_units = units_given + (outcome - target) / ISF
    implied_icr = carbs / ideal_units

and the daypart estimate is a carbohydrate-weighted median of those, shrunk
toward the configured value by sample count.

Nothing here writes a parameter. It produces a proposal with the evidence
attached, because an ICR that drifts tighter without anyone noticing is the one
failure mode that hurts.

Three properties keep it conservative:

- Loosening (less insulin per gram) is allowed to move faster than tightening,
  since the error that causes harm is only in one direction.
- Episodes near exercise are excluded rather than modelled. Twenty sessions in
  75 days is enough to know activity moves the ratio and not enough to say by
  how much.
- Episodes whose outcome is missing, or that were interrupted by more food, do
  not vote at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.application.insulin_recommendation import (
    AUTO_FIT_ICR_MAX_G_PER_UNIT,
    AUTO_FIT_ICR_MIN_G_PER_UNIT,
    DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT,
    DEFAULT_CORRECTION_TARGET_MMOL_L,
    _icr_for_time,
    _trusted_isf,
)
from glucotracker.infra.db.repositories.twin import TwinRepository

Daypart = Literal["morning", "day", "evening"]

LOOKBACK_DAYS = 30
OUTCOME_AT = timedelta(hours=3)
OUTCOME_TOLERANCE = timedelta(minutes=20)
MIN_CARBS_G = 20.0
MIN_EPISODES = 6
FULL_CONFIDENCE_EPISODES = 20
# Exercise shifts the ratio by more than this estimator could separate, so
# episodes near a session are dropped instead of being allowed to vote.
EXERCISE_EXCLUSION = timedelta(hours=2)
# Asymmetric caps per proposal. Loosening means less insulin per gram.
MAX_LOOSEN_FRACTION = 0.25
MAX_TIGHTEN_FRACTION = 0.10


@dataclass(frozen=True)
class IcrEpisode:
    """One completed food episode and the ratio it implies."""

    occurred_at: datetime
    carbs_g: float
    units: float
    outcome_mmol_l: float
    implied_icr: float


@dataclass(frozen=True)
class IcrProposal:
    """A per-daypart proposal with the evidence that produced it."""

    daypart: Daypart
    current_icr: float | None
    estimated_icr: float | None
    proposed_icr: float | None
    episode_count: int
    confidence: Literal["none", "low", "medium", "high"]
    capped: bool = False
    note: str | None = None


def daypart_of(at: datetime, twin_params) -> Daypart:
    """Return which configured slot a local wall time falls into."""
    minutes = at.hour * 60 + at.minute
    if twin_params.morning_start_minutes <= minutes < twin_params.day_start_minutes:
        return "morning"
    if twin_params.day_start_minutes <= minutes < twin_params.evening_start_minutes:
        return "day"
    return "evening"


def implied_icr(
    *,
    carbs_g: float,
    units: float,
    outcome_mmol_l: float,
    target_mmol_l: float,
    isf: float,
) -> float | None:
    """Return the ratio that would have landed this episode on target.

    An episode that finished above target needed more insulin than it got, so
    its implied ratio is tighter than the one used; one that finished below
    needed less. Returns None where the arithmetic has no meaning — a
    non-positive ideal dose means the outcome cannot be explained by the food.
    """
    if carbs_g < MIN_CARBS_G or units <= 0 or isf <= 0:
        return None
    ideal = units + (outcome_mmol_l - target_mmol_l) / isf
    if ideal <= 0:
        return None
    ratio = carbs_g / ideal
    if not AUTO_FIT_ICR_MIN_G_PER_UNIT <= ratio <= AUTO_FIT_ICR_MAX_G_PER_UNIT:
        return None
    return ratio


def weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    """Median of (value, weight); larger meals carry more evidence."""
    usable = [(v, w) for v, w in pairs if w > 0]
    if not usable:
        return None
    if len(usable) == 1:
        return usable[0][0]
    usable.sort(key=lambda item: item[0])
    total = sum(w for _, w in usable)
    seen = 0.0
    for value, weight in usable:
        seen += weight
        if seen >= total / 2:
            return value
    return usable[-1][0]


def propose(
    *,
    daypart: Daypart,
    episodes: list[IcrEpisode],
    current_icr: float | None,
) -> IcrProposal:
    """Shrink the measured ratio toward the configured one and cap the move."""
    count = len(episodes)
    if count < MIN_EPISODES:
        return IcrProposal(
            daypart=daypart,
            current_icr=current_icr,
            estimated_icr=None,
            proposed_icr=None,
            episode_count=count,
            confidence="none",
            note=f"нужно минимум {MIN_EPISODES} приёмов, есть {count}",
        )

    estimate = weighted_median([(e.implied_icr, e.carbs_g) for e in episodes])
    if estimate is None:
        return IcrProposal(
            daypart=daypart,
            current_icr=current_icr,
            estimated_icr=None,
            proposed_icr=None,
            episode_count=count,
            confidence="none",
        )
    if current_icr is None or current_icr <= 0:
        return IcrProposal(
            daypart=daypart,
            current_icr=current_icr,
            estimated_icr=round(estimate, 1),
            proposed_icr=round(estimate, 1),
            episode_count=count,
            confidence="low",
            note="текущее значение не задано, предложено измеренное",
        )

    strength = min(
        1.0,
        (count - MIN_EPISODES) / (FULL_CONFIDENCE_EPISODES - MIN_EPISODES),
    )
    shrunk = current_icr + strength * (estimate - current_icr)
    # A higher ratio means less insulin per gram, which is the safe direction.
    upper = current_icr * (1.0 + MAX_LOOSEN_FRACTION)
    lower = current_icr * (1.0 - MAX_TIGHTEN_FRACTION)
    proposed = max(lower, min(upper, shrunk))
    proposed = max(
        AUTO_FIT_ICR_MIN_G_PER_UNIT,
        min(AUTO_FIT_ICR_MAX_G_PER_UNIT, proposed),
    )
    spread = sorted(e.implied_icr for e in episodes)
    iqr = spread[int(len(spread) * 0.75)] - spread[int(len(spread) * 0.25)]
    confidence: Literal["none", "low", "medium", "high"] = (
        "high"
        if count >= FULL_CONFIDENCE_EPISODES and iqr <= estimate * 0.5
        else "medium"
        if count >= MIN_EPISODES + 4
        else "low"
    )
    return IcrProposal(
        daypart=daypart,
        current_icr=round(current_icr, 1),
        estimated_icr=round(estimate, 1),
        proposed_icr=round(proposed, 1),
        episode_count=count,
        confidence=confidence,
        capped=abs(proposed - shrunk) > 0.05,
    )


class IcrAutotuneService:
    """Read completed episodes and propose per-daypart ratios."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def params(self):
        return TwinRepository(self.session, self.user_id).get_or_create_params(
            persist=False,
        )

    def current_icr(self, daypart: Daypart) -> float | None:
        twin = self.params()
        reference = {
            "morning": twin.morning_start_minutes,
            "day": twin.day_start_minutes,
            "evening": twin.evening_start_minutes,
        }[daypart]
        return _icr_for_time(
            datetime(2000, 1, 1, reference // 60, reference % 60),
            twin,
        )[1]

    def isf(self) -> float:
        return _trusted_isf(self.params()) or DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT

    def target(self) -> float:
        return DEFAULT_CORRECTION_TARGET_MMOL_L
