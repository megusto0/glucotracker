# ADR-012 · Tarelka polish, onboarding, and insight flavor isolation

> Focused fixes for Tarelka issues visible in the first real builds: a CGM-only insight leaked into the food flavor, the "Goal" surface is empty by default, several visual elements crop or duplicate, and insights are rendered without the structure ADR-009 specified. Hand alongside ADR-009 for context.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-11 |
| Affects | Tarelka mobile: Today / Stats / Login / "Ещё"; backend `/v1/stats/insights` flavor gate; small schema addition for goal settings |
| Risk | Low — polish + one missing onboarding flow + one bug fix |

---

## Context — what the first Tarelka builds revealed

Field-tested screenshots from 2026-05-11 against the gluco_admin's Tarelka instance (same user, different flavor of the app — gluco has glucose, Tarelka has food only). Findings:

**(a) CGM-only insight leaked into Tarelka.** The Stats card displays «60% низких значений пришлись на 19:00–07:00». This is the `evening_lows` insight kind from ADR-009 §2.1, which is marked **gluco only**. It must never appear in the food flavor. Backend filtering by user flavor (or user's `is_diabetic` flag) is missing or wrong somewhere in the insights generation path.

**(b) Goal surface is empty by default.** Today's headline area shows a large empty circle with «—» and the label «цель не задана». 84.4g protein / 104.6g fat / 208.1g carbs appear below as bare numbers with no comparison context. Without a goal, all calorie totals are uncontextualized — the most-prominent UI element of the app is a dash.

**(c) Duplicate «Статистика →» on Today.** Two right-aligned links on consecutive rows: one in the page-indicator row (`● ВОСКРЕСЕНЬЕ ……… Статистика →`), one in the day-kicker row (`10 мая ……… Статистика →`). The exact same bug glucotracker had before ADR-002. Tarelka shares the Today composable in `src/main/`, so the fix should have propagated — apparently didn't, or regressed.

**(d) Date and logo crops.** «10 мая» shows without year and reads as cropped vertically. Per ADR-002 §3.2, the date format was specified as `28sp serif "10 мая 2026"`; either the year was dropped or the row height is too small. Separately, the login-screen logo crops on the bottom (user-reported; not visible in screenshots).

**(e) Insight text truncates mid-sentence.** «Около 59% твоих приёмов еды — после 11:00. 3...» and «Чаще всего: Протеиновое брауни Shagi. (7×), С...» both terminate in ellipsis. The card's max-lines is too tight, or the templates from ADR-009 §2.2 are longer than the layout accommodates.

**(f) БЖУ percentages identical across timeframes.** `Белки 17% · Жиры 45% · Углеводы 39%` appears the same for Неделя / 14 дней / Месяц tabs. Statistically improbable; likely a state-caching bug where the BJU breakdown computes once and doesn't re-compute on tab switch.

**(g) Monthly average ккал/день calculation wrong.** Month tab shows «В среднем 1 093 ккал в день»; 14-day shows «В среднем 2 342 ккал в день». The user does not eat half on the "old days" — the user simply has only 14 days of data total. The monthly average divides by 30 days (period length) instead of by N days with actual data. Misleading.

**(h) Insights packed into one card without divider.** Image 4 shows three observations crammed into one «наблюдение» block: a primary line, then a multi-line body with two more insights. ADR-009 §2.5 specified ONE primary line in serif emphasis, hairline divider, and up to two secondary one-liners. The implementation joined them into a single prose block.

**(i) Empty placeholder section.** «КОГДА ЕШЬ · МЕДИАНА ПО ЧАСАМ» renders empty pink rectangles. Either the data exists and isn't being read, or the section is half-implemented. Shipping it visible-but-empty is worse than hiding it.

## Decisions

### 2.1 — Flavor gate for insights (the leak fix)

Backend `GET /v1/stats/insights` must filter the kinds available by the **caller's flavor**, not just by user role or schema. Tarelka users get only the 6 food-only kinds from ADR-009 §2.1; gluco users get all 10.

Implementation: the request must carry the flavor (via either an explicit `?flavor=food|gluco` query parameter set by the client, OR — preferred — derived server-side from the user's account type, since BE-1..3 already track this). For each kind in the registry, check `kind.flavor in ("both", request.flavor)` before invoking `qualify()`. Kinds marked `gluco only` never run for food-flavor calls.

Add a guard in the kind registry itself:

```python
INSIGHT_KINDS: dict[str, InsightKind] = {
    "consistent":              InsightKind(flavor="both", ...),
    "weekday_pattern_sweet":   InsightKind(flavor="both", ...),
    "time_of_day_eating":      InsightKind(flavor="both", ...),
    "top_repeat_products":     InsightKind(flavor="both", ...),
    "late_meal_share":         InsightKind(flavor="both", ...),
    "today_morning":           InsightKind(flavor="both", ...),
    "meal_predictability":     InsightKind(flavor="gluco", ...),
    "evening_lows":            InsightKind(flavor="gluco", ...),    # ← was leaking
    "hypo_recovery_pattern":   InsightKind(flavor="gluco", ...),
    "late_meal_glucose_footprint": InsightKind(flavor="gluco", ...),
}

def get_qualifying_kinds(flavor: Flavor) -> list[InsightKind]:
    return [k for k in INSIGHT_KINDS.values() if k.flavor in ("both", flavor)]
```

Filter happens BEFORE qualification, not in rendering. No CGM-data queries run for Tarelka requests at all — both correctness and modest performance benefit.

### 2.2 — First-launch goals onboarding (so the circle is never empty)

When a Tarelka user first opens the app post-login and `user.kcal_goal_per_day IS NULL`, present a brief onboarding sheet **once**:

```
─────────────────────────────────────────────
Поставь цель на день — необязательно, но без неё
страница «Сегодня» будет пустоватой.

ККАЛ В ДЕНЬ                       2000
                                  ▽

БЕЛКИ, г                          100
                                  ▽

УГЛЕВОДЫ, г                       250
                                  ▽

ЖИРЫ, г                           70
                                  ▽

           [Готово]    [Пропустить]
─────────────────────────────────────────────
```

Tone: invitational, not blocking. «Пропустить» is a real escape — does NOT show the sheet again that session. But the empty-circle state on Today is replaced by a softer CTA:

```
Цели не заданы.
Их можно поставить в «Ещё → Цели»

[поставить] →
```

The «поставить» link reaches the same sheet from above. Once goals are set, the circle becomes its proper ring with current/target. After «Пропустить» chosen once, the sheet doesn't pop up again on subsequent launches — but the soft CTA on Today persists.

Schema (Tarelka-only — gluco might have a different goal model):

```sql
ALTER TABLE users
  ADD COLUMN kcal_goal_per_day      INT NULL,
  ADD COLUMN protein_goal_g_per_day INT NULL,
  ADD COLUMN carb_goal_g_per_day    INT NULL,
  ADD COLUMN fat_goal_g_per_day     INT NULL,
  ADD COLUMN goals_setup_completed  BOOLEAN NOT NULL DEFAULT FALSE;
```

`goals_setup_completed = TRUE` after either «Готово» or «Пропустить» — suppresses the one-time onboarding sheet. Goals themselves remain NULL until explicitly set; the soft CTA persists for as long as they are.

### 2.3 — Single «Статистика →» link on Today

Replays the ADR-002 §2.1 fix in Tarelka. The Today header must have exactly one right-aligned «Статистика →» link. ADR-002's `TodayHeader` composable lives in `src/main/`; both flavors should be using it. If Tarelka is using a separate header (e.g., from `tarelka-brand-evolution-prompts.md` §TR-2), update TR-2's `TarelkaTodayHeader` to follow the same one-link rule.

The pager-indicator row keeps the dots (`● ○`) and the kicker text (`ВОСКРЕСЕНЬЕ`) but does NOT carry the action link. The action link belongs only on the date row.

Same Compose UI test as ADR-002 §6: `onAllNodesWithText("Статистика").assertCountEquals(1)` on Today.

### 2.4 — Date format on Today: include year, fit row

Today's date display must render the full ISO-style serif: `10 мая 2026`. Per ADR-002 §3.2, this is `28sp serif` in `--ink`. The header row 2 height was specced at 44dp; if Tarelka's font metrics or padding produce visible crop, increase row 2 to 48dp and verify in Paparazzi snapshots for both the longest month name («сентября» / «декабря») and a short one («мая»).

The year is part of the date. Never drop it for length reasons — if 12 May 2026 («12 мая 2026») fits, so must «10 мая 2026». If a width issue exists, scale font down to 26sp before truncating; never drop year.

### 2.5 — Login logo: full visual bleed, padded

The login-screen logo (Tarelka serif T with the tangerine dot) reportedly crops on the bottom. Wrap the logo composable in a container with:
- min height: `lockup_height + 24dp top + 24dp bottom`
- center vertically
- no nested cropping (no `Modifier.height` smaller than the lockup itself)

If the screen has insets (status bar, keyboard, gesture bar), use `WindowInsets.systemBars.asPaddingValues()` on the outer scaffold so the logo is never pushed below the visible area.

Paparazzi snapshot: login screen on a small (5.5") and standard (6.7") device, both with and without keyboard up, all show the complete logo.

### 2.6 — Insight card structure per ADR-009 §2.5

Refresh the Tarelka Stats insight card to match ADR-009 §2.5 mobile spec exactly:

```
┌─────────────────────────────────────────────┐
│ НАБЛЮДЕНИЕ                                  │  tangerine 9.5sp letter-spaced
│                                             │
│ Около 59% твоих приёмов еды — после 11:00.  │  serif/sans 14sp, max 3 lines
│ 15 раз в неделю в среднем.                  │
│                                             │
│ ─ ─ ─                                       │  optional hairline divider
│                                             │
│ Чаще всего ешь в 06:00 и 23:00.             │  12sp ink-2, one line
│ Чаще всего: Протеиновое брауни Shagi (7×).  │  12sp ink-2, one line
└─────────────────────────────────────────────┘
```

Hard rules:
- ONE primary observation, max 3 lines, serif-emphasis font.
- Hairline divider (1px ink-3) between primary and secondaries.
- ONE OR TWO secondary observations, each one line, sans 12sp `--ink-2`.
- If the primary alone fills 3 lines, omit secondaries entirely.

Templates from ADR-009 §2.2 should already fit within these limits when rendered. If a specific template overflows (e.g., `top_repeat_products` with three products), drop products until the line fits — show 2 products instead of 3, or 1 instead of 2. Never truncate with ellipsis. Ellipsis is a failure state, not a design choice.

Implementation: the `InsightCard` composable takes a structured `List<RenderedInsight>` where each entry has explicit `primary | secondary` role. The endpoint per ADR-009 §2.4 already returns `weight: primary | secondary` — the card consumes that directly. Stop concatenating multiple insights into one Text() block.

### 2.7 — Truncation fix at the template layer

Per ADR-009 §2.2, each insight template renders to a specific Russian string. Some templates produce text longer than 3 short lines. Two fixes:

**(a) Tighten templates.** Re-examine each template for verbosity:

- `weekday_pattern_sweet`: «По вечерам в среду и пятницу сладкого больше всего — около 380 ккал из десертов и напитков.» → consider «По вечерам в среду и пятницу сладкого больше — около 380 ккал.»
- `time_of_day_eating`: «Чаще всего ешь в 13:00 и 19:00.» — already tight, OK.
- `top_repeat_products`: «Чаще всего: Протеиновое брауни (7×), Сырок глазированный (6×), Лаваш с курицей (5×).» — long product names + 3 entries blow the budget. Render at most 2 entries if total > ~70 chars; pick top 2 by frequency.

**(b) Adaptive truncation in code.** A helper:

```kotlin
fun truncateToLines(text: String, maxLines: Int, charsPerLine: Int): String {
    val maxChars = maxLines * charsPerLine
    if (text.length <= maxChars) return text
    // Truncate at the last sentence boundary that fits, NOT mid-word with ellipsis
    return text.substring(0, maxChars).substringBeforeLast(". ") + "."
}
```

Cut at sentence boundary, not at character. Never end with «…». If a template produces a single sentence longer than max, render the whole sentence and let the layout wrap it; if THAT overflows, reduce max-lines to fit by dropping secondaries (per §2.6).

### 2.8 — БЖУ recomputes per timeframe

State bug: the БЖУ percentages bar caches its computation and serves the same value across Неделя / 14 дней / Месяц tabs.

Fix: the Stats screen's state should be keyed on `(timeframe, lastFetchedAt)`. Switching tabs invalidates the cache. Implementation guess (without seeing the code): a `LaunchedEffect(timeframe)` should trigger re-fetch, or the ViewModel's `Flow<BjuBreakdown>` should be parameterized by timeframe rather than computed once at init.

Verify: tap Неделя → 14 дней → Месяц in sequence; observe three different percentages. If still identical, the data layer's caching is incorrect — fix at the query level.

### 2.9 — Average kcal/day uses N days with data, not period length

The Stats screen's headline («В среднем 2 342 ккал в день») must divide total kcal by the count of days that have at least one meal record, not by the number of calendar days in the period.

```python
# Wrong (current):
avg_kcal_per_day = total_kcal / period_days   # period_days = 7, 14, 30

# Right:
days_with_data = count_distinct_days_with_meals(user_id, period_start, period_end)
avg_kcal_per_day = total_kcal / max(days_with_data, 1)
```

For the gluco_admin's 14 days of data, Month (30-day period) average should be the same as 14-day average (~2342 ккал), not half — because the calculation only uses days with data.

Add a small label clarifying: «В среднем 2 342 ккал в день · 14 из 30 дней с записями» when `days_with_data < period_days`. Honest framing about the coverage.

### 2.10 — Hide unfinished sections

«КОГДА ЕШЬ · МЕДИАНА ПО ЧАСАМ» renders empty placeholder bars. Either:
- Implement properly (compute hourly meal-count histogram from existing data — it's a trivial SQL aggregation), OR
- Remove from the screen entirely until implemented.

Default: implement properly. Same `eaten_at_local_hour` field is already available; histogram by hour is one GROUP BY. Add:

```sql
SELECT EXTRACT(HOUR FROM eaten_at_local) AS hour, COUNT(*) AS n
FROM meals WHERE owner_id = ? AND eaten_at_local >= ?
GROUP BY hour
ORDER BY hour
```

Render as 24 bars (or 12, condensed to 2h buckets for tighter screens). Use `--bg-2` for empty hours, gradient up to tangerine for the busiest. This matches what the existing skeleton placeholder is hinting at.

If implementation is deferred beyond this PR, hide the section entirely. Don't ship empty pink rectangles.

## Specifications

### 3.1 — Settings entry «Цели» (new)

In the Ещё screen (Tarelka More), add a section between «БАЗА» and «МОЙ РИТМ»:

```
─────────────────────────────────────────────
ЦЕЛИ                                  Открыть →

ккал/день: 2000 · Б: 100 · Ж: 70 · У: 250
─────────────────────────────────────────────
```

If goals not set, body reads `Цели не заданы · поставить →` in `--ink-2`. Tap «Открыть» / «Поставить» → opens the goals sheet (same as §2.2). Allows users to revisit and change goals at any time.

### 3.2 — Onboarding state machine

```
First launch (post-auth):
  if user.goals_setup_completed == FALSE:
    show GoalsOnboardingSheet
    on Готово: save goals, set goals_setup_completed = TRUE, dismiss
    on Пропустить: set goals_setup_completed = TRUE (no goals saved), dismiss

Subsequent launches:
  if user.kcal_goal_per_day IS NULL:
    Today screen: show soft CTA «Цели не заданы · поставить →»
  else:
    Today screen: show goal ring per existing design
```

The sheet only auto-presents once per `goals_setup_completed = TRUE` flag. The user can always re-open via Ещё → Цели.

### 3.3 — Today goal area layout (with vs without goals)

When goals are set:
```
┌──────────────────────────────────────────────┐
│      ╭─────────╮                              │
│     ╱  1 306    ╲      осталось 694           │  ← goal ring + remaining
│    │   из 2000   │     до конца дня           │
│     ╲           ╱                             │
│      ╰─────────╯                              │
└──────────────────────────────────────────────┘
```

When goals not set (soft CTA replacement):
```
┌──────────────────────────────────────────────┐
│  ккал за день                                 │
│  1 306                                        │
│                                               │
│  Цели не заданы.                              │
│  Их можно поставить в «Ещё → Цели»            │
│  [поставить →]                                │
└──────────────────────────────────────────────┘
```

The empty-circle visual is dropped entirely in the "no goals" state. Showing a circle with «—» suggests the system is broken; showing a text-only state with a clear CTA tells the user this is intentional and they can act.

## Implementation tasks

One PR.

1. **Backend flavor filter for insights** per §2.1. Update the kind registry, add the filter in the request handler. Unit test: hit `/v1/stats/insights?flavor=food` with a fixture user who would qualify for `evening_lows` — verify the response omits that kind.
2. **Tarelka schema migration** per §2.2. New columns on `users` table.
3. **Onboarding sheet** per §2.2 and §3.2. Triggered once on first auth post-installation.
4. **Today screen goal area** per §3.3. Two branches based on `users.kcal_goal_per_day` nullness.
5. **Settings → Цели entry** per §3.1.
6. **TodayHeader fix** per §2.3. Single `Статистика →` link. Update `TarelkaTodayHeader` if it diverges from shared.
7. **Date format fix** per §2.4. Ensure year always renders. Row 2 height >= 48dp.
8. **Login logo padding fix** per §2.5. Outer scaffold uses `WindowInsets.systemBars`.
9. **InsightCard refactor** per §2.6. Consume structured primary/secondary entries; render with divider.
10. **Template tightening + truncation helper** per §2.7. Audit each template against length budget; add `truncateToLines` for safety.
11. **БЖУ cache fix** per §2.8.
12. **Avg-kcal calculation fix** per §2.9.
13. **«Когда ешь» histogram implementation** per §2.10 (or hide it).
14. **Tests:**
    - Insights endpoint flavor filter: `evening_lows`, `meal_predictability`, `hypo_recovery_pattern`, `late_meal_glucose_footprint` never in Tarelka response.
    - Paparazzi: Today with goals set / Today without goals / login screen logo intact / Stats card with 1 / 2 / 3 insights all rendering with correct divider structure.
    - Compose UI: exactly one «Статистика» tap target on Today.
    - Snapshot: Stats Month for a user with 14 days of data — average shows ~2342, not ~1093, with the «14 из 30 дней» annotation.
    - Snapshot: БЖУ tab switch produces 3 different percentage values across timeframes.

## Acceptance

- **No CGM insights in Tarelka.** Hitting `/v1/stats/insights` as a Tarelka user never returns kinds `evening_lows`, `meal_predictability`, `hypo_recovery_pattern`, or `late_meal_glucose_footprint`. Verified with the gluco_admin's actual data (where these kinds would otherwise qualify).
- **Goals are set on first launch.** A fresh Tarelka install + first auth presents the onboarding sheet exactly once. After «Готово» (with values) or «Пропустить» (without), the sheet doesn't re-appear automatically.
- **Today never shows the empty-«—»-circle.** Either the goal ring is populated (goals set) or the soft text CTA is present (goals not set). The big empty circle is gone.
- **Single «Статистика →».** Tarelka Today shows exactly one link.
- **Year always in date.** Today shows «10 мая 2026», not «10 мая». No vertical crop.
- **Logo intact.** Login screen logo visible in full with adequate padding on a 5.5" device.
- **Insights structured with divider.** Stats insight card shows primary + (optional) hairline + secondaries. No prose-block concatenation.
- **No mid-sentence ellipsis.** All rendered insights fit within their allocated space.
- **БЖУ tabs differ.** Three timeframe tabs produce three different percentage triples for the gluco_admin's data.
- **Honest averages.** Month tab shows «В среднем 2 342 ккал в день · 14 из 30 дней с записями», not 1093.
- **«Когда ешь» either real or absent.** No empty pink rectangles.

## Section overrides

- ADR-009 §2.1 — explicit gluco-only kinds list is normative; this ADR adds the enforcement mechanism (§2.1).
- ADR-002 §2.1 — single «Статистика» rule reaffirmed for Tarelka (§2.3).
- ADR-009 §2.5 — insight card structure reaffirmed; this ADR adds the «no mid-sentence ellipsis» rule and adaptive truncation (§2.7).
- TR-2 (tarelka-brand-evolution): Today layout updated with the goal-vs-no-goal branches (§3.3).
- TR-4 (Tarelka stats redesign): insight card structure per §2.6.

## Out-of-band asks

1. **Default goal values.** §2.2 suggests 2000 ккал / 100 / 70 / 250 as sheet defaults. These match a moderately-active adult and are sensible but arbitrary. Confirm or revise. Default if delegated: as written.
2. **Should the goal sheet be re-promotable?** Currently shows once. If the user dismissed it and later wants the sheet back, they go through Ещё → Цели. Alternatively, a small «настроить →» button could re-trigger the same sheet. Default: keep simple, settings-only re-entry.
3. **Goal sheet for gluco users?** Gluco flavor may need its own goal model (carbs ratio, target glucose, etc.) — out of scope here. This ADR addresses Tarelka only. If gluco goals need analog onboarding, it's a separate ADR.
4. **What happens if user's goals are wildly different from their habits?** E.g., goal 1500 кcal/day but actual average 3000. Currently the system shows the difference and that's it (no judgment per brand voice). Confirm — don't add coaching or alerts beyond the visual delta.
5. **Empty Когда ешь implementation priority.** If §2.10 is implemented properly, an hourly histogram looks nice but isn't critical. If implementation is non-trivial in the agent's current sprint, hiding the section is acceptable for v1. Default: hide if it slows down the PR; revisit in a polish sprint.
