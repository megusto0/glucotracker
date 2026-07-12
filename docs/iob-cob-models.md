# IOB & COB models (data-calibrated)

**Status:** implemented on the backend dashboard summary and twin insulin kernel  
**Scope:** informational on-board estimates for the glucose / Nightscout views — **not** dose guidance  
**Primary code:** `backend/glucotracker/application/twin/kernels.py`,  
`backend/glucotracker/application/glucose_dashboard.py`

---

## What was added

### 1. Biphasic insulin on board (IOB)

Replaced the simple **linear** “remaining = dose × (1 − t/DIA)” model with a
**data-calibrated biphasic** curve:

| API / concept | Meaning |
|---|---|
| `insulin_cumulative_absorbed(t, dia)` | Fraction of total insulin *action* delivered by time `t` |
| `insulin_iob_remaining_fraction(t, dia)` | IOB / dose still active |
| `insulin_activity_shape(t, dia)` | Instantaneous action rate, peak-normalized to 1 |
| `insulin_effect(...)` | Twin BG effect uses the new activity shape (peak amplitude still `units × isf`) |

Dashboard summary `iob_units` / `iob_minutes_remaining` use `decay="insulin_pd"`.

### 2. Macro-based carbs on board (COB)

COB is no longer a single global linear duration for every meal. Each meal is
classified from macros and gets its own absorption curve:

| Profile | Typical foods | Duration |
|---|---|---|
| **fast** | Energy drinks, pure sugar liquids, gels | **120 min** |
| **normal** | Fruit, potato, moderate mixed meals | **240 min** (or twin `carb_duration_minutes` when used as default) |
| **slow** | High fat/protein (egg salad, chocolate, heavy plates) | **420 min** |

Dashboard food events now include optional:

- `protein_g`, `fat_g`, `fiber_g`
- `absorption_profile` (`fast` \| `normal` \| `slow`)
- `absorption_minutes`

COB summary uses `decay="carb_pd"` (per-meal curve). Food lookback is up to **6 h**
so slow meals still count.

### 3. Supporting fixes already related

- CORS for browser desktop → API (login / fetch).
- Dashboard range filters convert **local wall time → UTC** so CGM windows are not empty under a UTC DB session.
- Nightscout page layout / chart sizing (separate UI commit history).

---

## Why

### Linear IOB was wrong for real rapid insulin

Historical CGM + insulin (owner with the richest log, isolated boluses) showed:

- Action is **front-loaded** (peak *rate* early, ~30–90 min).
- **Not** “most of the dose gone by 90 min” as cumulative effect:
  - ~25–35% of action by ~60–90 min  
  - ~60% by ~3 h  
  - long **tail** to ~5–6 h  

Linear DIA decay underestimates late IOB; the old bilinear twin peak dumped
too much effect mid-window.

### Twin ICR/ISF fit is a separate problem

The least-squares twin fit hit hard bounds (`ICR_MAX=40`, `ISF_MIN=0.2`) and
stored non-physiological parameters. That is **not** fixed by the IOB curve
alone, but the new kernel keeps peak amplitude = `units × isf` so once ISF/ICR
are sane, timing is more realistic.

Empirical ICR from meal+insulin history was closer to **~6–8 g/U**, not 40;
ISF from corrections closer to **~3+ mmol/L per U**, not 0.2.

### One COB duration cannot describe real meals

Same-day examples from the diary:

| Meal | Macros (C/P/F) | Expected |
|---|---|---|
| Energy drink (Adrenaline / Burn) | ~54 / 0 / 0 | Fast liquid sugar |
| Egg & vegetable salad | ~14.5 / 12.5 / 16.2 | Slow, long COB tail |

CGM history (low nearby insulin) supported:

- **Pure carb / drinks:** sharper rise, often largely done by ~2 h when not stacked.
- **High fat/protein:** slower early rise and **prolonged / second-wave** elevation toward 4–6 h.

---

## How (method)

### IOB curve

1. Take boluses with little nearby food/insulin (isolated corrections).
2. Resample CGM; estimate drop-rate (activity) after the bolus.
3. Integrate activity → **cumulative action delivered**.
4. Average curves → piecewise knots on a 0–360 min reference horizon.
5. For a twin DIA ≠ 360, **time-scale** the curve so it completes at `dia_minutes`.
6. IOB remaining = `1 − cumulative`; minutes remaining = search until residual ≲ 2%.

Reference cumulative knots (fraction absorbed):

```
0 → 0.00
30 → 0.12
60 → 0.25
90 → 0.35
120 → 0.45
180 → 0.60
240 → 0.73
270 → 0.78
300 → 0.87
360 → 1.00
```

### COB curves

1. Bucket historical meals by macros (pure carb vs high fat/protein vs mixed).
2. Prefer windows with **low nearby insulin** so IOB does not erase the rise.
3. Inspect time-to-peak, return toward baseline, late elevation.
4. Encode three cumulative profiles (`fast` / `normal` / `slow`) and durations.
5. Classify each new meal with `classify_carb_profile(...)` from C/P/F/fiber.
6. COB remaining = `carbs_g × carb_cob_remaining_fraction(elapsed, duration, profile)`.

Rough practical table (after eating):

| +min | Fast (energy drink) COB | Slow (egg salad) COB |
|---:|---|---|
| 60 | ~30% left | ~80%+ left |
| 90 | ~12% left | ~70% left |
| 120 | **gone** | ~60% left |
| 240 | gone | still meaningful tail |

### Classification rules (heuristic + history)

- **fast:** almost only carbs, negligible fat/protein/fiber (drinks, pure sugar).
- **slow:** high fat and/or protein vs carbs (and high absolute fat sweets).
- **normal:** everything else (starch, fruit, moderate mixed); duration can fall back to twin `carb_duration_minutes` when provided.

---

## Files touched

| File | Role |
|---|---|
| `backend/glucotracker/application/twin/kernels.py` | IOB + COB math, classification, activity shapes |
| `backend/glucotracker/application/glucose_dashboard.py` | Wire `insulin_pd` / `carb_pd` into summary; enrich food events |
| `backend/glucotracker/api/schemas.py` | Optional food-event macro / absorption fields |
| `backend/tests/application/twin/test_estimator.py` | Kernel unit tests |
| `backend/tests/test_user_isolation.py` | Dashboard IOB/COB expectations |

---

## Limits / next steps

- Curves are **population-of-one** (richest historical owner log), not multi-user.
- Insulin still confounds many meal windows; pure-carb sample is smaller.
- Twin **fitter bounds / ICR·ISF values** still need a dedicated fix.
- Optional next: per-title or per-pattern curves (always treat “Burn/Adrenaline” as fast; “халва/сырок” as slow dual-wave).
- Optional: drive twin `carb_effect` fully via `carb_effect_for_meal` using macros on every meal event.

---

## Medical note

IOB/COB on the dashboard are **informational diary context**, same as the rest of
Glucotracker. They are not closed-loop insulin dosing advice.
