# ADR-009 · Insights and UI integration

> Third of three categorization-related ADRs. ADR-007 categorizes the meal, ADR-008 categorizes the body's response. ADR-009 turns the resulting data into Russian-language observations and surfaces them on Stats, History, and Record screens. Hand all three ADRs to the agent together.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-10 |
| Finalized | 2026-05-11 |
| Affects | backend `insights/`, `stats.py`; mobile and desktop Stats screens; History filter chips; Record screen (gluco flavor) |
| Risk | Medium — the insight copy is the user-facing voice of the product. Errors are visible. |

---

## 1 · Context

After ADR-007 and ADR-008 ship, every meal has structured categories and (for gluco users) postprandial response data. None of this is visible to the user yet. ADR-009 is where the system turns into something observably better:

- Stats gets an insight card that answers "what's notable about my recent eating?"
- History filter chips ("Сладкое", "Завтраки") become functional
- Record screen (gluco) gets a postprandial mini-chart per meal

Pre-existing constraints honored:
- Tarelka voice (`tarelka-brand-evolution-prompts.md` §5): observations not judgments, no streaks, no leaderboards
- Banned-word lint from TR-6 still in force; this ADR extends it
- Backend is the single source of truth for insight wording (ADR-007 §2.4 "Server is authoritative for wording")
- Medical safety: nothing recommends doses, no "you should" copy

### 1.1 — Problem statement and stakeholder concerns

The product has enough structured data to describe patterns, but exposing that data directly would create three risks:

1. **Voice risk.** Pattern text can easily sound like praise, blame, or advice. Per `docs/tarelka-brand.md` "Voice Principles", the product must speak in short Russian observations, use server-confirmed facts, and avoid praise, blame, medical advice, insulin language, streak pressure, and goal-shaming.
2. **Medical-safety risk.** Glucose-derived observations are useful for a gluco user, but they must remain informational. Per `CONCEPT.md` §1 and `docs/architecture.md` "Medical Safety Boundary", the app can show observed context but must not recommend insulin, corrections, boluses, treatment changes, or medical decisions.
3. **Data-ownership risk.** The backend owns accepted meal totals, daily averages, insight wording, and history counts. Per `docs/architecture.md` "Data Ownership", clients may derive view-only chart presentation but must not become the authority for nutrition totals or insight wording.

Stakeholders and concerns:

| Stakeholder | Concern | ADR-009 response |
|---|---|---|
| Gluco user | Wants useful glucose context without treatment advice. | CGM-aware insight kinds are gluco-only, deterministic, and phrased as observations. |
| Food/Tarelka user | Wants food rhythm insight with no glucose surfaces. | Food flavor receives only food-only kinds; tangerine accents remain flavor-scoped. |
| Mobile user | Needs capture-and-glance surfaces, not dense analytics. | Stats and Today show at most a small number of observations; sparse data omits the card. |
| Desktop user | Needs fuller review and filtering workflows. | Desktop Stats gains the insight slot; History chips become real backend filters. |
| Backend maintainer | Needs testable, auditable copy generation. | No LLM NLG; each insight is rule-qualified and rendered from canonical templates. |
| Privacy/security reviewer | Needs no cross-user leaks. | All reads are scoped by `user_id`; shared products remain separate from user-owned meals. |

## 2 · Decisions

### 2.1 — Ten insight kinds, deterministic templating, no LLM

All insights are produced by a server-side **rule + template** pipeline. No LLM is involved in NLG. Each kind:

| Kind | Source axes | Min samples | Flavor |
|---|---|---|---|
| `consistent` | `derived_categories.meal_window`, kcal/day | 7 days | both |
| `weekday_pattern_sweet` | `taste_profile`, `meal_window`, weekday | 14 days | both |
| `time_of_day_eating` | `eaten_at` distribution | 14 days | both |
| `top_repeat_products` | meal name frequency | 14 days, ≥3 occurrences | both |
| `late_meal_share` | `meal_window` distribution | 14 days | both |
| `today_morning` | today's meals so far | 1 day | both |
| `meal_predictability` | per-product `glycemic_response` stdev | 5 occurrences/product | gluco only |
| `evening_lows` | `pre_meal_state` + CGM time-of-day | 7 days | gluco only |
| `hypo_recovery_pattern` | `is_hypo_recovery` count + timing | 14 days | gluco only |
| `late_meal_glucose_footprint` | `meal_window=night_cap` + next-morning CGM | 14 days | gluco only |

The `low_data` state is implicit — if no kind qualifies, the endpoint returns an empty list and the UI omits the card entirely.

### 2.2 — Verbatim Russian templates

Each kind has a single canonical template. Variables are filled with formatted numbers / names. **No LLM tweaks the wording.** Below, `{...}` are substitution slots; everything else is fixed copy.

#### `consistent`
```
Привычный для тебя ритм. Около {kcal_avg} ккал в день
за последние {days} дней.
```
Sample: `Привычный для тебя ритм. Около 1 970 ккал в день за последние 14 дней.`

Conditions: stdev of daily kcal across last 14 days < 25% of mean. Fired only when the user's pattern is actually consistent — no point announcing rhythm during a chaotic week.

#### `weekday_pattern_sweet`
```
По {day_label} {window_label} сладкого больше всего —
около {kcal_sweet} ккал из десертов и напитков.
```
Sample: `По вечерам в среду и пятницу сладкого больше всего — около 380 ккал из десертов и напитков.`

