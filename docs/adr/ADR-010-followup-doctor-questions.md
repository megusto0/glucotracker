# ADR-010 follow-up · Doctor-facing labels, ranges, and readability

> Patch to ADR-010 after seeing the first generated PDF against the actual clinical workflow. ADR-010 reorganized the data correctly but lost the doctor's question-mapping. This is a focused revision; the adaptive-window machinery underneath stays, only the surface presentation changes.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-11 |
| Affects | `reports/endocrinologist.py` template and renderer; gluco flavor only |
| Risk | Low — pure rendering changes, no schema or computation changes |

---

## Context — what the rendered PDF revealed

ADR-010 swapped doctor-familiar labels (`Завтрак / Обед / Ужин / Перекусы`) for technically-accurate adaptive ones (`1-й прием / дневные / вечерние / поздние ночные`). The accuracy is real — those windows correctly reflect what the patient eats and when — but the cost is that the doctor's standard questions no longer have a direct row to point at:

- "Сколько инсулина на завтрак?" — she's looking for a row called «Завтрак», not «1-й прием».
- "Какой сахар до завтрака?" — same.
- "Каков разброс доз?" — current report shows only medians, no range.

Additionally, three blocks in the rendered output don't earn their space relative to her workflow:

- **«Предсказуемость топ-продуктов»** is interesting analytically but is never something she asks about. ~120pt of vertical space.
- **«Отклик» column** renders as `S42% U8% M42%` with no legend. She doesn't know what S/U/M mean without an explanation that isn't in the PDF. Adds clutter, returns nothing.
- **Anchor displayed as `03:32`** is false precision. The algorithm computes in minutes, but a doctor reading "day starts at 03:32" is going to either disbelieve the data or get distracted by the oddity.

Finally, one issue is visible but **out of scope for this patch**: the auto-computed anchor of 03:32 itself. The "≥6h eating gap → first meal of day" heuristic from ADR-007 §3.5 misclassifies the patient's late-night snacks (05-07h cluster, often after a 7h gap from a 23h dinner) as next-day breakfast. The right semantic answer is "patient's day starts ~13:00", but the algorithm has no way to distinguish a long sleep break from a long late-meal-to-late-meal gap. Recommended workaround: set manual override in Settings. Algorithmic fix in §7.

## Fixes

### Fix 1 — Standard meal labels, adaptive timing in subtitle

The meal-profile table reverts to her familiar labels:

| New label | Maps to (adaptive) | Subtitle |
|---|---|---|
| `Завтрак` | `start` window | `(HH:MM–HH:MM)` actual range |
| `Обед` | `mid` window | `(HH:MM–HH:MM)` |
| `Ужин` | `late` window | `(HH:MM–HH:MM)` |
| `Поздний приём` | `night_cap` window | `(HH:MM–HH:MM)` |
| `Перекусы (все окна)` | `meal_role IN (snack, drink, dessert)` cross-window | (no time range; spans all windows) |

The label is the role; the parenthetical subtitle is the wall-clock range computed from the user's anchor. Example for a 13:00-anchor user:

```
Завтрак (13:00–16:00)
Обед (16:00–21:00)
Ужин (21:00–02:00)
Поздний приём (02:00–07:00)
Перекусы (все окна)
```

For a conventional 7:00-anchor user, the same labels render as `Завтрак (07:00–10:00)`, `Обед (10:00–15:00)`, etc. The doctor reads the same structure every time, regardless of patient.

If the auto-anchor is clearly off (see Context section about the 03:32 case), the patient can use the existing manual override from ADR-007 §2.2.d to force a sensible value.

### Fix 2 — Display times rounded to nearest hour

The internal anchor (`users.day_anchor_weekday_minutes`) keeps minute-level precision for accurate window classification. Display rounds to the nearest full hour:

```python
def display_hour_rounded(minutes_from_midnight: int) -> str:
    rounded_hour = round(minutes_from_midnight / 60) % 24
    return f"{rounded_hour:02d}:00"
```

`03:32` → `04:00`. `13:18` → `13:00`. `13:31` → `14:00`. Internal computations remain minute-precise; only the rendered PDF shows hourly.

Applies to:
- The «Мой ритм» banner: `День начинается ~04:00` (not `03:32`).
- The 24h ribbon labels: `04:00 / 07:00 / 12:00 / 17:00 / 04:00`.
- Each meal-profile row's subtitle: `(04:00–07:00)`.
- The daily grid's any time references.

Window endpoints are rounded individually — they tile without gaps because each window starts where the previous ended (rounded values pass through).

### Fix 3 — Median (range) in every numeric cell

The most important change for answering her standard questions. Each cell that currently shows a median now shows median with min-max range in parentheses:

**Before (current ADR-010 output):**
```
Окно                    N    Угл.   Инс.   До    +2ч   УК
Завтрак (04:00-07:00)   18   37     5,0    4,8   6,7   8,5
```

