"""Suggest the size of a follow-up bolus during a rise.

The common pattern is: dose conservatively at the meal, watch, and top up when
the curve turns out steeper than expected. That is a sound way to prioritise
avoiding a low, and the owner's own history supports it — follow-up boluses
larger than the modelled requirement produced no readings under 3.9 mmol/L,
while the under-sized ones produced the most.

What the history does not support is the *size* of that follow-up. Regressed
over 106 of them, the amount given tracks neither the reading on screen
(-0.038 +/- 0.070 U per mmol/L, against 1/ISF = 0.385) nor the carbohydrate
still to absorb (-0.005 +/- 0.008 U per gram, against 1/ICR = 0.108). It is
effectively a constant. Meanwhile the median state at that moment is 5.4 U
already active and 39 g still absorbing, so the rise being reacted to is
largely already covered.

This turns that decision into an arithmetic one. Where a forecast exists the
distance from it to target is the answer, because a forecast already contains
every unit on board and every gram still to absorb. Without one it falls back to
a mass balance — carbohydrate left over ICR, plus the correction, minus insulin
on board — which is workable at small quantities and unreliable at large ones.

Every term is already computed elsewhere; none of them is visible at the moment
the decision is made.

v2 (2026-10-04). A read-only backtest over 846 past moments
(`ml-labs/response-attribution/topup_backtest_server.py`) scored the balance
against the dose the next three hours implied. Carbohydrate left and insulin on
board barely predicted it (fitted weights 0.08 and −0.05 where the balance uses
+1 and −1): two large uncertain numbers whose difference is mostly noise. The
reading itself and its last half hour carried the information, and the stored
forecast was usable in only 17% of moments and is no longer consulted. The
answer is now the smaller of the balance and a model fitted on those moments.
Against the outcomes, in a time-ordered check, that cut the error from 1.35 to
1.00 U and the share of suggestions more than 1 U too high from 31% to 16%
(ISF 2.6; it held at 1.5 and 3.5). Taking the smaller of the two keeps the
balance's protection where insulin on board is large, which the history alone
rarely saw.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.api.schemas import GlucoseDashboardInsulinEvent
from glucotracker.application.glucose_dashboard import (
    GlucoseDashboardService,
    _local_wall_from_utc,
    _remaining_on_board,
)
from glucotracker.application.insulin_recommendation import (
    DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT,
    DEFAULT_CORRECTION_TARGET_MMOL_L,
    LOW_GLUCOSE_MMOL_L,
    TIR_HIGH_MMOL_L,
    _icr_for_time,
    _round_dose,
    _trusted_isf,
)
from glucotracker.application.on_board.classification import is_rapid_insulin_event
from glucotracker.application.time import local_now, local_wall_time
from glucotracker.application.twin.kernels import (
    PersonalizedInsulinKernel,
    personalized_insulin_minutes_remaining,
)
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.repositories.twin import TwinRepository

METHOD_VERSION = "top-up-history-min-balance-v2"
LOOKBACK_MINUTES = 40
TREND_MINUTES = 30
TREND_POINT_TOLERANCE_MINUTES = 8
# Frozen on 2026-10-04 from 324 moments without later food or insulin; the
# label was what was given plus the three-hour glucose change over ISF 2.6.
# Rise and fall are the last 30 minutes in mmol/L, divided by 2.6 to put them on
# the same footing as the correction term.
MODEL_CORRECTION_WEIGHT = 0.491
MODEL_CARB_WEIGHT = 0.096
MODEL_IOB_WEIGHT = 0.011
MODEL_RISE_WEIGHT = 0.967
MODEL_FALL_WEIGHT = 0.367
TREND_SCALE_MMOL_L = 2.6
MAX_TREND_MMOL_L = 3.0
# Below this the arithmetic is noise against the dose rounding.
MIN_SUGGESTION_UNITS = 0.2
# A follow-up bolus is a nudge on top of insulin that is already working; a
# large number here means the situation is not a top-up at all.
MAX_SUGGESTION_UNITS = 8.0

TopUpStatus = Literal[
    "ready",
    "not_needed",
    "low_or_falling",
    "glucose_unavailable",
    "icr_unavailable",
]


@dataclass(frozen=True)
class TopUpSuggestion:
    """A follow-up bolus with every term that produced it."""

    status: TopUpStatus
    units: float | None = None
    glucose_mmol_l: float | None = None
    projected_glucose_mmol_l: float | None = None
    projection_source: Literal["none", "linear_trend", "forecast"] = "none"
    target_mmol_l: float | None = None
    cob_g: float | None = None
    iob_units: float | None = None
    iob_minutes_remaining: int | None = None
    cob_minutes_remaining: int | None = None
    carb_units: float | None = None
    correction_units: float | None = None
    icr_g_per_unit: float | None = None
    isf_mmol_l_per_unit: float | None = None
    isf_source: Literal["manual", "fitted", "default"] | None = None
    note: str | None = None
    method_version: str = METHOD_VERSION
    #: Glucose change over the last 30 minutes; None without a reading then.
    trend_mmol_l_per_30_min: float | None = None
    #: The two candidates and which one the answer is.
    balance_units: float | None = None
    model_units: float | None = None
    limited_by: Literal["balance", "model"] | None = None


class TopUpDoseService:
    """Turn the current on-board state into a follow-up bolus number."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def suggest(
        self,
        *,
        target_mmol_l: float | None = None,
        at: datetime | None = None,
        exclude_insulin_id: UUID | None = None,
    ) -> TopUpSuggestion:
        """Return the follow-up bolus implied by carbs left, IOB and target."""
        # Android sends an Instant (`...Z`) while dashboard/on-board arithmetic
        # works in the configured local wall clock. Normalize at the boundary
        # so PostgreSQL's timezone-aware timestamps and SQLite's naive values
        # produce the same calculation.
        now = local_wall_time(at) if at is not None else local_now()
        target = (
            target_mmol_l
            if target_mmol_l is not None
            else DEFAULT_CORRECTION_TARGET_MMOL_L
        )
        dashboard = GlucoseDashboardService(self.session, self.user_id).dashboard(
            now - _minutes(LOOKBACK_MINUTES),
            now,
            "normalized",
        )
        summary = dashboard.summary
        glucose = summary.current_glucose
        if glucose is None:
            return TopUpSuggestion(
                status="glucose_unavailable",
                target_mmol_l=round(target, 1),
                cob_g=round(summary.cob_g, 1),
                iob_units=round(summary.iob_units, 2),
                iob_minutes_remaining=summary.iob_minutes_remaining,
                cob_minutes_remaining=summary.cob_minutes_remaining,
            )

        twin_params = TwinRepository(
            self.session,
            self.user_id,
        ).get_or_create_params(persist=False)
        iob_units = active_iob_units(
            self.session,
            self.user_id,
            as_of=now,
            dia_minutes=twin_params.dia_minutes,
            exclude_insulin_id=exclude_insulin_id,
        )
        trusted_isf = _trusted_isf(twin_params)
        isf = trusted_isf or DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT
        isf_source: Literal["manual", "fitted", "default"] = (
            "default"
            if trusted_isf is None
            else "manual"
            if twin_params.last_fit_method == "manual"
            else "fitted"
        )
        _, icr = _icr_for_time(now, twin_params)
        if icr is None or icr <= 0:
            return TopUpSuggestion(
                status="icr_unavailable",
                glucose_mmol_l=round(glucose, 1),
                target_mmol_l=round(target, 1),
                iob_units=round(iob_units, 2),
                cob_g=round(summary.cob_g, 1),
                iob_minutes_remaining=summary.iob_minutes_remaining,
                cob_minutes_remaining=summary.cob_minutes_remaining,
            )

        # The stored forecast matched what followed too rarely to be given a
        # weight; the last half hour of the trace stands in for direction.
        trend = _trend_over(dashboard.points, now)
        projected = glucose
        projection_source: Literal["none", "linear_trend", "forecast"] = "none"
        if trend is not None:
            projected = glucose + trend
            projection_source = "linear_trend"

        context = {
            "glucose_mmol_l": round(glucose, 1),
            "projected_glucose_mmol_l": round(projected, 1),
            "projection_source": projection_source,
            "target_mmol_l": round(target, 1),
            "cob_g": round(summary.cob_g, 1),
            "iob_units": round(iob_units, 2),
            "iob_minutes_remaining": summary.iob_minutes_remaining,
            "cob_minutes_remaining": summary.cob_minutes_remaining,
            "icr_g_per_unit": round(icr, 1),
            "isf_mmol_l_per_unit": round(isf, 2),
            "isf_source": isf_source,
            "trend_mmol_l_per_30_min": round(trend, 2) if trend is not None else None,
        }

        if glucose < LOW_GLUCOSE_MMOL_L or projected < LOW_GLUCOSE_MMOL_L:
            return TopUpSuggestion(
                status="low_or_falling",
                note="Глюкоза низкая или снижается — добавка не рассчитывается.",
                **context,
            )

        carb_units = summary.cob_g / icr
        correction_units = (glucose - target) / isf

        # The mass balance is right where the imbalance is large and obvious:
        # 80 g against 1 U needs units, 30 g against 9 U needs none. It fails
        # where the two sides are both large and nearly equal, because it is
        # then a difference of big uncertain numbers — and because IOB * ISF
        # stops being physical at that size, 9.8 U at ISF 2.6 implying a
        # 25 mmol/L fall that cannot happen while carbohydrate is absorbing.
        #
        # On 2026-08-02 that regime returned "enough" for ninety minutes while
        # glucose climbed from 10.1 to 11.7. Above the high band the belief that
        # the situation is handled has been contradicted by the reading itself,
        # so the correction toward target is offered instead of nothing.
        net = carb_units + correction_units - iob_units
        contradicted = net < MIN_SUGGESTION_UNITS and glucose > TIR_HIGH_MMOL_L
        if contradicted:
            net = correction_units
        balance = max(0.0, net)
        model = max(
            0.0,
            history_model_units(
                correction_units=correction_units,
                carb_units=carb_units,
                iob_units=iob_units,
                trend_mmol_l_per_30_min=trend,
            ),
        )
        limited_by: Literal["balance", "model"] = (
            "model" if model < balance else "balance"
        )
        net = min(model, balance)

        rounded = {
            "carb_units": round(carb_units, 2),
            "correction_units": round(correction_units, 2),
            "balance_units": round(balance, 2),
            "model_units": round(model, 2),
            "limited_by": limited_by,
        }

        if net < MIN_SUGGESTION_UNITS:
            return TopUpSuggestion(
                status="not_needed",
                units=0.0,
                note=(
                    "Активный инсулин уже покрывает оставшиеся углеводы "
                    "и отклонение от цели."
                ),
                **context,
                **rounded,
            )
        return TopUpSuggestion(
            status="ready",
            units=_round_dose(min(net, MAX_SUGGESTION_UNITS)),
            **context,
            **rounded,
        )