`{day_label}` is rendered from concentrated-day(s): "пятницам", "вторникам и пятницам", "выходным". `{window_label}` is the meal_window: "утром", "днём", "вечером", "ночью" (mapped from `start/mid/late/night_cap`).

Conditions: at least 3 such weekday-window cells must have ≥2 sweet meals each, AND they must aggregate to >25% of total sweet kcal.

#### `time_of_day_eating`
```
Чаще всего ешь в {h1}:00 и {h2}:00.
```
Sample: `Чаще всего ешь в 13:00 и 19:00.`

`{h1}, {h2}` are the two highest-density hours-of-day across the period (peaks must be ≥2 hours apart). If the second peak is <60% of the first, render only the first hour: `Чаще всего ешь около {h1}:00.`

#### `top_repeat_products`
```
Чаще всего: {p1} ({n1}×), {p2} ({n2}×), {p3} ({n3}×).
```
Sample: `Чаще всего: Протеиновое брауни (7×), Сырок глазированный (6×), Лаваш с курицей (5×).`

If only 2 products have ≥3 occurrences, render 2. If only 1, render `Чаще всего ешь: {p1} ({n1}×) — это твоя самая частая позиция.` If none, kind not fired.

#### `late_meal_share`
```
Около {pct}% твоих приёмов еды — после {window_threshold}.
{count_per_week} раз в неделю в среднем.
```
Sample: `Около 38% твоих приёмов еды — после 21:00. 5 раз в неделю в среднем.`

`{window_threshold}` is the user's `late` window start (rendered as a wall-clock hour). Fired when late+night_cap meals account for ≥25% of total. Below that, the pattern isn't notable.

#### `today_morning` (Today screen, slot=today)
```
К утру немного больше обычного.
```
or
```
Похоже на твой обычный завтрак.
```
or
```
{kcal_today_so_far} ккал к {hh:mm} — пока меньше обычного.
```

Conditions: `today_morning` fires only when the user has eaten ≥1 meal in the current day's `start` window. Compares today's `start`-window kcal to the same window's median over last 14 days. Three branches: 1.2× higher → first variant; within 0.8x..1.2× → second; lower → third.

#### `meal_predictability` (gluco only)
```
{product_name} — твой самый предсказуемый приём по отклику глюкозы.
В среднем +{delta_avg:.1f} ммоль/л на пике, ±{delta_stdev:.1f}.
```
Sample: `Лаваш с курицей и овощами — твой самый предсказуемый приём по отклику глюкозы. В среднем +2.8 ммоль/л на пике, ±0.6.`

Conditions: at least one product with ≥5 occurrences AND `delta_max stdev < 1.0`. Show the product with the lowest stdev among qualifying.

#### `evening_lows` (gluco only)
```
{share_pct}% твоих эпизодов ниже 4 ммоль/л — между {h1}:00 и {h2}:00.
```
Sample: `85% твоих эпизодов ниже 4 ммоль/л — между 19:00 и 07:00.`

Conditions: at least 10 hypo episodes (<4) in the period, AND ≥70% concentrated in a contiguous time window (allowing for wrap past midnight).

#### `hypo_recovery_pattern` (gluco only)
```
В {fraction} случаях из {total} сладких приёмов после {hh}:00
им предшествовал низкий сахар.
```
Sample: `В 4 случаях из 7 сладких приёмов после 22:00 им предшествовал низкий сахар.`

Conditions: at least 5 sweet meals after the user's `late` window start AND ≥30% of them have `is_hypo_recovery = true`. Honest framing: this is correlation, not categorization of intent.

#### `late_meal_glucose_footprint` (gluco only)
```
Поздние приёмы (после {hh}:00) в среднем оставляют глюкозу
на +{delta:.1f} ммоль выше обычного к {next_morning_h}:00.
```
Sample: `Поздние приёмы (после 22:00) в среднем оставляют глюкозу на +1.2 ммоль выше обычного к 03:00.`

Conditions: at least 5 night_cap-window meals in period AND a measurable difference (>0.5 mmol) in next-3-hours mean glucose vs days without a night_cap meal.

### 2.3 — Insight ranking and selection

The endpoint computes all qualifying insights, ranks them, returns top **3 max** for `slot=stats`, top **1** for `slot=today`. Ranking score for each:

```
score = recency_factor × novelty_factor × signal_strength
```

- `recency_factor`: 1.0 for insights computed from today's data, 0.7 for last-7d-only, 0.5 for last-14d.
- `novelty_factor`: 0.5 if same insight kind was returned in the last 7 days' calls (avoid repetition), 1.0 otherwise.
- `signal_strength`: kind-specific; e.g., for `weekday_pattern_sweet` it's the share of sweet kcal in the cell vs total; for `meal_predictability` it's `1.0 / stdev`.

This produces variety: the user doesn't see the same observation every day.

### 2.4 — Insight endpoint contract

```
GET /v1/stats/insights?period=7d|14d|30d&slot=stats|today
→ 200 OK
{
  "insights": [
    {
      "id":      "weekday_pattern_sweet:2026-05-10",
      "kind":    "weekday_pattern_sweet",
      "text":    "По вечерам в среду и пятницу сладкого больше всего — около 380 ккал из десертов и напитков.",
      "weight":  "primary" | "secondary",
      "computed_at": "2026-05-10T18:30:00Z"
    }
  ]
}
```

