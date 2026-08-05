# ADR-019 · What belongs together: sittings, episodes, and outcome windows

> Proposal, not yet accepted. Written after the History screen showed four insulin
> doses stacked under one meal while three other sittings looked uncovered — a
> display symptom of a grouping model that is defined in eight places.

| | |
|---|---|
| Status | **Accepted** — §2.1, 2.2, 2.4, 2.7 implemented; 2.3, 2.5, 2.6 partial (see §6) |
| Date | 2026-08-06 |
| Affects | backend `episodes.py`, `insulin_recommendation.py`, `therapy_analysis.py`, `icr_autotune.py`, `therapy_review.py`, `postprandial/`; desktop Nightscout page; mobile Today/History |
| Risk | Medium — changes numbers that existing stored results were computed with |

---

## 1 · Context

"Which meals and doses belong together" is currently decided independently in at
least eight places, with three different clustering windows and five different
outcome horizons. None of them reference each other.

### 1.1 — Clustering: three answers

| Where | Rule | Window |
|---|---|---|
| `episodes.py:36` | meals chain to the **previous** meal, transitively | 45 min |
| `episodes.py:37` | insulin joins an episode | ±90 min |
| `EatingOccasion.kt:16` | mobile narrows a backend episode into a sitting | 30 min |
| `EpisodeCoverage.kt:11` | a bolus counts as "on time" for a plate | 10 min |

Transitive chaining is the sharpest problem. On 5 August:

```
18:10 → 18:41  (31 min)  chained
18:41 → 19:25  (44 min)  chained — just under the window
19:25 → 20:31  (66 min)  new episode
```

Three separate eating events, 75 minutes end to end, become one episode because
each individual hop is under 45 minutes. Nothing in the rule bounds the total
span. A day of steady grazing collapses into a single episode.

The mobile client already works around this with its own 30-minute re-clustering,
which means the phone and the backend disagree about what a sitting is — and the
desktop, which uses raw `start_at`/`end_at` containment, is a third opinion.

### 1.2 — Outcome horizon: five answers

The question "how did this land?" is asked with a different horizon each time.

| Consumer | Horizon | Measured to |
|---|---|---|
| `episode_therapy.OUTCOME_HORIZON` | 2 h | value at horizon |
| `insulin_recommendation.OUTCOME_HORIZON` | 2 h | value at horizon |
| `icr_autotune.OUTCOME_AT` | 3 h | value at horizon ±20 min |
| `therapy_analysis` ICR / ISF | 2 h / 4 h | value at horizon (ISF now: trough) |
| `therapy_review` | 1–4 h, user-selected | value at horizon + peak/nadir |
| `postprandial/analyzer` | 3 h + extended | peak, delta, curve |
| `endocrinologist_report` | 3 h | window aggregate |

These are not deliberate differences per question — they are independent guesses.
Two of them (`icr_autotune` at 3 h, `therapy_analysis` ICR at 2 h) estimate *the
same quantity* from *the same episodes* and will disagree for that reason alone.

### 1.3 — Why it matters beyond display

Everything downstream inherits whichever grouping it happened to call:

- **ICR autotune** weights by carbohydrate per episode. If an episode is three
  sittings chained together, one "episode" carries 128 g and three doses, and the
  implied ratio it votes with is not a ratio anyone ate.
- **Prediction features** read carbs-on-board from meal events; grouping decides
  what counts as one carbohydrate impulse versus three.
- **Therapy classification** labels a whole component. A chained component
  containing a rescue and two ordinary plates classifies as `mixed`, which is the
  bucket that gets dropped from analysis.
- **Isolation checks** (`_has_neighbor`, ±2 h / ±4 h) are computed per consumer
  over its own candidate list, so "isolated" means something slightly different in
  each module.

---

## 2 · Proposed decisions

### 2.1 — Name three concepts and stop conflating them

| Concept | Question it answers | Consumers |
|---|---|---|
| **Sitting** | What did the person eat in one go? | display, per-meal attribution |
| **Episode** | One sitting plus the insulin covering it and the glucose it caused | analysis, autotune, training labels |
| **Observation window** | Over what span is an episode's result judged? | every outcome number |

A sitting is a fact about behaviour. An episode is a unit of therapy. They are
not the same object and should not share a constructor.

### 2.2 — Anchored clustering, never transitive

A sitting is the set of meals whose `eaten_at` falls within `SITTING_SPAN` of the
**first** meal of that sitting. When a meal falls outside, it opens a new sitting.

```
sitting_start = first.eaten_at
member if:  meal.eaten_at - sitting_start <= SITTING_SPAN
```

Proposed `SITTING_SPAN = 30 min`, matching what the mobile client already
concluded independently. The 5 August day then reads 18:10+18:41 (one sitting,
31 min — see open question 5.1), 19:25×3, 20:31×2.

This bounds an episode's total span by construction, which the current rule does
not.

### 2.3 — One implementation, consumed everywhere

`episodes.py` becomes the only module that groups. `insulin_recommendation`,
`therapy_analysis`, `icr_autotune`, `therapy_review` and `postprandial` consume
its output rather than re-deriving neighbours and isolation. Clients render what
the backend grouped and never re-cluster; `EatingOccasion.kt` is deleted.

### 2.4 — Observation windows from one table, keyed by purpose

```python
class Horizon(Enum):
    IMMEDIATE_RESPONSE = timedelta(hours=2)   # did the dose cover the food
    FULL_ABSORPTION    = timedelta(hours=3)   # ICR evidence, mixed meals
    INSULIN_EXHAUSTED  = timedelta(hours=4.5) # ISF evidence, per the DIA finding
```

