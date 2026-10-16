"""Best-guess ICR/ISF and what moves them: python ratio_profile_analysis.py ratio.jsonl"""

import json
import sys

import numpy as np
import pandas as pd

rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.startswith("{")]
d = pd.DataFrame(rows)
d["t"] = pd.to_datetime(d["t"], format="ISO8601")
d["day"] = (d["t"] - pd.Timedelta(hours=5)).dt.date  # a "day" starts at 05:00
rng = np.random.default_rng(0)
meals = d[d.kind == "meal"].copy()
corr = d[d.kind == "correction"].copy()


def daypart(h):
    return "night 0-6" if h < 6 else "morning 6-11" if h < 11 else "day 11-17" if h < 17 else "evening 17-24"


def boot_median(df, col, n=2000, weight=None):
    days = df["day"].unique()
    groups = {k: g for k, g in df.groupby("day")}
    out = []
    for _ in range(n):
        pick = rng.choice(days, len(days))
        s = pd.concat([groups[k] for k in pick])
        out.append(np.median(s[col]))
    return np.percentile(out, [5, 95])


meals["daypart"] = meals.hour.map(daypart)
meals["insulin_total"] = meals.given + meals.late + meals.prior_iob
clean = meals[
    (meals.more_carbs_4h < 5)
    & (meals.prior_carbs_3h < 5)
    & meals.bg0.notna()
    & meals.bg4h.notna()
    & (meals.given + meals.late > 0)
].copy()
clean["first_after_sleep"] = (clean.hours_since_prev_meal.fillna(99) >= 7) & clean.slept_h.notna()
clean["fat_ratio"] = clean.fat / clean.carbs
print(f"meals ≥15 g: {len(meals)}; clean 4 h windows with insulin: {len(clean)} over {clean.day.nunique()} days")
print(f"period {meals.t.min():%Y-%m-%d} … {meals.t.max():%Y-%m-%d}")

print("\n=== 1. Implied ICR per meal = carbs / (all insulin on it + Δ4h / ISF)")
for isf in (1.5, 2.6, 3.5):
    need = clean.insulin_total + (clean.bg4h - clean.bg0) / isf
    icr = (clean.carbs / need).where((need > 0.3))
    ok = icr.between(3, 40)
    c = clean[ok].assign(icr=icr[ok])
    lo, hi = boot_median(c, "icr")
    print(f"  ISF {isf}: overall median {c.icr.median():.1f} g/U  (CI90 {lo:.1f}–{hi:.1f}, n={len(c)}, dropped {int((~ok).sum())})")
    clean[f"icr_{isf}"] = icr.where(ok)

c = clean.dropna(subset=["icr_2.6"]).copy()
c["icr"] = c["icr_2.6"]
print("\n  by time of day (ISF 2.6 label):")
for part, g in c.groupby("daypart"):
    lo, hi = boot_median(g, "icr")
    print(f"    {part:13s} n={len(g):3d}  median {g.icr.median():5.1f}  CI90 {lo:.1f}–{hi:.1f}   (same at ISF 1.5: {g['icr_1.5'].median():.1f}, 3.5: {g['icr_3.5'].median():.1f})")

print("\n=== 2. What moves ICR: log(ICR) regression, day-bootstrap (ISF 2.6 label)")
c["log_icr"] = np.log(c.icr)
c["log_carbs"] = np.log(c.carbs)
c["fat_ratio_c"] = c.fat_ratio.clip(0, 1.5)
c["steps_k"] = (c.steps.fillna(c.steps.median()) / 1000).clip(0, 10)
c["steps_missing"] = c.steps.isna().astype(float)
c["slept_c"] = c.slept_h.fillna(c.slept_h.median()).clip(2, 12)
c["after_sleep"] = c.first_after_sleep.astype(float)
c["novorapid"] = (c.t >= pd.Timestamp("2026-08-10")).astype(float)
c["weekend"] = (c.weekday >= 5).astype(float)
c["start_high"] = (c.bg0 - 6).clip(-3, 8)
c["exercise_f"] = c.exercise.astype(float)
for p in ["night 0-6", "morning 6-11", "evening 17-24"]:
    c[p] = (c.daypart == p).astype(float)
features = [
    "night 0-6", "morning 6-11", "evening 17-24", "after_sleep", "log_carbs", "fat_ratio_c",
    "steps_k", "exercise_f", "slept_c", "start_high", "weekend", "novorapid",
]
X = np.column_stack([np.ones(len(c))] + [c[f].to_numpy(float) for f in features])
y = c.log_icr.to_numpy()


def huber(X, y, k=1.0, iters=30):
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(iters):
        r = y - X @ b
        s = np.median(np.abs(r)) / 0.6745 + 1e-9
        w = np.clip(k * s / np.maximum(np.abs(r), 1e-9), None, 1.0)
        W = np.sqrt(w)
        b = np.linalg.lstsq(X * W[:, None], y * W, rcond=None)[0]
    return b