`weight = primary` for the highest-ranked insight (rendered with kicker emphasis), `secondary` for others. Empty `insights[]` is a valid response — UI omits the card.

Cached server-side per `(user_id, period, slot, date)` for 1 hour. Recomputed on next call after expiry, on meal mutation, or on demand via `?force=true` (admin only).

### 2.5 — UI surfaces

#### Mobile (Tarelka, food flavor, per TR-4)

Insight card on Stats, refined per ADR-009:

```
┌─────────────────────────────────────────────┐
│ НАБЛЮДЕНИЕ                                  │  ← tangerine 9.5sp letter-spaced
│                                             │
│ По вечерам в среду и пятницу сладкого       │  ← serif fallback, sans 14sp
│ больше всего — около 380 ккал из десертов   │     max 3 lines (per TR-4)
│ и напитков.                                 │
│                                             │
│ ─ ─ ─                                       │  ← optional, see below
│                                             │
│ Чаще всего: Протеиновое брауни (7×).        │  ← secondary, 12sp ink-2
└─────────────────────────────────────────────┘
```

If the response has 1 insight, render only the primary block. If 2-3, render primary as above plus secondary lines below a hairline divider. Each secondary is one-line, 12sp.

#### Mobile (gluco flavor)

Same layout, **kicker color** is `--ink-2` graphite (NOT tangerine — tangerine is reserved for Tarelka brand per TR-1 §invariant 8).

#### Desktop (both flavors)

The desktop `Stats` page already has a header band and KPI strip (per the desktop screenshots earlier in the conversation). The insight card slots into the **right column** of the Stats grid, between the BJU-balance KPI card and the carbs-by-day chart:

```
┌──────────────────────────────────────────────────────────────────┐
│ 5 мая 2026 г.                                                    │
│ Профицит 1892 ккал за завершённые дни                            │
├────────────────┬────────────────┬────────────────┬───────────────┤
│ УГЛЕВОДЫ       │ ККАЛ           │ ГН             │ БЖУ-БАЛАНС    │
│ 149.6 г        │ 1536           │ 38             │ Б 43.8 Ж 85.5 │
├────────────────┴────────────────┴────────────────┴───────────────┤
│ ┌──────────────────────────────┐  ┌─────────────────────────────┐│
│ │ Углеводы (г) по дням         │  │ НАБЛЮДЕНИЕ                  ││
│ │ [bars chart]                 │  │                             ││
│ │                              │  │ По вечерам в среду и пятницу││
│ │                              │  │ сладкого больше всего — ... ││
│ └──────────────────────────────┘  │                             ││
│                                   │ ─ ─ ─                       ││
│                                   │ Чаще всего: ...             ││
│                                   └─────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

Card width matches one Stats grid column (≈340dp). Same vertical hierarchy as mobile. Hairline border, surface-2 fill. Both flavors render the kicker in `--ink-3` graphite on desktop (tangerine is a mobile-only food-flavor accent per TR design tokens).

#### History — filter chips become functional

The chips `Сладкое`, `Завтраки`, `Только фото`, `Низкая увер.` now drive a real backend filter:

| Chip | Filter |
|---|---|
| `Сладкое` | `ai_categories->>'taste_profile' IN ('sweet', 'drink_sweet')` |
| `Завтраки` | `derived_categories->>'meal_window' = 'start'` |
| `Только фото` | `source = 'photo'` |
| `Низкая увер.` | `(ai_categories->>'confidence')::float < 0.6` |

Chips are multi-select (intersection). Active chip uses the existing ink-fill style (no new colors). State is local to the History session (not persisted).

#### Record screen — postprandial mini-chart (gluco only)

A new section between the existing source/confidence block and the glucose-at-meal panel:

```
─────────────────────────────────────
ОТКЛИК ГЛЮКОЗЫ (ПО CGM)

[60dp tall mini-chart spanning full width]
 │     ╱─╲
 │    ╱   ╲___
 │   ╱        ╲___
 ●──●─────────────────●
 0  +30   +60   +90  +180

пик +2.9 ммоль/л на 65 мин · вернулась к 6.3
─────────────────────────────────────
```

Renders the five anchors as labeled dots, plus a smooth interpolated curve through them. X-axis: 0 / +30 / +60 / +90 / +180 in mono 8sp. Y-axis: implicit (no labels, just the curve shape). Below the chart, one mono line summarizing peak Δ and recovery state.

If `glycemic_response = unknown` (insufficient CGM coverage), render the section with `coverage_180min` percentage and a one-liner `недостаточно данных CGM для расчёта`. If `is_hypo_recovery = true`, prepend a kicker `КОРРЕКЦИЯ ГИПОГЛИКЕМИИ` instead of `ОТКЛИК ГЛЮКОЗЫ` — same data, different framing.

The chart uses Compose Canvas (mobile) / native Tauri canvas (desktop). Same warm editorial palette: graphite line, hairline grid, no fills.

#### Settings — Мой ритм (both flavors)

A dedicated sub-screen under Settings (mobile: More → "Мой ритм" · desktop: Settings → "Расписание дня"). Reached on-demand; nothing of this surface appears on Today or Stats. Visualizes the adaptive day_anchor from ADR-007 §2.2 — both its current state and its history of changes.

The screen has four blocks, stacked vertically:

**Block 1 — current windows ribbon (24h horizontal band).**

```
─────────────────────────────────────────────
МОЙ РИТМ

