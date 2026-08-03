# Handover — glucose prediction and insulin dosing

Branch `feat/normalized-model-space`, 18 commits on top of `65973e6`.
Owner: admin2. All figures below are that owner's data unless stated.

Read the "Retracted" section before trusting anything else here. Several
confident conclusions in this work were wrong and were caught by the user, not
by the analysis.

---

## 1. Ground rules that cost the most to learn

**Raw CGM is not physiology.** `nightscout_glucose_entries.value_mmol_l` reads
1.0–2.8 mmol/L below true glucose. Reading it directly produced "30% of time in
hypoglycemia" where the normalized figure was 1.6%. Every clinical statement
must use the normalized series. Raw is valid only for raw-on-raw internal
consistency, e.g. the forecast audit.

**A gap in logs is not a signal.** Meals are sometimes not recorded, and a
missing log is indistinguishable from a long fast — and more common. Any rule
keyed on "no meal for N hours" fails in the direction that *raises* the dose.
Corroborate with something that is recorded independently (sleep sessions).

**Attribution windows leak.** Summing insulin in a window around a meal lets
adjacent meals share the same units. This produced a clean-looking "your dose
does not scale with meal size" trend that disappeared entirely when restricted
to isolated sittings. Any per-meal ratio needs an isolation check before it
means anything.

---

## 2. What was changed

### Models trained in normalized space (`8a633fd`)

`application/glucose_normalization.py` is now the single training-space source
for the predictor, the twin ISF/ICR fitter and the on-board kernel fitter. It
calibrates **per sensor session** rather than by whichever sensor is newest.

Same commit: Huber delta 0.8 → 3.0 (the old value was below a typical 60–90 min
move, so every stage optimized L1 and returned a near-flat forecast), quantile
+ conformal intervals replacing `max(0.25, q80, q80)`, audit calibration
weights extended above 1.0, `sensor_age_days` as a feature, duplicate smoothing
pass removed, ~150 lines of dead code deleted.

The prospective audit deliberately stays raw-on-raw. A forecast and its outcome
share a timestamp and therefore share a bias, so stored errors are identical in
both spaces and v4/v5 history stays comparable.

### Replay harness (`2498e9a`, `d4dc026`, `d31a460`)

`backend/scripts/replay_glucose_prediction.py`. Walks a support bundle forward,
deleting everything after each anchor inside a rolled-back transaction, then
scores against what happened. `REPLAY_BACKEND` selects which checkout to import
from, so two runs over one snapshot give an A/B on identical anchors.
`--prepare` converts an exported bundle (ISO timestamps, dashed UUIDs, missing
`users` and `cgm_calibration_models` tables) into something the SQLite driver
can read.

Measured A/B, 137 anchors over 21 days, v5 against v8: lower MAE at 17 of 18
horizons, mean skill +5.2 pp, mean |coverage − 80%| halved from 6.1 to 3.0 pp.

### Dosing changes

| commit | change |
|---|---|
| `9791525` | correction projects with the forecast instead of a 15-min straight line; asymmetric caps (3.0 down, 1.0 up) because a predicted rise is the unreliable direction |
| `1f50303` | `/glucose/top-up-dose` + button on the desktop Nightscout page |
| `95378f8` | fall gate judges where a fall lands over 45 min, not its rate |
| `97e2402` | follow-up boluses reach the training label; top-up no longer says "enough" above the high band |
| `e01a72d` | therapy review cache version bumped so closed days recompute |
| `beb2a20`, `a5b53d2` | first meal after **recorded sleep** gets ICR × 7.1/8.7 |
| `79a017f` | surplus IOB (beyond what prior COB needs) reduces the meal total |
| `73b290c` | `icr_autotune.py` — proposes per-daypart ICR from outcomes, never writes |

### Client

`25b8dcb` coverage line in the Today episode header, `3fc9967` calculation stays
visible after a dose and becomes a comparison, `9b41bef` recommendation scoped to
one sitting rather than the whole episode, `e0880ac` layout/truncation,
`61fbde3` carb-correction marker shows what was eaten rather than the 15 g
default.

---

## 3. Measured facts that survived scrutiny

- **Sensor bias**: additive beats affine and pure gain on LOO-CV over 26
  fingerstick pairs (0.592 / 0.619 / 0.751 MAE). Do not promote a gain model.
  Drift is undetectable pooled (−0.002 ± 0.048/day) while consecutive pairs
  swing ±1.85 — the linear drift term is fitting noise and then being clipped
  by `MAX_DRIFT_PER_DAY = 0.5`.
- **Insulin action ends around 4.5 h, not the kernel's 6.5.** Carb-free windows
  (n=597): 90% of effect by 244 min against the model's 325. The configured
  `dia_minutes = 270` matches the data better than the kernel actually used.
  IOB is therefore overstated in the 3–6 h range.
