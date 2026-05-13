# ADR-010 · Endocrinologist report redesign

> Replaces the locked-window meal profile with adaptive windows from ADR-007 and adds two new clinically-valuable sections (response distribution per window, predictability per product) while keeping the report on a single A4 page. Hand alongside ADR-007 / ADR-008 / ADR-009.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-11 |
| Affects | backend `reports/endocrinologist.py` (or equivalent), PDF/HTML template, calling code; gluco flavor only (Tarelka does not have a clinical-report feature) |
| Risk | Low — additive in terms of data sources; redesign is layout work |

---

## 1 · Context

The current endocrinologist report (sample from 2026-05-11 attached) is functional but has two structural issues:

**Locked time-windows.** Meal categories `Завтрак / Обед / Ужин / Перекусы` use absolute wall-clock ranges (05-11 / 11-16 / 17-22 / other). For users with shifted day patterns — the gluco_admin's day starts ~13:00 — these labels misrepresent the data:

- 15 "Завтрак" episodes over 14 days, when the user almost never eats before 13:00
- 9 "Обед" episodes, despite eating regular midday meals (just at 16:00)
- 26 "Перекусы" — the dump bucket where the user's main daily eating ends up

An endocrinologist reading this sees: "patient skips breakfast 13 days of 14, eats only 9 lunches, has tons of snacks." The reality is different — patient has consistent eating, just shifted. ADR-007 §2.2 introduced adaptive windows precisely for this situation; the report should use them.

**Missing data from new categorization.** ADR-007 / ADR-008 / ADR-009 added:

- `glycemic_response` per meal (gentle/moderate/spike/unstable/unknown)
- `pre_meal_state` per meal (low/in_range/high/unknown)
- `is_meal_during_low` flag (from ADR-008 follow-up)
- Predictability per repeating product (Δ stdev across same-name meals)
- Hypo time-of-day concentration

None of this reaches the doctor. The clinical value is significant: spike% by window suggests dosing issues; predictability per product informs dosing strategy; meal-during-low frequency points to basal/bolus balance problems.

The report stays one A4 page per the user's constraint. Adding sections requires compacting others.

## 2 · Decisions

### 2.1 — Replace locked meal-windows with adaptive

The meal profile table is reorganized around `derived_categories.meal_window` from ADR-007:

| Old | New | Range (user-specific, example for ~13:00 anchor) |
|---|---|---|
| Завтрак | start | 13:00–16:00 |
| Обед | mid | 16:00–21:00 |
| Ужин | late | 21:00–02:00 |
| (split into other rows) | night_cap | 02:00–07:00 |
| Перекусы | snacks | any window |

The "Перекусы" row remains as a cross-window row, but now means "small/sweet items regardless of window" (from `derived_categories.meal_role IN (snack, drink, dessert)`) — not "didn't fit elsewhere."

Window labels in the rendered PDF use the **wall-clock range derived from the user's anchor**, e.g., "Старт дня (13:00–16:00)" not "start". The doctor sees the user's real schedule, not jargon.

### 2.2 — Add response distribution per window

