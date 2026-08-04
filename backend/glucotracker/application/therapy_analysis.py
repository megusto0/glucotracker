"""Long-term retrospective ICR and ISF analysis by time of day.

The analysis deliberately uses completed, isolated therapy episodes.  It is
descriptive evidence from the past, not a prospective dose recommendation.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from statistics import median
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.api.schemas import GlucoseDashboardPoint
from glucotracker.application.body_states import BodyStateService
from glucotracker.application.episode_therapy import (
    TherapyClass,
    TherapyConfidence,
    classify_episode_therapy,
)
from glucotracker.application.episodes import (
    EpisodeComponent,
    EpisodeQueryService,
)
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.icr_autotune import (
    EXERCISE_EXCLUSION,
    Daypart,
    IcrEpisode,
    daypart_of,
    propose,
)
from glucotracker.application.insulin_recommendation import (
    DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT,
    _trusted_isf,
)
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import (
    is_rapid_insulin_event,
)
from glucotracker.application.time import (
    local_now,
    local_wall_time,
    utc_instant_from_local_wall,
)
from glucotracker.infra.db.repositories.health_connect import (
    HealthConnectRepository,
)
from glucotracker.infra.db.repositories.twin import TwinRepository

AnalysisConfidence = Literal["none", "low", "medium", "high"]
IsfSource = Literal["correction_episodes", "configured_fallback"]
IsfIdentifiability = Literal["identified", "thin", "not_identified"]
BasalSignal = Literal["insufficient", "stable", "rising", "falling"]

# v3: measured ratios are compared against the configured slots, episodes near
# effort are excluded, and ISF says how thin its evidence is.
THERAPY_ANALYSIS_MODEL_VERSION = "retrospective-therapy-analysis-v3"
# Below this many isolated corrections the ISF median is an estimate rather
# than a measurement, and the page must say so.
MIN_ISF_EPISODES_FOR_CONFIDENCE = 12
ICR_HORIZON_MINUTES = 120
ISF_HORIZON_MINUTES = 240
BIN_HOURS = 4
BACKGROUND_WINDOW_MINUTES = 60
BACKGROUND_WASHOUT_MINUTES = 240
BACKGROUND_POINT_TOLERANCE = timedelta(minutes=15)
MIN_BACKGROUND_GLUCOSE = 3.0
MAX_BACKGROUND_GLUCOSE = 15.0
MAX_BACKGROUND_DRIFT = 5.0
MIN_HR_SAMPLES_PER_WINDOW = 3
MIN_ELEVATED_HR_BPM = 80.0
ELEVATED_HR_ABOVE_RESTING_BPM = 20.0
BACKGROUND_SIGNAL_THRESHOLD = 0.5
MIN_ICR = 3.0
MAX_ICR = 40.0
MIN_ISF = 0.2
MAX_ISF = 8.0


@dataclass(frozen=True)
class TherapyAnalysisMetric:
    """Robust distribution summary for one parameter."""

    value: float | None
    q1: float | None
    q3: float | None
    sample_count: int
    confidence: AnalysisConfidence


@dataclass(frozen=True)
class TherapyAnalysisSlot:
    """ICR and ISF evidence for one local-time bin."""

    start_hour: int
    end_hour: int
    label: str
    icr_g_per_unit: TherapyAnalysisMetric
    isf_mmol_l_per_unit: TherapyAnalysisMetric


@dataclass(frozen=True)
class TherapyBasalSlot:
    """Background glucose drift evidence for one local clock hour."""

    hour: int
    label: str
    quiet_drift_mmol_l_per_hour: TherapyAnalysisMetric
    elevated_hr_drift_mmol_l_per_hour: TherapyAnalysisMetric
    unknown_hr_drift_mmol_l_per_hour: TherapyAnalysisMetric
    signal: BasalSignal


@dataclass(frozen=True)
class TherapyBasalProfile:
    """Twenty-four-hour background drift profile with activity separated."""

    window_minutes: int
    washout_minutes: int
    resting_reference_bpm: float | None
    elevated_hr_threshold_bpm: float | None
    quiet_window_count: int
    elevated_hr_window_count: int
    unknown_hr_window_count: int
    slots: list[TherapyBasalSlot]


@dataclass(frozen=True)
class IcrDaypartComparison:
    """What is configured for a slot against what its outcomes imply."""

    daypart: Daypart
    label: str
    start_hour: int
    end_hour: int
    configured_icr_g_per_unit: float | None
    measured_icr_g_per_unit: float | None
    proposed_icr_g_per_unit: float | None
    episode_count: int
    confidence: AnalysisConfidence
    capped: bool
    note: str | None


@dataclass(frozen=True)
class TherapyAnalysis:
    """Complete long-term therapy analysis response."""

    from_date: date
    to_date: date
    period_days: int
    target_mmol_l: float
    icr_horizon_minutes: int
    isf_horizon_minutes: int
    bin_hours: int
    overall_icr_g_per_unit: TherapyAnalysisMetric
    overall_isf_mmol_l_per_unit: TherapyAnalysisMetric
    isf_source: IsfSource
    slots: list[TherapyAnalysisSlot]
    basal_profile: TherapyBasalProfile
    computed_at: datetime
    model_version: str
    # ISF is structurally harder to see than ICR: it needs a correction with no
    # food anywhere near it, and most boluses sit beside a meal. Printing a
    # number without saying how thin the evidence was invites acting on noise.
    isf_identifiability: IsfIdentifiability = "not_identified"
    isf_note: str = ""
    isf_correction_count: int = 0
    #: Measured against what is actually configured, on the configured slots.
    icr_proposals: list[IcrDaypartComparison] = field(default_factory=list)
    icr_excluded_for_activity: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Evidence:
    timestamp: datetime
    value: float
    #: Carbohydrates behind this episode; larger plates carry more evidence.
    weight: float = 1.0


@dataclass(frozen=True)
class _Candidate:
    key: str
    timestamp: datetime
    classification: TherapyClass
    confidence: TherapyConfidence
    carbs_g: float
    insulin_units: float
    glucose_start: float | None
    glucose_plus_2h: float | None
    glucose_plus_4h: float | None


@dataclass(frozen=True)
class _BackgroundWindow:
    timestamp: datetime
    drift_mmol_l_per_hour: float
    heart_rate_group: Literal["quiet", "elevated", "unknown"]


class TherapyAnalysisService:
    """Aggregate owner-scoped completed episodes into time-of-day evidence."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.episodes = EpisodeQueryService(session, user_id)
        self.dashboard = GlucoseDashboardService(session, user_id)

    def analyze(
        self,
        *,
        period_days: int,
        target_mmol_l: float,
        to_date: date | None = None,
    ) -> TherapyAnalysis:
        """Return completed clean episodes over the requested trailing period."""
        today = local_now().date()
        period_end = min(to_date or today, today)
        period_start = period_end - timedelta(days=period_days - 1)
        context_start = period_start - timedelta(days=1)
        context_end = period_end + timedelta(days=1)

        components = self.episodes.components(
            datetime.combine(context_start, time.min),
            datetime.combine(context_end + timedelta(days=1), time.min),
        )
        points = self._analysis_points(
            datetime.combine(context_start, time.min) - timedelta(minutes=30),
            datetime.combine(context_end + timedelta(days=1), time.min)
            + timedelta(hours=4),
        )
        candidates = sorted(
            (
                self._candidate(
                    component,
                    _points_near(points, component.start_at),
                )
                for component in components
                if context_start <= component.start_at.date() <= context_end
            ),
            key=lambda item: item.timestamp,
        )
        period_candidates = [
            item
            for item in candidates
            if period_start <= item.timestamp.date() <= period_end
        ]

        isf_evidence = self._isf_evidence(
            period_candidates,
            candidates,
            target_mmol_l,
        )
        overall_isf = _metric([item.value for item in isf_evidence])
        params = TwinRepository(
            self.session,
            self.user_id,
        ).get_or_create_params(persist=False)
        fallback_isf = (
            _trusted_isf(params) or DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT
        )
        isf_source: IsfSource = (
            "correction_episodes"
            if overall_isf.value is not None
            else "configured_fallback"
        )
        analysis_isf = overall_isf.value or fallback_isf

        slot_isf = {
            start_hour: _metric(
                [
                    item.value
                    for item in isf_evidence
                    if _slot_start(item.timestamp.hour) == start_hour
                ]
            )
            for start_hour in range(0, 24, BIN_HOURS)
        }
        active_spans = self._active_spans(period_start, period_end)
        icr_evidence, excluded_for_activity = self._icr_evidence(
            period_candidates,
            candidates,
            target_mmol_l,
            analysis_isf,
            slot_isf,
            active_spans,
        )
        overall_icr = _metric([item.value for item in icr_evidence])
        icr_proposals = _icr_proposals(icr_evidence, params)
        basal_profile = self._basal_profile(
            period_start=period_start,
            period_end=period_end,
            points=points,
            components=components,
        )

        slots = []
        for start_hour in range(0, 24, BIN_HOURS):
            end_hour = start_hour + BIN_HOURS
            slots.append(
                TherapyAnalysisSlot(
                    start_hour=start_hour,
                    end_hour=end_hour,
                    label=f"{start_hour:02d}:00–{end_hour:02d}:00",
                    icr_g_per_unit=_metric(
                        [
                            item.value
                            for item in icr_evidence
                            if _slot_start(item.timestamp.hour) == start_hour
                        ]
                    ),
                    isf_mmol_l_per_unit=slot_isf[start_hour],
                )
            )

        notes = [
            (
                "ICR: еда или перекус с инсулином, известным исходом и без "
                "другого вмешательства за 2 часа до и после."
            ),
            (
                "ISF: отдельная коррекция инсулином при повышенной глюкозе, "
                "без еды или другого вмешательства за 4 часа до и после."
            ),
            (
                "Фоновый профиль: изменение нормализованной глюкозы за час "
                "без углеводов и быстрого инсулина в предыдущие 4 часа."
            ),
            (
                "Часы с повышенным пульсом показаны отдельно и не формируют "
                "сигнал фоновой стабильности."
            ),
            "Значение — медиана; диапазон — межквартильный интервал.",
        ]
        if isf_source == "configured_fallback":
            notes.append(
                "Чистых коррекций для ISF не найдено; при поправке ICR "
                f"использован текущий ISF {analysis_isf:.2f}."
            )
        if excluded_for_activity:
            notes.append(
                f"Исключено рядом с нагрузкой: {excluded_for_activity} "
                "приёмов — эффект тренировки больше, чем эта оценка способна "
                "отделить."
            )

        correction_count = sum(
            item.classification == "insulin_correction"
            for item in period_candidates
        )
        identifiability, isf_note = _isf_identifiability(
            isolated=overall_isf.sample_count,
            corrections=correction_count,
        )

        return TherapyAnalysis(
            from_date=period_start,
            to_date=period_end,
            period_days=period_days,
            target_mmol_l=round(target_mmol_l, 1),
            icr_horizon_minutes=ICR_HORIZON_MINUTES,
            isf_horizon_minutes=ISF_HORIZON_MINUTES,
            bin_hours=BIN_HOURS,
            overall_icr_g_per_unit=overall_icr,
            overall_isf_mmol_l_per_unit=overall_isf,
            isf_source=isf_source,
            isf_identifiability=identifiability,
            isf_note=isf_note,
            isf_correction_count=correction_count,
            icr_proposals=icr_proposals,
            icr_excluded_for_activity=excluded_for_activity,
            slots=slots,
            basal_profile=basal_profile,
            computed_at=datetime.now(UTC),
            model_version=THERAPY_ANALYSIS_MODEL_VERSION,
            notes=notes,
        )

    def _active_spans(
        self,
        period_start: date,
        period_end: date,
    ) -> list[tuple[datetime, datetime]]:
        """Return effort windows widened by the exclusion margin, in local time."""
        states = BodyStateService(self.session, self.user_id).intervals(
            datetime.combine(period_start, time.min),
            datetime.combine(period_end + timedelta(days=1), time.min),
        )
        return [
            (
                state.start_at - EXERCISE_EXCLUSION,
                state.end_at + EXERCISE_EXCLUSION,
            )
            for state in states
            if state.kind == "activity"
        ]

    def _basal_profile(
        self,
        *,
        period_start: date,
        period_end: date,
        points: list[GlucoseDashboardPoint],
        components: list[EpisodeComponent],
    ) -> TherapyBasalProfile:
        """Summarize clean one-hour glucose drift by local clock hour."""
        heart_rate_samples = self._heart_rate_samples(
            datetime.combine(period_start, time.min),
            datetime.combine(period_end + timedelta(days=1), time.min),
        )
        heart_rates = [bpm for _, bpm in heart_rate_samples]
        resting_reference = (
            _percentile(sorted(heart_rates), 0.25) if heart_rates else None
        )
        elevated_threshold = (
            max(
                MIN_ELEVATED_HR_BPM,
                resting_reference + ELEVATED_HR_ABOVE_RESTING_BPM,
            )
            if resting_reference is not None
            else None
        )
        heart_rate_by_hour: dict[datetime, list[float]] = defaultdict(list)
        for timestamp, bpm in heart_rate_samples:
            hour = timestamp.replace(minute=0, second=0, microsecond=0)
            heart_rate_by_hour[hour].append(bpm)

        intervention_times = sorted(
            {
                meal.eaten_at
                for component in components
                for meal in component.meals
            }
            | {
                _local_wall_time(event.timestamp)
                for component in components
                for event in component.insulin
                if is_rapid_insulin_event(
                    insulin_type=event.insulin_type,
                    event_type=event.event_type,
                )
            }
        )
        point_times = [point.timestamp for point in points]
        windows: list[_BackgroundWindow] = []
        day = period_start
        while day <= period_end:
            for hour in range(24):
                start_at = datetime.combine(day, time(hour=hour))
                end_at = start_at + timedelta(
                    minutes=BACKGROUND_WINDOW_MINUTES
                )
                if _contains_timestamp(
                    intervention_times,
                    start_at - timedelta(minutes=BACKGROUND_WASHOUT_MINUTES),
                    end_at,
                ):
                    continue
                start = _nearest_indexed(points, point_times, start_at)
                end = _nearest_indexed(points, point_times, end_at)
                if start is None or end is None or start.timestamp == end.timestamp:
                    continue
                start_value = _point_value(start)
                end_value = _point_value(end)
                elapsed_hours = (
                    end.timestamp - start.timestamp
                ).total_seconds() / 3600
                if (
                    start_value is None
                    or end_value is None
                    or elapsed_hours < 0.5
                    or not MIN_BACKGROUND_GLUCOSE
                    <= start_value
                    <= MAX_BACKGROUND_GLUCOSE
                    or not MIN_BACKGROUND_GLUCOSE
                    <= end_value
                    <= MAX_BACKGROUND_GLUCOSE
                ):
                    continue
                drift = (end_value - start_value) / elapsed_hours
                if abs(drift) > MAX_BACKGROUND_DRIFT:
                    continue
                hr_values = heart_rate_by_hour.get(start_at, [])
                heart_rate_group = _heart_rate_group(
                    hr_values,
                    elevated_threshold,
                )
                windows.append(
                    _BackgroundWindow(
                        timestamp=start_at,
                        drift_mmol_l_per_hour=drift,
                        heart_rate_group=heart_rate_group,
                    )
                )
            day += timedelta(days=1)

        slots: list[TherapyBasalSlot] = []
        for hour in range(24):
            hour_windows = [
                window for window in windows if window.timestamp.hour == hour
            ]
            quiet = _metric(
                [
                    window.drift_mmol_l_per_hour
                    for window in hour_windows
                    if window.heart_rate_group == "quiet"
                ]
            )
            slots.append(
                TherapyBasalSlot(
                    hour=hour,
                    label=f"{hour:02d}:00",
                    quiet_drift_mmol_l_per_hour=quiet,
                    elevated_hr_drift_mmol_l_per_hour=_metric(
                        [
                            window.drift_mmol_l_per_hour
                            for window in hour_windows
                            if window.heart_rate_group == "elevated"
                        ]
                    ),
                    unknown_hr_drift_mmol_l_per_hour=_metric(
                        [
                            window.drift_mmol_l_per_hour
                            for window in hour_windows
                            if window.heart_rate_group == "unknown"
                        ]
                    ),
                    signal=_background_signal(quiet),
                )
            )

        return TherapyBasalProfile(
            window_minutes=BACKGROUND_WINDOW_MINUTES,
            washout_minutes=BACKGROUND_WASHOUT_MINUTES,
            resting_reference_bpm=(
                round(resting_reference, 1)
                if resting_reference is not None
                else None
            ),
            elevated_hr_threshold_bpm=(
                round(elevated_threshold, 1)
                if elevated_threshold is not None
                else None
            ),
            quiet_window_count=sum(
                window.heart_rate_group == "quiet" for window in windows
            ),
            elevated_hr_window_count=sum(
                window.heart_rate_group == "elevated" for window in windows
            ),
            unknown_hr_window_count=sum(
                window.heart_rate_group == "unknown" for window in windows
            ),
            slots=slots,
        )

    def _heart_rate_samples(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[tuple[datetime, float]]:
        """Read owner-scoped embedded Heart Connect samples in local time."""
        from_utc = utc_instant_from_local_wall(from_datetime)
        to_utc = utc_instant_from_local_wall(to_datetime)
        margin = timedelta(days=1)
        records = HealthConnectRepository(
            self.session,
            self.user_id,
        ).list_records_by_type_and_time(
            "HeartRateRecord",
            from_utc - margin,
            to_utc + margin,
        )
        samples_by_time: dict[datetime, float] = {}
        for record in records:
            samples = record.payload.get("samples")
            if not isinstance(samples, list):
                continue
            for sample in samples:
                if not isinstance(sample, dict):
                    continue
                timestamp = _payload_timestamp(sample.get("time"))
                bpm = _finite_number(sample.get("beatsPerMinute"))
                if (
                    timestamp is None
                    or bpm is None
                    or bpm < 25
                    or bpm > 240
                    or timestamp < from_utc
                    or timestamp >= to_utc
                ):
                    continue
                samples_by_time[timestamp] = bpm
        return [
            (local_wall_time(timestamp), bpm)
            for timestamp, bpm in sorted(samples_by_time.items())
        ]

    def _analysis_points(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[GlucoseDashboardPoint]:
        """Normalize each historical sensor with its own calibration model."""
        sensors = [
            sensor
            for sensor in self.dashboard.list_sensors()
            if not sensor.excluded_from_analytics
            and _local_wall_time(sensor.started_at) <= to_datetime
            and (
                sensor.ended_at is None
                or _local_wall_time(sensor.ended_at) >= from_datetime
            )
        ]
        if not sensors:
            return self.dashboard.dashboard(
                from_datetime,
                to_datetime,
                "raw",
            ).points

        by_timestamp: dict[datetime, GlucoseDashboardPoint] = {}
        for sensor in sensors:
            segment_from = max(
                from_datetime,
                _local_wall_time(sensor.started_at),
            )
            segment_to = min(
                to_datetime,
                _local_wall_time(sensor.ended_at)
                if sensor.ended_at is not None
                else to_datetime,
            )
            if segment_from >= segment_to:
                continue
            segment = self.dashboard.dashboard(
                segment_from,
                segment_to,
                "normalized",
            )
            for point in segment.points:
                by_timestamp[point.timestamp] = point
        return sorted(by_timestamp.values(), key=lambda point: point.timestamp)

    def _candidate(
        self,
        component: EpisodeComponent,
        points: list[GlucoseDashboardPoint],
    ) -> _Candidate:
        therapy = classify_episode_therapy(component, points)
        start = _nearest(points, component.start_at)
        plus_2h = _nearest(
            points,
            component.start_at + timedelta(hours=2),
        )
        plus_4h = _nearest(
            points,
            component.start_at + timedelta(hours=4),
        )
        return _Candidate(
            key="|".join(
                sorted(
                    [f"m:{meal.id}" for meal in component.meals]
                    + [f"i:{event.id}" for event in component.insulin]
                )
            ),
            timestamp=component.start_at,
            classification=therapy.classification,
            confidence=therapy.confidence,
            carbs_g=sum(
                float(meal.total_carbs_g or 0) for meal in component.meals
            ),
            insulin_units=sum(
                float(event.insulin_units or 0) for event in component.insulin
            ),
            glucose_start=_point_value(start),
            glucose_plus_2h=_point_value(plus_2h),
            glucose_plus_4h=_point_value(plus_4h),
        )

    def _isf_evidence(
        self,
        period_items: list[_Candidate],
        all_items: list[_Candidate],
        target_mmol_l: float,
    ) -> list[_Evidence]:
        evidence: list[_Evidence] = []
        for item in period_items:
            if (
                item.classification != "insulin_correction"
                or item.confidence == "low"
                or item.carbs_g > 0
                or item.insulin_units <= 0
                or item.insulin_units > 15
                or _has_neighbor(
                    item,
                    all_items,
                    before=timedelta(hours=4),
                    after=timedelta(hours=4),
                )
            ):
                continue
            start = item.glucose_start
            after = item.glucose_plus_4h
            if (
                start is None
                or after is None
                or start < target_mmol_l + 0.8
                or after < 3.0
                or after >= start
            ):
                continue
            value = (start - after) / item.insulin_units
            if MIN_ISF <= value <= MAX_ISF:
                evidence.append(_Evidence(item.timestamp, value))
        return evidence

    def _icr_evidence(
        self,
        period_items: list[_Candidate],
        all_items: list[_Candidate],
        target_mmol_l: float,
        fallback_isf: float,
        slot_isf: dict[int, TherapyAnalysisMetric],
        active_spans: list[tuple[datetime, datetime]],
    ) -> tuple[list[_Evidence], int]:
        """Return usable ICR evidence and how much of it exercise removed.

        Effort moves the ratio by more than this estimator could separate, so
        an episode next to a session is dropped rather than allowed to drag the
        ratio for every other meal of that daypart. The count of what was
        dropped is reported, because an exclusion nobody can see is
        indistinguishable from a bug.
        """
        evidence: list[_Evidence] = []
        excluded_for_activity = 0
        for item in period_items:
            if (
                item.classification not in {"meal", "snack"}
                or item.confidence == "low"
                or item.carbs_g < 10
                or item.insulin_units <= 0
                or item.insulin_units > 30
                or item.glucose_plus_2h is None
                or not 3.0 <= item.glucose_plus_2h <= 15.0
                or _has_neighbor(
                    item,
                    all_items,
                    before=timedelta(hours=2),
                    after=timedelta(hours=2),
                )
            ):
                continue
            if _within_any(item.timestamp, active_spans):
                excluded_for_activity += 1
                continue
            local_isf = slot_isf[_slot_start(item.timestamp.hour)]
            isf = (
                local_isf.value
                if local_isf.value is not None and local_isf.sample_count >= 2
                else fallback_isf
            )
            adjusted_units = item.insulin_units + (
                item.glucose_plus_2h - target_mmol_l
            ) / isf
            if adjusted_units <= 0.25:
                continue
            value = item.carbs_g / adjusted_units
            if MIN_ICR <= value <= MAX_ICR:
                evidence.append(
                    _Evidence(item.timestamp, value, weight=item.carbs_g)
                )
        return evidence, excluded_for_activity


def _within_any(
    at: datetime,
    spans: list[tuple[datetime, datetime]],
) -> bool:
    return any(start <= at <= end for start, end in spans)


DAYPART_LABELS: dict[Daypart, str] = {
    "morning": "Утро",
    "day": "День",
    "evening": "Вечер",
}


def _icr_proposals(
    evidence: list[_Evidence],
    params,
) -> list[IcrDaypartComparison]:
    """Group measured ratios onto the configured slots and propose a value.

    The four-hour table cannot answer "should I change my settings?", because
    its bins are not the bins the settings use. This one is aligned to the
    configured boundaries so the two numbers on each row are comparable.
    """
    bounds: dict[Daypart, tuple[int, int]] = {
        "morning": (params.morning_start_minutes, params.day_start_minutes),
        "day": (params.day_start_minutes, params.evening_start_minutes),
        "evening": (params.evening_start_minutes, params.morning_start_minutes),
    }
    comparisons: list[IcrDaypartComparison] = []
    for daypart in ("morning", "day", "evening"):
        # The ratio and its carbohydrate weight are the only fields propose()
        # reads; units and outcome were already folded into the implied ratio
        # by _icr_evidence, so they are not carried again here.
        episodes = [
            IcrEpisode(
                occurred_at=item.timestamp,
                carbs_g=item.weight,
                units=0.0,
                outcome_mmol_l=0.0,
                implied_icr=item.value,
            )
            for item in evidence
            if daypart_of(item.timestamp, params) == daypart
        ]
        configured = _configured_icr(daypart, params)
        proposal = propose(
            daypart=daypart,
            episodes=episodes,
            current_icr=configured,
        )
        start_minutes, end_minutes = bounds[daypart]
        comparisons.append(
            IcrDaypartComparison(
                daypart=daypart,
                label=DAYPART_LABELS[daypart],
                start_hour=start_minutes // 60,
                end_hour=end_minutes // 60,
                configured_icr_g_per_unit=(
                    round(configured, 1) if configured else None
                ),
                measured_icr_g_per_unit=proposal.estimated_icr,
                proposed_icr_g_per_unit=proposal.proposed_icr,
                episode_count=proposal.episode_count,
                confidence=proposal.confidence,
                capped=proposal.capped,
                note=proposal.note,
            )
        )
    return comparisons


def _configured_icr(daypart: Daypart, params) -> float | None:
    return {
        "morning": params.icr_morning,
        "day": params.icr_day,
        "evening": params.icr_evening,
    }[daypart]


def _isf_identifiability(
    *,
    isolated: int,
    corrections: int,
) -> tuple[IsfIdentifiability, str]:
    """Say how much of the correction evidence survived isolation, and why.

    Measured over 75 days for this owner: 75% of boluses land within ten
    minutes of a meal, so almost nothing is a clean correction and only the
    carbohydrate ratio is really determined. The page has to say that instead
    of printing a median of a handful of episodes beside a solid ICR.
    """
    if isolated == 0:
        return (
            "not_identified",
            "Ни одной изолированной коррекции: ISF по данным не определяется, "
            "показано настроенное значение.",
        )
    if isolated < MIN_ISF_EPISODES_FOR_CONFIDENCE:
        return (
            "thin",
            f"Изолированных коррекций: {isolated} из {corrections}. "
            "Болюсы почти всегда стоят рядом с едой, поэтому надёжно "
            "определяется только ICR — это оценка, а не измерение.",
        )
    return (
        "identified",
        f"Изолированных коррекций: {isolated} из {corrections}.",
    )


def _has_neighbor(
    item: _Candidate,
    all_items: list[_Candidate],
    *,
    before: timedelta,
    after: timedelta,
) -> bool:
    return any(
        candidate.key != item.key
        and item.timestamp - before
        <= candidate.timestamp
        <= item.timestamp + after
        for candidate in all_items
    )


def _points_near(
    points: list[GlucoseDashboardPoint],
    timestamp: datetime,
) -> list[GlucoseDashboardPoint]:
    return [
        point
        for point in points
        if timestamp - timedelta(minutes=30)
        <= point.timestamp
        <= timestamp + timedelta(hours=4, minutes=15)
    ]


def _nearest(
    points: list[GlucoseDashboardPoint],
    timestamp: datetime,
) -> GlucoseDashboardPoint | None:
    if not points:
        return None
    point = min(points, key=lambda candidate: abs(candidate.timestamp - timestamp))
    return (
        point
        if abs(point.timestamp - timestamp) <= timedelta(minutes=15)
        else None
    )


def _nearest_indexed(
    points: list[GlucoseDashboardPoint],
    timestamps: list[datetime],
    target: datetime,
) -> GlucoseDashboardPoint | None:
    """Find a nearby point without scanning the full long-term series."""
    if not timestamps:
        return None
    index = bisect_left(timestamps, target)
    candidates = [
        points[candidate_index]
        for candidate_index in (index - 1, index)
        if 0 <= candidate_index < len(points)
    ]
    point = min(
        candidates,
        key=lambda candidate: abs(candidate.timestamp - target),
    )
    return (
        point
        if abs(point.timestamp - target) <= BACKGROUND_POINT_TOLERANCE
        else None
    )


def _contains_timestamp(
    timestamps: list[datetime],
    start: datetime,
    end: datetime,
) -> bool:
    index = bisect_left(timestamps, start)
    return index < len(timestamps) and timestamps[index] <= end


def _heart_rate_group(
    values: list[float],
    elevated_threshold: float | None,
) -> Literal["quiet", "elevated", "unknown"]:
    if (
        elevated_threshold is None
        or len(values) < MIN_HR_SAMPLES_PER_WINDOW
    ):
        return "unknown"
    elevated_count = sum(value >= elevated_threshold for value in values)
    if (
        median(values) >= elevated_threshold
        or elevated_count / len(values) >= 1 / 3
    ):
        return "elevated"
    return "quiet"


def _background_signal(metric: TherapyAnalysisMetric) -> BasalSignal:
    if metric.value is None or metric.sample_count < 3:
        return "insufficient"
    if metric.value > BACKGROUND_SIGNAL_THRESHOLD:
        return "rising"
    if metric.value < -BACKGROUND_SIGNAL_THRESHOLD:
        return "falling"
    return "stable"


def _payload_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _point_value(point: GlucoseDashboardPoint | None) -> float | None:
    if point is None:
        return None
    return float(
        point.normalized_value
        if point.normalized_value is not None
        else point.raw_value
    )


def _slot_start(hour: int) -> int:
    return hour - hour % BIN_HOURS


def _metric(values: list[float]) -> TherapyAnalysisMetric:
    ordered = sorted(values)
    count = len(ordered)
    if not ordered:
        return TherapyAnalysisMetric(None, None, None, 0, "none")
    confidence: AnalysisConfidence = (
        "high" if count >= 8 else "medium" if count >= 4 else "low"
    )
    return TherapyAnalysisMetric(
        value=round(float(median(ordered)), 2),
        q1=round(_percentile(ordered, 0.25), 2),
        q3=round(_percentile(ordered, 0.75), 2),
        sample_count=count,
        confidence=confidence,
    )


def _percentile(ordered: list[float], fraction: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)