Сейчас день начинается в ~13:00
по последним 7 дням

   13:00      16:00      21:00      02:00      07:00
   ┌──────┬──────────┬──────────┬──────────┐
   │ start│   mid    │   late   │night_cap │
   └──────┴──────────┴──────────┴──────────┘
              ● — сейчас 14:23, окно «mid»
─────────────────────────────────────────────
```

The ribbon is a horizontal Canvas drawing, ~24dp tall (mobile) / 28dp (desktop), filling content width. Four colored bands (the four windows) with hairline dividers between them. Above each band: the wall-clock start time of that window (mono 9sp, `--muted`). Below each band: the window's slug (small-caps sans 9sp, `--ink-2`).

Window band fills are subtle tonal variants of `--bg-2`, not loud colors — different enough to distinguish, quiet enough to read as a single graphic. Standard order (start/mid/late/night_cap) regardless of which hour they start at.

A circle marker (`●`, 6dp) sits on the ribbon at the user's current wall-clock position, with a caption below: `сейчас HH:MM, окно «<slug>»`. Marker is `--ink` (high contrast). Updates every 60 seconds while the screen is in foreground.

**Block 2 — weekend/weekday split, conditional.**

Rendered only when `users.day_anchor_weekend_minutes IS NOT NULL` (per ADR-007 §2.2c — the split fires only when the data supports it). If absent, this block is omitted entirely (no "no split detected" copy).

```
─────────────────────────────────────────────
ВЫХОДНЫЕ
Утром позже на ~2 часа.

   15:00      18:00      23:00      04:00      09:00
   ┌──────┬──────────┬──────────┬──────────┐
   │ start│   mid    │   late   │night_cap │
   └──────┴──────────┴──────────┴──────────┘
─────────────────────────────────────────────
```

A second ribbon with the same structure, shifted by the difference between weekday and weekend anchors. The descriptor line above describes the difference in plain Russian: `Утром позже на ~2 часа`, `Утром раньше на ~1 час`, etc.

**Block 3 — history of changes (last 90 days).**

A vertical timeline showing periods of schedule stability, with shifts marked:

```
─────────────────────────────────────────────
ИЗМЕНЕНИЯ ЗА 90 ДНЕЙ

11 фев → 27 фев     старт ~12:00     16 дней
27 фев                ↘ сдвиг -1ч
27 фев → 14 мар     старт ~11:00     15 дней
14 мар                ↗ сдвиг +2ч
14 мар → сегодня    старт ~13:00     58 дней (текущий)
─────────────────────────────────────────────
```

Rendered as a flat list of stability periods, each with:
- date range (mono 10sp, `--ink-2`),
- start time during that period (sans 12sp, `--ink`),
- duration in days (mono 10sp, `--muted`).

Between consecutive periods, a single-line shift annotation: `↗ сдвиг +Nч` or `↘ сдвиг -Nч`, indented, in `--ink-3`. Arrows are unicode (`↗` for shift forward / later, `↘` for shift backward / earlier). The current period is annotated with `(текущий)`.

If history has no shifts (anchor stable for 90 days), render one line: `Расписание стабильно с DD MMM (N дней).`

If history has too few qualifying days (<14 days of data), render: `Слишком мало данных для истории.` and omit the list.

**Block 4 — controls.**

Three actions, stacked:

```
─────────────────────────────────────────────
УПРАВЛЕНИЕ

[ Задать вручную → ]

[ Отметить нетипичный период → ]

