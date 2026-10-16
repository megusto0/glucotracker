"""Superposition model: every meal and every dose on one timeline.

Isolated-episode estimators need a meal with nothing else for hours around it.
This owner eats again within five hours in most sittings, so those estimators
see a handful of episodes. Here each 30-minute CGM change is explained by the
part of every recent meal and dose that acted inside that half hour:

    ΔBG[t, t+30] = Σ_m CSF_g(m) · carbs_m · ΔFc_m
                 − ISF_g     · Σ_i units_i · ΔFi_i
                 + drift_g(h) · 0.5 h
                 + ε

ΔF is the change of the cumulative action curve across the interval, taken
from the backend kernels (``twin/kernels.py``) with a time stretch that is
chosen by held-out error, not assumed. The model is linear in CSF, ISF and the
drifts, so the fit is a robust least squares and the ICR it implies is
ISF / CSF. Groups g are daypart × insulin (Fiasp before 2026-08-10, NovoRapid after; same pump).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from glucotracker.application.twin.kernels import (  # noqa: E402
    carb_cumulative_absorbed,
    carb_absorption_duration_minutes,
    classify_carb_profile,
    insulin_cumulative_absorbed,
)

STEP_MIN = 30
LOOKBACK_MIN = 8 * 60
INSULIN_SWITCH = pd.Timestamp("2026-08-10")
DAYPARTS = (("night", 0, 6), ("morning", 6, 11), ("day", 11, 18), ("evening", 18, 24))


def daypart(hour: float) -> str:
    for name, lo, hi in DAYPARTS:
        if lo <= hour < hi:
            return name
    return "night"


def regime(at: pd.Timestamp) -> str:
    return "novorapid" if at >= INSULIN_SWITCH else "fiasp"


@dataclass(frozen=True)
class Kernels:
    insulin_stretch: float = 1.0  # 1.0 = 360-minute reference curve
    carb_stretch: float = 1.0

    def insulin(self, minutes: np.ndarray) -> np.ndarray:
        dia = int(round(360 * self.insulin_stretch))
        return np.array([insulin_cumulative_absorbed(float(m), dia) for m in minutes])

    def carbs(self, minutes: np.ndarray, profile: str, duration: int) -> np.ndarray:
        d = int(round(duration * self.carb_stretch))
        return np.array(
            [carb_cumulative_absorbed(float(m), duration_min=d, profile=profile) for m in minutes]
        )


def cgm_grid(cgm: pd.DataFrame, step_min: int = 5, max_gap_min: int = 15) -> pd.Series:
    """Raw CGM on a regular grid; short gaps interpolated, long gaps left empty."""
    s = cgm.set_index("at")["value_mmol_l"].sort_index()
    s = s[~s.index.duplicated()]
    grid = pd.date_range(s.index.min().ceil(f"{step_min}min"), s.index.max(), freq=f"{step_min}min")
    merged = s.reindex(s.index.union(grid)).interpolate(method="time", limit_area="inside")
    # Blank grid points whose nearest raw reading is too far away.
    raw_times = s.index.to_numpy()
    pos = np.searchsorted(raw_times, grid.to_numpy())
    left = np.abs(grid.to_numpy() - raw_times[np.clip(pos - 1, 0, len(raw_times) - 1)])
    right = np.abs(raw_times[np.clip(pos, 0, len(raw_times) - 1)] - grid.to_numpy())
    near = np.minimum(left, right) <= np.timedelta64(max_gap_min, "m")
    out = merged.reindex(grid)
    out[~near] = np.nan
    return out


@dataclass
class Design:
    frame: pd.DataFrame  # one row per interval: t, y, group keys
    carb: np.ndarray  # n × G   (carbs · ΔFc summed per group)
    insulin: np.ndarray  # n × R   (units · ΔFi summed per regime)
    drift: np.ndarray  # n × G   (0.5 h indicator per group)
    groups: list[str]
    regimes: list[str]


def build_design(
    sittings: pd.DataFrame,
    insulin: pd.DataFrame,
    grid: pd.Series,
    kernels: Kernels,
    *,
    meal_scale: np.ndarray | None = None,
    horizon_min: int = STEP_MIN,
) -> Design:
    t = grid.index
    starts = t[(t.minute % STEP_MIN == 0)]
    y0 = grid.reindex(starts).to_numpy()
    y1 = grid.reindex(starts + pd.Timedelta(minutes=horizon_min)).to_numpy()
    ok = np.isfinite(y0) & np.isfinite(y1) & (y0 >= 3.9)
    starts, y0, y1 = starts[ok], y0[ok], y1[ok]
    n = len(starts)

    groups = sorted({f"{regime(s)}:{daypart(s.hour)}" for s in starts})
    regimes = sorted({regime(s) for s in starts})
    gidx = {g: i for i, g in enumerate(groups)}
    ridx = {r: i for i, r in enumerate(regimes)}
    row_group = np.array([gidx[f"{regime(s)}:{daypart(s.hour)}"] for s in starts])
    row_regime = np.array([ridx[regime(s)] for s in starts])

    start_ns = starts.to_numpy()
    carb = np.zeros((n, len(groups)))
    ins = np.zeros((n, len(regimes)))
    lookback = np.timedelta64(LOOKBACK_MIN, "m")

    for k, meal in enumerate(sittings.itertuples(index=False)):
        if meal.carbs <= 0:
            continue
        at = np.datetime64(meal.at)
        lo, hi = np.searchsorted(start_ns, at - np.timedelta64(horizon_min, "m")), np.searchsorted(start_ns, at + lookback)
        if lo >= hi:
            continue
        profile = classify_carb_profile(carbs_g=meal.carbs, protein_g=meal.protein, fat_g=meal.fat, fiber_g=meal.fiber)
        duration = carb_absorption_duration_minutes(carbs_g=meal.carbs, protein_g=meal.protein, fat_g=meal.fat, fiber_g=meal.fiber)
        m0 = (start_ns[lo:hi] - at) / np.timedelta64(1, "m")
        d = kernels.carbs(m0 + horizon_min, profile, duration) - kernels.carbs(m0, profile, duration)
        scale = 1.0 if meal_scale is None else meal_scale[k]
        g = gidx.get(f"{regime(meal.at)}:{daypart(meal.at.hour + meal.at.minute / 60)}")
        if g is None:
            continue
        # The meal's own daypart owns its CSF, wherever its tail lands.
        carb[lo:hi, g] += meal.carbs * scale * d

    for dose in insulin.itertuples(index=False):
        at = np.datetime64(dose.at)
        lo, hi = np.searchsorted(start_ns, at - np.timedelta64(horizon_min, "m")), np.searchsorted(start_ns, at + lookback)
        if lo >= hi:
            continue
        m0 = (start_ns[lo:hi] - at) / np.timedelta64(1, "m")
        d = kernels.insulin(m0 + horizon_min) - kernels.insulin(m0)
        ins[lo:hi, ridx[regime(dose.at)]] -= dose.insulin_units * d

    drift = np.zeros((n, len(groups)))
    drift[np.arange(n), row_group] = horizon_min / 60
    frame = pd.DataFrame({"t": starts, "y": y1 - y0, "bg": y0, "group": row_group, "regime": row_regime})
    return Design(frame, carb, ins, drift, groups, regimes)


@dataclass
class Fit:
    csf: dict[str, float]
    isf: dict[str, float]
    drift: dict[str, float]
    icr: dict[str, float]
    coef: np.ndarray


def matrix(d: Design) -> np.ndarray:
    return np.hstack([d.carb, d.insulin, d.drift])


def fit(d: Design, rows: np.ndarray | None = None, *, f_scale: float = 0.3) -> Fit:
    X = matrix(d)
    y = d.frame["y"].to_numpy()
    if rows is not None:
        X, y = X[rows], y[rows]
    G, R = len(d.groups), len(d.regimes)
    lower = np.r_[np.zeros(G + R), np.full(G, -np.inf)]
    upper = np.full(2 * G + R, np.inf)
    x0 = np.r_[np.full(G, 0.3), np.full(R, 2.0), np.zeros(G)]
    res = least_squares(lambda b: X @ b - y, x0, bounds=(lower, upper), loss="soft_l1", f_scale=f_scale)
    b = res.x
    csf = dict(zip(d.groups, b[:G]))
    isf = dict(zip(d.regimes, b[G : G + R]))
    drift = dict(zip(d.groups, b[G + R :]))
    icr = {g: (isf[g.split(":")[0]] / c if c > 1e-6 else float("inf")) for g, c in csf.items()}
    return Fit(csf, isf, drift, icr, b)


def predict(d: Design, f: Fit) -> np.ndarray:
    return matrix(d) @ f.coef