- **ICR is identifiable, ISF is not.** Four estimators converge on ~8.5 g/U
  against the configured 8.0/9.3/10.0. ISF in insulin-dominant windows fits at
  −0.01 ± 0.08 mmol/L per U — indistinguishable from zero — because 75% of
  boluses land within ±10 min of a meal, so only the ratio is determined.
- **ISF is probably ~4.0, not 2.6.** One genuinely isolated correction
  (2026-08-02 11:35, IOB 0, COB 0: 1.0 U → −4.0 mmol/L) and the 100/TDD rule
  (4.1) agree. n=1 for the direct measurement. **Not changed — owner's call.**
- **All 13 on-board kernel fits are rejected**, and always will be: the gate
  needs 0.10 mmol/L absolute improvement on holdout glucose MAE, while kernel
  shape's entire contribution there is ~0.007 even with a free 28-parameter
  impulse response. The gate asks for 14–140× more than the lever can deliver.
- **Corrections are a third of all insulin** (2.0/day, 8.5 U/day). They mostly
  work — median nadir 6.3, 4% below 3.9 — but 45% are stacked on existing IOB,
  and they correct a *plateau* (median glucose 9.0, rise only +0.50/h), not a
  spike. Basal is not the cause: clean drift is +0.106 mmol/L/h and corrections
  cluster 08–20h.
- **First meal after sleep needs ~18% more insulin per gram** (7.1 vs 8.7 g/U,
  n=18) and those meals run 06:00–20:00 with a median at **14:00**, so a clock
  window cannot capture it. By hour, morning and day are indistinguishable
  (7.7 vs 7.9) while only evening separates (10.1).

---

## 4. Retracted — do not rebuild on these

- ~~"30% of time below 3.9"~~ — raw-scale artifact. Normalized: 1.6%.
- ~~"37% of meal insulin arrives after the meal", "dose centre of mass is
  −35 min"~~ — conflated meal boluses with corrections. Boluses at the meal sit
  on a −0.40/h trend (37% rising); later ones on +1.80/h (86% rising). They are
  two different acts. The original nearest-event measurement (median lag 0,
  75% within ±10 min) was the correct one.
- ~~"your dose does not scale with meal size" (5.8 → 13.5 g/U)~~ — attribution
  artifact. Isolated sittings show 7.3 / 14.3 / 9.6 / 14.2, i.e. no trend.
- ~~"widen the daypart ICR split"~~ — based on two episodes from one day. Over
  75 days the autotuner proposes essentially no change (8.0→8.0, 9.3→8.5,
  10.0→10.1).
- ~~"small meals are eaten on a downtrend"~~ — about half of *all* sittings
  start falling regardless of size; if anything the largest fall most.

**`97e2402` rests on a contested premise.** It counts follow-up boluses toward
the meal's training label. If the rise they answer was caused by that meal,
counting them is right; if by something else, it inflates the recommendation.
The 86%-rising statistic does not distinguish these. Consider making it
conditional (only when the rise began inside that meal's absorption window) or
reverting.

---

## 5. Outstanding

1. **Exercise is invisible to dosing.** `icr_autotune` excludes those episodes;
   `_build_food_coverages` and the twin fitter do not. A meal near a session
   looks like "few carbs, much insulin" and drags ICR down for everything else.
   Twenty sessions in 75 days is enough to exclude, not to model.
2. **ISF** — see above. Owner's decision. Do not ship it in the same release as
   anything else, or the effects mix.
3. **On-board fit acceptance metric** — judge kernel shape on something
   shape-sensitive (post-bolus trajectory at 2–4 h, time to baseline), not on
   aggregate glucose MAE.
4. **`GET /glucose/therapy-analysis`** is still missing from
   `ISOLATION_TEST_ENDPOINTS`; that is the one failing test on this branch and
   it predates this work.
5. Calibration rests on ≤3 stable fingersticks per sensor. Residual scatter
   ~0.55 mmol/L (MARD ~10%) is larger than the forecast's entire advantage over
   persistence (~0.06 at 60 min). Fingerstick capture strategy is worth more
   than forecast modelling.

## 6. Deploy

No migrations. The predictor refits on every request, so nothing to retrain.
The only cache is `therapy_review_caches`, invalidated by the version bump in
`e01a72d`. Desktop needs a rebuild (new endpoint and regenerated types); Android
needs its own build.

Expect meal recommendations to rise ~15% from the label change. Compare against
what is actually injected for the first few days rather than following blind.

## 7. Where things are

Analysis scripts (not committed) lived in the session scratchpad; the ones worth
recreating are the deconvolution fit, the isolated-window ICR/ISF fits, and the
per-sitting ratio table. The committed harness is
`backend/scripts/replay_glucose_prediction.py`.

Bundles used: 14-day (2026-07-19→08-01), 75-day replay export
(2026-05-19→08-01, SHA-256 `2ac2cc5b…`), and two 24-hour exports.