def history_model_units(
    *,
    correction_units: float,
    carb_units: float,
    iob_units: float,
    trend_mmol_l_per_30_min: float | None,
) -> float:
    """What the frozen history model says a follow-up should be, unclamped."""
    trend = trend_mmol_l_per_30_min or 0.0
    trend = max(-MAX_TREND_MMOL_L, min(MAX_TREND_MMOL_L, trend))
    return (
        MODEL_CORRECTION_WEIGHT * correction_units
        + MODEL_CARB_WEIGHT * carb_units
        - MODEL_IOB_WEIGHT * iob_units
        + MODEL_RISE_WEIGHT * max(trend, 0.0) / TREND_SCALE_MMOL_L
        - MODEL_FALL_WEIGHT * max(-trend, 0.0) / TREND_SCALE_MMOL_L
    )


def _trend_over(points, now: datetime) -> float | None:
    """Glucose now minus 30 minutes ago, from the same display series."""
    if not points:
        return None
    latest = max(points, key=lambda point: point.timestamp)
    target = latest.timestamp - _minutes(TREND_MINUTES)
    earlier = min(points, key=lambda point: abs(point.timestamp - target))
    if abs(earlier.timestamp - target) > _minutes(TREND_POINT_TOLERANCE_MINUTES):
        return None
    return float(latest.display_value) - float(earlier.display_value)


