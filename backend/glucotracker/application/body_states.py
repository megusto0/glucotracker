"""Sleep and hard-effort intervals, from the watch or from heart rate alone.

Health Connect sessions are the truth when they arrive, but they often arrive
late: the phone syncs sleep and workout sessions hours after the fact, while
heart-rate samples stream in continuously. So every session is taken as
recorded, and heart rate fills the gaps — a sustained trough reads as sleep, a
sustained climb reads as effort. Inferred intervals never overlap a recorded
one; the recorded span is subtracted first, and only what is left over and
still long enough survives.

Both thresholds are drawn from the wearer's own window rather than being fixed
bpm, because a resting rate of 50 and a resting rate of 75 do not share a
meaningful cut-off.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.application.health_connect_samples import (
    METADATA_MARGIN,
    as_utc,
    heart_rate_samples,
)
from glucotracker.application.time import (
    local_wall_time,
    utc_instant_from_local_wall,
)
from glucotracker.infra.db.repositories.health_connect import (
    HealthConnectRepository,
)

BodyStateKind = Literal["sleep", "activity"]
BodyStateSource = Literal["recorded", "heart_rate"]
BodyStateConfidence = Literal["low", "medium", "high"]

# Heart rate is read well beyond the reported window: a night's trough starts
# before midnight, and the percentile baseline needs a stable stretch around
# the range to mean anything.
HR_CONTEXT = timedelta(hours=12)
MIN_HR_SAMPLES = 12

# Sleeping heart rate sits just above the window's floor, so the cut-off is
# anchored to a robust minimum rather than to a share of the window. A fixed
# share would only find sleep on days where sleep happened to occupy that share
# — an afternoon of it, or a short night, would vanish.
FLOOR_PERCENTILE = 0.05
SLEEP_ABOVE_FLOOR_BPM = 8.0
SLEEP_RUN_GAP = timedelta(minutes=10)
MIN_SLEEP = timedelta(minutes=90)
MIN_RECORDED_SLEEP = timedelta(minutes=45)
SLEEP_RECOVERY_WINDOW = timedelta(hours=2)
# A flat window would put the cut-off above every sample and read the whole day
# as one long sleep. The trough has to sit clearly below the middle of the
# window before any of it counts.
MIN_SLEEP_SEPARATION_BPM = 6.0

RESTING_PERCENTILE = 0.25
# "Intense" against the wearer's own resting rate. The floor keeps a very low
# resting rate from labelling an ordinary walk as effort.
MIN_INTENSE_BPM = 100.0
INTENSE_ABOVE_RESTING_BPM = 30.0
ACTIVITY_RUN_GAP = timedelta(minutes=6)
MIN_ACTIVITY = timedelta(minutes=10)
MIN_RECORDED_ACTIVITY = timedelta(minutes=5)
MIN_ACTIVITY_SAMPLES = 3
# Above this an inferred effort is as good as a recorded one for reading a day.
CONFIDENT_ACTIVITY = timedelta(minutes=20)


@dataclass(frozen=True)
class BodyStateInterval:
    """One sleep or hard-effort span in local wall-clock time."""

    kind: BodyStateKind
    source: BodyStateSource
    start_at: datetime
    end_at: datetime
    #: Minutes visible inside the requested range.
    minutes: int
    #: Minutes the state actually lasted, which a night crossing midnight keeps
    #: even when only its tail falls inside the requested day.
    total_minutes: int
    confidence: BodyStateConfidence
    label: str | None = None
    mean_bpm: float | None = None
    peak_bpm: float | None = None


class BodyStateService:
    """Assemble recorded and heart-rate-inferred body states for a range."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    def intervals(
        self,
        local_from: datetime,
        local_to: datetime,
    ) -> list[BodyStateInterval]:
        """Return every state overlapping a local wall-clock range, in order."""
        from_utc = utc_instant_from_local_wall(local_from)
        to_utc = utc_instant_from_local_wall(local_to)
        if to_utc <= from_utc:
            return []

        recorded_sleep = self._recorded(
            "SleepSessionRecord",
            from_utc,
            to_utc,
            minimum=MIN_RECORDED_SLEEP,
        )
        recorded_activity = self._recorded(
            "ExerciseSessionRecord",
            from_utc,
            to_utc,
            minimum=MIN_RECORDED_ACTIVITY,
        )
        samples = heart_rate_samples(
            self.session,
            self.user_id,
            from_utc - HR_CONTEXT,
            to_utc + HR_CONTEXT,
        )

        inferred_sleep = _subtract(
            self._inferred_sleep(samples),
            [(start, end) for start, end, _ in recorded_sleep],
            minimum=MIN_SLEEP,
        )
        inferred_activity = _subtract(
            self._inferred_activity(samples),
            [(start, end) for start, end, _ in recorded_activity],
            minimum=MIN_ACTIVITY,
        )

        intervals = [
            *(
                _recorded_interval("sleep", start, end, label, samples)
                for start, end, label in recorded_sleep
            ),
            *(
                _recorded_interval("activity", start, end, label, samples)
                for start, end, label in recorded_activity
            ),
            *(
                _inferred_interval("sleep", start, end, samples)
                for start, end in inferred_sleep
            ),
            *(
                _inferred_interval("activity", start, end, samples)
                for start, end in inferred_activity
            ),
        ]
        clipped = [
            _clip(interval, from_utc, to_utc) for interval in intervals
        ]
        return sorted(
            (
                interval
                for interval in clipped
                if interval is not None and interval.minutes >= 1
            ),
            key=lambda interval: (interval.start_at, interval.kind),
        )

    def _recorded(
        self,
        record_type: str,
        from_utc: datetime,
        to_utc: datetime,
        *,
        minimum: timedelta,
    ) -> list[tuple[datetime, datetime, str | None]]:
        """Return owner-scoped sessions that really overlap the range."""
        rows = HealthConnectRepository(
            self.session,
            self.user_id,
        ).list_records_by_type_and_time(
            record_type,
            from_utc - METADATA_MARGIN,
            to_utc + METADATA_MARGIN,
        )
        sessions: list[tuple[datetime, datetime, str | None]] = []
        for row in rows:
            start = as_utc(row.start_time)
            end = as_utc(row.end_time)
            if start is None or end is None or end - start < minimum:
                continue
            if end <= from_utc or start >= to_utc:
                continue
            sessions.append((start, end, _session_label(row.payload)))
        return _merge(sessions)

    def _inferred_sleep(
        self,
        samples: list[tuple[datetime, float]],
    ) -> list[tuple[datetime, datetime]]:
        """Return sustained low-heart-rate troughs that were slept through."""
        if len(samples) < MIN_HR_SAMPLES:
            return []
        values = sorted(bpm for _, bpm in samples)
        threshold = _percentile(values, FLOOR_PERCENTILE) + SLEEP_ABOVE_FLOOR_BPM
        if median(values) - threshold < MIN_SLEEP_SEPARATION_BPM:
            return []
        runs = _runs(
            samples,
            lambda bpm: bpm <= threshold,
            SLEEP_RUN_GAP,
            MIN_SLEEP,
        )
        return [
            (start, end)
            for start, end in runs
            if any(
                bpm > threshold
                for at, bpm in samples
                if timedelta(0) < at - end <= SLEEP_RECOVERY_WINDOW
            )
        ]

    def _inferred_activity(
        self,
        samples: list[tuple[datetime, float]],
    ) -> list[tuple[datetime, datetime]]:
        """Return sustained climbs well above the wearer's resting rate."""
        if len(samples) < MIN_HR_SAMPLES:
            return []
        values = sorted(bpm for _, bpm in samples)
        resting = _percentile(values, RESTING_PERCENTILE)
        threshold = max(MIN_INTENSE_BPM, resting + INTENSE_ABOVE_RESTING_BPM)
        runs = _runs(
            samples,
            lambda bpm: bpm >= threshold,
            ACTIVITY_RUN_GAP,
            MIN_ACTIVITY,
        )
        return [
            (start, end)
            for start, end in runs
            if sum(start <= at <= end for at, _ in samples) >= MIN_ACTIVITY_SAMPLES
        ]


