# Medical Safety

Status: source of truth
Last updated: 2026-05-13
Owner/area: medical and feature-gating boundaries

Glucotracker is informational only. It is a diary and context tool, not a medical
decision system.

## Never Do

Never recommend:

- insulin dose;
- bolus;
- correction;
- target glucose as an instruction;
- treatment decision;
- what the user should eat to correct glucose.

Avoid wording that implies a prescription, judgment, or clinical conclusion.

## Allowed

The app may show observed facts:

- accepted carbs, kcal, macros, and meal timing;
- read-only CGM values from Nightscout/local cache;
- read-only insulin events imported from Nightscout;
- TIR and glucose summaries computed by backend;
- observed ratios in reports when labelled as observed/informational;
- sparse-data and data-quality warnings.

## Nightscout

Nightscout insulin is read-only context. Glucotracker may send accepted meals to
Nightscout as diary-only treatments, but it must not create editable insulin
treatments or dose recommendations.

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

Doctor reports are informational and must use observed wording. The report may
include CGM, TIR, insulin event history, and observed carb/insulin ratios, but it
must not say or imply "recommended ratio" or dosing advice.

## Copy Review Checklist

Before merging user-facing copy that mentions glucose or insulin, verify:

- no imperative treatment language;
- no dose/bolus/correction instruction;
- no praise/blame;
- no hidden advice inside notifications;
- no food flavor string references glucose, insulin, sensor, Nightscout, CGM, or
  TIR.