[ Очистить ручное расписание ]   (visible only when override is set)
─────────────────────────────────────────────
```

- **Задать вручную** opens a time-picker sheet. On confirm, writes `users.day_anchor_user_override_minutes`. Returns to the screen, which now shows `Сейчас день начинается в HH:MM (задано вручную)` above Block 1, and Block 3 changes its header to `ИЗМЕНЕНИЯ ЗА 90 ДНЕЙ (до ручной настройки)`.
- **Отметить нетипичный период** opens a date-range picker. On confirm, inserts a row into `non_typical_periods`. No immediate visible change on this screen — but the next nightly recompute will exclude those days from anchor calculations.
- **Очистить ручное расписание** clears `users.day_anchor_user_override_minutes` and triggers an immediate anchor recomputation. Visible only when override is currently set. After clearing, the screen updates to show the automatically-computed anchor.

All three controls are simple text buttons, `--ink` text on `--bg`, hairline border, full-width on mobile / left-aligned on desktop. No icons. The order matters: the most common action ("set manually" when system inferred wrong) is first.

**Desktop variant.** Same four blocks, but the two ribbons (Blocks 1+2) sit side-by-side in a 2-column grid when both are present, instead of stacked. Block 3 (history) is full-width below. Block 4 (controls) is right-aligned, single row of buttons.

### 2.6 — Rationale and alternatives considered

The accepted decision is to use backend-owned deterministic insight generation with fixed templates, small Top-N selection, and role-aware UI surfaces.

Rationale:

- **Deterministic templates over LLM wording.** Insight copy is product voice and medical-adjacent. Fixed templates are reviewable, snapshot-testable, lintable, and stable across releases. This follows ADR-007 §2.4's server-authoritative wording principle and keeps the UI from inventing copy.
- **Backend endpoint over client-side aggregation.** The backend already owns accepted records and totals. Keeping insights in the backend prevents divergent mobile/desktop calculations, preserves user scoping, and makes food/gluco role gating enforceable in one place.
- **Empty list over low-data placeholder.** Low-data insight placeholders create noise and invite speculative copy. Returning `insights: []` lets each UI omit the card cleanly.
- **Top 3 / Top 1 selection over feeds.** Stats needs a small observation card, not another timeline. Today needs at most one soft line. Longer insight history is intentionally out of scope for v1.
- **`Мой ритм` as Settings surface over Stats surface.** Day-anchor visualization is diagnostic and corrective. It belongs with Settings because the user opens it when the inferred schedule feels wrong, not during daily capture.

Alternatives rejected:

| Alternative | Why rejected |
|---|---|
| LLM-generated insight prose | Hard to lint, harder to guarantee no advice or judgment, and unnecessary for fixed observation classes. |
| Client-computed insights | Duplicates product math and risks flavor-specific data leaks, especially for food users. |
| Persisting every generated insight as a feed | Adds a new UX surface and storage lifecycle without a clear v1 workflow. |
| Showing disabled/empty cards for sparse data | Violates the capture-and-glance principle and makes low-data states feel like errors. |
| 404 for food users on glucose-derived insight requests | Feature-gating invariant requires stable 403 only for glucose endpoints; the mixed stats endpoint instead returns only food-safe kinds. |

## 3 · Specifications

### 3.1 — Backend module layout

```
backend/glucotracker/
└─ application/
   └─ insights/
      ├─ __init__.py
      ├─ kinds/                # one file per insight kind
      │  ├─ consistent.py
      │  ├─ weekday_pattern_sweet.py
      │  ├─ time_of_day_eating.py
      │  ├─ top_repeat_products.py
      │  ├─ late_meal_share.py
      │  ├─ today_morning.py
      │  ├─ meal_predictability.py
      │  ├─ evening_lows.py
      │  ├─ hypo_recovery_pattern.py
      │  └─ late_meal_glucose_footprint.py
      ├─ ranker.py             # §2.3 score function
      ├─ generator.py          # composes kinds → ranks → top N
      └─ templates.py          # §2.2 templates as Python f-strings
```

Each kind module exports:

```python
def qualify(user_id: UUID, period: timedelta) -> Optional[QualifyResult]:
    """Returns {"variables": {...}, "signal_strength": float} or None if not qualifying."""

def render(variables: dict) -> str:
    """Applies the template from templates.py with the given variables."""
```

`generator.py` orchestrates: calls each kind's `qualify`, collects qualifying ones, ranks, takes top N. Result wrapped into the §2.4 response shape.

### 3.2 — Banned-word lint extension

Templates and any kind-rendered text must pass the existing TR-6 banned-word check, plus:

- No words that frame eating as success/failure: `молодец`, `лень`, `срыв`, `держись`, `так держать`.
- No words that prescribe: `надо`, `нужно`, `следует`, `попробуй меньше/больше`, `сократи`, `увеличь`.
- No comparison with other users: any string containing `другие`, `пользователи`, `обычный человек` is banned.
- No counter-words: `подряд`, `рекорд`, `серия дней`.

CI test: every entry in `templates.py` is rendered with synthetic variables and checked against the banned list. Build fails on any hit.

### 3.3 — Today screen integration (mobile)

The Today screen's existing `softObservation` field (specced in TR-2) is now populated by the `today_morning` insight from `slot=today`. If the endpoint returns an empty list for today, the line is omitted (per TR-2 acceptance: "the line is absent (no empty placeholder)").

### 3.4 — Caching

Insights are server-cached at `(user_id, period, slot, date)` granularity. TTL 1 hour. Invalidated on:
- Meal create / update / delete affecting the period.
- Manual refresh (admin endpoint).
- Postprandial response computed for a meal in the period (gluco-only kinds may now qualify).

The cache lives in Redis if available, else in a Postgres table `insight_cache` with row-level TTL.

### 3.5 — Schedule endpoint and history table

The "Мой ритм" UI surface needs two reads: current anchor state and the history of changes. The current state already lives in `users` table per ADR-007 §3.1; history requires a new table.

```sql
CREATE TABLE day_anchor_history (
  id            UUID PRIMARY KEY,
  user_id       UUID NOT NULL REFERENCES users(id),
  effective_from DATE NOT NULL,            -- first day this anchor applied
  effective_to   DATE NULL,                -- last day this anchor applied; NULL = current
  anchor_weekday_minutes INT NOT NULL,
  anchor_weekend_minutes INT NULL,         -- same shape as users.day_anchor_weekend_minutes
  basis         TEXT NOT NULL,             -- "weighted_7d" | "shift_3d" | "user_override" | "absolute_fallback"
  recorded_at   TIMESTAMPTZ NOT NULL,
  CONSTRAINT only_one_current_per_user EXCLUDE USING gist
    (user_id WITH =) WHERE (effective_to IS NULL)
);
CREATE INDEX idx_anchor_history_user_date ON day_anchor_history(user_id, effective_from DESC);
```

The nightly anchor recompute job (ADR-007 §3.5) writes a new row to `day_anchor_history` **only when the computed anchor differs from the current row** by ≥30 minutes (avoid storing 89,000 daily snapshots). When writing a new row, the previous current row's `effective_to` is set to the day before.

For a user with stable schedule, this table grows by 0 rows per day. For a user shifting once a month, ~12 rows per year. Trivially compact.

New backend endpoint:

```
GET /v1/me/schedule
→ 200 OK
{
  "current": {
    "anchor_weekday_minutes": 780,        // 13:00
    "anchor_weekend_minutes": 900,        // 15:00, or null
    "basis": "weighted_7d",
    "windows_weekday": [
      {"slug": "start",     "from": "13:00", "to": "16:00"},
      {"slug": "mid",       "from": "16:00", "to": "21:00"},
      {"slug": "late",      "from": "21:00", "to": "02:00"},
      {"slug": "night_cap", "from": "02:00", "to": "07:00"}
    ],
    "windows_weekend": [...]               // same shape, only if anchor_weekend_minutes != null
  },
  "history": [
    {
      "effective_from": "2026-02-27",
      "effective_to":   "2026-03-13",
      "anchor_weekday_minutes": 660,       // 11:00
      "duration_days": 15,
      "shift_from_previous_minutes": -60   // -1h
    },
    {
      "effective_from": "2026-03-14",
      "effective_to":   null,
      "anchor_weekday_minutes": 780,
      "duration_days": 58,
      "shift_from_previous_minutes": 120
    }
  ],
  "manual_override": {
    "is_set": false,
    "minutes": null
  },
  "non_typical_periods": [
    {"start_date": "2026-04-15", "end_date": "2026-04-22", "note": "отпуск"}
  ]
}
```

Endpoint is per-user, role-agnostic (both flavors expose schedule — Tarelka users have a rhythm too). Cache is unnecessary; the data is small and changes at most nightly.

Companion write endpoints:

```
PUT  /v1/me/schedule/override        { "minutes": 780 }     → 204
DELETE /v1/me/schedule/override                              → 204
POST /v1/me/schedule/non-typical-period
  { "start_date": "...", "end_date": "...", "note": "..." }  → 201 with new period
