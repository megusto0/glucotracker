# ADR-008 follow-up · Hypo-recovery filter, meal-during-low signal, and fat-delayed peaks

> Patch to ADR-008 after observing real-data results on the first 102 meals. ADR-008 is already implemented; this is an additive amendment, not a rewrite. Three focused fixes, each independent.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-10 |
| Affects | `application/postprandial/analyzer.py`, `application/postprandial/thresholds.py`, `meals` schema (one new JSONB field) |
| Risk | Low — additive flags, no breaking changes to existing fields |

---

## Context — what real data revealed

After ADR-008 backfilled the user's 102 meals, three issues surfaced:

1. **`is_hypo_recovery = true` for Monster Energy Ultra** (15 kcal, sugar-free). Classified as `drink_sweet` by taste-profile and matched all four criteria from §2.4. But Monster Ultra has 0g carbs — drinking it during a low does not raise glucose. Single hit, but it's a false positive that exposes a logic gap: the recovery filter trusts taste over carb content.

2. **Only 1 hit for `is_hypo_recovery`, but 29 of 102 meals (28%) started with `pre_meal_state = low`.** Of those 29, most are main meals (lavash with chicken, borsch, dinners) eaten during evening hypos. By the §2.4 spec they're correctly excluded from `is_hypo_recovery` (kcal ≥ 250). But this pattern — eating dinner while low — is itself a clinically meaningful signal that doesn't have a name in the schema. It's invisible to insights.