**After:**
```
Окно                    N    Углеводы          Инсулин        Сахар до       Сахар +2ч       УК
Завтрак (04:00-07:00)   18   37 (12-78)        5,0 (1,8-9,4)  4,8 (3,3-7,1)  6,7 (4,2-9,8)   8,5
```

This directly answers "сколько инсулина на завтрак?" — `5,0 (1,8-9,4)` says "typically 5 units, but ranges from 1.8 to 9.4 across the period." She reads both the typical dose and the spread in one glance.

The range format is `median (min-max)`. Computed on the actual values for that window over the period; no filtering. Rendered space-separated, with hairspace before parenthesis. If only one episode in the window, render as `5,0` (no parens — there's no range with N=1).

For the «Итого / медиана» row at the bottom, render the **daily totals**:
```
Итого / медиана (день)  68   226 (82-373)      17 (8-47)      ...
```

Daily totals show insulin total per day and carbs total per day with their range. This answers "сколько инсулина в день, и какой разброс?" directly.

### Fix 4 — Drop the «Предсказуемость» section and the «Отклик» column

Both are removed from the report. Recovered vertical space ~150pt is redistributed:

- The meal-profile table gets a bit more breathing room per row (rows go from 14pt to 17pt for readability with the new wider cells).
- The daily grid can use slightly wider columns for the same data.

The data isn't deleted from the system (it still lives in `postprandial_response` and `ai_categories`); it just doesn't appear in the doctor's report. Future surfaces (Stats screen, in-app insights) still use it per ADR-009.

If a doctor asks about predictability in the future, it can come back; for now, optimize for her actual questions.

### Fix 5 — Daily-grid window column uses readable counters

The current column rendering shows characters like `1ДВPН` which is the result of box-drawing-character font fallback. Even if the font supported them, the encoding is opaque without a legend.

New format: per-window meal counters with single-letter prefix.

```
Дата       TIR    Угл.       Инс.       Гипо   Спайки   Окна
28.04      78%    198 г      16,5 ЕД    2      3        З:1 О:0 У:2 П:3
29.04      84%    220 г      18,2 ЕД    1      2        З:1 О:1 У:2 П:2
03.05      86%    246 г      26,6 ЕД    1      3        З:2 О:0 У:3 П:1
```

Letters: `З` Завтрак, `О` Обед, `У` Ужин, `П` Поздний приём. Counts how many meals fell in each window that day. Zero counts shown explicitly (e.g., `О:0`) — gives the doctor visibility into days the patient skipped a meal type.

This format renders reliably in any monospace font, is self-documenting (the letters match the meal-profile labels above), and packs the same information as a glyph strip without the legend problem.

Daily grid column widths after this fix:

| Col | Width |
|---|---|
| Дата | 50pt |
| TIR | 40pt |
| Угл. | 50pt |
| Инс. | 50pt |
| Гипо | 30pt |
| Спайки | 40pt |
| Окна | 130pt |

Fits within the page width with margin.

### Fix 6 — «Спайки» column stays, with explicit definition in footer

The spike count per day remains in the daily grid (it IS useful for the doctor — high-spike days are dosing-relevant). But "spike" needs a definition somewhere. Add to footer:

```
«Спайки» — приёмы пищи с подъёмом глюкозы ≥4 ммоль/л на пике в течение
180 минут после еды.
```

One line, 8pt. Defines what she's reading.

## Specifications

### Layout heights after the fixes (recap, A4 portrait 595×842pt usable ~770pt)

```
┌─────────────────────────────────────────────────────────┐
│ HEADER                                                  │  40pt
├─────────────────────────────────────────────────────────┤
│ GLYCEMIC PROFILE (6 KPIs + hypo line)                   │  90pt
├─────────────────────────────────────────────────────────┤
│ МОЙ РИТМ (banner + ribbon, hour-rounded)                │  50pt
├─────────────────────────────────────────────────────────┤
│ ПРОФИЛЬ ПРИЁМОВ ПИЩИ                                    │
│ (Завтрак / Обед / Ужин / Поздний приём / Перекусы +    │  220pt
│  total daily row), each with median (range)             │
├─────────────────────────────────────────────────────────┤
│ ПО ДНЯМ (14 rows, new Окна column З:N О:N У:N П:N)     │  280pt
├─────────────────────────────────────────────────────────┤
│ FOOTER (calc windows + spike definition + sources)      │  50pt
└─────────────────────────────────────────────────────────┘
                                                  Total ≈ 730pt
```

Single A4 page, ~40pt headroom for spacing.

### Footer (now 3-4 lines)

```
Окна расчёта: до еды -30…-15 мин, после еды +90…+150 мин.
«Спайки» — приёмы с подъёмом глюкозы ≥4 ммоль/л на пике в течение 180 минут.
Окна дня (Завтрак/Обед/Ужин/Поздний приём) построены адаптивно по последним 7 дням
ритма пациента. Если расписание определено некорректно — поправь в «Мой ритм».
Инсулин получен из Nightscout (только чтение). Наблюдаемый УК = г углеводов на 1 ЕД
meal-linked инсулина. Отчёт информационный и не является медицинской рекомендацией.
```

Five short lines, 8pt. Includes the manual-override pointer for cases like the 03:32 misclassification.

## Implementation tasks

One PR.

1. **Template:** swap row labels from adaptive names to `Завтрак / Обед / Ужин / Поздний приём / Перекусы (все окна)`. Subtitles use `display_hour_rounded` on the window's start and end. The mapping function `adaptive_window_to_doctor_label(meal_window)` is one-liner.
2. **Numeric cells:** every "median" cell in the meal-profile table now renders `median (min-max)`. Use `format_with_range(values: list[float], decimals: int) -> str`. Skip the range when `len(values) ≤ 1`.
3. **Total row:** the bottom row uses daily aggregates (total insulin per day, total carbs per day) with their ranges, not per-meal medians.
4. **Drop sections:** remove «Предсказуемость топ-продуктов» block. Remove «Отклик» column from the meal-profile table.
5. **Daily-grid Окна column:** new renderer `format_daily_windows(meals_by_window: dict) -> str` producing `З:N О:N У:N П:N`. Replace existing column.
6. **Footer:** add the «Спайки» definition line. Add the «Если расписание определено некорректно» line with reference to in-app «Мой ритм».
7. **Round display times:** `display_hour_rounded` function applied to every wall-clock time in the rendered output (anchor banner, ribbon labels, meal-profile subtitles).
8. **Page-size check:** generate against gluco_admin's actual data; verify it stays one page. If overflow, reduce row height in daily grid first (14pt → 13pt); avoid shrinking font below 9pt anywhere.
9. **Tests:**
   - Snapshot: report for the same fixture as ADR-010's snapshot test. Verify labels are now `Завтрак` etc., subtitles are rounded times, ranges appear in cells.
   - Edge case: a window with only 1 meal renders insulin as `5,0` (no range parens).
   - Edge case: a window with 0 meals renders `—` for all numeric columns.
   - Edge case: daily windows column for a day with 0 of one type renders `З:0` explicitly, not blank.

## Acceptance

- **Doctor's questions answer directly.** Standard rows for breakfast/lunch/dinner exist with these exact labels. Each numeric cell shows median + range. Can answer "сколько инсулина на завтрак?" with one cell lookup: `5,0 (1,8-9,4)`.
- **No `03:32`-style times in rendered PDF.** All wall-clock times in the output end with `:00`.
- **No `S<x>% U<y>% M<z>%` strings anywhere.** «Отклик» column is gone.
- **No «Предсказуемость» block.** Section is absent.
- **Daily grid renders all 14 days with readable Окна column** in the format `З:N О:N У:N П:N`. No box-drawing or substituted glyphs.
- **Footer explains «Спайки» and mentions adaptive windows** with a pointer to in-app Мой ритм for manual correction.
- **Single A4 page** for gluco_admin's actual 14-day data. No overflow.

## Section overrides

- Overrides ADR-010 §2.1 meal label mapping table. The mapping inverts: standard labels are the primary surface; adaptive technical names live underneath only in code.
- Overrides ADR-010 §2.2 (drops the «Отклик» column).
- Overrides ADR-010 §2.3 (drops the predictability section).
- Overrides ADR-010 §2.6 daily-grid Окна column format.
- Updates ADR-010 §3.2 layout heights and §3.3 footer content.

## Out-of-band asks (for later, not blocking this patch)

1. **Anchor algorithm robustness against shifted-day eaters.** The rendered report shows anchor=03:32, semantically wrong. This is the ADR-007 §3.5 «first meal after ≥6h gap» heuristic firing on a late-night-to-morning gap in the user's all-day eating pattern. Proposed fix in a future ADR: combine the eating-gap signal with a glucose-stability signal (sleep ≈ time with no eating AND low glucose variability) to better identify true sleep windows. Out of scope here; for now, manual override is the workaround.

2. **Restore predictability section if doctor asks for it.** §2.3 is removed but the underlying data still computes. If the doctor in a future visit asks about per-food predictability, the section can come back as a configurable option, not default-on.

3. **Add a 30-day or 90-day report variant.** Current report is 14-day; for longer periods, the daily-grid section won't fit (30 rows × 14pt = 420pt is too much). A longer-period variant might switch to a weekly-aggregate grid instead. Out of scope.

4. **Show anchor manual override in the report itself.** Currently the footer says «поправь в Мой ритм», but doesn't indicate whether the current anchor IS a manual override. Add a small `(задано вручную)` flag next to the anchor time when override is active. Minor UX polish.

5. **Display the median sleep duration / largest eating gap.** As a sanity check for the anchor calculation, it might help the doctor to see «patient typically has a 5-hour eating gap from 07:00 to 12:00» — clarifying whether the auto-detected anchor reflects reality. Could go in the «Мой ритм» banner.
