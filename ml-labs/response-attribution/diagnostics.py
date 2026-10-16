"""Reproduce the findings in REPORT.md from a private CSV extract.

    python diagnostics.py --data C:\\path\\to\\extract

The extract directory holds ``live_*.csv`` files (see README.md). Only
aggregates are printed; no meal, dose or reading leaves this process.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import Data, food_episodes, load  # noqa: E402
from superposition import Kernels, build_design, cgm_grid, fit  # noqa: E402

LAGS = list(range(-120, 481, 30))
INSULIN_SWITCH = pd.Timestamp("2026-08-10")
ISF_CONFIGURED = 2.6
TARGET = 6.0


def _bootstrap_median(values: np.ndarray, rng: np.random.Generator, n: int = 2000) -> np.ndarray:
    return np.percentile([np.median(rng.choice(values, len(values))) for _ in range(n)], [5, 95])


def coverage(data: Data) -> None:
    print("\n== 1. How much isolated evidence exists")
    for minutes in (120, 180, 300):
        e = food_episodes(data, clean_minutes=minutes)
        print(f"  sittings ≥20 g with nothing else for {minutes} min: {e['exclusion'].isna().sum()} of {len(e)}")
    e = food_episodes(data, clean_minutes=300)
    print("  exclusion reasons (5 h):", e["exclusion"].value_counts().to_dict())
    nb = e[e["exclusion"] == "no_bolus"]
    doses = data.insulin["at"].to_numpy()
    nearest = [((doses - np.datetime64(t)) / np.timedelta64(1, "m"))[np.argmin(np.abs(doses - np.datetime64(t)))] for t in nb["t0"]]
    bins = pd.cut(pd.Series(nearest), [-1e9, -240, -30, 60, 240, 1e9]).value_counts().sort_index()
    print("  'no bolus in −30…+60 min' sittings, nearest dose offset:", {str(k): int(v) for k, v in bins.items()})


def lag_matrix(starts: np.ndarray, times: np.ndarray, amounts: np.ndarray) -> np.ndarray:
    out = np.zeros((len(starts), len(LAGS)))
    for t, a in zip(times, amounts):
        lag = (starts - t) / np.timedelta64(1, "m")
        for j, lo in enumerate(LAGS):
            out[(lag >= lo) & (lag < lo + 30), j] += a
    return out


def placebo_fir(data: Data, grid: pd.Series) -> None:
    """Free-shape response per lag, including lags *before* the event.

    Without confounding, an event cannot move glucose before it happens, so the
    negative-lag sum is a placebo: it should be ≈0.
    """
    print("\n== 2. Distributed-lag response with placebo lags")
    starts = grid.index[grid.index.minute % 30 == 0]
    y0 = grid.reindex(starts).to_numpy()
    y1 = grid.reindex(starts + pd.Timedelta(minutes=30)).to_numpy()
    ok = np.isfinite(y0) & np.isfinite(y1) & (y0 >= 3.9)
    starts, y = starts[ok], (y1 - y0)[ok]
    s = starts.to_numpy()
    meals = data.sittings[data.sittings["carbs"] > 0]
    food = meals["at"].to_numpy()
    ins = data.insulin
    near_food = np.array(
        [((food > np.datetime64(t - pd.Timedelta(hours=2))) & (food < np.datetime64(t + pd.Timedelta(hours=2)))).any() for t in ins["at"]]
    )
    blocks = {
        "carbs, per 10 g": (lag_matrix(s, food, meals["carbs"].to_numpy()), 10.0),
        "meal bolus, per U": (lag_matrix(s, ins.loc[near_food, "at"].to_numpy(), ins.loc[near_food, "insulin_units"].to_numpy()), -1.0),
        "food-free bolus, per U": (lag_matrix(s, ins.loc[~near_food, "at"].to_numpy(), ins.loc[~near_food, "insulin_units"].to_numpy()), -1.0),
    }
    hours = np.zeros((len(s), 6))
    hours[np.arange(len(s)), starts.hour // 4] = 1
    X = np.hstack([b for b, _ in blocks.values()] + [hours])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    days = starts.normalize()
    unique_days = np.unique(days)
    rng = np.random.default_rng(2)
    boot = []
    for _ in range(300):
        pick = rng.choice(unique_days, len(unique_days))
        idx = np.concatenate([np.where(days == d)[0] for d in pick])
        boot.append(np.linalg.lstsq(X[idx], y[idx], rcond=None)[0])
    boot = np.array(boot)
    lags = np.array(LAGS)
    n = len(LAGS)
    effects = {}
    for k, (name, (_, sign)) in enumerate(blocks.items()):
        block = slice(k * n, (k + 1) * n)
        after = sign * beta[block][lags >= 0].sum()
        before = sign * beta[block][lags < 0].sum()
        ci_a = np.percentile(sign * boot[:, block][:, lags >= 0].sum(1), [5, 95])
        ci_b = np.percentile(sign * boot[:, block][:, lags < 0].sum(1), [5, 95])
        effects[name] = after
        print(f"  {name:24s} after: {after:+.2f} {ci_a.round(2)}   placebo before: {before:+.2f} {ci_b.round(2)}")
    print(
        f"  (sign convention: carbs = mmol/L rise, insulin = mmol/L fall; configured ISF {ISF_CONFIGURED})"
    )
    ratio = effects["meal bolus, per U"] / (effects["carbs, per 10 g"] / 10)
    print(f"  ratio meal-bolus effect / carb effect = {ratio:.1f} g/U (ratio only; both magnitudes are attenuated)")


def pooled_kernel_fit(data: Data, grid: pd.Series) -> None:
    print("\n== 3. Pooled kernel regression (what the twin fitter does)")
    for horizon in (60, 120, 180):
        f = fit(build_design(data.sittings, data.insulin, grid, Kernels(), horizon_min=horizon))
        print(f"  Δ over {horizon} min: ISF = {', '.join(f'{k} {v:.2f}' for k, v in f.isf.items())}")


def horizon_drift(data: Data) -> None:
    print("\n== 4. Does reading the outcome at 2–3 h bias ICR?")
    rng = np.random.default_rng(0)
    for clean, pairs in ((180, [(120, 180)]), (300, [(120, 300), (180, 300)])):
        e = food_episodes(data, clean_minutes=clean)
        c = e[e["exclusion"].isna()]
        for a, b in pairs:
            x = (c[f"bg_{b}"] - c[f"bg_{a}"]).dropna().to_numpy()
            ci = _bootstrap_median(x, rng)
            print(f"  clean {clean} min, n={len(x)}: BG {a}->{b} min median {np.median(x):+.2f} CI90 {ci.round(2)}, falling {np.mean(x < 0):.0%}")
        for h in sorted({120, 180, clean}):
            adj = c["units"] + (c[f"bg_{h}"] - TARGET) / ISF_CONFIGURED
            icr = (c["carbs"] / adj).where(adj > 0.25)
            print(f"    implied ICR read at +{h} min: median {icr.median():.1f} g/U")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    data = load(args.data)
    grid = cgm_grid(data.cgm)
    print(f"meals {len(data.meals)}, sittings {len(data.sittings)}, doses {len(data.insulin)}, CGM {len(data.cgm)}")
    coverage(data)
    placebo_fir(data, grid)
    pooled_kernel_fit(data, grid)
    horizon_drift(data)


if __name__ == "__main__":
    main()
