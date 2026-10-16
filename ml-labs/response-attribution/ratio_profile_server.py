"""Read-only per-meal and per-correction ledger for ICR/ISF profiling.

Run on the server like ``dose_backtest_server.py``. Prints one JSON line per
food sitting (kind="meal") and per food-free correction (kind="correction"),
numbers only: no titles, no ids.
"""

import json
import sys
from bisect import bisect_left
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from glucotracker.application.episodes import EpisodeQueryService
from glucotracker.application.glucose_normalization import GlucoseNormalizationService
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import is_rapid_insulin_event
from glucotracker.application.twin.kernels import insulin_cumulative_absorbed
from glucotracker.config import get_settings

USER = UUID("f51669a5-b262-475b-979c-4da82b072266")
FROM = datetime(2026, 4, 26)
TO = datetime.now()
LOCAL = timedelta(hours=4)

engine = create_engine(get_settings().database_url)
session = Session(engine)

series = GlucoseNormalizationService(session, USER).series(FROM, TO)
cgm = sorted(
    (_local_wall_time(s.timestamp) if s.timestamp.tzinfo else s.timestamp, s.normalized_mmol_l)
    for s in series
    # Normalized values only: uncalibrated stretches are dropped, not filled raw.
    if s.is_normalized
)
cgm_t = [t for t, _ in cgm]
print(f"# cgm {len(cgm)} normalized of {len(series)}", file=sys.stderr)