Every consumer names the horizon it wants. Where they disagree today, the
disagreement becomes a visible choice rather than a scattered constant.

`4.5 h` rather than the current 4 h reflects the handover's measured finding that
insulin action ends around 4.5 h, not the kernel's 6.5.

### 2.5 — An outcome is a path, never a single reading

Reading the value *at* the horizon has produced two real defects already: a meal
that peaked at 13.1 and landed at 5.3 was reported as optimal, and every ISF
estimate was biased low because the 4-hour reading had already rebounded off the
trough. Every outcome carries `peak`, `nadir`, their times, and time out of band.
Consumers pick the statistic their question needs; none of them re-read the raw
series.

### 2.6 — Episodes get stable identity

The current episode key is a sorted concatenation of meal and insulin ids, so it
changes whenever a meal is edited or a late bolus is imported. Longitudinal
analysis cannot follow an episode across a correction.

`meal_insulin_episode_snapshots` already exists. Proposal: episodes are persisted
with a UUID, and analysis references that id. A re-grouped episode keeps its id
when its anchor meal is unchanged.

### 2.7 — Grouping is versioned like a model

Anything that stores a derived number records the grouping version alongside the
model version, the way `therapy_review_caches` records `model_version` today.
Changing `SITTING_SPAN` invalidates stored results instead of silently mixing two
definitions in one chart.

---

## 3 · What this unlocks

- **Autotune** votes with one ratio per sitting instead of one per chained
  component, and can finally exclude an episode for a stated reason (near
  exercise, interrupted, no outcome) recorded once rather than per module.
- **Prediction** gets carbohydrate impulses that match what was actually eaten in
  one go, which is what the absorption model assumes.
- **Classification** runs on sittings, so a rescue stops being averaged into a
  `mixed` component with two ordinary plates.
- **Comparisons over time** become meaningful, because an episode has an id and
  the grouping that produced it is recorded.

---

## 4 · Migration

1. Add `SITTING_SPAN` clustering beside the existing rule, behind a flag; expose
   both groupings on `/glucose/episodes` for one release.
2. Replay the 75-day export under both and diff: episode count, carbs per episode,
   implied ICR per daypart. **Do not adopt on reasoning alone** — the handover
   records several confident conclusions that did not survive measurement.
3. Adopt if the diff is explainable; bump the grouping version; recompute caches.
4. Delete `EatingOccasion.kt` and the desktop containment check in the same
   release, so no client outlives the change with its own idea of a sitting.

---

## 5 · Open questions

1. **Is 30 minutes right, and is it one number?** 18:10 + 18:41 is 31 minutes —
   just outside. A pastry half an hour after пирожки is plausibly the same
   sitting, plausibly not. This wants measurement against the export, not taste.
2. **Should a sitting ever split on composition?** A rescue eaten mid-meal is a
   different act from the meal around it, and merging them hides both.
   *Partly answered by `c4cdb9c`*: a bolus chasing a rise the meal caused is now
   classified `catch_up` rather than folded into meal coverage. What ICR does
   with it remains open — see the handover's note against `97e2402`.
3. **What happens to already-stored results** computed under the old grouping —
   recompute, or keep and mark? Recomputation changes historical charts the owner
   has already looked at.
4. **Does the insulin window stay ±90 min** once sittings are bounded, or should
   coverage be anchored to the sitting's span rather than to each meal?

---

## 6 · What shipped, and what did not

Adopted on the proposed numbers at the owner's direction, without the §4 replay
first. **The replay diff is still owed** — until it runs, §5.1 is unanswered and
the 30-minute span is a reasoned guess, not a measured one.

Implemented:

- §2.2 anchored clustering, in `episodes.py`. `SITTING_SPAN = 30 min`.
  **First attempt was ineffective**: it clustered only meals with no insulin
  link, so on any real day — where every plate has a bolus — it never ran. An
  automatic link joins a bolus to every meal from 30 min before to 90 min after
  it, and the component walk then chained meal → insulin → meal without bound,
  which kept 18:10 → 20:31 as one episode. Sittings are now formed over every
  meal, a reviewed link is still drawn as given, and an automatic link joins
  only the nearest meal — reaching that meal's whole sitting and no further.
  This is §5.4 answered: coverage anchors to the sitting, not to each meal.
- §2.4 `Horizon` in the new `grouping.py`; `therapy_analysis` and `icr_autotune`
  now name the horizon they want. **This moved the ISF horizon from 4 h to
  4.5 h**, so ISF estimates change again on top of the trough fix in `51726a5`.
- §2.7 `GROUPING_VERSION`, folded into the therapy review and analysis model
  versions so stored results recompute rather than mixing two definitions.

Not done, deliberately:

- §2.3 clients still re-cluster. `EatingOccasion.kt` narrows an episode to a
  sitting because insulin-linked episodes can still span wider than one through
  the ±90 min coverage window; deleting it would undo `9b41bef`. Its constant is
  now pinned to `SITTING_SPAN` with a comment, so the two cannot drift. The real
  fix is the backend carrying sittings on the episodes response.
- §2.5 outcomes carry peak and nadir in `therapy_review` and in the ISF
  estimator, but `episode_therapy` and `postprandial` still read a single value.
- §2.6 episodes still have no stable id; `meal_insulin_episode_snapshots` exists
  and is the obvious place, but nothing was changed to use it.
