# IOB & COB models — On-Board V2

**Status:** implemented and active behind validation-backed per-user fits

**Scope:** informational diary context for glucose / Nightscout views

**Not in scope:** insulin dose, bolus, correction, target, or treatment advice

**Primary code:**

- `backend/glucotracker/application/twin/kernels.py`
- `backend/glucotracker/application/on_board/fitter.py`
- `backend/glucotracker/application/on_board/service.py`
- `backend/glucotracker/infra/db/repositories/on_board.py`
- `backend/glucotracker/application/glucose_dashboard.py`

Per `CONCEPT.md` §1, these values are display-only. Nightscout insulin remains
read-only, raw CGM is never modified, and the model cannot recommend an action.

---

## 1. Runtime behavior

The dashboard performs no fitting. It loads the newest validated current-user
fit once, then sums the small number of active food/insulin events.

Fallback order:

1. validated personal model;
2. soft macro/identity prior for COB;
3. the previous piecewise population curve for IOB.

A sparse, rejected, malformed, or missing fit never replaces the fallback.
Rejected attempts remain in append-only audit history with `active = false`.

The response exposes provenance and confidence:

- `iob_model_source`: `population` | `personalized`
- `iob_model_confidence`: `none` | `low` | `medium` | `high`
- `cob_model_source`: `macro_prior` | `personalized`
- `cob_model_confidence`: `none` | `low` | `medium` | `high`

Food markers also expose the three explicit fast/normal/slow weights and their
personalization source. Insulin markers retain `insulin_type` even when that
event is not eligible for rapid IOB.

---

## 2. Smooth personal IOB

The fitted kernel is a two-component second-order Erlang survival mixture:

```text
Sraw(t) = w · exp(−t/τfast) · (1 + t/τfast)
        + (1−w) · exp(−t/τslow) · (1 + t/τslow)

S(t) = (Sraw(t) − Sraw(H)) / (1 − Sraw(H)),  for t < H
S(t) = 0,                                      for t ≥ H

IOB(t) = units · S(t)
```

Only four timing parameters are fitted:

- fast-component weight `w`;
- fast time constant `τfast`;
- slow time constant `τslow`;
- bounded completion horizon `H` (candidate range 330–420 minutes).

The Erlang mixture is truncated and renormalized at `H`, preventing unrelated
baseline drift from creating an implausibly long rapid-insulin tail. Its exact
analytic derivative supplies the activity rate. Peak-normalized activity keeps
the existing twin amplitude semantics separate from timing. The practical
remaining-time threshold is cached, so dashboard requests do not
finite-difference curves or repeatedly search them.

The previous data-calibrated piecewise curve remains bit-for-bit unchanged and
is used whenever no personal fit has passed validation.

Only compatible rapid-bolus events contribute. Explicit basal, temporary basal,
long-acting insulin, combo/dual-wave, square-wave, and extended deliveries stay
visible as markers but are not summed into rapid IOB. Legacy bolus rows whose
`insulin_type` is missing remain eligible for the generic rapid model; they do
not create a type-specific fit.

---

## 3. Soft meal COB

The former hard `fast | normal | slow` bucket is now a convex mixture of the
three stable basis curves:

```text
Fmeal(t) = wfast · Ffast(t)
         + wnormal · Fnormal(t)
         + wslow · Fslow(t)

COB(t) = carbs · (1 − Fmeal(t))
```

The fast and slow basis horizons remain fixed; the normal basis uses the
current owner-scoped twin setting so training and dashboard calculation use
the same timing (180 minutes by default):

| Basis  |            Reference horizon |
| ------ | ---------------------------: |
| fast   |                      120 min |
| normal | configured (180 min default) |
| slow   |                      420 min |

The population prior uses:

- carbohydrate, protein, fat, and fiber ratios;
- known liquid vs solid form;
- sweet-drink / sweet identity metadata;
- optional reviewed profile hints.

A low-fat solid is therefore not treated identically to a sugar drink merely
because both have sparse macros. Every prior retains support for uncertainty
instead of pretending a meal belongs to exactly one class.

Personal fallback hierarchy:

1. repeated exact meal fingerprint;
2. personal category (`fast|normal|slow` × `liquid|solid`);
3. macro/identity prior.

Fingerprints prefer stable product IDs, then normalized item identities, then
the meal title. The canonical identity is SHA-256 hashed before persistence, so
private product/meal names are not stored as model keys.

Fat and protein can delay the carbohydrate-appearance mixture, but they are
never converted into extra carbohydrate grams. COB continues to mean recorded
carbohydrates on board.

---

## 4. Retrospective fit

The fit uses the current user's raw visible CGM plus accepted meals and imported
rapid insulin. Sensor-excluded/corrupt CGM is already removed by the shared
visibility filter. All timestamps are converted UTC → configured local wall
clock before day grouping.

### Whole-day model

Truly isolated corrections are too sparse for an unconstrained personal curve.
V2 therefore fits timing over complete days. Raw CGM is median-downsampled to
15-minute bins, then first differences are modeled:

```text
ΔG = intercept
   + nonnegative meal amplitude · Δ absorbed carbs
   − nonnegative insulin amplitude · Δ insulin action
   + robust residual
```

