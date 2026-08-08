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
from glucotracker.application.glucose_trend_projection import (
    GlucoseTrendProjectionService,
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

LOOKBACK_MINUTES = 30
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
    carb_units: float | None = None
    correction_units: float | None = None
    icr_g_per_unit: float | None = None
    isf_mmol_l_per_unit: float | None = None
    isf_source: Literal["manual", "fitted", "default"] | None = None
    note: str | None = None


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
            )

        twin_params = TwinRepository(
            self.session,
            self.user_id,
        ).get_or_create_params(persist=False)
        iob_units = _active_iob_units(
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
            )

        # Prefer where the curve is heading over where it currently sits; the
        # projection is already asymmetric and refuses to overstate a rise.
        projection = GlucoseTrendProjectionService(
            self.session,
            self.user_id,
        ).project(now)
        projected = glucose
        projection_source: Literal["none", "linear_trend", "forecast"] = "none"
        if projection.is_usable and projection.projected_mmol_l is not None:
            projected = glucose + (projection.move_mmol_l or 0.0)
            projection_source = "forecast"

        context = {
            "glucose_mmol_l": round(glucose, 1),
            "projected_glucose_mmol_l": round(projected, 1),
            "projection_source": projection_source,
            "target_mmol_l": round(target, 1),
            "cob_g": round(summary.cob_g, 1),
            "iob_units": round(iob_units, 2),
            "icr_g_per_unit": round(icr, 1),
            "isf_mmol_l_per_unit": round(isf, 2),
            "isf_source": isf_source,
        }

        if glucose < LOW_GLUCOSE_MMOL_L or projected < LOW_GLUCOSE_MMOL_L:
            return TopUpSuggestion(
                status="low_or_falling",
                note="Глюкоза низкая или снижается — добавка не рассчитывается.",
                **context,
            )

        carb_units = summary.cob_g / icr
        correction_units = (projected - target) / isf

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
        contradicted = (
            net < MIN_SUGGESTION_UNITS
            and min(glucose, projected) > TIR_HIGH_MMOL_L
        )
        if contradicted:
            net = correction_units

        rounded = {
            "carb_units": round(carb_units, 2),
            "correction_units": round(correction_units, 2),
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


def _minutes(value: int):
    from datetime import timedelta

    return timedelta(minutes=value)


def _active_iob_units(
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
