"""Read-only backtest of the "Сколько добавить?" button (TopUpDoseService).

Two kinds of moments, each scored against what glucose did next:

A. every follow-up dose the owner actually gave 30–240 min after a meal —
   what the button would have said just before it;
B. moments the owner did *not* top up while carbs were still absorbing and
   glucose was above 8 — what the button would have said then.

One JSON line per moment, numbers only. Run on the server like
``dose_backtest_server.py``.
"""

import json
import sys
from bisect import bisect_left
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from glucotracker.application.episodes import EpisodeQueryService
from glucotracker.application.glucose_normalization import GlucoseNormalizationService
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import is_rapid_insulin_event
from glucotracker.application.top_up_dose import TopUpDoseService
from glucotracker.config import get_settings

USER = UUID("f51669a5-b262-475b-979c-4da82b072266")
FROM = datetime(2026, 5, 1)
TO = datetime(2026, 10, 4, 6)
GROUP = timedelta(minutes=10)

engine = create_engine(get_settings().database_url)
session = Session(engine)
series = GlucoseNormalizationService(session, USER).series(FROM, TO)
cgm = sorted(
    (_local_wall_time(s.timestamp) if s.timestamp.tzinfo else s.timestamp, s.normalized_mmol_l)
    for s in series
)
cgm_t = [t for t, _ in cgm]


def window(a, b):
    lo, hi = bisect_left(cgm_t, a), bisect_left(cgm_t, b)
    return [v for _, v in cgm[lo:hi]]


def at_time(t, tol=timedelta(minutes=8)):
    i = bisect_left(cgm_t, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(cgm):
            gap = abs(cgm_t[j] - t)
            if gap <= tol and (best is None or gap < best[0]):
                best = (gap, cgm[j][1])
    return best[1] if best else None


def mean_between(a, b):
    w = window(a, b)
    return round(sum(w) / len(w), 2) if len(w) >= 3 else None


components = EpisodeQueryService(session, USER).components(FROM, TO)
meals = sorted(
    (min(m.eaten_at for m in c.meals), sum(float(m.total_carbs_g or 0) for m in c.meals))
    for c in components
    if c.meals
)
meal_t = [m[0] for m in meals]
events = {}
for c in components:
    for e in c.insulin:
        if e.insulin_units and is_rapid_insulin_event(
            insulin_type=e.insulin_type, event_type=e.event_type
        ):
            events[e.id] = (_local_wall_time(e.timestamp), float(e.insulin_units), e.id)
doses = sorted(events.values())
# The same dose sometimes arrives twice (local write + Nightscout echo).
dedup, seen = [], set()
for d in doses:
    key = (d[0].replace(microsecond=0), d[1])
    if key not in seen:
        seen.add(key)
        dedup.append(d)
doses = dedup
dose_t = [d[0] for d in doses]


def meals_between(a, b, min_carbs=5.0):
    lo, hi = bisect_left(meal_t, a), bisect_left(meal_t, b)
    return [m for m in meals[lo:hi] if m[1] >= min_carbs]


def units_between(a, b):
    lo, hi = bisect_left(dose_t, a), bisect_left(dose_t, b)
    return sum(d[1] for d in doses[lo:hi])


svc = TopUpDoseService(session, USER)


def _minutes_since_meal(at):
    previous = meals_between(at - timedelta(hours=6), at + timedelta(seconds=1), 15.0)
    return round((at - previous[-1][0]).total_seconds() / 60) if previous else None


def emit(kind, at, given, exclude_id):
    try:
        s = svc.suggest(at=at, exclude_insulin_id=exclude_id)
    except Exception as exc:  # pragma: no cover - diagnostic only
        print(f"# {kind} {at}: {exc!r}", file=sys.stderr)
        session.rollback()
        return
    after = at + GROUP
    row = {
        "kind": kind,
        "t": at.isoformat(),
        "given": round(given, 2),
        "status": s.status,
        "units": s.units,
        "glucose": s.glucose_mmol_l,
        "projected": s.projected_glucose_mmol_l,
        "projection_source": s.projection_source,
        "cob": s.cob_g,
        "iob": s.iob_units,
        "carb_units": s.carb_units,
        "correction_units": s.correction_units,
        "icr": s.icr_g_per_unit,
        "isf": s.isf_mmol_l_per_unit,
        "cob_min": s.cob_minutes_remaining,
        "iob_min": s.iob_minutes_remaining,
        "more_food": bool(meals_between(at - timedelta(minutes=20), at + timedelta(hours=3))),
        "more_insulin": round(units_between(after, at + timedelta(hours=3)), 2),
        "bg_now": at_time(at),
        "bg_m15": at_time(at - timedelta(minutes=15)),
        "bg_m30": at_time(at - timedelta(minutes=30)),
        "minutes_since_meal": _minutes_since_meal(at),
        "hour": at.hour + at.minute / 60,
        "bg2h": mean_between(at + timedelta(minutes=105), at + timedelta(minutes=135)),
        "bg3h": mean_between(at + timedelta(minutes=165), at + timedelta(minutes=195)),
        "bg4h": mean_between(at + timedelta(minutes=225), at + timedelta(minutes=255)),
    }
    w = window(at + timedelta(minutes=20), at + timedelta(hours=4))
    row["nadir"] = round(min(w), 2) if len(w) >= 20 else None
    row["peak"] = round(max(w), 2) if len(w) >= 20 else None
    print(json.dumps(row))


# A. Follow-up doses actually given.
i = 0
while i < len(doses):
    at, units, dose_id = doses[i]
    j = i + 1
    total = units
    while j < len(doses) and doses[j][0] - at <= GROUP:
        total += doses[j][1]
        j += 1
    recent = meals_between(at - timedelta(minutes=240), at - timedelta(minutes=30), 15.0)
    near = meals_between(at - timedelta(minutes=30), at + timedelta(minutes=30))
    if recent and not near and at >= FROM + timedelta(hours=6):
        emit("given", at, total, dose_id)
    i = j

# B. Moments without a top-up: every 30 min, 45–240 min after a meal, no dose
# in the previous 45 min or the next 90, glucose above 8.
for meal_at, carbs in meals:
    if carbs < 15:
        continue
    for minutes in range(45, 241, 30):
        at = meal_at + timedelta(minutes=minutes)
        if units_between(at - timedelta(minutes=45), at + timedelta(minutes=90)) > 0:
            continue
        if meals_between(at - timedelta(minutes=30), at + timedelta(minutes=30)):
            continue
        now = window(at - timedelta(minutes=6), at + timedelta(seconds=1))
        if not now or now[-1] <= 8.0:
            continue
        emit("skipped", at, 0.0, None)
