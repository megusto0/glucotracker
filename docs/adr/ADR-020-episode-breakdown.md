# ADR-020 — Episode breakdown, and what counts as a carbohydrate correction

Status: accepted
Date: 2026-08-07
Supersedes: nothing. Extends [ADR-019](ADR-019-episode-grouping.md).

## Context

ADR-019 settled what belongs together. `episode_therapy.py` then labelled each
group — meal, snack, carbohydrate correction, insulin correction, mixed — and the
diary coloured rows by that label. Two problems had accumulated.

**The label was wrong often enough to be noticed.** The owner reported ordinary
food showing as an orange carbohydrate correction "even when it isn't". The rule
was:

```
carb_correction ⟸ meals ∧ ¬insulin ∧ (low_at_start ∨ (settled ∧ falling ∧ carbs ≤ 30))
```

`falling` meant a calibrated slope at or below −1 mg/dL per minute. Nothing in
the rule asked where the fall was going. A descent from a meal peak — 8.7 → 7.7 →
6.7 over twenty minutes — satisfies it exactly, so a small plate eaten during the
ordinary come-down after lunch was filed as hypoglycaemia treatment. The repo's
own test suite pinned this behaviour with an omelette.

The deeper mistake is a category error. The rule extrapolates a slope to guess
whether a low is coming. That is the question a live app must answer, and it has
to guess. This code runs over history, where the answer is in the data.

**A second, independent definition existed and read raw glucose.**
`postprandial/analyzer.py` computes `is_hypo_recovery` per meal from
`compute_pre_meal_state`, which compared the stored sensor value against 4.0.
This owner's raw stream runs 1.0–2.8 mmol/L below true glucose, so a drink at a
calibrated 5.5 arrived as a raw 3.2 and was recorded as hypo treatment. That flag
feeds a user-facing insight and `on_board/service.py`, which *excludes* such
meals from the IOB/COB fits — so the mislabel was quietly deleting real training
data.

Separately, the mockup (screen H, "Разбор эпизода") asked for a detail sheet: a
window of CGM either side of an episode, the readings that carry its story, what
else happened nearby, and a probable cause. It was drawn for a carbohydrate
correction. The owner asked for a system covering every class.

## Decision

### 1. Classification is retrospective and reads the trough

A carbohydrate correction requires three conditions, all of which must hold:

1. **a low happened.** The lowest calibrated reading in `[start − 20 min,
   start + 25 min]` is at or below `NEAR_LOW_MMOL_L = 4.5`. The window opens
   before the plate because the decision was made on what glucose was doing
   then, and closes after it because fast carbohydrate takes about a quarter of
   an hour to bite while glucose keeps falling.
2. **the portion was a treatment,** not a meal: `0 < carbs ≤ 30 g`.
3. **nothing was dosed with it,** once a late bolus can no longer be attributed
   to the sitting — the existing settling rule, unchanged.

4.5 rather than 3.9 because treating starts before the threshold is crossed and
a rescue that worked never reaches 3.9 at all. Above 4.5 nothing was rescued,
however fast glucose was moving.

Everything else — a steep fall, fast carbohydrate, a lean portion, a reversal of
at least 1.5 mmol/L within the hour — only moves confidence. `falling` is no
longer able to create the label on its own, which is the whole change.

If no calibrated reading covers the plate, the label is **not** a correction.
Whether a low happened is unknown, and unknown must not render as an orange row.

### 2. Evidence replaces the condition chain

Each class emits named `TherapyEvidence(code, text, weight)`. The score is their
sum; confidence is a threshold on it rather than an ad-hoc branch. `reasons`
survives as the plain sentences, so existing clients are unaffected; anything
that needs to branch on *why* reads the codes. The evidence list is also what
the breakdown sheet renders under "вероятная причина".

### 3. One glucose space

`postprandial/analyzer.py` now reads `GlucoseNormalizationService`. Every
absolute threshold in that module — the 4.0 low, the 10.0 high, the sustained
spike level — was being evaluated on the raw scale. The readings it passes
around are `CalibratedReading`, and the docstring says so.

### 4. The breakdown is six blocks, the same for every class

`episode_breakdown.py` returns, for any episode:

| block | what varies by class |
| --- | --- |
| window | nothing — always −2 h / +4 h of calibrated points |
| anchors | *which* readings: a rescue leads with its trough, a correction with the reading it was given at, food with the value before it |
| derived | rise per gram for food, fall per unit for insulin |
| crossings | nothing — other episodes, sleep, activity, with signed offsets |
| cause | the class's own explanation |
| frequency | what is counted: lows, corrections, or repeats of this dish |

Points are sent one by one rather than as a path. The day chart wants shape and
draws a line; here the useful information is measurement density and where the
trace breaks, so gaps stay visible instead of being bridged.

**Anchor searches stop at the next episode.** In the night this was written
against, a 53 g biscuit seventy-five minutes after a 12 g rescue drove glucose to
8.3 — higher than the rescue ever did. An uncapped 150-minute peak search would
have called that the rescue's peak and derived a carbohydrate sensitivity almost
half again too steep from twelve grams of juice.

The endpoint takes the same `from`/`to` the list was drawn with, not a range
derived server-side, because grouping a different span can split a sitting
differently and resolve a client's key to a different episode or to none.

## Consequences

### Tests that changed expectation

Two tests asserted the old behaviour and now assert the opposite. Both are
rewritten with the reasoning in the docstring, not silently flipped:

- `test_small_main_meal_during_fast_fall_is_carb_correction` → an omelette
  during a fall that lands at 6.7 is a **meal**. It is paired with a new test
  carrying the identical food and slope three mmol/L lower, which is a rescue —
  the pair is the argument.
- `test_sitting_in_progress_is_not_called_a_rescue` kept its name and its point
  but needed a genuinely low trace, because at 7.2 the settling rule is no
  longer what decides.

### Known limits

- `NEAR_LOW_MMOL_L = 4.5` and the evidence weights are reasoned, not fitted. The
  replay diff over the 75-day export (ADR-019 §4) is the instrument that would
  settle them and has not been run.
- Frequency counts a cheap proxy per class rather than re-grouping 30 days:
  lows from the normalized series for a correction, correction events for
  insulin, repeats of the same dish for food. The labels say what was counted.
- Lows are counted rather than rescues, deliberately: a low slept through and
  never treated is the same problem, and leaving it out would understate exactly
  the thing worth knowing.
- The breakdown runs grouping, normalization over 30 days, and body-state
  inference per open. It is a detail sheet opened one at a time, not a list
  cell, but it has not been measured on the real database.