A new column `Отклик` next to `Сахар +2ч` shows the percentage of meals in that window with `glycemic_response = spike` (and `unstable` if it's significant). This is the clinical signal: a window with 60% spike rate has a dosing problem; one with 10% does not.

Rendered as compact mini-bars:

```
spike 38% ████░░░░░░
gent. 12% █░░░░░░░░░
```

Or numerically when bars don't fit: `S38% G12% M50%` mono.

### 2.3 — Add predictability table for top-5 products

A new section below the meal-profile table:

```
ПРЕДСКАЗУЕМОСТЬ ТОП-ПРОДУКТОВ

Продукт                              N   Δ ммоль/л   σ      Класс
Лаваш с курицей (домашний)           6   +2.0        ±0.6   стабильный
Протеиновое брауни                   7   +3.4        ±1.1   средний
Сырок глазированный                  6   +4.2        ±1.4   средний
Кусочек торта                        4   +5.1        ±1.8   нестабильный
Кола Ориджинал                       4   +0.9        ±0.4   recovery⁕
```

Computed via `aggregate_by_product` from ADR-008 §3.5 + `exclude_delayed_peaks=True` (from ADR-008 follow-up). Min 3 samples to qualify.

`Класс` is computed:
- `стабильный` if σ < 1.0 mmol/L
- `средний` if σ in [1.0, 1.5]
- `нестабильный` if σ > 1.5

Special suffix `recovery⁕` if ≥50% of the product's occurrences had `is_meal_during_low=true` — annotated with a footnote: "⁕ часто потребляется при сахаре <4 ммоль/л; средняя дельта занижена". This handles the "Cola Original Δ 0.9" misread that real-data analysis surfaced.

Showing this gives the doctor specific clinical handles: "for Лаваш с курицей, standard dosing reliable; for Кусочек торта, recommend wider buffer".

### 2.4 — Add hypo time-of-day concentration line

Single line in the glycemic-profile section, after the existing low/high percentages:

```
ГИПО (<3.9):   14 %    ·   28 эпизодов
ИЗ НИХ:   85 % в окне 19:00–07:00   ·   средняя длительность 22 мин
```

For this user: clearly surfaces the evening/overnight hypo concentration. The endo immediately sees where to focus.

### 2.5 — Add meal-during-low metric

In the meal-profile table, add a column `% при низком` showing the share of meals in that window where `pre_meal_state = low` (regardless of whether they qualify as hypo_recovery). For users like gluco_admin, this column will show ~28% in the late window, which is itself a clinical signal.

### 2.6 — Compact daily grid to fit all 14 days

The current report says "Показано 9 из 14 дней" because rows are too wide. The new grid fits all 14:

```
ПО ДНЯМ

Дата   TIR   Угл.   Инс.   Гипо <3.9   Спайки   Окно лента
─────────────────────────────────────────────────────────
28.04  78%   198    16.5   2           3        S─M═L═N─
29.04  84%   220    18.2   1           2        ─M═L═N─
30.04  72%   312    24.8   3           5        S─M═L══N
01.05  88%   165    14.1   0           1        ─M═L═
...
11.05  84%   220    18.0   1           1        S─M═L═
─────────────────────────────────────────────────────────
Медиана 80%  226    17.0   ...         ...
```

Each row: mono font, ~14px tall. 14 rows × 14px = 196px. Fits.

The `Окно лента` column is a 6-character mono visualization of which adaptive windows the user ate in that day: `S` (start), `M` (mid), `L` (late), `N` (night_cap). `═` if 2+ meals in window, `─` if 1 meal, empty if 0. Provides at-a-glance pattern recognition for the doctor.

### 2.7 — Keep insulin metrics; restructure aggregation

The doctor reads insulin per-meal because that's how dosing works. Keep:
- Median insulin per window (new windows now)
- Median observed УК per window
- Total daily insulin (median + IQR if space allows)

Drop:
- The "Сахар +2ч" stays but only as median across the window, not the special calculation-window footer (move that to a single page-footer line)

## 3 · Specifications

### 3.1 — One-page layout (A4 portrait, 595×842pt)

Stacked blocks with these target heights:

```
┌─────────────────────────────────────────────────────────┐
│ HEADER · period, days with data, CGM coverage, episodes │  40pt
├─────────────────────────────────────────────────────────┤
│ GLYCEMIC PROFILE                                        │
│ TIR · <3.9% · <3.0% · >10% · mean · CV               │  90pt
│ Hypo concentration line                                 │
├─────────────────────────────────────────────────────────┤
│ ADAPTIVE WINDOWS BANNER                                 │
│ "Day starts ~13:00 (weighted 7d); no weekend split"     │  50pt
│ [24h ribbon: S═══M══════L═══════N═══════]               │
├─────────────────────────────────────────────────────────┤
│ MEAL PROFILE BY ADAPTIVE WINDOW                         │
│ Window | N | Carb | Ins | Sugar before/+2h | УК |       │
│        Response % | Meal-during-low %                   │  170pt
│ (5 rows: start, mid, late, night_cap, snacks)          │
├─────────────────────────────────────────────────────────┤
│ PREDICTABILITY OF TOP PRODUCTS                          │
│ (5-row table)                                           │  120pt
├─────────────────────────────────────────────────────────┤
│ DAILY GRID (all 14 days, compact)                       │  240pt
├─────────────────────────────────────────────────────────┤
│ FOOTER (calc windows, sources, disclaimer)              │  30pt
└─────────────────────────────────────────────────────────┘
                                                  Total ≈ 740pt
```

A4 usable is ~770pt after 36pt top/bottom margins. Fits with 30pt headroom for spacing.

### 3.2 — Block details

#### Header (40pt)

```
glucotracker  ·  отчёт для врача                  Период: 28 апр – 11 мая 2026
                                                   14 дней · 13/14 с едой · 68 эпизодов · CGM 92%
```

Left: brand + report type. Right: period summary in two compact lines.

#### Glycemic profile (90pt)

Single row of 6 numeric KPIs, each in a hairline-bordered cell:

```
TIR 4.0-10.0    Время <3.9    Время <3.0    Время >10    Среднее    CV
   80%             14%           4.8%           6%        6.2          39%
   (target ≥70)    (target ≤4)   (target 0)     (target ≤25)  (target 3.9-7.8) (target <36)
```

Reference targets below each value in 8pt `--muted`. Helps the doctor see at a glance which metrics are off (the user's <3.9 at 14% is way above the ≤4% target — visible immediately).

Below this row, one more line:

```
Гипо <3.9:  28 эпизодов · 85% в окне 19:00–07:00 · средняя длительность 22 мин
```

#### Adaptive windows banner (50pt)

```
МОЙ РИТМ
День начинается ~13:00 (по последним 7 дням, без разделения будни/выходные)

  13:00          16:00          21:00          02:00          07:00
  ┌──────┬─────────────┬─────────────┬─────────────┐
  │ start│     mid     │    late     │   night_cap │
  └──────┴─────────────┴─────────────┴─────────────┘
```

Same ribbon as ADR-009 §2.5 "Settings — Мой ритм", scaled down. No `сейчас` marker on the report (it's not a live view). If weekend split is active, render TWO ribbons stacked, with weekend labeled.

#### Meal profile by window (170pt)

```
ОКНО (время)              N    Угл.    Инс.    Сахар    Сахар    УК      Отклик               % при
                                медиана медиана  до      +2ч              spike/unstable      низком

Старт (13:00–16:00)       12   38г     5.5Е    5.0      6.4     8.3 г/Е  S25% U8%            17%
Середина (16:00–21:00)    18   46г     5.0Е    4.4      5.7     9.3 г/Е  S22% U6%             8%
Поздно (21:00–02:00)      14   42г     5.5Е    4.6      4.5     8.6 г/Е  S50% U14%           36%
Ночь (02:00–07:00)         8   28г     3.0Е    4.2      4.8     ─        S38% U13%           50%
Перекусы (любое окно)     16   28г     2.8Е    5.0      6.7     9.6 г/Е  S31% U6%            22%

Итого / медиана           68   39г     4.0Е    4.7      6.0     9.0 г/Е
```

Row order = chronological by window (start→mid→late→night_cap), then snacks as a cross-cutting row. Total at bottom.

Three new columns vs the original report:
- `Отклик`: `S<x>% U<y>%` where S=spike, U=unstable. Other classes (gentle/moderate) are the implied remainder; explicit only when interesting.
- `% при низком`: share of meals in that window with `pre_meal_state=low`.

For this user, the late window's 36% meal-during-low and 50% spike rate are immediately visible as the most clinically interesting row.

#### Predictability of top products (120pt)

```
ПРЕДСКАЗУЕМОСТЬ ТОП-ПРОДУКТОВ

Продукт                              N      Δ           σ      Класс

Лаваш с курицей и овощами            6     +2.0 ммоль   ±0.6   стабильный
Протеиновое брауни Shagi             7     +3.4 ммоль   ±1.1   средний
Сырок глазированный ×2               6     +4.2 ммоль   ±1.4   средний
Кусочек торта                        4     +5.1 ммоль   ±1.8   нестабильный
Кола Ориджинал                       4     +0.9 ммоль   ±0.4   recovery⁕

⁕ ≥50% случаев потребления при сахаре <4 ммоль/л; средняя дельта может быть занижена
```

Top 5 products by frequency, with at least 3 meals each. If fewer than 3 products qualify, render only the qualifying rows + a note "Недостаточно повторов для большего количества продуктов."

#### Daily grid (240pt)

```
ПО ДНЯМ

Дата      TIR     Угл.   Инс.   Гипо   Спайки   Окна
28.04    78%     198г   16.5Е   2      3        S─M══L═N─
29.04    84%     220г   18.2Е   1      2        ─M══L═N─
30.04    72%     312г   24.8Е   3      5        S─M══L══N
01.05    88%     165г   14.1Е   0      1        ─M══L═
02.05    81%     287г   23.1Е   2      4        ─M═L═══N─
03.05    86%     246г   26.6Е   1      3        S─M─L══N
04.05    84%     191г   22.8Е   1      2        ─M─L═
05.05    83%     186г   17.6Е   1      2        ─M══L═N
06.05    90%      82г    8.0Е   1      0        ─M─L─
07.05    59%     190г   15.2Е   1      4        ─M══L══N
08.05    88%     373г   26.5Е   1      5        S─M═══L═══N
09.05    79%     208г   18.4Е   2      3        ─M══L══N─
10.05    82%     245г   19.7Е   1      2        S─M═L═N
11.05    84%     220г   18.0Е   1      1        ─M══L═

Медиана  80%    226г   17.0Е   1      2.5
```

Mono font 9pt. Row height ~14pt. 14 rows fit in ~200pt + header. The `Окна` column is the at-a-glance pattern viewer (already specced in §2.6).

#### Footer (30pt)

```
Окна расчёта: до еды -30…-15 мин, после еды +90…+150 мин. Инсулин получен из Nightscout (только чтение).
Наблюдаемый УК — эмпирический показатель: г углеводов на 1 ЕД meal-linked инсулина.
Отчёт информационный и не является медицинской рекомендацией.
Окна дня вычисляются адаптивно по последним 7 дням. См. «Мой ритм» в приложении для управления.
```

Three-line, 8pt `--muted`. Last line is new — explains the adaptive window methodology.

### 3.3 — Edge cases

| Situation | Render |
|---|---|
| <14 days of data | Period label shows actual range; all sections compute from available days; no padding. |
| Anchor not yet computed (<7 qualifying days) | "Мой ритм" banner reads: "Расписание ещё определяется. Используется стандартная сетка (05-11 / 11-16 / 17-22 / прочее)." Meal-profile rows fall back to original labels. |
| <3 samples for any product | Predictability table shows only qualifying products; if none, replace the table with "Недостаточно повторов для оценки." |
| CGM coverage <60% over period | Header coverage shows orange (≥60% green, 40-60% orange, <40% red). All glycemic_response values for affected meals are `unknown` and excluded from `Отклик` percentages. |
| No insulin data (no Nightscout) | Insulin and УК columns rendered as `—`. Report still useful for glycemic + categorization analysis. |
| User has weekday/weekend split | "Мой ритм" banner shows two ribbons; meal profile shows both anchors used; footer adds "Будни/выходные считаются раздельно." |
| User has manual anchor override | "Мой ритм" banner notes "(задано вручную)". No "by 7 days" caveat. |
| Non-typical period overlaps report range | Footer adds "Период включает X дней, помеченных как нетипичные; они исключены из расчёта окон." |

## 4 · Implementation tasks

One PR.

1. **Data layer.** Add to existing report-generation module: queries for response distribution per window, meal-during-low share per window, top-5 product predictability via `aggregate_by_product`. All read existing fields (`derived_categories`, `ai_categories`, `postprandial_response`); no new computation.
2. **Template restructure.** Update the HTML/CSS template (or jsPDF / WeasyPrint pipeline, whichever the current report uses) to the new block layout per §3.2. The 24h ribbon and the per-day Окна mini-strip are new visual components.
3. **Window labels.** Replace hard-coded "Завтрак / Обед / Ужин / Перекусы" with dynamically rendered "Старт (HH:MM–HH:MM)" based on user's current anchor state.
4. **Edge-case rendering.** Implement the table in §3.3. Each case is one if-branch + one alternative copy.
5. **Footer update.** Add the "Окна дня вычисляются адаптивно..." line.
6. **PDF size verification.** Generate the report for the gluco_admin's actual 14-day data; manually verify it fits one A4 page with no overflow. Iterate font sizes / cell padding if needed.
7. **Tests:**
   - Snapshot: report HTML for a fixture user with the same shape as the gluco_admin's data — content matches expected blocks.
   - Edge case: report for a user with no Nightscout — insulin columns render `—`, no crash.
   - Edge case: report for a user with <7 days — fallback labels appear, no anchor banner contradictions.
   - Visual: open the generated PDF, confirm single page.

## 5 · Section overrides

- Replaces the locked-window logic in the current `reports/endocrinologist.py` (or equivalent). All hard-coded time ranges for meal classification are removed; the module now reads `derived_categories.meal_window` from the meal records.
- Adds dependency on ADR-007's `users.day_anchor_*` fields, ADR-008's `postprandial_response`, ADR-008-followup's `is_meal_during_low`.
- The "Calculation windows" footer line existed in the original; it stays but is consolidated into the unified footer per §3.2.

## 6 · Acceptance

- **Single page.** Generated PDF for the gluco_admin's actual 14-day period fits one A4 page (595×842pt) with all sections visible and no content overflow.
- **Adaptive labels.** "Завтрак / Обед / Ужин" labels are gone; replaced by "Старт (HH:MM–HH:MM)" reflecting the user's anchor. For a user with 13:00 anchor, the breakfast row reads "Старт (13:00–16:00)" not "Завтрак".
- **All 14 days visible.** The daily grid shows all 14 days (or however many days the period covers), not just 9 of 14.
- **Response distribution present.** Each window row has a non-empty `Отклик` cell showing spike% and (when relevant) unstable%.
- **Predictability section populated.** For the gluco_admin's data, at least 4 products from the top-5 by frequency qualify (Лаваш, Брауни, Сырок, Кусочек торта all have ≥4 samples). The recovery footnote appears for Кола Ориджинал (if ADR-008-followup is shipped and the data confirms ≥50% при низком).
- **Hypo concentration visible.** The "Гипо <3.9 ... 85% в окне 19:00–07:00" line is present and the percentage is computed from CGM data, not hard-coded.
- **Footer notes adaptive windows.** Last line of footer explains the methodology with a forward reference to "Мой ритм".
- **Fallback behavior.** A test user with 5 days of data and no anchor yet generates a report using absolute windows with a banner indicating "Расписание ещё определяется."

## 7 · Out-of-band asks

1. **PDF generation pipeline.** §4.2 says "HTML/CSS or jsPDF or WeasyPrint, whichever the current report uses". Identify the current toolchain. Default if delegated: keep it; just update the template.
2. **Localization of window names.** §2.1 uses "Старт / Середина / Поздно / Ночь" as Russian-friendly labels. Confirm or revise. Default if delegated: ship as written; revise if the user finds them awkward.
3. **Response % display: bars vs numbers.** §2.2 offers both. The mockups in §3.2 use numbers (`S38% U13%`). Confirm the choice; bars are visually cleaner but take more horizontal space. Default: numbers.
4. **Per-product predictability sample threshold.** §2.3 uses ≥3. Some products have only 2 instances in 14 days; raising threshold to 5 reduces the table. Default: 3 — informative even if low-confidence.
5. **Inclusion of weekly vs full-period.** Currently report shows full 14-day medians. For longer reports (30-day, 90-day), a "by week" breakdown might be useful. Out of scope for this redesign; revisit if the user requests longer periods.
6. **What about delayed_peak_likely meals?** Per ADR-008-followup, fat-heavy meals get this flag and are excluded from "lowest response" aggregations. For the predictability table specifically, they should also be excluded (predictability requires the peak to be visible in the analysis window). Confirm. Default: exclude them via the same `exclude_delayed_peaks=True` parameter.
