"""Energy spent in a day's efforts, read from the heart rate.

The wearable no longer writes calories to Health Connect: since the switch to
the Gadgetbridge bridge only heart rate, steps and sleep arrive. Health
Connect then reports a basal-only "total" that the energy model rightly
rejects, and a four-hour ride used to count as a few hundred steps.

So the effort spans the body-state reader already finds — recorded workouts
and sustained heart-rate climbs, pauses included — are priced minute by minute
with Keytel's heart-rate equation, less the resting metabolism the day's base
already counts. Keytel's equation was fitted on exercise; at the heart rate of
a stop at the lights or an easy stroll it overstates the cost several times
over. So below the effort threshold the detector uses, the credit tapers off
linearly and reaches nothing at the flex point (resting + 15 bpm), below which
heart rate says little about energy. Steps taken inside the spans are reported
too, so walking is not counted twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.application.body_states import (
    HR_CONTEXT,
    INTENSE_ABOVE_RESTING_BPM,
    MIN_INTENSE_BPM,
    RESTING_PERCENTILE,
    BodyStateService,
)
from glucotracker.application.health_connect_samples import (
    METADATA_MARGIN,
    heart_rate_samples,
    resolve_instant,
)
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.domain.energy import (
    FLEX_HR_OFFSET,
    KCAL_PER_MIN_CAP,
    MINUTES_PER_DAY,
    bmr_mifflin_st_jeor,
    keypoint_kcal_per_min,
)
from glucotracker.infra.db.models import UserProfile
from glucotracker.infra.db.repositories.health_connect import (
    HealthConnectRepository,
)

# A reading stands for the time until the next one, but not forever: a strap
# that drops out for twenty minutes did not record twenty minutes of effort.
MAX_SAMPLE_SPAN = timedelta(minutes=5)


@dataclass(frozen=True)
class ActivityEffort:
    """What a day's effort spans add on top of resting metabolism."""

    kcal: float
    minutes: int
    steps: int


class ActivityEnergyService:
    """Price one owner's effort spans for a local calendar day."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def for_day(self, day: date, profile: UserProfile) -> ActivityEffort | None:
        if (
            profile.weight_kg is None
            or profile.height_cm is None
            or profile.age_years is None
            or profile.sex not in ("male", "female")
        ):
            return None
        local_from = datetime.combine(day, time.min)
        local_to = local_from + timedelta(days=1)
        spans = [
            (
                utc_instant_from_local_wall(state.start_at),
                utc_instant_from_local_wall(state.end_at),
            )
            for state in BodyStateService(self.session, self.user_id).intervals(
                local_from,
                local_to,
            )
            if state.kind == "activity"
        ]
        if not spans:
            return ActivityEffort(kcal=0.0, minutes=0, steps=0)

        from_utc = utc_instant_from_local_wall(local_from)
        to_utc = utc_instant_from_local_wall(local_to)
        context = heart_rate_samples(
            self.session,
            self.user_id,
            from_utc - HR_CONTEXT,
            to_utc + HR_CONTEXT,
        )
        if not context:
            return ActivityEffort(kcal=0.0, minutes=0, steps=0)
        values = sorted(bpm for _, bpm in context)
        resting = values[min(len(values) - 1, int(RESTING_PERCENTILE * len(values)))]
        flex = resting + FLEX_HR_OFFSET
        effort = max(MIN_INTENSE_BPM, resting + INTENSE_ABOVE_RESTING_BPM, flex + 1)
        basal_per_minute = (
            bmr_mifflin_st_jeor(
                profile.weight_kg,
                profile.height_cm,
                profile.age_years,
                profile.sex,
            )
            / MINUTES_PER_DAY
        )

        kcal = 0.0
        minutes = 0.0
        for start, end in spans:
            inside = [(at, bpm) for at, bpm in context if start <= at <= end]
            for index, (at, bpm) in enumerate(inside):
                following = inside[index + 1][0] if index + 1 < len(inside) else end
                span = min(following - at, MAX_SAMPLE_SPAN).total_seconds() / 60
                minutes += span
                if bpm <= flex:
                    continue
                share = min(1.0, (bpm - flex) / (effort - flex))
                gross = min(
                    keypoint_kcal_per_min(
                        round(max(bpm, effort)),
                        profile.weight_kg,
                        profile.age_years,
                        profile.sex,
                    ),
                    KCAL_PER_MIN_CAP,
                )
                kcal += share * max(0.0, gross - basal_per_minute) * span
        return ActivityEffort(
            kcal=round(kcal, 1),
            minutes=round(minutes),
            steps=self._steps_inside(spans),
        )

    def _steps_inside(self, spans: list[tuple[datetime, datetime]]) -> int:
        """Steps counted inside the spans, by the source that saw the most.

        The phone and the strap both write steps for the same minutes; adding
        them up would double the walking taken back out of the day.
        """
        rows = HealthConnectRepository(
            self.session,
            self.user_id,
        ).list_records_by_type_and_time(
            "StepsRecord",
            spans[0][0] - METADATA_MARGIN,
            spans[-1][1] + METADATA_MARGIN,
        )
        by_origin: dict[str, float] = {}
        for row in rows:
            payload: dict[str, Any] = row.payload or {}
            count = payload.get("count")
            start = resolve_instant(payload.get("startTime"), row)
            end = resolve_instant(payload.get("endTime"), row, fallback_to_end=True)
            if not isinstance(count, (int, float)) or start is None or end is None:
                continue
            length = (end - start).total_seconds()
            for span_start, span_end in spans:
                if length <= 0:
                    share = 1.0 if span_start <= start <= span_end else 0.0
                else:
                    overlap = (
                        min(end, span_end) - max(start, span_start)
                    ).total_seconds()
                    share = max(0.0, overlap) / length
                if share > 0:
                    origin = row.data_origin or ""
                    by_origin[origin] = by_origin.get(origin, 0.0) + count * share
        return round(max(by_origin.values(), default=0.0))