def _runs(
    samples: list[tuple[datetime, float]],
    matches: Callable[[float], bool],
    max_gap: timedelta,
    minimum: timedelta,
) -> list[tuple[datetime, datetime]]:
    """Return maximal spans of matching samples, tolerating a stray reading.

    A single off-threshold sample does not end a run; only a sustained
    departure past ``max_gap``, or a gap that long between matching samples,
    closes one.
    """
    runs: list[tuple[datetime, datetime]] = []
    run_start: datetime | None = None
    last_match: datetime | None = None
    for at, bpm in samples:
        if matches(bpm):
            if run_start is None:
                run_start = at
            elif last_match is not None and at - last_match > max_gap:
                runs.append((run_start, last_match))
                run_start = at
            last_match = at
        elif (
            run_start is not None
            and last_match is not None
            and at - last_match > max_gap
        ):
            runs.append((run_start, last_match))
            run_start = None
            last_match = None
    if run_start is not None and last_match is not None:
        runs.append((run_start, last_match))
    return [(start, end) for start, end in runs if end - start >= minimum]


def _merge(
    sessions: list[tuple[datetime, datetime, str | None]],
) -> list[tuple[datetime, datetime, str | None]]:
    """Fold overlapping or touching recorded sessions into single spans."""
    merged: list[tuple[datetime, datetime, str | None]] = []
    for start, end, label in sorted(
        sessions,
        key=lambda session: (session[0], session[1]),
    ):
        if merged and start <= merged[-1][1]:
            previous = merged[-1]
            merged[-1] = (
                previous[0],
                max(previous[1], end),
                previous[2] or label,
            )
            continue
        merged.append((start, end, label))
    return merged