b = huber(X, y)
days = c.day.unique()
idx = {k: np.where(c.day.to_numpy() == k)[0] for k in days}
B = []
for _ in range(500):
    pick = np.concatenate([idx[k] for k in rng.choice(days, len(days))])
    B.append(huber(X[pick], y[pick]))
B = np.array(B)
print(f"  n={len(c)} meals, {len(days)} days; baseline = daytime 11-17, weekday, Fiasp period")
units = {"log_carbs": "per doubling of carbs", "fat_ratio_c": "per +0.5 g fat/g carb", "steps_k": "per 1000 steps (−1…+3 h)",
         "slept_c": "per +1 h sleep", "start_high": "per +1 mmol/L at start"}
for j, f in enumerate(features, start=1):
    scale = {"log_carbs": np.log(2), "fat_ratio_c": 0.5}.get(f, 1.0)
    eff = np.exp(b[j] * scale) - 1
    lo, hi = np.exp(np.percentile(B[:, j] * scale, [5, 95])) - 1
    flag = "  *" if lo > 0 or hi < 0 else ""
    print(f"  {f:14s} {eff*100:+6.1f}% ICR {units.get(f, ''):26s} CI90 {lo*100:+.0f}…{hi*100:+.0f}%{flag}")
print("  (+% = more grams per unit = less insulin needed; * = interval excludes 0)")

print("\n=== 3. ISF from food-free corrections")
corr["trend60"] = corr.bg0 - corr.bg_m60
corr["fall_3_4h"] = corr.bg0 - corr[["bg180", "bg240"]].mean(axis=1)
base = corr[corr.bg0.notna() & corr.fall_3_4h.notna() & (corr.other_insulin_4h == 0)]
for name, g in [
    ("all food-free corrections", base),
    ("start ≥ 7.5", base[base.bg0 >= 7.5]),
    ("level start (|Δ60| ≤ 0.6), ≥ 7.5", base[(base.bg0 >= 7.5) & (base.trend60.abs() <= 0.6)]),
    ("rising start (Δ60 > 0.6), ≥ 7.5", base[(base.bg0 >= 7.5) & (base.trend60 > 0.6)]),
]:
    if len(g) == 0:
        print(f"  {name}: none")
        continue
    isf = g.fall_3_4h / (g.units + g.prior_iob * 0.6)
    print(f"  {name:36s} n={len(g):2d}  ISF (fall to 3–4 h mean / U) median {isf.median():.2f}  IQR {isf.quantile(.25):.2f}–{isf.quantile(.75):.2f}")

print("\n=== 4. ISF and CSF jointly from meal windows: Δ4h = CSF·carbs − ISF·insulin + c")
X2 = np.column_stack([np.ones(len(c)), c.carbs, -c.insulin_total])
y2 = (c.bg4h - c.bg0).to_numpy()
b2 = huber(X2, y2)
B2 = []
for _ in range(500):
    pick = np.concatenate([idx[k] for k in rng.choice(days, len(days))])
    B2.append(huber(X2[pick], y2[pick]))
B2 = np.array(B2)
print(f"  ISF {b2[2]:.2f} (CI90 {np.percentile(B2[:,2],5):.2f}–{np.percentile(B2[:,2],95):.2f}); CSF {b2[1]:.3f}/g; implied ICR {b2[2]/b2[1]:.1f} g/U"
      f" (CI90 {np.percentile(B2[:,2]/B2[:,1],5):.1f}–{np.percentile(B2[:,2]/B2[:,1],95):.1f}) — attenuated by confounding, a lower bound on ISF")

print("\n=== 5. Fixed + proportional: need = a + carbs / ICR_marginal (clean meals)")
for isf in (1.5, 2.6, 3.5):
    need = (c.insulin_total + (c.bg4h - c.bg0) / isf).to_numpy()
    X3 = np.column_stack([np.ones(len(c)), c.carbs])
    b3 = huber(X3, need)
    B3 = []
    for _ in range(500):
        pick = np.concatenate([idx[k] for k in rng.choice(days, len(days))])
        B3.append(huber(X3[pick], need[pick]))
    B3 = np.array(B3)
    print(f"  ISF {isf}: need ≈ {b3[0]:.1f} U + carbs / {1/b3[1]:.1f}  (fixed CI90 {np.percentile(B3[:,0],5):.1f}…{np.percentile(B3[:,0],95):.1f} U; marginal ICR CI90 {1/np.percentile(B3[:,1],95):.1f}–{1/np.percentile(B3[:,1],5):.1f})")
print("  ICR by meal size (ISF 2.6):", c.groupby(pd.cut(c.carbs, [0, 30, 50, 80, 300]), observed=True).icr.agg(["median", "size"]).round(1).to_dict("index"))

print("\n=== 6. First meal after sleep (the calculator currently tightens ICR by ×0.82 here)")
for k, g in c.groupby("first_after_sleep"):
    print(f"  first_after_sleep={k}: n={len(g)} median ICR {g.icr.median():.1f}, median carbs {g.carbs.median():.0f}")