3. **Croissant с какао Δ 0.2, Cheetos Пицца Δ 0.5, Cola Original Δ 0.9.** Croissant and Cheetos are high-fat — fat delays gastric emptying, the real glucose peak happens at 4-6 hours post-meal, **outside the 180-minute analysis window**. The analyzer reads "tiny response" but the truth is "peak missed". Cola Original at Δ 0.9 across 4 samples is suspicious for a different reason (probably consumed during lows as recovery, but the recovery filter didn't catch it for reasons that should be debugged separately).

## Three fixes

### Fix 1 — `is_hypo_recovery` requires actionable carbs

Update the recovery filter in §2.4 to add a carb threshold:

```python
def is_hypo_recovery(meal: Meal, pre_state: PreMealState, taste: TasteProfile, role: MealRole) -> bool:
    return all([
        pre_state == PreMealState.LOW,
        meal.kcal < 250,
        meal.carb_g >= 10,                                   # ← NEW
        taste in (TasteProfile.SWEET, TasteProfile.DRINK_SWEET),
        role in (MealRole.SNACK, MealRole.DRINK),
    ])
```

Rationale: the "rule of 15" in T1D practice is 15g fast carbs to recover a low. A meal claiming to be recovery should have at least 10g (lenient threshold catches partial recoveries). Diet sodas, sugar-free energy drinks, and zero-cal sparkling waters all fail this and are correctly excluded from `is_hypo_recovery` regardless of their `taste_profile` classification.

This does not change `taste_profile` — Monster Ultra and Cola Zero remain `drink_sweet` (the user picked them for the sweet sensation, that's a real category). The fix is only in the recovery-detection logic.

### Fix 2 — `meal_during_low` as an independent signal

Add a new boolean to `postprandial_response`:

```json
{
  "...": "...",
  "is_hypo_recovery": false,
  "is_meal_during_low": true,    // ← NEW: pre_meal_state == low, regardless of size/role/taste
  "...": "..."
}
```

Trivial to compute (`pre_meal_state == LOW`), but having it as a named flag makes ADR-009 insight generation cleaner — a new insight kind can use it directly without re-querying CGM windows.

For the user's data, this surfaces a real pattern: ~28% of meals start with a low. Some are recoveries (small sweet snacks), most are scheduled meals consumed while hypo. Both deserve visibility; conflating them under one flag loses information.

Companion insight kind to add to ADR-009 (recorded here, implemented there):

```
kind: "meals_during_low_share"
template: |
  Около {pct}% твоих приёмов еды начинаются при сахаре ниже 4 ммоль/л
  — чаще всего в окне {window_label}.
sample: "Около 28% твоих приёмов еды начинаются при сахаре ниже 4 ммоль/л — чаще всего в окне вечером."
min samples: 14 days, ≥10 such meals
flavor: gluco only
```

This is an observation, not a recommendation. Phrasing carefully avoids prescribing: it doesn't say "you should eat before getting low" or "this is bad". It's pattern visibility.

### Fix 3 — Extended-window samples + `delayed_peak_likely` flag

The 180-min window from ADR-008 §2.2 misses peaks for high-fat meals. Two changes:

**3a. Two additional sample anchors at +240min and +300min.** Computed for every meal, same interpolation rules as the existing five. Storage cost is trivial (~50 bytes per meal).

```json
{
  "anchors": {
    "t0":   { "value": 5.7, "source": "actual" },
    "t30":  { "value": 7.2, "source": "actual" },
    "t60":  { "value": 8.4, "source": "actual" },
    "t90":  { "value": 7.8, "source": "actual" },
    "t180": { "value": 6.3, "source": "actual" },
    "t240": { "value": 8.1, "source": "actual" },   // ← NEW
    "t300": { "value": 9.4, "source": "actual" }    // ← NEW
  },
  "extended_coverage_300min": 0.91,                   // ← NEW
}
```

The deferred-trigger worker (§2.5) now runs at `eaten_at + 300min` instead of `+180min`. Acceptable latency increase — postprandial response visualizations aren't real-time anyway.

**3b. New flag `delayed_peak_likely: bool`.** Set when:

- `meal.fat_share > 0.35` (i.e., fat contributes >35% of kcal — high-fat foods), AND
- `peak_at_or_after_t180` is true (the highest reading in the 0-300min window lies at t180 or later), AND
- `extended_coverage_300min ≥ 0.7`

When this flag is true, the existing `glycemic_response` classification is **annotated**, not changed. The classification still uses the 0-180min window per §2.3 (don't break existing aggregations); the flag tells insight generators "this meal's response is probably understated".

Insight generators (ADR-009) that rank "lowest response products" must filter out meals with `delayed_peak_likely = true` from the per-product aggregation. Otherwise Cheetos Пицца and Круассан show up at the top of "predictable / safe" lists, which is misleading.

Concretely: `aggregate_by_product` from ADR-008 §3.5 gains a parameter `exclude_delayed_peaks=True` (default true). Set false only when explicitly asking "what's the apparent 180-min response" for a product.

## Schema and code changes

```sql
-- Existing JSONB column gets new keys; no migration required.
-- (Postgres JSONB is schemaless.)

-- For SQLite (mobile cache), if you store this column as TEXT and parse client-side,
-- no migration. If you have it as Room TypeConverter for a strict struct,
-- update the data class to include the new fields with nullable defaults.
```

`thresholds.py` constants:

```python
HYPO_RECOVERY_MIN_CARB_G = 10.0
DELAYED_PEAK_FAT_SHARE = 0.35
DELAYED_PEAK_MIN_EXTENDED_COVERAGE = 0.7
EXTENDED_WINDOW_MINUTES = 300
DEFERRED_WORKER_DELAY_MINUTES = 300  # was 180
```

`analyzer.py`:

```python
class PostprandialAnalyzer:
    def analyze(self, meal: Meal) -> Optional[PostprandialResponse]:
        # ... existing anchors at t0..t180 ...

        anchors_extended = self._sample_extended(meal)   # +240, +300
        extended_coverage = self._coverage(meal, minutes=300)

        delayed_peak_likely = (
            meal.fat_share > 0.35 and
            self._peak_at_or_after_t180(meal) and
            extended_coverage >= 0.7
        )

        is_meal_during_low = (pre_meal_state == PreMealState.LOW)

        is_hypo_recovery = all([
            pre_meal_state == PreMealState.LOW,
            meal.kcal < 250,
            meal.carb_g >= 10,                                 # ← NEW
            taste in (TasteProfile.SWEET, TasteProfile.DRINK_SWEET),
            role in (MealRole.SNACK, MealRole.DRINK),
        ])

        return PostprandialResponse(
            anchors=anchors,
            anchors_extended=anchors_extended,
            extended_coverage_300min=extended_coverage,
            delayed_peak_likely=delayed_peak_likely,
            is_meal_during_low=is_meal_during_low,
            is_hypo_recovery=is_hypo_recovery,
            ...
        )
```

`aggregate_by_product` from §3.5:

```python
def aggregate_by_product(user_id, product_name, days=30, exclude_delayed_peaks=True):
    meals = query_meals(user_id, name=product_name, last_days=days)
    responses = [
        m.postprandial_response for m in meals
        if m.postprandial_response
        and (not exclude_delayed_peaks or not m.postprandial_response.delayed_peak_likely)
    ]
    # ... rest unchanged
```

## Implementation tasks

One PR.

1. **Thresholds.** Add the four constants to `thresholds.py`.
2. **Analyzer.** Compute extended anchors, extended coverage, delayed_peak_likely, meal_during_low. Update `is_hypo_recovery` to include carb threshold.
3. **Worker delay.** Change deferred-trigger from `+180min` to `+300min`.
4. **Aggregation filter.** Update `aggregate_by_product` with `exclude_delayed_peaks` parameter.
5. **Backfill.** Recompute postprandial response for all meals from the last 30 days. Idempotent — just re-runs the analyzer.
6. **Tests:**
   - Unit: Monster Ultra synthetic case (kcal=15, carb=0, pre=low, taste=drink_sweet, role=drink) → `is_hypo_recovery=false`, `is_meal_during_low=true`.
   - Unit: small chocolate (kcal=80, carb=10, pre=low, taste=sweet, role=snack) → `is_hypo_recovery=true`.
   - Unit: dinner during low (kcal=500, carb=40, pre=low) → `is_hypo_recovery=false`, `is_meal_during_low=true`.
   - Unit: high-fat synthetic meal with rising t240/t300 → `delayed_peak_likely=true`.
   - Integration: backfill on the user's actual 102 meals. Verify:
     - Monster Ultra no longer flagged as recovery
     - `is_meal_during_low=true` for ~29 meals
     - Croissant 7 DAYS and Cheetos Пицца both gain `delayed_peak_likely=true` (assuming fat_share >35%)
     - At least one previously-flagged-recovery meal (if any other than Monster) survives the new filter

## Acceptance

- Monster Energy Ultra in the user's data: `is_hypo_recovery=false`, `is_meal_during_low=true`.
- Count of `is_meal_during_low=true` meals in the period: ≥25, ≤32 (i.e., consistent with the 29 low-pre-meal observation, allowing for ±3 boundary cases).
- Croissant 7 DAYS с кремом какао: `delayed_peak_likely=true` (if fat_share confirms >35%; verify by looking at the actual macro values in the user's product DB).
- Cheetos Пицца: `delayed_peak_likely=true` (same condition).
- `aggregate_by_product("Круассан 7 DAYS с кремом какао", exclude_delayed_peaks=True)` returns None or with `samples=0`. The "lowest response products" insight list no longer includes croissants or fat-heavy snacks.
- Existing `glycemic_response` classifications for all 102 meals are unchanged (the patch is additive — `delayed_peak_likely` flags the issue, doesn't reclassify).

## Section overrides

- Updates ADR-008 §2.2: anchor set grows from 5 to 7 points (t0, t30, t60, t90, t180, t240, t300).
- Updates ADR-008 §2.4: hypo_recovery gains `meal.carb_g >= 10` condition.
- Updates ADR-008 §2.5: deferred-trigger worker delay changes from 180min to 300min.
- Updates ADR-008 §3.1: `postprandial_response` JSONB gains `anchors_extended`, `extended_coverage_300min`, `delayed_peak_likely`, `is_meal_during_low` keys.
- Updates ADR-008 §3.5: `aggregate_by_product` gains `exclude_delayed_peaks` parameter.
- ADR-009 backlog: add `meals_during_low_share` insight kind per Fix 2.

## Out-of-band asks

1. **Cola Original mystery.** Δ 0.9 across 4 samples is suspicious. Before assuming a bug, check: of those 4 Cola entries, how many had `pre_meal_state=low`? If ≥3, the patch will reclassify them as `is_meal_during_low=true` and Cola's apparent low response is correctly explained as "consumed during lows, raised glucose modestly". If <3, there's a separate issue worth investigating (sample size? portion underreporting? brand_slug mismatch in taste_profile classifier?).
2. **Fat-share computation.** Requires that `meal.fat_g` is present and accurate. Some packaged products in the user's DB may have null fat values. Default if missing: treat `fat_share = unknown`, skip the `delayed_peak_likely` flag (false). Confirm.
3. **Window length 300min.** Generous. Acceptable trade-off: meals from late evening (`night_cap` window, after midnight in user's schedule) need CGM coverage running until 7-8 AM for full analysis. Sensor coverage of 98% should cover this, but be aware of edge cases.