def _minutes(value: int):
    from datetime import timedelta

    return timedelta(minutes=value)


def active_iob_units(
    session: Session,
    user_id: UUID,
    *,
    as_of: datetime,
    dia_minutes: int,
    exclude_insulin_id: UUID | None,
) -> float:
    """Return owner-scoped rapid IOB, optionally before one selected bolus.

    A retrospective explanation is evaluated at the selected bolus timestamp.
    The dashboard quite correctly includes an event at that timestamp in its
    current state, but the explanation must answer the instant immediately
    before that event. Filtering by the persisted owner-scoped id avoids the
    selected bolus subtracting itself while retaining every earlier dose.
    """
    repository = OnBoardRepository(session, user_id)
    fit = repository.get_active_fit("iob", "rapid")
    kernel: PersonalizedInsulinKernel | None = None
    if fit is not None:
        try:
            kernel = PersonalizedInsulinKernel.from_mapping(fit.params_json)
        except ValueError:
            kernel = None
    horizon = dia_minutes
    if kernel is not None:
        horizon = max(
            horizon,
            personalized_insulin_minutes_remaining(0, kernel),
        )
    rows = repository.list_training_insulin(
        as_of - _minutes(horizon),
        as_of,
    )
    events = [
        GlucoseDashboardInsulinEvent(
            id=row.id,
            timestamp=_local_wall_from_utc(row.timestamp),
            insulin_units=row.insulin_units,
            event_type=row.event_type,
            insulin_type=row.insulin_type,
            notes=row.notes,
        )
        for row in rows
        if row.id != exclude_insulin_id
        and is_rapid_insulin_event(
            insulin_type=row.insulin_type,
            event_type=row.event_type,
        )
    ]
    units, _ = _remaining_on_board(
        events,
        as_of=as_of,
        duration_minutes=dia_minutes,
        amount=lambda event: event.insulin_units,
        decay="insulin_pd",
        insulin_kernel=kernel,
    )
    return units
