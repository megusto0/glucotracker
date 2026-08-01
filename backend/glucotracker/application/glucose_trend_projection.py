"""Where glucose is heading, as a dose input.

A reading of 7.0 that is falling and a reading of 7.0 that is rising need
different insulin, and a 15-minute straight-line extrapolation cannot tell them
apart once carbohydrate absorption and insulin action are both in play. The
prospective forecast already models exactly that counterfactual — its stated
assumption is "no new food or insulin", which is precisely "where do I end up if
I dose nothing extra".

This module turns the newest stored forecast into a single projected glucose
value, after correcting it against the owner's own evaluated forecast history.
Two properties of that history drive the design:

- The forecast is directionally reliable but magnitude-shy. Regressed on 897
  in-range 60-minute outcomes, ``actual_move = 1.50 * predicted_move``, so the
  raw forecast understates the move it is describing. The factor is refitted per
  owner rather than hard-coded, so it tracks the model as it changes.
- Reliability is not symmetric. On the same history a predicted fall of more
  than 1 mmol/L was directionally right 81% of the time, while a predicted rise
  of 0.5-1.0 mmol/L was right 74% at 60 minutes and only 33% at 90. Predicting a
  fall and dosing less is the recoverable error; predicting a rise and dosing
  more is not. Upward projection is therefore capped far more tightly than
  downward, and small predicted moves are ignored in both directions.

Nothing here produces an insulin number on its own; it produces the glucose
value the existing correction arithmetic should be reasoning about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.glucose_prediction import (
    AUDIT_CALIBRATION_SOURCE_VERSIONS,
)
from glucotracker.infra.db.models import (
    GlucosePredictionPointAudit,
    GlucosePredictionRun,
)

# Insulin reaches roughly half its action by this point, so it is the horizon a
# correction is really aimed at.
DEFAULT_PROJECTION_HORIZON_MINUTES = 60
# A forecast anchored further back than this describes a different situation.
MAX_FORECAST_AGE = timedelta(minutes=20)
# Below this the predicted move is inside the model's own noise.
MIN_ACTIONABLE_MOVE_MMOL_L = 0.5
# Asymmetric trust: a predicted fall may reduce a dose substantially, a
# predicted rise may only ever nudge one up.
MAX_DOWNWARD_PROJECTION_MMOL_L = 3.0
MAX_UPWARD_PROJECTION_MMOL_L = 1.0

CALIBRATION_LOOKBACK_DAYS = 21
CALIBRATION_MIN_SAMPLES = 40
CALIBRATION_FULL_STRENGTH_SAMPLES = 200
CALIBRATION_MIN_FACTOR = 0.5
CALIBRATION_MAX_FACTOR = 2.5

ProjectionStatus = Literal[
    "ready",
    "no_forecast",
    "forecast_stale",
    "move_below_threshold",
]


@dataclass(frozen=True)
class TrendProjection:
    """Projected glucose at the correction horizon, with its provenance."""

    status: ProjectionStatus
    horizon_minutes: int
    anchor_mmol_l: float | None = None
    anchor_at: datetime | None = None
    raw_predicted_mmol_l: float | None = None
    projected_mmol_l: float | None = None
    calibration_factor: float = 1.0
    calibration_samples: int = 0
    capped: bool = False
    model_version: str | None = None

    @property
    def is_usable(self) -> bool:
        """Return whether a caller may substitute this for a flat projection."""
        return self.status == "ready" and self.projected_mmol_l is not None

    @property
    def move_mmol_l(self) -> float | None:
        """Return the applied move against the forecast anchor."""
        if self.projected_mmol_l is None or self.anchor_mmol_l is None:
            return None
        return self.projected_mmol_l - self.anchor_mmol_l


class GlucoseTrendProjectionService:
    """Project glucose forward for dosing using the stored forecast."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def project(
        self,
        at: datetime,
        *,
        horizon_minutes: int = DEFAULT_PROJECTION_HORIZON_MINUTES,
    ) -> TrendProjection:
        """Return the calibrated projection for a dose decision at ``at``.

        Only forecasts anchored at or before ``at`` are considered, so a
        retrospective review cannot borrow a forecast made after the event.
        """
        at = _as_utc(at)
        run = self.session.scalar(
            select(GlucosePredictionRun)
            .where(
                GlucosePredictionRun.owner_id == self.user_id,
                GlucosePredictionRun.anchor_timestamp <= at,
                GlucosePredictionRun.anchor_timestamp >= at - MAX_FORECAST_AGE,
            )
            .order_by(GlucosePredictionRun.anchor_timestamp.desc())
            .limit(1)
        )
        if run is None:
            return TrendProjection(
                status="no_forecast",
                horizon_minutes=horizon_minutes,
            )

        anchor_at = _as_utc(run.anchor_timestamp)
        if at - anchor_at > MAX_FORECAST_AGE:
            return TrendProjection(
                status="forecast_stale",
                horizon_minutes=horizon_minutes,
                anchor_at=anchor_at,
                model_version=run.model_version,
            )

        point = self.session.scalar(
            select(GlucosePredictionPointAudit).where(
                GlucosePredictionPointAudit.run_id == run.id,
                GlucosePredictionPointAudit.horizon_minutes == horizon_minutes,
            )
        )
        if point is None:
            return TrendProjection(
                status="no_forecast",
                horizon_minutes=horizon_minutes,
                anchor_at=anchor_at,
                model_version=run.model_version,
            )

        anchor_value = float(run.anchor_value_mmol_l)
        raw_predicted = float(point.predicted_value_mmol_l)
        factor, samples = self._calibration_factor(anchor_at, horizon_minutes)
        move = (raw_predicted - anchor_value) * factor

        if abs(move) < MIN_ACTIONABLE_MOVE_MMOL_L:
            return TrendProjection(
                status="move_below_threshold",
                horizon_minutes=horizon_minutes,
                anchor_mmol_l=anchor_value,
                anchor_at=anchor_at,
                raw_predicted_mmol_l=raw_predicted,
                calibration_factor=factor,
                calibration_samples=samples,
                model_version=run.model_version,
            )

        limited = max(
            -MAX_DOWNWARD_PROJECTION_MMOL_L,
            min(MAX_UPWARD_PROJECTION_MMOL_L, move),
        )
        return TrendProjection(
            status="ready",
            horizon_minutes=horizon_minutes,
            anchor_mmol_l=anchor_value,
            anchor_at=anchor_at,
            raw_predicted_mmol_l=raw_predicted,
            projected_mmol_l=round(anchor_value + limited, 2),
            calibration_factor=factor,
            calibration_samples=samples,
            capped=abs(limited - move) > 1e-9,
            model_version=run.model_version,
        )

    def _calibration_factor(
        self,
        before: datetime,
        horizon_minutes: int,
    ) -> tuple[float, int]:
        """Fit how far the forecast under- or over-states its own moves.

        Regresses the observed move on the predicted move over already-evaluated
        forecasts strictly older than ``before``, then shrinks toward 1.0 so a
        thin history cannot swing a dose.
        """
        rows = self.session.execute(
            select(
                GlucosePredictionRun.anchor_value_mmol_l,
                GlucosePredictionPointAudit.predicted_value_mmol_l,
                GlucosePredictionPointAudit.actual_value_mmol_l,
            )
            .join(
                GlucosePredictionPointAudit,
                GlucosePredictionPointAudit.run_id == GlucosePredictionRun.id,
            )
            .where(
                GlucosePredictionRun.owner_id == self.user_id,
                GlucosePredictionPointAudit.owner_id == self.user_id,
                GlucosePredictionRun.model_version.in_(
                    AUDIT_CALIBRATION_SOURCE_VERSIONS
                ),
                GlucosePredictionPointAudit.horizon_minutes == horizon_minutes,
                GlucosePredictionPointAudit.evaluation_status == "evaluated",
                GlucosePredictionPointAudit.actual_value_mmol_l.is_not(None),
                GlucosePredictionRun.anchor_timestamp < before,
                GlucosePredictionRun.anchor_timestamp
                >= before - timedelta(days=CALIBRATION_LOOKBACK_DAYS),
            )
        ).all()
        if len(rows) < CALIBRATION_MIN_SAMPLES:
            return 1.0, len(rows)

        anchors = np.asarray([float(r[0]) for r in rows])
        predicted = np.asarray([float(r[1]) for r in rows]) - anchors
        actual = np.asarray([float(r[2]) for r in rows]) - anchors
        denominator = float(predicted @ predicted)
        if denominator <= 1e-9:
            return 1.0, len(rows)

        # Slope through the origin: a forecast of no move must stay no move.
        fitted = float(predicted @ actual) / denominator
        strength = min(
            1.0,
            max(
                0.0,
                (len(rows) - CALIBRATION_MIN_SAMPLES)
                / (CALIBRATION_FULL_STRENGTH_SAMPLES - CALIBRATION_MIN_SAMPLES),
            ),
        )
        shrunk = 1.0 + strength * (fitted - 1.0)
        return (
            round(
                max(CALIBRATION_MIN_FACTOR, min(CALIBRATION_MAX_FACTOR, shrunk)),
                3,
            ),
            len(rows),
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