DELETE /v1/me/schedule/non-typical-period/{id}              → 204
```

### 3.6 — Shift-annotation rendering rules

The schedule history endpoint returns `shift_from_previous_minutes` as a signed integer. The UI renders this as:

```python
def render_shift(minutes: int) -> str:
    if minutes == 0:
        return ""  # don't render shift annotations of zero (shouldn't happen given 30-min threshold)
    arrow = "↗" if minutes > 0 else "↘"
    hours = abs(minutes) / 60
    if hours < 1.5:
        return f"{arrow} сдвиг {'-' if minutes < 0 else '+'}{int(abs(minutes))}мин"
    elif hours == int(hours):
        return f"{arrow} сдвиг {'-' if minutes < 0 else '+'}{int(hours)}ч"
    else:
        return f"{arrow} сдвиг {'-' if minutes < 0 else '+'}{hours:.1f}ч"
```

Examples:
- `+60` → `↗ сдвиг +1ч`
- `-90` → `↘ сдвиг -1.5ч`
- `+45` → `↗ сдвиг +45мин`
- `+120` → `↗ сдвиг +2ч`

Rendered in the timeline as a single line between consecutive periods, indented to match the period date stamps.

## 4 · Implementation tasks

One PR per phase; phases sequential.

**Phase A · Endpoint and food-only kinds (3 days)**

- A1. `application/insights/` module skeleton per §3.1.
- A2. Implement food-only kinds: `consistent`, `weekday_pattern_sweet`, `time_of_day_eating`, `top_repeat_products`, `late_meal_share`, `today_morning`. Each with unit tests using fixture data.
- A3. `ranker.py` and `generator.py` per §2.3.
- A4. `GET /v1/stats/insights` endpoint per §2.4.
- A5. Banned-word lint extension per §3.2.
- A6. Caching per §3.4.

**Phase B · CGM-aware kinds (1 day, gluco-only)**

- B1. Implement: `meal_predictability`, `evening_lows`, `hypo_recovery_pattern`, `late_meal_glucose_footprint`. Each unit-tested against synthetic `postprandial_response` data plus CGM streams.
- B2. Role-gate: `food` flavor users get insights from food-only kinds only; gluco gets all 10.

**Phase C · UI integration (3 days)**

- C1. Mobile (Tarelka) Stats: refine the insight card per §2.5 mobile spec. Updates TR-4.
- C2. Mobile (gluco) Stats: same component, graphite kicker variant.
- C3. Desktop Stats: insight card slot in the right column of Stats grid per §2.5 desktop spec.
- C4. History filter chips wired to backend per §2.5 history spec.
- C5. Record screen (gluco only) postprandial mini-chart per §2.5 record spec. Uses Compose Canvas (mobile) / Tauri canvas (desktop). Hypo-recovery prepended kicker swap.
- C6. Today's `softObservation` wired to the `today_morning` insight per §3.3.

**Phase D · "Мой ритм" Settings surface (2 days)**

- D1. Schema migration for `day_anchor_history` table per §3.5. Backfill: insert one row per user reflecting their current `users.day_anchor_*` state with `effective_from = today, effective_to = NULL, basis = current_basis`.
- D2. Modify the nightly anchor-recompute job (ADR-007 §3.5) to write a new history row when the new computed anchor differs from the current by ≥30 minutes. Close the previous row by setting its `effective_to` to yesterday.
- D3. Backend endpoints per §3.5: `GET /v1/me/schedule`, `PUT/DELETE /v1/me/schedule/override`, `POST/DELETE /v1/me/schedule/non-typical-period`.
- D4. Mobile (both flavors): new route "Мой ритм" reachable from Settings. Renders the four blocks per §2.5 "Settings — Мой ритм".
  - The 24h ribbon is a custom `Canvas` composable (`@Composable fun DayRibbon(windows, currentTime, modifier)`) with the now-marker updating every 60s.
  - The history list is a simple `LazyColumn` of period rows + shift annotations.
  - Controls open standard time-picker / date-range-picker sheets.
- D5. Desktop (both flavors): same route in Settings, two-column ribbon layout when weekend split exists.
- D6. Tests:
  - Unit: shift-rendering function (§3.6) produces correct Russian for ±30min, ±60min, ±90min, ±120min, ±150min.
  - Unit: history endpoint returns correct period list for a user with 3 historical anchor rows.
  - Integration: setting manual override via PUT immediately changes the response of `GET /v1/me/schedule`. Clearing it via DELETE returns the auto-computed anchor.
  - Paparazzi (mobile): "Мой ритм" screen in three states — no history yet (fewer than 14 days), single stable period (90 days no shifts), multi-period history (2-3 shifts).

## 5 · Section overrides

- TR-3 (Tarelka): insight kinds list there is superseded by §2.1 here. The 5 kinds in TR-3 collapse into the 10 here, with TR-3's `today_morning` mapping to the same name and `weekday_pattern` becoming `weekday_pattern_sweet`.
- TR-4: insight card visual spec is unchanged structurally; the wiring to backend insights is now real.
- T9 / Record screen for gluco: gains the postprandial section per §2.5.
- ADR-007 §3.5: the nightly anchor-recompute job gains the responsibility of writing to `day_anchor_history` on significant change. The recompute logic itself is unchanged.
- T11 (More / Settings): adds a new entry "Мой ритм" routing to the new screen. No other Settings changes.

## 6 · Acceptance

- **Templates render correctly.** Snapshot tests for each kind: given fixture qualify-results, the rendered Russian string matches the template character-for-character.
- **Banned words.** CI grep across all rendered insights for the user's actual data over 30 days produces zero hits in the banned-word list.
- **Top-N ranking.** Synthetic fixtures producing 5+ qualifying insights at once → response always has ≤3 entries for `slot=stats`, ≤1 for `slot=today`. The highest-`signal_strength` kind is always `weight=primary`.
- **History filter correctness.** Toggle `Сладкое` → only meals with `taste_profile in {sweet, drink_sweet}` show. Toggle `Завтраки` → only meals with `meal_window=start` show. Both together: intersection.
- **Record postprandial.** For a meal with `glycemic_response=moderate`, peak Δ=2.9, the chart renders 5 dots, a curve through them, and the line `пик +2.9 ммоль/л на 65 мин · вернулась к 6.3`. For a meal with `glycemic_response=unknown` (low CGM coverage), no chart — just the message and the coverage percentage.
- **No insights when sparse.** A user with <7 days of meals: endpoint returns `{insights: []}`. UI omits the card entirely (no empty box).
- **food flavor never sees gluco insights.** As `food` user, hitting the endpoint with `slot=stats` returns at most the 6 food-only kinds. CGM-derived kinds are never present in the response.
- **Voice consistency on real data.** Run insight generation over the user's 30 days of data. Manual review: every rendered string sounds like the brand (calm, descriptive, no judgment). Adjust templates if any sound off.
- **Schedule visualization correctness.** For the user's actual anchor (~13:00 weekday), the "Мой ритм" screen renders the four windows at 13-16, 16-21, 21-02, 02-07. The "сейчас" marker accurately tracks the current wall-clock time within a 60s update cycle.
- **History tracking.** A synthetic test: seed a user with 3 different anchors recorded over 90 days (one at 11:00, one at 12:00, one at 13:00, with shifts on day 14 and day 60). The history endpoint returns all three periods correctly with `shift_from_previous_minutes` set. UI renders the three rows + two shift annotations.
- **Manual override round-trip.** Setting override via UI → the "сейчас день начинается в HH:MM (задано вручную)" copy appears immediately and the timeline's most recent period closes with `(до ручной настройки)`. Clearing returns to auto-computed state.
- **No history below threshold.** For a user with <14 days of qualifying data, the history block shows "Слишком мало данных для истории." and the ribbon uses absolute-fallback windows without crash.
- **Non-typical period round-trip.** Adding a date range via the UI inserts a `non_typical_periods` row and is reflected in the response of `GET /v1/me/schedule`. The next nightly recompute excludes those dates.

## 7 · Out-of-band asks

1. **Insight scheduling.** §3.4 caches at the date+(period+slot) level for 1 hour. Should the worker pre-warm the cache nightly so morning-load is instant? Default if delegated: no — the cost on demand is <100ms, not worth pre-warming infrastructure.
2. **`today_morning` thresholds.** §2.2 uses 1.2× and 0.8× as comparison bands. Calibrate after observing real distributions; many days will sit in the "обычный" band, which is fine. Default: ship as written.
3. **Should past insights be shown?** A "history of insights" feed could be useful but adds UX surface. Default: no; insights are ephemeral, current-only.
4. **Russian copy approval.** Every template in §2.2 should be reviewed by you (the user) before this ships. The voice is the brand. Default if delegated: ship as written; expect 1-2 revisions in week 1.
5. **Mini-chart vs full chart in Record.** §2.5 specs a 60dp mini-chart. If you want a tap-to-expand to a full 200dp chart with dose markers and trend annotations, that's a v2 feature. Default: mini only for v1.

## 8 · Consequences

### 8.1 — Positive consequences

- Users see categorization and CGM analysis as calm, Russian-language observations instead of raw technical fields.
- Desktop and mobile share one authoritative insight source, reducing divergence between clients.
- Food and gluco flavors can reuse the same Stats surface while preserving glucose feature-gating.
- History chips become auditable backend filters rather than best-effort client heuristics.
- Record screens can explain postprandial context where it belongs: attached to the meal that produced the response.
- The `Мой ритм` surface gives users a way to inspect and correct day-anchor inference without making the main diary more complex.
- Banned-word lint and snapshot tests make product voice regressions visible in CI.

### 8.2 — Negative consequences and costs

- The backend owns more presentation logic. This is intentional, but it means copy changes require backend releases and contract tests.
- Insight ranking introduces cache invalidation complexity around meal mutation and postprandial recomputation.
- Schedule history adds a new table and migration path. The table is small, but it must still follow the forward-only, non-destructive migration rule.
- CGM-aware insights depend on ADR-008 data quality. Missing CGM coverage must degrade to omitted insights rather than misleading copy.
- UI clients must tolerate empty insight arrays and must not reserve blank card space.
- Russian templates need manual review after real-data rollout; deterministic copy still may sound slightly off in edge cases.

### 8.3 — Risk mitigations

| Risk | Mitigation |
|---|---|
| Judgmental or prescriptive copy reaches users | Fixed templates, banned-word lint (§3.2), snapshot tests (§6), and manual Russian copy review (§7.4). |
| Cross-user data leak in insights | Repository-level `user_id` scoping for every meal, CGM, schedule, and cache query; two-user isolation tests for scoped repositories. |
| Food flavor receives glucose insight | Role-aware generator selection; food users receive only the six food-only kinds. |
| Sparse data creates false certainty | Minimum sample gates per kind and `insights: []` for low-data states. |
| Repeated observations feel stale | Ranking includes novelty factor (§2.3); future persisted history can strengthen this without changing client UI. |
| Schedule history grows without bound | Rows are written only when anchors shift by ≥30 minutes (§3.5), not every day. |
| Cache serves stale insight after mutation | Invalidate on meal create/update/delete and postprandial recompute (§3.4). |

### 8.4 — Rollout and migration consequences

- Phase order is mandatory: ADR-007 categories and ADR-008 postprandial fields must exist before the full ADR-009 insight set is meaningful.
- Phase A can ship first with food-only insights. This gives immediate value to both flavors and exercises the endpoint contract.
- Phase B must add gluco-only insight tests before exposing CGM-aware kinds.
- Phase C can progressively enhance UI surfaces because `insights: []` is valid and non-breaking.
- Phase D requires a forward-only migration for `day_anchor_history`; no destructive changes are permitted.
- OpenAPI must be regenerated after endpoint/schema changes so desktop and Android generated clients stay aligned with `docs/openapi.json`, the legitimate API surface.

## 9 · Related documentation

- `docs/ADR-007-meal-categorization (1).md` — defines `ai_categories`, `derived_categories`, and adaptive `day_anchor` state consumed here.
- `docs/ADR-008-postprandial-cgm.md` — defines `postprandial_response`, glycemic response classes, and per-product aggregation used by gluco insights.
- `docs/ADR-008-followup-recovery-and-delayed-peaks.md` — amends ADR-008 with `is_meal_during_low`, delayed-peak handling, and a future ADR-009 backlog insight.
- `docs/architecture.md` — establishes backend data ownership, frontend display boundaries, and the medical safety boundary.
- `CONCEPT.md` §1, §2, §5, §6, §7 — defines mobile scope, desktop-only omissions, design tokens, animation limits, and accessibility rules.
- `docs/tarelka-brand.md` "Voice Principles", "Color", and "Copy" — defines food-flavor voice, tangerine scoping, and banned copy examples.
- `docs/openapi.json` — source of truth for client-consumable endpoint contracts after implementation.

## 10 · Final review

Reviewed on 2026-05-11.

Checklist:

- [x] Context explains why the decision is needed and what prior work it depends on.
- [x] Decision section states the accepted architecture, alternatives, and rationale.
- [x] Implementation details cover backend modules, endpoint contracts, caching, UI surfaces, schedule history, tests, and rollout phases.
- [x] Consequences document benefits, costs, risks, and mitigations.
- [x] Stakeholder concerns are listed and mapped to concrete ADR responses.
- [x] Related ADRs and product documents are referenced explicitly.
- [x] Medical safety and food/gluco feature gating are preserved.
- [x] Multi-user data isolation is called out as a repository-level requirement.
- [x] No new colors, fonts, radii, or unapproved visual language are introduced.
- [x] The ADR follows the established local ADR structure: metadata table, Context, Decisions, Specifications, Implementation tasks, Section overrides, Acceptance, Out-of-band asks, and final Consequences/References/Review sections.

Final status: **Accepted and finalized**. Implementation remains phased as described in §4; this document is complete as the architectural decision record.
