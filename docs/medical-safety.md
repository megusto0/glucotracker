# Medical Safety

Status: source of truth
Last updated: 2026-07-25
Owner/area: feature-gating boundaries

## Allowed

The app may show observed facts:

- accepted carbs, kcal, macros, and meal timing;
- read-only CGM values from Nightscout/local cache;
- read-only insulin events imported from Nightscout;
- TIR and glucose summaries computed by backend;
- observed ratios in reports when labelled as observed/informational;
- digital twin parameters and reconstructed curves when clearly labelled as
  research output, not CGM truth;
- sparse-data and data-quality warnings.

## Nightscout

Nightscout insulin is read-only context. Glucotracker may send accepted meals to
Nightscout as diary-only treatments. Manual insulin treatments created by
Glucotracker can be edited or deleted; the backend applies the same operation to
the Nightscout treatment.

## Feature Gates

Food users must not receive glucose-related responses. Glucose/Nightscout/sensor
fingerstick/report endpoints return:

```json
{"code": "feature_disabled", "feature": "glucose"}
```

or the appropriate feature name, with HTTP `403`.

Role-specific response variants:

- `/dashboard/today` omits glucose keys for food users;
- `/timeline` returns a food-only response variant for food users.

## Reports

Doctor reports may include CGM, TIR, insulin event history, and observed
carb/insulin ratios.

## Digital Twin

Digital twin output is research/reconstructed context and is not live CGM.
