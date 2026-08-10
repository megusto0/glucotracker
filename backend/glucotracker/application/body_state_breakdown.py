"""Detailed, read-only sleep and activity episodes for the mobile diary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.body_states import BodyStateInterval, BodyStateService
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.health_connect_samples import (
    METADATA_MARGIN,
    heart_rate_samples,
    resolve_instant,
)
from glucotracker.application.time import local_wall_time, utc_instant_from_local_wall
from glucotracker.application.top_up_dose import active_iob_units
from glucotracker.infra.db.models import TwinParams
from glucotracker.infra.db.repositories.activity_annotations import (
    ActivityAnnotationRepository,
)
from glucotracker.infra.db.repositories.health_connect import HealthConnectRepository

LOW_MMOL_L = 3.9
HIGH_MMOL_L = 10.0
DETAIL_MATCH_TOLERANCE = timedelta(minutes=15)
POINT_TOLERANCE = timedelta(minutes=20)
ACTIVITY_FOLLOW_UP = timedelta(hours=2)
HISTORY_DAYS = 30
DEFAULT_DIA_MINUTES = 270
NO_STEPS_RULE_MINUTES = 40
STEADY_BAND_BPM = 10.0
STEADY_SUGGESTION_PERCENT = 70
SUGGESTION_MIN_MEAN_BPM = 100

ActivityType = Literal["cycling", "gym", "walking", "other"]
ActivityTypeSource = Literal["user", "recorded", "rule", "none"]
SleepStageKind = Literal["awake", "light", "deep", "rem", "unknown"]
InsightCode = Literal[
    "sleep_low_near_wake",
    "sleep_low",
    "sleep_shorter",
    "sleep_longer",
    "sleep_summary",
    "activity_drop_with_iob",
    "activity_drop",
    "activity_rise",
    "activity_flat",
    "activity_no_glucose",
]


@dataclass(frozen=True)
class BodyStatePoint:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class SleepStage:
    stage: SleepStageKind
    start_at: datetime
    end_at: datetime
    minutes: int


@dataclass(frozen=True)
class BodyStateBreakdown:
    kind: Literal["sleep", "activity"]
    source: Literal["recorded", "heart_rate"]
    start_at: datetime
    end_at: datetime
    total_minutes: int
    label: str | None
    heart_rate_points: list[BodyStatePoint] = field(default_factory=list)
    mean_bpm: float | None = None
    peak_bpm: float | None = None
    sleep_stages: list[SleepStage] = field(default_factory=list)
    glucose_points: list[BodyStatePoint] = field(default_factory=list)
    tir_percent: int | None = None
    low_minutes: int = 0
    steps: int | None = None
    steps_available: bool = False
    steady_percent: int | None = None
    glucose_start: float | None = None
    glucose_after: float | None = None
    glucose_two_hour_minimum: float | None = None
    glucose_delta_two_hours: float | None = None
    iob_start_units: float | None = None
    activity_type: ActivityType | None = None
    activity_type_source: ActivityTypeSource = "none"
    suggested_activity_type: ActivityType | None = None
    remember_no_steps_rule: bool = False
    frequency_count: int = 0
    frequency_days: int = HISTORY_DAYS
    average_duration_minutes: int | None = None
    insight_code: InsightCode = "sleep_summary"
    insight_at: datetime | None = None
    insight_value: float | None = None
    insight_comparison_minutes: int | None = None


class BodyStateBreakdownService:
    """Read one state using only owner-scoped raw and glucose records."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.annotations = ActivityAnnotationRepository(session, user_id)

    def breakdown(
        self,
        *,
        kind: Literal["sleep", "activity"],
        start_at: datetime,
        end_at: datetime,
    ) -> BodyStateBreakdown | None:
        start_at = _wall_clock(start_at)
        end_at = _wall_clock(end_at)
        if end_at <= start_at:
            return None
        state = self._resolve_state(kind, start_at, end_at)
        if state is None:
            return None

        from_utc = utc_instant_from_local_wall(state.start_at)
        to_utc = utc_instant_from_local_wall(state.end_at)
        hr = [
            BodyStatePoint(local_wall_time(at), round(bpm, 1))
            for at, bpm in heart_rate_samples(
                self.session,
                self.user_id,
                from_utc,
                to_utc,
            )
        ]
        hr_values = [point.value for point in hr]
        history = BodyStateService(self.session, self.user_id).intervals(
            state.start_at - timedelta(days=HISTORY_DAYS),
            state.start_at,
        )
        same_kind = [item for item in history if item.kind == kind]
        average_duration = (
            round(sum(item.total_minutes for item in same_kind) / len(same_kind))
            if same_kind
            else None
        )

        if kind == "sleep":
            return self._sleep(
                state,
                hr,
                hr_values,
                same_kind,
                average_duration,
            )
        return self._activity(
            state,
            hr,
            hr_values,
            same_kind,
            average_duration,
        )

    def save_activity_label(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        activity_type: ActivityType,
        remember_no_steps_rule: bool,
    ) -> None:
        start_at = _wall_clock(start_at)
        end_at = _wall_clock(end_at)
        if self._resolve_state("activity", start_at, end_at) is None:
            raise LookupError("Activity interval was not found")
        self.annotations.upsert(
            start_at=start_at,
            end_at=end_at,
            activity_type=activity_type,
            remember_no_steps_rule=remember_no_steps_rule,
        )

    def _resolve_state(
        self,
        kind: Literal["sleep", "activity"],
        start_at: datetime,
        end_at: datetime,
    ) -> BodyStateInterval | None:
        candidates = BodyStateService(self.session, self.user_id).intervals(
            start_at - DETAIL_MATCH_TOLERANCE,
            end_at + DETAIL_MATCH_TOLERANCE,
        )
        matches = [
            state
            for state in candidates
            if state.kind == kind
            and abs(state.start_at - start_at) <= DETAIL_MATCH_TOLERANCE
            and abs(state.end_at - end_at) <= DETAIL_MATCH_TOLERANCE
        ]
        return min(
            matches,
            key=lambda state: abs(state.start_at - start_at)
            + abs(state.end_at - end_at),
            default=None,
        )

    def _glucose(self, start_at: datetime, end_at: datetime) -> list[BodyStatePoint]:
        points = (
            GlucoseDashboardService(self.session, self.user_id)
            .dashboard(start_at, end_at, "normalized")
            .points
        )
        return [
            BodyStatePoint(point.timestamp, round(float(point.display_value), 1))
            for point in points
            if point.display_value is not None
        ]

    def _sleep(
        self,
        state: BodyStateInterval,
        hr: list[BodyStatePoint],
        hr_values: list[float],
        history: list[BodyStateInterval],
        average_duration: int | None,
    ) -> BodyStateBreakdown:
        glucose = self._glucose(state.start_at, state.end_at)
        stages = self._sleep_stages(state.start_at, state.end_at)
        low_minutes = _minutes_in_band(glucose, lambda value: value < LOW_MMOL_L)
        tir = (
            round(
                100
                * sum(LOW_MMOL_L <= point.value <= HIGH_MMOL_L for point in glucose)
                / len(glucose)
            )
            if glucose
            else None
        )
        low_near_wake = _low_near_awake(glucose, stages)
        comparison = (
            state.total_minutes - average_duration
            if average_duration is not None
            else None
        )
        if low_near_wake is not None:
            insight: InsightCode = "sleep_low_near_wake"
            insight_at, insight_value = low_near_wake
        elif low_minutes:
            insight = "sleep_low"
            low = min(glucose, key=lambda point: point.value)
            insight_at, insight_value = low.timestamp, low.value
        elif comparison is not None and comparison <= -20:
            insight = "sleep_shorter"
            insight_at = insight_value = None
        elif comparison is not None and comparison >= 20:
            insight = "sleep_longer"
            insight_at = insight_value = None
        else:
            insight = "sleep_summary"
            insight_at = insight_value = None
        return BodyStateBreakdown(
            kind="sleep",
            source=state.source,
            start_at=state.start_at,
            end_at=state.end_at,
            total_minutes=state.total_minutes,
            label=state.label,
            heart_rate_points=hr,
            mean_bpm=(
                round(sum(hr_values) / len(hr_values), 1)
                if hr_values
                else state.mean_bpm
            ),
            peak_bpm=round(max(hr_values), 1) if hr_values else state.peak_bpm,
            sleep_stages=stages,
            glucose_points=glucose,
            tir_percent=tir,
            low_minutes=low_minutes,
            frequency_count=len(history),
            average_duration_minutes=average_duration,
            insight_code=insight,
            insight_at=insight_at,
            insight_value=insight_value,
            insight_comparison_minutes=comparison,
        )

    def _activity(
        self,
        state: BodyStateInterval,
        hr: list[BodyStatePoint],
        hr_values: list[float],
        history: list[BodyStateInterval],
        average_duration: int | None,
    ) -> BodyStateBreakdown:
        glucose = self._glucose(
            state.start_at - timedelta(minutes=30),
            state.end_at + ACTIVITY_FOLLOW_UP,
        )
        start = _nearest(glucose, state.start_at)
        after = _nearest(glucose, state.end_at)
        follow_up = [
            point
            for point in glucose
            if state.end_at <= point.timestamp <= state.end_at + ACTIVITY_FOLLOW_UP
        ]
        minimum = min(follow_up, key=lambda point: point.value, default=None)
        delta = (
            round(minimum.value - start.value, 1)
            if minimum is not None and start is not None
            else None
        )
        steps, steps_available = self._steps(state.start_at, state.end_at)
        steady = _steady_percent(hr_values)
        annotation = self.annotations.get(state.start_at, state.end_at)
        recorded_type = _recorded_activity_type(state.label)
        remembered = self.annotations.remembered_no_steps_type()
        observed_mean = (
            state.mean_bpm
            or (sum(hr_values) / len(hr_values) if hr_values else 0)
        )
        rule_eligible = (
            not steps_available
            and state.total_minutes >= NO_STEPS_RULE_MINUTES
            and (steady or 0) >= STEADY_SUGGESTION_PERCENT
            and observed_mean >= SUGGESTION_MIN_MEAN_BPM
        )
        if annotation is not None:
            activity_type = annotation.activity_type
            type_source: ActivityTypeSource = "user"
        elif recorded_type is not None:
            activity_type = recorded_type
            type_source = "recorded"
        elif rule_eligible and remembered in {"cycling", "gym", "walking", "other"}:
            activity_type = remembered
            type_source = "rule"
        else:
            activity_type = None
            type_source = "none"
        suggested: ActivityType | None = None
        if activity_type is None and rule_eligible:
            suggested = "cycling"

        params = self.session.scalar(
            select(TwinParams).where(TwinParams.owner_id == self.user_id)
        )
        iob = active_iob_units(
            self.session,
            self.user_id,
            as_of=state.start_at,
            dia_minutes=(
                params.dia_minutes if params is not None else DEFAULT_DIA_MINUTES
            ),
            exclude_insulin_id=None,
        )
        if delta is None:
            insight: InsightCode = "activity_no_glucose"
        elif delta < -0.3 and iob >= 0.1:
            insight = "activity_drop_with_iob"
        elif delta < -0.3:
            insight = "activity_drop"
        elif delta > 0.3:
            insight = "activity_rise"
        else:
            insight = "activity_flat"
        return BodyStateBreakdown(
            kind="activity",
            source=state.source,
            start_at=state.start_at,
            end_at=state.end_at,
            total_minutes=state.total_minutes,
            label=state.label,
            heart_rate_points=hr,
            mean_bpm=(
                round(sum(hr_values) / len(hr_values), 1)
                if hr_values
                else state.mean_bpm
            ),
            peak_bpm=round(max(hr_values), 1) if hr_values else state.peak_bpm,
            glucose_points=glucose,
            steps=steps,
            steps_available=steps_available,
            steady_percent=steady,
            glucose_start=start.value if start else None,
            glucose_after=after.value if after else None,
            glucose_two_hour_minimum=minimum.value if minimum else None,
            glucose_delta_two_hours=delta,
            iob_start_units=round(iob, 1),
            activity_type=activity_type,
            activity_type_source=type_source,
            suggested_activity_type=suggested,
            remember_no_steps_rule=bool(
                annotation and annotation.remember_no_steps_rule
            ),
            frequency_count=len(history),
            average_duration_minutes=average_duration,
            insight_code=insight,
            insight_at=minimum.timestamp if minimum else None,
            insight_value=minimum.value if minimum else None,
        )

    def _sleep_stages(self, start_at: datetime, end_at: datetime) -> list[SleepStage]:
        from_utc = utc_instant_from_local_wall(start_at)
        to_utc = utc_instant_from_local_wall(end_at)
        rows = HealthConnectRepository(
            self.session,
            self.user_id,
        ).list_records_by_type_and_time(
            "SleepSessionRecord",
            from_utc - METADATA_MARGIN,
            to_utc + METADATA_MARGIN,
        )
        result: list[SleepStage] = []
        for row in rows:
            stages = (row.payload or {}).get("stages")
            if not isinstance(stages, list):
                continue
            for raw in stages:
                if not isinstance(raw, dict):
                    continue
                start = resolve_instant(raw.get("startTime"), row)
                end = resolve_instant(raw.get("endTime"), row, fallback_to_end=True)
                if start is None or end is None or end <= start:
                    continue
                local_start = max(start_at, local_wall_time(start))
                local_end = min(end_at, local_wall_time(end))
                if local_end <= local_start:
                    continue
                result.append(
                    SleepStage(
                        stage=_stage_kind(raw.get("stage") or raw.get("stageType")),
                        start_at=local_start,
                        end_at=local_end,
                        minutes=round((local_end - local_start).total_seconds() / 60),
                    )
                )
        return sorted(result, key=lambda stage: (stage.start_at, stage.end_at))

    def _steps(self, start_at: datetime, end_at: datetime) -> tuple[int | None, bool]:
        from_utc = utc_instant_from_local_wall(start_at)
        to_utc = utc_instant_from_local_wall(end_at)
        rows = HealthConnectRepository(
            self.session,
            self.user_id,
        ).list_records_by_type_and_time(
            "StepsRecord",
            from_utc - METADATA_MARGIN,
            to_utc + METADATA_MARGIN,
        )
        total = 0.0
        seen = False
        for row in rows:
            count = _number((row.payload or {}).get("count"))
            record_start = resolve_instant((row.payload or {}).get("startTime"), row)
            record_end = resolve_instant(
                (row.payload or {}).get("endTime"),
                row,
                fallback_to_end=True,
            )
            if count is None or record_start is None or record_end is None:
                continue
            overlap = max(
                timedelta(0),
                min(to_utc, record_end) - max(from_utc, record_start),
            )
            if record_end == record_start:
                if from_utc <= record_start <= to_utc:
                    total += count
                    seen = True
            elif overlap > timedelta(0):
                total += count * overlap.total_seconds() / (
                    record_end - record_start
                ).total_seconds()
                seen = True
        return (round(total), True) if seen else (None, False)


