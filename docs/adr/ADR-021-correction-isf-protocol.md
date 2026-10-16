# ADR-021 — ISF only from level-start corrections, with a measured placebo

Status: accepted
Date: 2026-10-01
Supersedes: nothing. Amends the ISF rule of `therapy_analysis.py` (v8 → v9);
keeps the "measured to the trough" decision of 2026-08-04.

## Context

The owner asked for an analyzer that explains each meal's, dose's and
activity's effect on glucose, and why. A first prototype
(`ml-labs/response-attribution/`, live data 2026-04-26 … 2026-10-01) found that
the free-living diary does not identify the absolute effect of insulin:

- **Isolated evidence is rare.** 54 of 695 sittings with ≥20 g carbs have
  nothing else for two hours; 13 for five.
- **Doses answer the trace.** A distributed-lag fit gives each dose an "effect"
  in the hour _before_ it was given: glucose was already climbing (median
  +0.4 mmol/L in the preceding 30 min). Any regression over the diary — the twin
  fitter included — reads insulin as nearly inert (fitted ISF 0.1–0.27 against a
  configured 2.6; the twin fit of 2026-05-23 hit its 0.2 bound for this reason).
- **The trough rule finds a fall where there was no insulin.** On independent
  quiet windows (no food 4 h, no insulin 5 h) glucose ends where it starts, yet
  start-minus-minimum over 45 min – 4 h reads ~1.0–1.3 mmol/L.

Of 13 food-free corrections reaching the ISF gates, 10 began on a climb, 2 on a
fall, 1 level.

## Decision

`application/correction_protocol.py` holds the rules; `therapy_analysis.py`
applies them:

1. **Level start.** A correction is ISF evidence only if glucose changed by at
   most ±0.6 mmol/L over the hour before the dose and ±0.4 over the last 30 min.
   Otherwise it is rejected as `rising_before_dose`, `falling_before_dose` or
   `pre_dose_missing`. This is the placebo check: the pre-dose change is the
   effect the dose cannot have had.
2. **Placebo subtraction.** The trough is kept — the 2026-08-04 rebound case
   still holds — but the median start-minus-minimum of non-overlapping quiet
   windows in the same period is subtracted before dividing by the dose. With
   fewer than 8 windows nothing is subtracted, and the response says so.
3. The response carries `isf_placebo_fall_mmol_l`, `isf_placebo_window_count`
   and per-case `pre_dose_change_mmol_l`; the desktop card shows the correction
   and, when level-start rejections exist, what a usable correction looks like.

## Consequences

- ISF on this owner's history becomes "not identified" or "thin" more often,
  and ICR evidence falls back to the configured ISF more often. That is the
  honest state: the diary cannot answer it.
- ISF is measured going forward by corrections given from a level hour with no
  food 4 h either side. The app names this condition; it does not prompt doses
  or suggest amounts.
- The placebo assumes the quiet-window background holds at elevated glucose.
  The diary cannot check this — the owner treats highs, so untreated high
  stretches barely exist (2–5 per washout setting). A designed basal fasting
  test at an elevated start is the only way to measure it.
- Any future coefficient fit over the diary (twin, response attribution) must
  pass the same pre-event placebo check before its numbers are shown.
