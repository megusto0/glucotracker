"""Episode ledger for the response-attribution prototype.

Reads a private CSV extract (never committed) and builds one row per food
sitting with everything the later layers need: the bolus that went with it,
what was already on board, the calibrated-free raw CGM path, activity and
sleep context, and an explicit exclusion reason when the episode cannot vote.

All times are converted to naive local wall clock (Europe/Samara, fixed +04:00),
the same convention the backend uses for ``meals.eaten_at``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

LOCAL_OFFSET = pd.Timedelta(hours=4)
SITTING_SPAN = pd.Timedelta(minutes=30)
BOLUS_BEFORE = pd.Timedelta(minutes=30)
BOLUS_AFTER = pd.Timedelta(minutes=60)
CGM_TOLERANCE = pd.Timedelta(minutes=7)
DUPLICATE_DOSE_GAP = pd.Timedelta(seconds=120)
OFFSETS_MIN = tuple(range(-30, 361, 15))


def _local(values: pd.Series) -> pd.Series:
    """Parse tz-aware strings and return naive local wall clock."""
    instants = pd.to_datetime(values, utc=True, format="ISO8601")
    return (instants + LOCAL_OFFSET).dt.tz_localize(None)


@dataclass
class Data:
    meals: pd.DataFrame
    insulin: pd.DataFrame
    cgm: pd.DataFrame
    steps: pd.DataFrame
    sleep: pd.DataFrame
    sittings: pd.DataFrame = field(default_factory=pd.DataFrame)


def load(root: Path) -> Data:
    meals = pd.read_csv(root / "live_meals.csv")
    meals["at"] = pd.to_datetime(meals["eaten_at"], format="ISO8601")
    for column in ("total_carbs_g", "total_protein_g", "total_fat_g", "total_fiber_g"):
        meals[column] = meals[column].fillna(0.0)
    meals = meals.sort_values("at").reset_index(drop=True)

    insulin = pd.read_csv(root / "live_insulin.csv")
    insulin["at"] = _local(insulin["timestamp"])
    insulin = insulin.sort_values("at").reset_index(drop=True)
    # The same dose arrives twice when the Nightscout echo and the local write
    # both land; keep the first of an identical pair inside two minutes.
    keep = np.ones(len(insulin), dtype=bool)
    for i in range(1, len(insulin)):
        same = insulin.at[i, "insulin_units"] == insulin.at[i - 1, "insulin_units"]
        close = insulin.at[i, "at"] - insulin.at[i - 1, "at"] <= DUPLICATE_DOSE_GAP
        if same and close and keep[i - 1]:
            keep[i] = False
    insulin = insulin[keep].reset_index(drop=True)

    cgm = pd.read_csv(root / "live_cgm.csv")
    cgm["at"] = _local(cgm["timestamp"])
    cgm = cgm.drop_duplicates("at").sort_values("at")
    sensors = pd.read_csv(root / "live_sensors.csv")
    for _, s in sensors[sensors["excluded_from_analytics"] == "t"].iterrows():
        start = _local(pd.Series([s["started_at"]]))[0]
        end = _local(pd.Series([s["ended_at"]]))[0]
        cgm = cgm[(cgm["at"] < start) | (cgm["at"] > end)]
    cgm = cgm[(cgm["value_mmol_l"] >= 2.0) & (cgm["value_mmol_l"] <= 25.0)]
    cgm = cgm.reset_index(drop=True)

    hc = pd.read_csv(root / "live_hc.csv")
    payload = hc["payload"].map(json.loads)
    hc["start"] = _local(payload.map(lambda p: p.get("startTime")))
    hc["end"] = _local(payload.map(lambda p: p.get("endTime")))
    steps = hc[hc["record_type"] == "StepsRecord"].copy()
    steps["count"] = payload[steps.index].map(lambda p: float(p.get("count") or 0))
    sleep = hc[hc["record_type"] == "SleepSessionRecord"][["start", "end"]].copy()

    data = Data(meals=meals, insulin=insulin, cgm=cgm, steps=steps, sleep=sleep)
    data.sittings = _sittings(meals)
    return data


def _sittings(meals: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    current: dict | None = None
    for _, meal in meals.iterrows():
        if current is not None and meal["at"] - current["at"] <= SITTING_SPAN:
            current["carbs"] += meal["total_carbs_g"]
            current["protein"] += meal["total_protein_g"]
            current["fat"] += meal["total_fat_g"]
            current["fiber"] += meal["total_fiber_g"]
            current["kcal"] += meal["total_kcal"] or 0.0
            current["sources"].add(meal["source"])
            current["end"] = meal["at"]
            continue
        current = {
            "at": meal["at"],
            "end": meal["at"],
            "carbs": meal["total_carbs_g"],
            "protein": meal["total_protein_g"],
            "fat": meal["total_fat_g"],
            "fiber": meal["total_fiber_g"],
            "kcal": meal["total_kcal"] or 0.0,
            "sources": {meal["source"]},
        }
        rows.append(current)
    frame = pd.DataFrame(rows)
    frame["source"] = frame["sources"].map(lambda s: next(iter(s)) if len(s) == 1 else "mixed")
    return frame.drop(columns="sources")


def cgm_at(cgm: pd.DataFrame, at: pd.Timestamp) -> float:
    times = cgm["at"].to_numpy()
    i = np.searchsorted(times, np.datetime64(at))
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            gap = abs(pd.Timestamp(times[j]) - at)
            if gap <= CGM_TOLERANCE and (best is None or gap < best[0]):
                best = (gap, cgm["value_mmol_l"].iat[j])
    return float(best[1]) if best else float("nan")


def food_episodes(data: Data, *, clean_minutes: int = 300) -> pd.DataFrame:
    """One row per food sitting with ≥20 g carbs, flagged clean or not."""
    s, ins = data.sittings, data.insulin
    clean_after = pd.Timedelta(minutes=clean_minutes)
    rows = []
    for _, sit in s[s["carbs"] >= 20].iterrows():
        t0 = sit["at"]
        bolus = ins[(ins["at"] >= t0 - BOLUS_BEFORE) & (ins["at"] <= t0 + BOLUS_AFTER)]
        units = float(bolus["insulin_units"].sum())
        first_bolus = (bolus["at"].min() - t0).total_seconds() / 60 if len(bolus) else np.nan
        prior_ins = ins[(ins["at"] >= t0 - pd.Timedelta(hours=5)) & (ins["at"] < t0 - BOLUS_BEFORE)]
        prior_iob = _remaining_iob(prior_ins, t0)
        later_ins = ins[(ins["at"] > t0 + BOLUS_AFTER) & (ins["at"] <= t0 + clean_after)]
        later_food = s[(s["at"] > sit["end"]) & (s["at"] <= t0 + clean_after) & ((s["carbs"] >= 3) | (s["kcal"] >= 40))]
        prior_food = s[(s["at"] >= t0 - pd.Timedelta(hours=3)) & (s["at"] < t0) & (s["carbs"] >= 3)]
        win = data.steps[(data.steps["start"] >= t0 - pd.Timedelta(hours=1)) & (data.steps["start"] < t0 + pd.Timedelta(hours=3))]
        slept = data.sleep[(data.sleep["end"] <= t0) & (data.sleep["end"] >= t0 - pd.Timedelta(hours=14))]
        path = {m: cgm_at(data.cgm, t0 + pd.Timedelta(minutes=m)) for m in OFFSETS_MIN}

        reason = None
        if units <= 0:
            reason = "no_bolus"
        elif len(later_food):
            reason = "more_food"
        elif len(later_ins):
            reason = "more_insulin"
        elif len(prior_food):
            reason = "prior_food"
        elif prior_iob >= 0.5:
            reason = "prior_insulin"
        elif np.isnan(path[0]) or path[0] < 4.0:
            reason = "low_or_missing_start"
        elif any(np.isnan(path[m]) for m in (120, 180, 240, 300)):
            reason = "cgm_gap"

        rows.append(
            {
                "t0": t0,
                "hour": t0.hour + t0.minute / 60,
                "carbs": sit["carbs"],
                "protein": sit["protein"],
                "fat": sit["fat"],
                "fiber": sit["fiber"],
                "kcal": sit["kcal"],
                "source": sit["source"],
                "units": units,
                "bolus_offset_min": first_bolus,
                "prior_iob": prior_iob,
                "steps_window": float(win["count"].sum()) if len(win) else np.nan,
                "slept_h": float(((slept["end"] - slept["start"]).dt.total_seconds() / 3600).sum()) if len(slept) else np.nan,
                "novorapid": t0 >= pd.Timestamp("2026-08-10"),
                "exclusion": reason,
                **{f"bg_{m}": v for m, v in path.items()},
            }
        )
    return pd.DataFrame(rows)


# Population cumulative insulin action from twin/kernels.py (360 min horizon).
_INSULIN_KNOTS = np.array(
    [(0, 0), (30, 0.12), (60, 0.25), (90, 0.35), (120, 0.45), (150, 0.54), (180, 0.60),
     (210, 0.65), (240, 0.73), (270, 0.78), (300, 0.87), (330, 0.93), (360, 1.0)],
    dtype=float,
)


def insulin_cum(minutes: float | np.ndarray) -> np.ndarray:
    return np.interp(minutes, _INSULIN_KNOTS[:, 0], _INSULIN_KNOTS[:, 1], left=0.0, right=1.0)


def _remaining_iob(events: pd.DataFrame, at: pd.Timestamp) -> float:
    if events.empty:
        return 0.0
    minutes = (at - events["at"]).dt.total_seconds().to_numpy() / 60
    return float((events["insulin_units"].to_numpy() * (1 - insulin_cum(minutes))).sum())


def fasting_windows(data: Data, *, span_min: int = 180, washout_min: int = 240) -> pd.DataFrame:
    """Background drift over carb- and bolus-free spans, one per local hour."""
    events = np.sort(
        np.concatenate(
            [
                data.sittings.loc[data.sittings["carbs"] >= 3, "at"].to_numpy(),
                data.insulin["at"].to_numpy(),
            ]
        )
    )
    start = data.cgm["at"].min().ceil("h")
    end = data.cgm["at"].max().floor("h")
    rows = []
    for t in pd.date_range(start, end, freq="h"):
        lo = np.datetime64(t - pd.Timedelta(minutes=washout_min))
        hi = np.datetime64(t + pd.Timedelta(minutes=span_min))
        if np.searchsorted(events, hi) - np.searchsorted(events, lo):
            continue
        a, b = cgm_at(data.cgm, t), cgm_at(data.cgm, t + pd.Timedelta(minutes=span_min))
        if np.isnan(a) or np.isnan(b) or a < 4.0:
            continue
        rows.append({"t": t, "hour": t.hour, "start": a, "drift": b - a, "novorapid": t >= pd.Timestamp("2026-08-10")})
    return pd.DataFrame(rows)
