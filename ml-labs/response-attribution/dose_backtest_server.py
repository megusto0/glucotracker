"""Read-only backtest of the meal-dose estimator, run on the server.

Prints one JSON line per food sitting: the production estimate computed with
history strictly before the sitting, a same-regime variant, what was actually
given, and the normalized CGM outcome. No titles, no ids.
"""

import json
import sys
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import glucotracker.application.insulin_recommendation as ir
from glucotracker.application.episodes import EpisodeQueryService
from glucotracker.application.glucose_normalization import GlucoseNormalizationService
from glucotracker.application.nightscout_context import _local_wall_time
from glucotracker.application.on_board.classification import is_rapid_insulin_event
from glucotracker.config import get_settings
from glucotracker.infra.db.repositories.twin import TwinRepository

try:  # present once the shadow estimator is deployed
    from glucotracker.application.dose_shadow import shadow_meal_estimate
except ImportError:  # pragma: no cover - older deployments
    shadow_meal_estimate = None

USER = UUID("f51669a5-b262-475b-979c-4da82b072266")
FROM = datetime(2026, 4, 26)
TO = datetime(2026, 10, 1, 12)
EVAL_FROM = datetime(2026, 5, 20)
INSULIN_SWITCH = datetime(2026, 8, 10)
ORIGINAL_WINDOW = ir.HISTORY_WINDOW

engine = create_engine(get_settings().database_url)
session = Session(engine)

series = GlucoseNormalizationService(session, USER).series(FROM, TO)
cgm = sorted((_local_wall_time(s.timestamp) if s.timestamp.tzinfo else s.timestamp, s.normalized_mmol_l) for s in series)
cgm_t = [t for t, _ in cgm]
print(f"# normalized samples {len(cgm)}", file=sys.stderr)

from bisect import bisect_left  # noqa: E402


def window(a, b):
    lo, hi = bisect_left(cgm_t, a), bisect_left(cgm_t, b)
    return [v for _, v in cgm[lo:hi]]


def at(t, tol=timedelta(minutes=10)):
    i = bisect_left(cgm_t, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(cgm):
            gap = abs(cgm_t[j] - t)
            if gap <= tol and (best is None or gap < best[0]):
                best = (gap, cgm[j][1])
    return best[1] if best else None


components = EpisodeQueryService(session, USER).components(FROM, TO)
params = TwinRepository(session, USER).get_or_create_params(persist=False)
svc = ir.HistoricalInsulinRecommendationService(session, USER)
svc.preload_history(EVAL_FROM, TO)

meal_starts = sorted(
    min(m.eaten_at for m in c.meals)
    for c in components
    if c.meals and sum(float(m.total_carbs_g or 0) for m in c.meals) >= 5
)
doses = sorted(
    (_local_wall_time(e.timestamp), float(e.insulin_units or 0), e.event_type)
    for c in components
    for e in c.insulin
    if e.insulin_units
    and is_rapid_insulin_event(insulin_type=e.insulin_type, event_type=e.event_type)
)
dose_t = [d[0] for d in doses]
seen = set()
dedup = []
for d in doses:
    key = (d[0].replace(microsecond=0), d[1])
    if key in seen:
        continue
    seen.add(key)
    dedup.append(d)
doses = dedup
dose_t = [d[0] for d in doses]


def units_between(a, b):
    lo, hi = bisect_left(dose_t, a), bisect_left(dose_t, b)
    return sum(d[1] for d in doses[lo:hi])


for c in components:
    if not c.meals:
        continue
    meals = sorted(c.meals, key=lambda m: m.eaten_at)
    t0 = meals[0].eaten_at
    carbs = sum(float(m.total_carbs_g or 0) for m in meals)
    if t0 < EVAL_FROM or carbs < 15:
        continue
    ids = [m.id for m in meals]
    row = {
        "t": t0.isoformat(),
        "carbs": round(carbs, 1),
        "fat": round(sum(float(m.total_fat_g or 0) for m in meals), 1),
        "protein": round(sum(float(m.total_protein_g or 0) for m in meals), 1),
        "kcal": round(sum(float(m.total_kcal or 0) for m in meals), 1),
        "novorapid": t0 >= INSULIN_SWITCH,
        "source": "/".join(sorted({str(getattr(m.source, "value", m.source)) for m in meals})),
    }
    for name, history in (
        ("prod", ORIGINAL_WINDOW),
        ("regime", min(ORIGINAL_WINDOW, t0 - INSULIN_SWITCH) if t0 >= INSULIN_SWITCH else min(ORIGINAL_WINDOW, t0 - datetime(2026, 4, 26))),
    ):
        ir.HISTORY_WINDOW = max(history, timedelta(days=1))
        est = svc._meal_estimate(ids, meals, twin_params=params)
        row[name] = est.recommended_units
        row[name + "_hist"] = est.history_median_units
        row[name + "_n"] = len(est.matches)
        row[name + "_w"] = est.history_weight
        if name == "prod":
            row["icr_cfg"] = est.icr_configured_g_per_unit
            row["icr_dose"] = est.icr_dose_units
            row["icr_eff"] = est.icr_g_per_unit
            row["after_sleep"] = est.icr_after_sleep
    ir.HISTORY_WINDOW = ORIGINAL_WINDOW
    row["given"] = round(units_between(t0 - timedelta(minutes=45), t0 + timedelta(minutes=90)), 2)
    row["given_late"] = round(units_between(t0 + timedelta(minutes=90), t0 + timedelta(hours=3)), 2)
    row["prior_units"] = round(units_between(t0 - timedelta(hours=4), t0 - timedelta(minutes=45)), 2)
    lo, hi = bisect_left(meal_starts, t0 + timedelta(minutes=31)), bisect_left(meal_starts, t0 + timedelta(hours=3))
    row["more_food"] = hi > lo
    lo, hi = bisect_left(meal_starts, t0 - timedelta(hours=3)), bisect_left(meal_starts, t0)
    row["prior_food"] = hi > lo
    row["bg0"] = at(t0)
    row["bg_m30"] = at(t0 - timedelta(minutes=30))
    w = window(t0 + timedelta(minutes=165), t0 + timedelta(minutes=195))
    row["bg3h"] = round(sum(w) / len(w), 2) if len(w) >= 3 else None
    w = window(t0 + timedelta(minutes=225), t0 + timedelta(minutes=255))
    row["bg4h"] = round(sum(w) / len(w), 2) if len(w) >= 3 else None
    if shadow_meal_estimate is not None and row["bg0"] is not None:
        trend = (
            (row["bg0"] - row["bg_m30"]) / 30.0 if row["bg_m30"] is not None else None
        )
        shadow = shadow_meal_estimate(
            production_meal_units=row["prod"],
            carbs_g=carbs,
            fat_g=row["fat"],
            trend_mmol_l_per_min=trend,
            after_sleep=bool(row["after_sleep"]),
        )
        row["shadow"] = shadow.shadow_meal_units if shadow is not None else None
    w = window(t0 + timedelta(minutes=30), t0 + timedelta(hours=4))
    row["nadir"] = round(min(w), 2) if len(w) >= 20 else None
    row["peak"] = round(max(w), 2) if len(w) >= 20 else None
    print(json.dumps(row))
