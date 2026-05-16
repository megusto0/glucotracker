# ADR-008 · Postprandial CGM analysis

> Second of three categorization-related ADRs. ADR-007 categorizes the meal itself (taste, role, window, provenance). ADR-008 categorizes what happens to the body afterward, by joining each meal with the CGM stream that follows it. Hand both ADRs to the agent together.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-10 |
| Affects | backend `meals.py`, `cgm.py`, `postprandial.py` (new), schema additions; medical (gluco) flavor only |
| Risk | Low — additive; computations are deterministic from CGM data |

---

## 1 · Context

The user has 14 days of dense CGM (3956 readings, ~98% coverage) and 13 days of meal data (102 entries) on the same wall-clock timeline. Joining them at the meal-level unlocks a class of insights pure-meal categorization cannot produce:

- per-product glucose response (which foods spike vs which don't, in this user's body)
- per-product predictability (low variance = easier to plan insulin around)
- pre-meal state effects (eating starting at 4.5 produces different curves than at 6.5)
- hypo-recovery detection (an entry that's actually treatment, not nutrition)
- late-meal glucose footprint (next-morning impact)

These are all observations, not recommendations. The medical-only constraint stands: nothing here suggests insulin doses or dietary changes. Tarelka (food flavor) does not see CGM data, so this entire ADR is gated to the gluco flavor server-side via role checks (per BE-4).

## 2 · Decisions

### 2.1 — Three CGM-derived axes per meal

| Axis | Type | Source |
|---|---|---|
| `pre_meal_state` | enum: `low | in_range | high | unknown` | CGM at `eaten_at` ± 5 min |
| `glycemic_response` | enum: `gentle | moderate | spike | unstable | unknown` | CGM curve over `eaten_at` + 0..180 min |
| `is_hypo_recovery` | bool | derived from `pre_meal_state` + meal characteristics |

These are **derived**, never user-edited, never sent to an LLM. Pure functions of CGM + meal data.

### 2.2 — Five sample anchors

For every meal, the analyzer stores glucose at five time points relative to `eaten_at`:

```
t = 0     (the eating moment, ±2.5 min)
t = +30   minutes
t = +60   minutes
t = +90   minutes
t = +180  minutes
```

If the exact 5-min CGM reading is missing, linear interpolation between the two surrounding readings is acceptable. If a sample anchor would land in a CGM gap >15 min, it's recorded as `null` and the relevant insights skip that meal.

The anchors are denormalized onto the meal record (JSONB column) for fast read; the raw CGM stream remains the source of truth.

### 2.3 — Glycemic response classification (deterministic thresholds)

Computed from the five anchors plus a peak-detection scan of the full 0..180 min window:

| Class | Definition |
|---|---|
| `gentle` | peak Δ from `t=0` < 2.0 mmol/L AND returns within 0.5 mmol of baseline by `t=+90` |
| `moderate` | peak Δ in [2.0, 4.0] mmol/L OR baseline-return between +90 and +180 min |
| `spike` | peak Δ ≥ 4.0 mmol/L OR sustained >10 mmol/L for ≥30 min |
| `unstable` | ≥2 distinct peaks during 0..180 min OR coefficient of variation in that window >25% |
| `unknown` | <60% CGM coverage in the window, or `pre_meal_state == unknown` |

Thresholds are documented constants, tunable. Initial values calibrated from typical T1D postprandial curves; adjust after observing real distributions in the user's data.

### 2.4 — Hypo recovery detection

A meal is flagged `is_hypo_recovery = true` when **all** of:

- `pre_meal_state == low` (glucose <4.0 mmol/L in the 30-min window before `eaten_at`)
- `meal.kcal < 250` (small portion)
- `meal.derived_categories.taste_profile in {sweet, drink_sweet}` (fast carbs)
- `meal.derived_categories.meal_role in {snack, drink}`

This filter catches entries like "Шоколад тёмный 24г" eaten right after a low — not a dessert, but a treatment. Insights then can subtract these from "sweet snacking" patterns and report them separately.

False positives are tolerable (a small sweet snack happening to coincide with a low gets flagged); false negatives matter less than honest counting. The user can mentally correct, and the flag is internal to insight generation, not displayed prominently.

### 2.5 — Late-binding trigger (analyzer runs at +180 min)

Postprandial samples don't exist at meal-creation time. The analyzer is a **deferred sweeper**, not a real-time hook:

- A worker runs every 5 minutes.
- Selects meals where `eaten_at < now() - 180 min` AND `postprandial_response IS NULL` AND `estimate_status = 'succeeded'`.
- For each, computes the five anchors + classification. Writes to `meals.postprandial_response`.

This avoids any race with the meal-completion or categorization pipelines. The meal already has its nutrition values long before the analyzer touches it. If the analyzer is offline for hours, it catches up on its next run; the data is fully derived from immutable CGM history.

Re-run on demand (e.g., after a CGM gap is filled by Nightscout): a separate command `recompute_postprandial(meal_id)` exists for one-off recomputation.

### 2.6 — CGM coverage and data quality flags

A `coverage_180min` percentage is stored alongside the postprandial response. If <60%, `glycemic_response = unknown` and insights skip the meal. If <80% but ≥60%, the meal is included but flagged in `quality_flags` so insight generators can downweight it.

## 3 · Specifications

### 3.1 — Schema additions

```sql
ALTER TABLE meals
  ADD COLUMN postprandial_response  JSONB    NULL,
  ADD COLUMN postprandial_computed_at TIMESTAMPTZ NULL;

CREATE INDEX idx_meals_glycemic_response
  ON meals ((postprandial_response->>'glycemic_response'));
CREATE INDEX idx_meals_hypo_recovery
  ON meals ((postprandial_response->>'is_hypo_recovery'));
```

`postprandial_response` example:

```json
{
  "anchors": {
    "t0":   { "value": 5.7, "source": "actual" },
    "t30":  { "value": 7.2, "source": "interpolated" },
    "t60":  { "value": 8.4, "source": "actual" },
    "t90":  { "value": 7.8, "source": "actual" },
    "t180": { "value": 6.3, "source": "actual" }
  },
  "peak":           { "value": 8.6, "minutes_from_t0": 65 },
  "delta_max":      2.9,
  "pre_meal_state": "in_range",
  "pre_meal_glucose_at_minus_15": 5.6,
  "glycemic_response": "moderate",
  "is_hypo_recovery": false,
  "coverage_180min": 0.97,
  "quality_flags":  [],
  "computed_at":    "2026-05-10T18:23:01Z"
}
```

### 3.2 — Backend module layout

```
backend/glucotracker/
├─ application/
│  └─ postprandial/
│     ├─ __init__.py
│     ├─ analyzer.py          # PostprandialAnalyzer
│     ├─ thresholds.py        # constants for §2.3 classification
│     └─ worker.py            # deferred sweeper (§2.5)
└─ domain/
   └─ postprandial.py         # PostprandialResponse model
```

`analyzer.py` exposes:

```python
class PostprandialAnalyzer:
    def analyze(self, meal: Meal) -> Optional[PostprandialResponse]:
        """Compute anchors and classification. Returns None if insufficient CGM."""

    def recompute(self, meal_id: UUID) -> None:
        """Force-recompute even if already analyzed."""
```

`worker.py` runs every 5 minutes, batches up to 100 meals per run, processes serially (no parallelism — CGM stream is per-user and not contended).

### 3.3 — Pre-meal state computation

```python
def compute_pre_meal_state(meal: Meal, cgm: CGMReadingsRepo) -> PreMealState:
    window_start = meal.eaten_at - timedelta(minutes=30)
    window_end = meal.eaten_at + timedelta(minutes=5)
    readings = cgm.between(meal.user_id, window_start, window_end)
    if len(readings) == 0:
        return PreMealState.UNKNOWN

    # The reading nearest to eaten_at; default to the median if cluster is noisy.
    nearest = min(readings, key=lambda r: abs(r.timestamp - meal.eaten_at))

    if nearest.value < 4.0:
        return PreMealState.LOW
    elif nearest.value > 10.0:
        return PreMealState.HIGH
    else:
        return PreMealState.IN_RANGE
```

### 3.4 — Glycemic response computation

```python
def classify_response(anchors, peak, coverage) -> GlycemicResponse:
    if coverage < 0.60 or anchors.t0 is None:
        return GlycemicResponse.UNKNOWN

    delta_max = peak.value - anchors.t0.value

    if delta_max < 2.0 and abs(anchors.t90.value - anchors.t0.value) < 0.5:
        return GlycemicResponse.GENTLE

    if delta_max >= 4.0 or sustained_above_10(window):
        return GlycemicResponse.SPIKE

    if peak_count(window, prominence=1.0) >= 2:
        return GlycemicResponse.UNSTABLE

    if cv(window) > 0.25:
        return GlycemicResponse.UNSTABLE

    return GlycemicResponse.MODERATE
```

`peak_count` finds local maxima with `prominence` ≥1.0 mmol/L (i.e., genuine peaks, not noise). `cv` is coefficient of variation over the 180-min window.

### 3.5 — Per-product aggregation (read-time, not stored)

Insight generators (ADR-009) frequently want "average response for product X across all meals where the user ate X". This is **computed at insight-generation time**, not stored:

```python
def aggregate_by_product(user_id, product_name, days=30):
    meals = query_meals(user_id, name=product_name, last_days=days)
    responses = [m.postprandial_response for m in meals if m.postprandial_response]
    if len(responses) < 3:
        return None  # need at least 3 samples for a stable mean

    return {
        "samples": len(responses),
        "mean_delta_max": mean(r.delta_max for r in responses),
        "stdev_delta_max": stdev(r.delta_max for r in responses),
        "predictable": stdev(r.delta_max for r in responses) < 1.0,
    }
```

Used by the `meal_predictability` insight in ADR-009.

## 4 · Implementation tasks

One PR.

1. **Schema migration** per §3.1.
2. **`PostprandialAnalyzer`** per §3.2-3.4. Pure-Python module, fully unit-testable with synthetic CGM streams.
3. **Threshold constants** in `postprandial/thresholds.py`. Documented with rationale.
4. **Worker** per §3.2 + §2.5. 5-min schedule via Celery beat.
5. **Recompute endpoint** `POST /v1/admin/postprandial/recompute?from=...&to=...` for backfill and manual reruns. Admin-only (gluco flavor only by role gate).
6. **Backfill** all meals from last 30 days as a one-off operation after deploy.
7. **Tests:**
   - Unit: each glycemic_response class triggers correctly on synthetic curves.
   - Unit: pre_meal_state classifies correctly across boundaries (3.99/4.0/4.01 mmol/L; 9.99/10.0/10.01 mmol/L).
   - Unit: hypo_recovery detection requires ALL conditions; missing any one returns false.
   - Unit: insufficient CGM coverage produces `glycemic_response = unknown`.
   - Integration: process a real meal from the user's DB; verify all anchors interpolated correctly when one CGM reading is missing in the window.

## 5 · Section overrides

- Compatible with ADR-007. The `derived_categories` JSONB and `postprandial_response` JSONB are independent columns; ADR-007 owns the former, ADR-008 owns the latter. Insight generators (ADR-009) read both.
- The medical-flavor exclusivity is enforced by ADR's `BE-4` role-gating: `food` flavor users get 403 on any endpoint that returns `postprandial_response`. Internally, the analyzer can run for any user; the gating is at the read endpoint.

## 6 · Acceptance

- **Real-data validation.** Run the analyzer over the user's 102 meals from 28 April–10 May. Sanity check:
  - Meals during the documented evening hypo cluster (19-22h) — most should have `pre_meal_state = low` or `in_range` with subsequent moderate response (insulin already aboard, slow rise).
  - "Кусочек торта" entries in the data should have `glycemic_response in {moderate, spike}`, not `gentle` (it's high-carb).
  - Late-night sweet entries following an evening hypo should have `is_hypo_recovery = true`.
- **Coverage handling.** A meal with a CGM gap covering the full 0..180 min window produces `glycemic_response = unknown`, `coverage_180min < 0.6`, and is excluded from all insight aggregations.
- **Threshold sensitivity.** Synthetic test: a meal with delta_max = 3.99 → `moderate`; delta_max = 4.0 → `spike`. No off-by-one errors at boundaries.
- **Per-product aggregation.** With 5 instances of "Лаваш с курицей и овощами" in the user's data, `aggregate_by_product` returns a populated mean and stdev. With 2 instances of "Cheetos Пицца", returns None (insufficient samples).
- **Re-run idempotency.** Calling `recompute(meal_id)` twice produces identical output (deterministic).

## 7 · Out-of-band asks

1. **Threshold values.** §2.3 sets `gentle < 2.0`, `spike ≥ 4.0`. These are reasonable starts but should be calibrated after observing the user's real distributions. After 30 days, run a percentile analysis: `gentle` should cover the bottom ~30% of responses, `spike` the top ~30%, `moderate` the middle ~40%. Adjust thresholds toward those quantiles. Default if delegated: ship with the constants; tune in v2.
2. **Hypo recovery `kcal < 250` threshold.** Some recovery snacks are larger (a glass of juice + cookie = 200; a piece of cake = 400+). Confirm 250 or relax to 350. Default: 250 — false-negative on large recovery is fine; false-positive on a 350-kcal regular dessert is worse.
3. **CGM gap interpolation policy.** §2.2 allows linear interpolation between adjacent readings. Some research uses cubic splines for smoother curves. Default: linear; the precision difference is below CGM sensor noise.
4. **Should `pre_meal_state` consider trend, not just value?** A glucose of 5.5 *falling fast* is functionally pre-low, even if not yet below 4.0. Confirm or extend. Default: value only for v1; trend in v2 if it adds insight value.
5. **Storage cost.** `postprandial_response` JSON ~ 400 bytes per meal. At 100 meals/day, that's ~150 MB/year per user. Acceptable for self-hosted SQLite/Postgres. Confirm or move to a separate compact table. Default: keep in JSONB on `meals` for query simplicity.
