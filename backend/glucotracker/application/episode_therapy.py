"""Automatic therapy intent classification for grouped food/insulin episodes.

Episode linkage answers "which records belong together."  This module adds a
separate, read-only interpretation layer: meal, snack, carbohydrate rescue,
insulin correction, or mixed treatment.  It never rewrites meal/insulin links
and never creates treatment records.

The classification is *retrospective*. Earlier versions guessed forward from the
trend at the plate — "glucose is falling steeply, so this must be a rescue" —
which is the question a live app has to answer but not the one asked here. By
the time an episode is drawn in the diary the trace has already happened, so
whether a low occurred is a fact to be read rather than a slope to be
extrapolated. That change is what the nadir gate below encodes, and it is the
single reason ordinary food stopped being filed as a rescue.

Each class is decided from named evidence rather than a chain of conditions, so
the reason a label was chosen survives into the response and, from there, into
the episode breakdown the client shows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from glucotracker.api.schemas import GlucoseDashboardPoint
from glucotracker.application.episodes import EpisodeComponent
from glucotracker.application.grouping import (
    INSULIN_COVERAGE_WINDOW,
    RISING_PER_MINUTE,
    SITTING_SPAN,
)
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import normalized_text

TherapyClass = Literal[
    "meal",
    "snack",
    "carb_correction",
    "insulin_correction",
    "mixed",
    "unresolved",
]
TherapyConfidence = Literal["low", "medium", "high"]

LOW_GLUCOSE_MMOL_L = 3.9
LEVEL_TWO_LOW_MMOL_L = 3.0
# Treating starts before the threshold is crossed, and a rescue that worked
# never reaches 3.9 at all. Anything that bottomed out this close to the line
# counts as "a low, or the edge of one"; anything above it is not a low that
# food was answering, however fast glucose happened to be moving at the time.
NEAR_LOW_MMOL_L = 4.5
SNACK_MAX_CARBS_G = 30.0
DEFAULT_RESCUE_CARBS_G = 15.0
POINT_TOLERANCE = timedelta(minutes=15)
TREND_LOOKBACK = timedelta(minutes=20)
OUTCOME_HORIZON = timedelta(hours=2)
PEAK_HORIZON = timedelta(minutes=150)
SNACK_ROLES = {"snack", "drink", "dessert"}
FAST_CARB_TASTES = {"sweet", "drink_sweet"}
# The trough that prompted the food. It opens before the plate because the
# decision is made on what glucose was doing then, and closes after it because
# fast carbs need a quarter of an hour to bite and glucose keeps falling
# meanwhile.
RESCUE_TROUGH_BEFORE = timedelta(minutes=20)
RESCUE_TROUGH_AFTER = timedelta(minutes=25)
# How long a rescue has to show it worked, and by how much.
RESCUE_REVERSAL_WINDOW = timedelta(minutes=60)
RESCUE_REVERSAL_MMOL_L = 1.5
# A bolus this soon after the plate is still part of dosing it; past the far
# edge the meal is no longer plausibly the cause of what is being chased.
CATCH_UP_AFTER = timedelta(minutes=20)
CATCH_UP_UNTIL = timedelta(hours=3)
# Same boundary read the other way: insulin given inside it was dosed *for* the
# food, which is the one thing a rescue never is.
DOSED_WITH_PLATE = CATCH_UP_AFTER
# One threshold for "glucose is climbing", shared with the grouping tiebreak
# that decides which sitting a dose between two of them belongs to.
CATCH_UP_RISING_PER_MINUTE = RISING_PER_MINUTE
# -1 mg/dL per minute, the conventional "falling fast" arrow.
FALLING_PER_MINUTE = -(1 / 18.0182)
# How long "there is no bolus here" has to wait before it means anything.
# Equal to the window in which a later bolus still attaches to the sitting, so
# the classifier never draws a conclusion from insulin that may still arrive.
SETTLING_WINDOW = INSULIN_COVERAGE_WINDOW

# Score thresholds. The rescue gate alone contributes 5, so a bare gate lands on
# "medium" and corroborating evidence — fast carbs, a lean portion, a reversal —
# is what earns "high".
HIGH_CONFIDENCE_SCORE = 8.0
MEDIUM_CONFIDENCE_SCORE = 6.0


def mmol(value: float) -> str:
    """One decimal with the decimal comma Russian copy uses."""
    return f"{value:.1f}".replace(".", ",")


@dataclass(frozen=True)
class TherapyEvidence:
    """One named observation that argued for the label finally chosen.

    Only evidence that holds is emitted. ``code`` is stable and machine-facing;
    ``text`` is the sentence the diary shows.
    """

    code: str
    text: str
    weight: float = 0.0


@dataclass(frozen=True)
class EpisodeTherapy:
    """Read-only therapy interpretation returned with one episode."""

    classification: TherapyClass
    confidence: TherapyConfidence
    reasons: list[str]
    evidence: list[TherapyEvidence] = field(default_factory=list)
    score: float = 0.0
    suggested_carbs_g: float | None = None
    suggestion_source: Literal["ada_default"] | None = None
    glucose_at_start_raw: float | None = None
    glucose_at_start_normalized: float | None = None
    glucose_plus_2h_raw: float | None = None
    glucose_plus_2h_normalized: float | None = None
    peak_post_event_raw: float | None = None
    peak_post_event_normalized: float | None = None
    trough_normalized: float | None = None
    trough_at: datetime | None = None


def classify_episode_therapy(
    component: EpisodeComponent,
    points: list[GlucoseDashboardPoint],
    now: datetime | None = None,
) -> EpisodeTherapy:
    """Classify one component from calibrated glucose, once it has settled.

    [now] is app-local wall time, the same convention as `component.start_at`.
    It defaults to the real clock, so every past episode is settled and only a
    sitting still in progress is held back.
    """
    start_at = component.start_at
    at_start = _nearest(points, start_at)
    plus_2h = _nearest(points, start_at + OUTCOME_HORIZON)
    post_points = [
        point
        for point in points
        if start_at <= point.timestamp <= start_at + PEAK_HORIZON
    ]

    raw_at = _raw(at_start)
    normalized_at = _normalized(at_start)
    raw_plus_2h = _raw(plus_2h)
    normalized_plus_2h = _normalized(plus_2h)
    raw_peak = max((_raw(point) for point in post_points), default=None)
    normalized_peak = max(
        (_normalized(point) for point in post_points),
        default=None,
    )
    normalized_trend = _trend(points, start_at, normalized=True)
    trough = _trough(points, start_at)

    # Every judgement reads the calibrated value alone. This used to take
    # min(raw, normalized) as a safety floor, which is right for an alarm and
    # wrong for a judgement: this owner's raw stream sits 1.0-2.8 mmol/L below
    # true glucose, so an ordinary 5.5 arrived as a raw 3.5 and the plate that
    # followed was filed as a rescue. `_normalized` already falls back to raw
    # for a session with no calibration, which is the only place raw should
    # still decide anything. Both raw figures are still reported.
    trough_value = trough[0] if trough is not None else None
    # Same reason. A constant offset would cancel out of a slope, but the
    # calibration is affine, so the calibrated trend is the one to read.
    falling = normalized_trend is not None and normalized_trend <= FALLING_PER_MINUTE
    # "No bolus" is only evidence once a bolus would no longer be linked here.
    # Inside the window the user may still be photographing the plate and has
    # simply not dosed yet — and a half-entered lunch is exactly what "food, no
    # insulin, small carbs, drifting down" looks like.
    settled = start_at + SETTLING_WINDOW <= (
        now if now is not None else _local_wall_time(datetime.now(UTC))
    )

    total_carbs = sum(float(meal.total_carbs_g or 0) for meal in component.meals)
    roles = {
        normalized_text(str((meal.derived_categories or {}).get("meal_role") or ""))
        for meal in component.meals
    }
    roles.discard("")
    tastes = {
        normalized_text(str((meal.ai_categories or {}).get("taste_profile") or ""))
        for meal in component.meals
    }
    tastes.discard("")
    explicit_corrections = [
        event
        for event in component.insulin
        if "correction" in normalized_text(event.event_type)
    ]
    food_boluses = [
        event for event in component.insulin if event not in explicit_corrections
    ]

    classification: TherapyClass
    confidence: TherapyConfidence
    evidence: list[TherapyEvidence]
    suggested_carbs: float | None = None
    suggestion_source: Literal["ada_default"] | None = None

    rescue = _rescue_evidence(
        component,
        points,
        trough=trough,
        falling=falling,
        settled=settled,
        total_carbs=total_carbs,
        roles=roles,
        tastes=tastes,
    )

    if rescue is not None:
        classification = "carb_correction"
        evidence = rescue
        suggested_carbs = DEFAULT_RESCUE_CARBS_G
        suggestion_source = "ada_default"
    elif component.meals and explicit_corrections:
        classification = "mixed"
        evidence = [
            TherapyEvidence(
                "food_with_correction",
                "еда и отдельная коррекция инсулином в одном эпизоде",
                6.0 if food_boluses else 4.0,
            )
        ]
    elif component.meals:
        classification, evidence = _food_evidence(
            total_carbs=total_carbs,
            roles=roles,
            food_boluses=food_boluses,
        )
    elif component.insulin:
        classification = "insulin_correction"
        evidence = [
            TherapyEvidence("insulin_without_food", "инсулин без еды", 4.0),
            TherapyEvidence(
                "marked_correction"
                if explicit_corrections
                else "no_food_nearby",
                "событие помечено как коррекция"
                if explicit_corrections
                else "рядом нет записи о еде",
                4.0 if explicit_corrections else 2.0,
            ),
        ]
    else:
        classification = "unresolved"
        evidence = [TherapyEvidence("no_context", "недостаточно контекста")]

    # Both figures stay visible on every class, so a disputed label can be
    # checked against the numbers that produced it.
    if raw_at is not None and normalized_at is not None:
        evidence = [
            *evidence,
            TherapyEvidence(
                "calibration",
                f"raw {mmol(raw_at)}, нормализованная {mmol(normalized_at)}",
            ),
        ]

    score = sum(item.weight for item in evidence)
    confidence = _confidence(score)

    return EpisodeTherapy(
        classification=classification,
        confidence=confidence,
        reasons=[item.text for item in evidence],
        evidence=evidence,
        score=round(score, 1),
        suggested_carbs_g=suggested_carbs,
        suggestion_source=suggestion_source,
        glucose_at_start_raw=_rounded(raw_at),
        glucose_at_start_normalized=_rounded(normalized_at),
        glucose_plus_2h_raw=_rounded(raw_plus_2h),
        glucose_plus_2h_normalized=_rounded(normalized_plus_2h),
        peak_post_event_raw=_rounded(raw_peak),
        peak_post_event_normalized=_rounded(normalized_peak),
        trough_normalized=_rounded(trough_value),
        trough_at=trough[1] if trough is not None else None,
    )


def _rescue_evidence(
    component: EpisodeComponent,
    points: list[GlucoseDashboardPoint],
    *,
    trough: tuple[float, datetime] | None,
    falling: bool,
    settled: bool,
    total_carbs: float,
    roles: set[str],
    tastes: set[str],
) -> list[TherapyEvidence] | None:
    """Evidence that this episode was food answering a low, or None.

    Three conditions gate the label, and all three must hold:

    - glucose actually reached a low, or its edge, around the plate;
    - the portion was small enough to be a treatment rather than a meal;
    - no insulin was dosed with it, once late insulin can no longer arrive.

    Everything after the gate only moves confidence. The gate is the whole
    change: before it, a steep slope alone was enough, so a descent from a meal
    peak toward a perfectly ordinary 6.7 made the next plate a rescue.
    """
    if not component.meals:
        return None
    if trough is None:
        # No calibrated glucose around the plate. Whether a low happened is
        # unknown, and "unknown" must not read as "yes" for a hypo label.
        return None

    trough_value, trough_at = trough
    if trough_value > NEAR_LOW_MMOL_L:
        return None
    if not 0 < total_carbs <= SNACK_MAX_CARBS_G:
        return None

    first_meal_at = min(meal.eaten_at for meal in component.meals)
    dosed_with_plate = [
        event
        for event in component.insulin
        if _local_wall_time(event.timestamp) <= first_meal_at + DOSED_WITH_PLATE
    ]
    if dosed_with_plate or not settled:
        return None

    evidence: list[TherapyEvidence] = []
    if trough_value < LOW_GLUCOSE_MMOL_L:
        evidence.append(
            TherapyEvidence(
                "low_before_food",
                f"глюкоза опускалась до {mmol(trough_value)} ммоль/л"
                f" в {trough_at:%H:%M}",
                3.0,
            )
        )
    else:
        evidence.append(
            TherapyEvidence(
                "near_low_before_food",
                f"глюкоза подходила к нижней границе: {mmol(trough_value)} ммоль/л",
                2.0,
            )
        )
    if trough_value < LEVEL_TWO_LOW_MMOL_L:
        evidence.append(
            TherapyEvidence("severe_low", "гипогликемия второго уровня", 1.0)
        )
    evidence.append(
        TherapyEvidence(
            "small_portion", f"небольшой приём: {total_carbs:.0f} г", 1.0
        )
    )
    evidence.append(
        TherapyEvidence("no_bolus", "рядом нет пищевого болюса", 1.0)
    )
    if falling:
        evidence.append(
            TherapyEvidence("falling", "глюкоза быстро снижалась перед едой", 1.0)
        )
    if tastes & FAST_CARB_TASTES or roles & SNACK_ROLES:
        evidence.append(
            TherapyEvidence("fast_carbs", "быстрые углеводы", 1.0)
        )
    if _is_lean(component):
        evidence.append(
            TherapyEvidence(
                "lean_portion", "почти чистые углеводы, без жира и белка", 1.0
            )
        )
    reversal = _reversal(points, trough_at, trough_value)
    if reversal is not None:
        evidence.append(
            TherapyEvidence(
                "reversed",
                f"глюкоза развернулась вверх на +{mmol(reversal)} ммоль/л",
                2.0,
            )
        )
    return evidence


def _food_evidence(
    *,
    total_carbs: float,
    roles: set[str],
    food_boluses: list[object],
) -> tuple[TherapyClass, list[TherapyEvidence]]:
    """Snack or meal, once a rescue has been ruled out."""
    is_role_snack = (
        bool(roles) and roles.issubset(SNACK_ROLES) and total_carbs <= SNACK_MAX_CARBS_G
    )
    if is_role_snack:
        return "snack", [
            TherapyEvidence(
                "snack_role",
                f"роль продукта: {', '.join(sorted(roles))}",
                8.0,
            )
        ]
    if not roles and total_carbs <= SNACK_MAX_CARBS_G:
        return "snack", [
            TherapyEvidence(
                "small_portion",
                f"небольшой отдельный приём: {total_carbs:.0f} г",
                6.0,
            )
        ]
    evidence = [
        TherapyEvidence(
            "meal_carbs", f"углеводы приёма: {total_carbs:.0f} г", 6.0
        )
    ]
    if roles and not roles.issubset(SNACK_ROLES):
        evidence = [
            TherapyEvidence(
                "meal_role", f"роль приёма: {', '.join(sorted(roles))}", 6.0
            )
        ]
    if food_boluses:
        evidence.append(
            TherapyEvidence("dosed", "приём покрыт болюсом", 2.0)
        )
    return "meal", evidence


def _confidence(score: float) -> TherapyConfidence:
    if score >= HIGH_CONFIDENCE_SCORE:
        return "high"
    if score >= MEDIUM_CONFIDENCE_SCORE:
        return "medium"
    return "low"


def _is_lean(component: EpisodeComponent) -> bool:
    """Whether the portion is carbohydrate rather than food.

    Juice and glucose tablets are almost pure carbohydrate; an omelette with
    seven grams of carbohydrate is not, and the difference is what separates a
    treatment from a small meal eaten while glucose happened to be moving.
    """
    carbs = sum(float(meal.total_carbs_g or 0) for meal in component.meals)
    protein = sum(float(meal.total_protein_g or 0) for meal in component.meals)
    fat = sum(float(meal.total_fat_g or 0) for meal in component.meals)
    if carbs <= 0:
        return False
    return (protein * 4 + fat * 9) <= carbs * 4


def _trough(
    points: list[GlucoseDashboardPoint],
    start_at: datetime,
) -> tuple[float, datetime] | None:
    """Lowest calibrated value around the plate, with when it happened."""
    window = [
        point
        for point in points
        if start_at - RESCUE_TROUGH_BEFORE
        <= point.timestamp
        <= start_at + RESCUE_TROUGH_AFTER
    ]
    values = [
        (value, point.timestamp)
        for point in window
        if (value := _normalized(point)) is not None
    ]
    return min(values) if values else None


def _reversal(
    points: list[GlucoseDashboardPoint],
    trough_at: datetime,
    trough_value: float,
) -> float | None:
    """How far glucose climbed back from the trough, if it climbed at all."""
    after = [
        value
        for point in points
        if trough_at < point.timestamp <= trough_at + RESCUE_REVERSAL_WINDOW
        if (value := _normalized(point)) is not None
    ]
    if not after:
        return None
    rise = max(after) - trough_value
    return rise if rise >= RESCUE_REVERSAL_MMOL_L else None


def _nearest(
    points: list[GlucoseDashboardPoint],
    target: datetime,
) -> GlucoseDashboardPoint | None:
    if not points:
        return None
    nearest = min(points, key=lambda point: abs(point.timestamp - target))
    return nearest if abs(nearest.timestamp - target) <= POINT_TOLERANCE else None


def catch_up_event_ids(
    component: EpisodeComponent,
    points: list[GlucoseDashboardPoint],
) -> set[UUID]:
    """Boluses given to chase a rise the meal was already causing.

    Not meal insulin and not a correction. It answers a rise that has already
    started, so it is given knowing something the dose at the plate could not:
    that the first bolus did not hold. Counting it as ordinary meal coverage
    makes the food look like it needed more insulin, when what it needed was
    the same insulin earlier — and a recommendation that quotes the inflated
    total up front is a different, riskier act than 8 U now and 4 U if it
    climbs.

    Measured over 75 days for this owner: boluses at the plate sit on a
    −0.40 mmol/L per hour trend, later ones on +1.80 with 86% rising. The two
    acts separate on what glucose was doing, so that is the test used here.
    A bolus given while glucose is flat or falling stays an ordinary one.
    """
    if not component.meals:
        return set()
    sitting_at = min(meal.eaten_at for meal in component.meals)
    catch_ups: set[UUID] = set()
    for event in component.insulin:
        at = _local_wall_time(event.timestamp)
        if not (sitting_at + CATCH_UP_AFTER <= at <= sitting_at + CATCH_UP_UNTIL):
            continue
        # A plate from a *later sitting* makes the rise ambiguous; that insulin
        # belongs to it. A second dish of this sitting does not: the owner
        # photographs a meal dish by dish, so "any meal after the first one"
        # matched their own second photograph and disqualified every catch-up in
        # any sitting of more than one plate — which is most of them. The label
        # existed and could not fire where it was needed.
        if any(
            sitting_at + SITTING_SPAN < meal.eaten_at <= at
            for meal in component.meals
        ):
            continue
        rising = [
            trend
            for trend in (
                _trend(points, at, normalized=True),
                _trend(points, at, normalized=False),
            )
            if trend is not None
        ]
        if rising and max(rising) >= CATCH_UP_RISING_PER_MINUTE:
            catch_ups.add(event.id)
    return catch_ups


def _trend(
    points: list[GlucoseDashboardPoint],
    target: datetime,
    *,
    normalized: bool,
) -> float | None:
    recent = [
        point
        for point in points
        if target - TREND_LOOKBACK <= point.timestamp <= target
    ]
    if len(recent) < 2:
        return None
    first = recent[0]
    last = recent[-1]
    minutes = (last.timestamp - first.timestamp).total_seconds() / 60
    if minutes < 5:
        return None
    value = _normalized if normalized else _raw
    first_value = value(first)
    last_value = value(last)
    if first_value is None or last_value is None:
        return None
    return (last_value - first_value) / minutes


def _raw(point: GlucoseDashboardPoint | None) -> float | None:
    return float(point.raw_value) if point is not None else None


def _normalized(point: GlucoseDashboardPoint | None) -> float | None:
    if point is None:
        return None
    return float(
        point.normalized_value
        if point.normalized_value is not None
        else point.raw_value
    )


def _rounded(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None
