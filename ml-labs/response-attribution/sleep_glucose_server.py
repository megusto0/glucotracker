"""Read-only: glucose during every recorded sleep session (one JSON line each).

Uses the dashboard's normalized display series, so sensor offsets and the
dashboard's own compression/jump flags are the same ones the app shows.
Run on the server like ``dose_backtest_server.py``.
"""

import json
import sys
from bisect import bisect_left
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from glucotracker.application.episodes import EpisodeQueryService
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import is_rapid_insulin_event
from glucotracker.application.twin.kernels import insulin_cumulative_absorbed
from glucotracker.config import get_settings

USER = UUID("f51669a5-b262-475b-979c-4da82b072266")
LOCAL = timedelta(hours=4)
engine = create_engine(get_settings().database_url)
session = Session(engine)


def _local(value):
    instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (instant + LOCAL).replace(tzinfo=None) if instant.tzinfo else instant


sleeps = []
for (payload,) in session.execute(
    text(
        "select payload from health_connect_records where owner_id = :u "
        "and record_type = 'SleepSessionRecord'"
    ),
    {"u": str(USER)},
):
    p = payload if isinstance(payload, dict) else json.loads(payload)
    if p.get("startTime") and p.get("endTime"):
        start, end = _local(p["startTime"]), _local(p["endTime"])
        origin = ((p.get("metadata") or {}).get("dataOrigin") or {}).get("packageName", "")
        if timedelta(hours=1) <= end - start <= timedelta(hours=16):
            sleeps.append((start, end, origin))
sleeps = sorted(set(sleeps))
# Overlapping duplicates from two writers: keep the longest of any overlap.
merged = []
for s in sleeps:
    if merged and s[0] < merged[-1][1]:
        if (s[1] - s[0]) > (merged[-1][1] - merged[-1][0]):
            merged[-1] = s
        continue
    merged.append(s)
print(f"# sleep sessions {len(sleeps)} -> {len(merged)} after overlap merge", file=sys.stderr)

frm = min(s[0] for s in merged) - timedelta(days=1)
to = max(s[1] for s in merged) + timedelta(days=1)
components = EpisodeQueryService(session, USER).components(frm, to)
meals = sorted(
    (
        min(m.eaten_at for m in c.meals),
        sum(float(m.total_carbs_g or 0) for m in c.meals),
        sum(float(m.total_fat_g or 0) for m in c.meals),
        sum(float(m.total_protein_g or 0) for m in c.meals),
    )
    for c in components
    if c.meals
)
meal_t = [m[0] for m in meals]
events = {}
for c in components:
    for e in c.insulin:
        if e.insulin_units and is_rapid_insulin_event(insulin_type=e.insulin_type, event_type=e.event_type):
            events[e.id] = (_local_wall_time(e.timestamp), float(e.insulin_units))
doses, seen = [], set()
for d in sorted(events.values()):
    key = (d[0].replace(microsecond=0), d[1])
    if key not in seen:
        seen.add(key)
        doses.append(d)
dose_t = [d[0] for d in doses]


def iob_at(t):
    lo, hi = bisect_left(dose_t, t - timedelta(hours=6)), bisect_left(dose_t, t)
    return sum(u * (1 - insulin_cumulative_absorbed((t - dt).total_seconds() / 60, 360)) for dt, u in doses[lo:hi])


dashboard = GlucoseDashboardService(session, USER)
for start, end, origin in merged:
    try:
        points = dashboard.dashboard(start - timedelta(hours=1), end + timedelta(hours=2), "normalized").points
    except Exception as exc:  # pragma: no cover
        print(f"# {start}: {exc!r}", file=sys.stderr)
        session.rollback()
        continue
    # Normalized values only: a point without a calibration is dropped, never
    # replaced by its raw reading.
    series = [
        (p.timestamp.replace(tzinfo=None) if p.timestamp.tzinfo is None else _local_wall_time(p.timestamp),
         float(p.normalized_value), list(p.flags or []))
        for p in points
        if p.normalized_value is not None
    ]
    raw_count = sum(1 for p in points if start <= (p.timestamp.replace(tzinfo=None) if p.timestamp.tzinfo is None else _local_wall_time(p.timestamp)) <= end)
    inside = [s for s in series if start <= s[0] <= end]
    lo, hi = bisect_left(meal_t, start - timedelta(hours=6)), bisect_left(meal_t, start)
    before = meals[lo:hi]
    last_meal = before[-1] if before else None
    during_meals = [m for m in meals[bisect_left(meal_t, start):bisect_left(meal_t, end)] if m[1] >= 3]
    during_doses = [d for d in doses[bisect_left(dose_t, start):bisect_left(dose_t, end)]]
    profile = {}
    for t, v, _ in inside:
        k = int((t - start).total_seconds() // 1800)  # 30-minute bins from sleep start
        profile.setdefault(k, []).append(v)
    row = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hours": round((end - start).total_seconds() / 3600, 2),
        "origin": origin.split(".")[-1][:20],
        "n_cgm": len(inside),
        "n_cgm_all": raw_count,
        "cgm_coverage": round(len(inside) / max(1, (end - start).total_seconds() / 300), 2),
        "bg_start": inside[0][1] if inside else None,
        "bg_end": inside[-1][1] if inside else None,
        "bg_min": min(v for _, v, _ in inside) if inside else None,
        "bg_max": max(v for _, v, _ in inside) if inside else None,
        "bg_mean": round(sum(v for _, v, _ in inside) / len(inside), 2) if inside else None,
        "min_below_3_9": sum(5 for _, v, _ in inside if v < 3.9),
        "min_above_10": sum(5 for _, v, _ in inside if v > 10),
        "compression_points": sum(1 for _, _, f in inside if "compression_suspected" in f),
        "jump_points": sum(1 for _, _, f in inside if "jump_suspected" in f),
        "last_meal_h_before": round((start - last_meal[0]).total_seconds() / 3600, 2) if last_meal else None,
        "last_meal_carbs": round(last_meal[1], 1) if last_meal else None,
        "last_meal_fat": round(last_meal[2], 1) if last_meal else None,
        "carbs_4h_before": round(sum(m[1] for m in before if m[0] >= start - timedelta(hours=4)), 1),
        "iob_at_start": round(iob_at(start), 2),
        "bolus_4h_before": round(sum(d[1] for d in doses[bisect_left(dose_t, start - timedelta(hours=4)):bisect_left(dose_t, start)]), 2),
        "meals_during": len(during_meals),
        "doses_during": len(during_doses),
        "units_during": round(sum(d[1] for d in during_doses), 2),
        "profile_30min": {str(k): round(sum(v) / len(v), 2) for k, v in sorted(profile.items())},
    }
    print(json.dumps(row))