The meal and insulin amplitudes are nuisance coefficients. They are not saved or
shown and cannot become dose advice. The shared timing kernel is selected with a
bounded deterministic grid and strong distance penalties toward the population
prior. A cheap deterministic screen spans at most 768 training observations;
only its best 16 kernels receive the full robust training evaluation. The full
later-day holdout and every activation guard remain unchanged. Regression uses
Huber iteratively reweighted least squares plus ridge regularization; no
NumPy/SciPy runtime dependency is required.

### Meal evidence quality

A meal can still contribute its population prior to whole-day confounder
control, but it receives exact/category personalization keys only when:

- cached postprandial analysis is newer than the meal edit;
- 0–180 min and 180–300 min coverage are each at least 80%;
- it is not marked low-coverage;
- it is not a hypo-recovery meal or a meal during low glucose.

Delayed-peak meals are retained when extended coverage is good; they are useful
evidence for the slow basis. Raw CGM, not the sparse episode snapshot anchors,
is the response series.

---

## 5. Leakage prevention and activation gates

Only full historical local days are eligible. The current incomplete day and at
least the latest 420 minutes are excluded. Training uses a rolling window of at
most 90 days.

Production gates:

- daily CGM coverage ≥ 85%;
- no CGM gap > 20 minutes;
- at least 7 training days and 3 later holdout days;
- at least 30 rapid events across 10 days for IOB fitting;
- at least 30 meals across 10 days for global COB fitting;
- category override: at least 8 events across 5 days;
- exact fingerprint override: at least 4 events across 3 days, with stronger
  shrinkage when evidence is small.

All intervals from one date stay entirely in training or holdout. Candidate
selection sees training dates only. The baseline is the exact model currently
served to that user: the legacy piecewise IOB curve with their configured DIA,
the configured normal-carb duration, and any active personal overrides. A
candidate activates only when later holdout dates improve over that production
baseline by both:

- at least `0.10 mmol/L` absolute MAE; and
- at least `5%` relative MAE.

P90 and per-day worsening guards can still reject a model that improves only the
average. These are engineering acceptance thresholds, not clinical targets.

---

## 6. Persistence and user isolation

Migration `0b1c2d3e4f5a` adds `on_board_model_fits` as forward-only,
non-destructive, append-only history. Each row stores:

- `owner_id`, model kind, privacy-safe scope key, version;
- JSON parameters and metrics;
- training bounds, sample/day counts;
- candidate and baseline validation MAE;
- confidence, acceptance status, active flag, fitted time.

`OnBoardRepository` requires `user_id` and applies it to every read, activation,
deactivation, and training-data query. Activating Alice's fit can deactivate only
Alice's rows. An accepted COB result replaces the complete active override set:
scopes absent from the new validated model are retired without deleting their
history. Rejected or insufficient attempts never change the active set.
Parametrized two-user tests cover repository, fitter-service, worker, and
dashboard isolation.

The fitter runs:

- after a successful existing `/twin/fit` workflow; and
- in a six-hour background loop, with at most one automatic attempt per user per
  24 hours.

The Windows launcher enables the single-process background tasks by default.
CPU-heavy fitting is dispatched to a worker thread, so the FastAPI event loop
continues serving requests while the bounded retrospective search runs.

---

## 7. Related data/import fixes

- Slow-meal dashboard lookback now uses the canonical 420-minute maximum rather
  than 360 minutes.
- Glucose and insulin imports keep separate owner-scoped watermarks, so a
  current glucose stream cannot suppress backfill of a lagging insulin stream
  (or vice versa).
- Background Nightscout import refreshes insulin together with CGM when enabled.
- Twin history queries convert local bounds to UTC before filtering timestamped
  Nightscout rows.
- `insulin_type` is preserved through dashboard and twin marker schemas.
- Resetting twin parameters deactivates, but never deletes, personal on-board
  fits.

---

## 8. Limits

- CGM, meals, and insulin do not uniquely identify gastric appearance, insulin
  sensitivity, exercise, stress, or baseline drift. V2 controls this with a
  small parameter count, nuisance amplitudes, shrinkage, and future-day holdout;
  it does not claim physiological identification.
- Type-specific insulin fitting is intentionally absent until enough correctly
  typed events exist. Long-acting and scheduled extended delivery need separate
  models.
- Exact meal personalization will often remain unavailable; category and macro
  priors are the intended sparse-data behavior.
- This model is informational diary context only. It must never be used to
  calculate or recommend insulin.

Background references for the chosen model family and identifiability limits:

- [Two-compartment IOB estimation](https://pmc.ncbi.nlm.nih.gov/articles/PMC4609789/)
- [Bayesian oral-glucose model from CGM/pump data](https://pmc.ncbi.nlm.nih.gov/articles/PMC10973685/)
- [Why meal appearance is confounded in CGM alone](https://pmc.ncbi.nlm.nih.gov/articles/PMC8875069/)
- [Probabilistic meal/action estimation with uncertainty](https://pmc.ncbi.nlm.nih.gov/articles/PMC2769912/)
- [Late effects of dietary fat and protein](https://pmc.ncbi.nlm.nih.gov/articles/PMC3836096/)