def _subtract(
    spans: list[tuple[datetime, datetime]],
    covered: list[tuple[datetime, datetime]],
    *,
    minimum: timedelta,
) -> list[tuple[datetime, datetime]]:
    """Remove recorded coverage from inferred spans, keeping long remainders."""
    remaining = list(spans)
    for cover_start, cover_end in covered:
        next_remaining: list[tuple[datetime, datetime]] = []
        for start, end in remaining:
            if cover_end <= start or cover_start >= end:
                next_remaining.append((start, end))
                continue
            if start < cover_start:
                next_remaining.append((start, min(end, cover_start)))
            if end > cover_end:
                next_remaining.append((max(start, cover_end), end))
        remaining = next_remaining
    return [(start, end) for start, end in remaining if end - start >= minimum]


def _window(
    samples: list[tuple[datetime, float]],
    start: datetime,
    end: datetime,
) -> list[float]:
    return [bpm for at, bpm in samples if start <= at <= end]


def _recorded_interval(
    kind: BodyStateKind,
    start: datetime,
    end: datetime,
    label: str | None,
    samples: list[tuple[datetime, float]],
) -> BodyStateInterval:
    return _interval(kind, "recorded", start, end, "high", label, samples)


def _inferred_interval(
    kind: BodyStateKind,
    start: datetime,
    end: datetime,
    samples: list[tuple[datetime, float]],
) -> BodyStateInterval:
    confidence: BodyStateConfidence = (
        "medium"
        if kind == "sleep" or end - start >= CONFIDENT_ACTIVITY
        else "low"
    )
    return _interval(kind, "heart_rate", start, end, confidence, None, samples)


def _interval(
    kind: BodyStateKind,
    source: BodyStateSource,
    start: datetime,
    end: datetime,
    confidence: BodyStateConfidence,
    label: str | None,
    samples: list[tuple[datetime, float]],
) -> BodyStateInterval:
    values = _window(samples, start, end)
    length = round((end - start).total_seconds() / 60)
    return BodyStateInterval(
        kind=kind,
        source=source,
        start_at=local_wall_time(start),
        end_at=local_wall_time(end),
        minutes=length,
        total_minutes=length,
        confidence=confidence,
        label=label,
        mean_bpm=round(sum(values) / len(values), 1) if values else None,
        peak_bpm=round(max(values), 1) if values else None,
    )


def _clip(
    interval: BodyStateInterval,
    from_utc: datetime,
    to_utc: datetime,
) -> BodyStateInterval | None:
    """Trim a state to the reported range without losing its true length."""
    start = max(interval.start_at, local_wall_time(from_utc))
    end = min(interval.end_at, local_wall_time(to_utc))
    if end <= start:
        return None
    if start == interval.start_at and end == interval.end_at:
        return interval
    return BodyStateInterval(
        kind=interval.kind,
        source=interval.source,
        start_at=start,
        end_at=end,
        minutes=round((end - start).total_seconds() / 60),
        total_minutes=interval.total_minutes,
        confidence=interval.confidence,
        label=interval.label,
        mean_bpm=interval.mean_bpm,
        peak_bpm=interval.peak_bpm,
    )


def _percentile(sorted_values: list[float], fraction: float) -> float:
    index = min(len(sorted_values) - 1, int(fraction * len(sorted_values)))
    return float(sorted_values[index])


def _session_label(payload: dict[str, Any] | None) -> str | None:
    """Return whatever the wearable called this session, if it named it."""
    for key in ("title", "notes", "exerciseType"):
        value = (payload or {}).get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return None