def _wall_clock(value: datetime) -> datetime:
    """Treat API body-state timestamps as the wall-clock identifiers they are."""
    return value.replace(tzinfo=None)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return (
        number
        if number == number and number not in (float("inf"), float("-inf"))
        else None
    )


def _stage_kind(raw: Any) -> SleepStageKind:
    if isinstance(raw, (int, float)):
        return {1: "awake", 4: "light", 5: "deep", 6: "rem"}.get(
            int(raw),
            "unknown",
        )
    text = str(raw or "").lower().replace("stage_", "").replace("sleep_", "")
    if "awake" in text or "out_of_bed" in text:
        return "awake"
    if "light" in text:
        return "light"
    if "deep" in text:
        return "deep"
    if "rem" in text:
        return "rem"
    return "unknown"


def _nearest(
    points: list[BodyStatePoint],
    at: datetime,
) -> BodyStatePoint | None:
    candidate = min(points, key=lambda point: abs(point.timestamp - at), default=None)
    if candidate is None or abs(candidate.timestamp - at) > POINT_TOLERANCE:
        return None
    return candidate


def _minutes_in_band(
    points: list[BodyStatePoint],
    matches,
) -> int:
    minutes = 0.0
    for left, right in zip(points, points[1:], strict=False):
        gap = right.timestamp - left.timestamp
        if gap > timedelta(minutes=10) or gap <= timedelta(0):
            continue
        if matches(left.value) and matches(right.value):
            minutes += gap.total_seconds() / 60
    return round(minutes)


def _low_near_awake(
    glucose: list[BodyStatePoint],
    stages: list[SleepStage],
) -> tuple[datetime, float] | None:
    lows = [point for point in glucose if point.value < LOW_MMOL_L]
    awake = [stage for stage in stages if stage.stage == "awake"]
    candidates = [
        (point, stage)
        for point in lows
        for stage in awake
        if stage.start_at - timedelta(minutes=10)
        <= point.timestamp
        <= stage.end_at + timedelta(minutes=10)
    ]
    if not candidates:
        return None
    point, stage = min(candidates, key=lambda pair: pair[0].value)
    return stage.start_at, point.value


def _steady_percent(values: list[float]) -> int | None:
    if not values:
        return None
    middle = float(median(values))
    inside = sum(abs(value - middle) <= STEADY_BAND_BPM for value in values)
    return round(100 * inside / len(values))


def _recorded_activity_type(label: str | None) -> ActivityType | None:
    text = (label or "").lower()
    if any(token in text for token in ("велосип", "cycling", "bike", "cycle")):
        return "cycling"
    if any(token in text for token in ("зал", "силов", "gym", "strength", "weight")):
        return "gym"
    if any(token in text for token in ("ходь", "walk", "hiking")):
        return "walking"
    return None