def at(t, tol=timedelta(minutes=8)):
    i = bisect_left(cgm_t, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(cgm):
            gap = abs(cgm_t[j] - t)
            if gap <= tol and (best is None or gap < best[0]):
                best = (gap, cgm[j][1])
    return best[1] if best else None


def window(a, b):
    lo, hi = bisect_left(cgm_t, a), bisect_left(cgm_t, b)
    return [v for _, v in cgm[lo:hi]]


def mean_between(a, b, need=3):
    w = window(a, b)
    return round(sum(w) / len(w), 2) if len(w) >= need else None


components = EpisodeQueryService(session, USER).components(FROM, TO)
sittings = []
for c in components:
    if not c.meals:
        continue
    meals = sorted(c.meals, key=lambda m: m.eaten_at)
    sittings.append(
        {
            "t": meals[0].eaten_at,
            "carbs": sum(float(m.total_carbs_g or 0) for m in meals),
            "fat": sum(float(m.total_fat_g or 0) for m in meals),
            "protein": sum(float(m.total_protein_g or 0) for m in meals),
            "fiber": sum(float(m.total_fiber_g or 0) for m in meals),
            "kcal": sum(float(m.total_kcal or 0) for m in meals),
            "source": "/".join(sorted({str(getattr(m.source, "value", m.source)) for m in meals})),
        }
    )
sittings.sort(key=lambda s: s["t"])
meal_t = [s["t"] for s in sittings]

events = {}
for c in components:
    for e in c.insulin:
        if e.insulin_units and is_rapid_insulin_event(
            insulin_type=e.insulin_type, event_type=e.event_type
        ):
            events[e.id] = (_local_wall_time(e.timestamp), float(e.insulin_units))
doses, seen = [], set()
for d in sorted(events.values()):
    key = (d[0].replace(microsecond=0), d[1])
    if key not in seen:
        seen.add(key)
        doses.append(d)
dose_t = [d[0] for d in doses]


def units_between(a, b):
    lo, hi = bisect_left(dose_t, a), bisect_left(dose_t, b)
    return sum(d[1] for d in doses[lo:hi])


def iob_at(t, since=timedelta(hours=6), until=timedelta(0)):
    lo, hi = bisect_left(dose_t, t - since), bisect_left(dose_t, t - until)
    return sum(u * (1 - insulin_cumulative_absorbed((t - dt).total_seconds() / 60, 360)) for dt, u in doses[lo:hi])


def carbs_between(a, b, min_carbs=0.0):
    lo, hi = bisect_left(meal_t, a), bisect_left(meal_t, b)
    return sum(s["carbs"] for s in sittings[lo:hi] if s["carbs"] >= min_carbs)


# Health Connect: payload instants are true UTC.
rows = session.execute(
    text(
        "select record_type, payload from health_connect_records where owner_id = :u "
        "and record_type in ('StepsRecord','SleepSessionRecord','ExerciseSessionRecord')"
    ),
    {"u": str(USER)},
).all()


def _local(value):
    if not value:
        return None
    instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (instant + LOCAL).replace(tzinfo=None) if instant.tzinfo else instant


steps, sleeps, exercises = [], [], []
for record_type, payload in rows:
    p = payload if isinstance(payload, dict) else json.loads(payload)
    start, end = _local(p.get("startTime")), _local(p.get("endTime"))
    if start is None or end is None:
        continue
    if record_type == "StepsRecord":
        steps.append((start, end, float(p.get("count") or 0)))
    elif record_type == "SleepSessionRecord":
        sleeps.append((start, end))
    else:
        exercises.append((start, end))
steps.sort()
step_t = [s[0] for s in steps]
print(f"# steps {len(steps)} sleeps {len(sleeps)} exercises {len(exercises)}", file=sys.stderr)


def steps_between(a, b):
    lo, hi = bisect_left(step_t, a), bisect_left(step_t, b)
    return sum(s[2] for s in steps[lo:hi])


def has_steps_coverage(a, b):
    lo, hi = bisect_left(step_t, a - timedelta(hours=3)), bisect_left(step_t, b + timedelta(hours=3))
    return hi > lo


def sleep_before(t):
    """Hours slept in sessions ending within 14 h before t, and hours since waking."""
    relevant = [(s, e) for s, e in sleeps if t - timedelta(hours=14) <= e <= t]
    if not relevant:
        return None, None
    hours = sum((e - s).total_seconds() / 3600 for s, e in relevant)
    woke = max(e for _, e in relevant)
    return round(hours, 2), round((t - woke).total_seconds() / 3600, 2)


def exercise_near(a, b):
    return any(s < b and e > a for s, e in exercises)


for i, s in enumerate(sittings):
    t0 = s["t"]
    if s["carbs"] < 15 or t0 < FROM + timedelta(days=1):
        continue
    previous_meal = sittings[i - 1]["t"] if i > 0 else None
    slept, since_wake = sleep_before(t0)
    row = {
        "kind": "meal",
        "t": t0.isoformat(),
        "hour": round(t0.hour + t0.minute / 60, 2),
        "weekday": t0.weekday(),
        **{k: round(v, 1) for k, v in s.items() if k in ("carbs", "fat", "protein", "fiber", "kcal")},
        "source": s["source"],
        "hours_since_prev_meal": round((t0 - previous_meal).total_seconds() / 3600, 2) if previous_meal else None,
        "given": round(units_between(t0 - timedelta(minutes=45), t0 + timedelta(minutes=90)), 2),
        "late": round(units_between(t0 + timedelta(minutes=90), t0 + timedelta(hours=4)), 2),
        "prior_iob": round(iob_at(t0 - timedelta(minutes=45)), 2),
        "prior_carbs_3h": round(carbs_between(t0 - timedelta(hours=3), t0 - timedelta(minutes=1)), 1),
        "more_carbs_4h": round(carbs_between(t0 + timedelta(minutes=31), t0 + timedelta(hours=4)), 1),
        "bg0": at(t0),
        "bg_m30": at(t0 - timedelta(minutes=30)),
        "bg2h": mean_between(t0 + timedelta(minutes=105), t0 + timedelta(minutes=135)),
        "bg3h": mean_between(t0 + timedelta(minutes=165), t0 + timedelta(minutes=195)),
        "bg4h": mean_between(t0 + timedelta(minutes=225), t0 + timedelta(minutes=255)),
        "bg5h": mean_between(t0 + timedelta(minutes=285), t0 + timedelta(minutes=315)),
        "steps": steps_between(t0 - timedelta(hours=1), t0 + timedelta(hours=3)) if has_steps_coverage(t0, t0) else None,
        "exercise": exercise_near(t0 - timedelta(hours=1), t0 + timedelta(hours=3)),
        "slept_h": slept,
        "since_wake_h": since_wake,
    }
    w = window(t0 + timedelta(minutes=20), t0 + timedelta(hours=4))
    row["nadir"] = round(min(w), 2) if len(w) >= 20 else None
    row["peak"] = round(max(w), 2) if len(w) >= 20 else None
    print(json.dumps(row))

# Food-free corrections, doses grouped within 30 minutes.
i = 0
while i < len(doses):
    t0, units = doses[i]
    j = i + 1
    while j < len(doses) and doses[j][0] - t0 <= timedelta(minutes=30):
        units += doses[j][1]
        j += 1
    i_next = j
    if carbs_between(t0 - timedelta(hours=3), t0 + timedelta(hours=4), 3.0) == 0:
        row = {
            "kind": "correction",
            "t": t0.isoformat(),
            "hour": round(t0.hour + t0.minute / 60, 2),
            "units": round(units, 2),
            "prior_iob": round(iob_at(t0 - timedelta(minutes=1)), 2),
            "other_insulin_4h": round(units_between(t0 + timedelta(minutes=31), t0 + timedelta(hours=4, minutes=30)), 2),
            "bg0": at(t0),
            "bg_m30": at(t0 - timedelta(minutes=30)),
            "bg_m60": at(t0 - timedelta(minutes=60)),
            **{
                f"bg{m}": mean_between(t0 + timedelta(minutes=m - 15), t0 + timedelta(minutes=m + 15))
                for m in (60, 120, 180, 240, 270)
            },
        }
        w = window(t0 + timedelta(minutes=45), t0 + timedelta(hours=4))
        row["nadir"] = round(min(w), 2) if len(w) >= 20 else None
        print(json.dumps(row))
    i = i_next
