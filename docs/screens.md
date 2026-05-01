# Screens

Last updated: 2026-04-29

Glucotracker is a personal food diary for a type-1 diabetic. The desktop app has five screens accessible from the left sidebar. Every screen communicates with the backend through REST; the frontend owns presentation only.

## Navigation

Left sidebar, 192px wide. Icons from Lucide. Items:

| Route      | Label        | Icon       |
|------------|--------------|------------|
| `/`        | Журнал       | SquarePen  |
| `/feed`    | История      | List       |
| `/stats`   | Статистика   | BarChart3  |
| `/database`| База         | Database   |
| `/settings`| Настройки    | Settings   |

Active item: left border accent, slightly lighter background.

---

## Журнал (`/`, ChatPage)

The main screen. It is not a chat messenger. It is a daily food ledger with a bottom input area.

The selected day is part of the creation context. If the user is viewing an
older day and adds a manual meal or a photo meal, the new meal belongs to that
selected day with the current local time. This supports backfilling old days.
If the user meant today, they can change the meal date/time in the right panel.

### Layout

- Left: selected day's meal ledger rows, scrolling vertically.
- Right: contextual panel (420px) opens when a meal row is selected.

### Meal rows

Each row shows:

| Column        | Content                                   |
|---------------|-------------------------------------------|
| Time          | HH:MM, monospace                          |
| Thumbnail     | 44x44 photo or placeholder                |
| Title         | Meal name or item names joined by `+`     |
| Subtitle      | Source, status, quantity badge, NS badge  |
| Dotted line   | Visual separator                          |
| Carbs         | Number + `У`                              |
| Protein       | Number + `Б`                              |
| Fat           | Number + `Ж`                              |
| Kcal          | Number + `ккал`                           |
| Chevron       | MoreVertical icon                         |

### Bottom input area

User can type food names. Prefix triggers autocomplete:

- `bk:` — Burger King patterns
- `mc:` — McDonald's patterns
- Plain text — product and pattern search

Selected items become chips with quantity. User can also paste or drag photos.

Manual entries, autocomplete entries, and photo drafts use the currently
selected journal day. Do not force them to today unless the UI first changes the
selected day to today.

### Photo flow

1. User pastes/drops/uploads one or more photos.
2. Photos are uploaded to `POST /meals/{id}/photos`.
3. Backend calls Gemini, normalizes response, creates draft items.
4. Draft appears in the right panel with evidence, assumptions, confidence, warnings.
5. User reviews, edits items, accepts or discards.

### Right panel (SelectedMealPanel)

Shows when a meal row is selected:

- Photo thumbnail, title, source/status tags
- Name edit form
- Date and time edit form
- Quantity section (if multi-unit)
- Current weight edit form for one-item meals with known grams
- Repeat by weight form, backed by `POST /meal_items/{id}/copy_by_weight`
- Quick repeat action for one recognized unit/package when evidence provides
  count and unit weight, e.g. `Добавить 1 упаковку · 20 г` for `3 × 20 г`
- Macro breakdown: carbs, protein, fat, fiber
- Source and confidence
- Nightscout sync status
- Component breakdown (if photo-estimated with known components)
- Assumptions list
- Evidence data
- Per-unit and total nutrition comparison
- Re-estimate controls (model selection, comparison panel)
- Product memory (remember label-calculated items)
- Action buttons: save, discard, duplicate, delete

### Nightscout day bar

When Nightscout is configured, a status bar at the top shows today's sync state. User can sync the current day to Nightscout.

---

## История (`/feed`, FeedPage)

A chronological stream of all food events, automatically grouped into **food episodes** when meals and insulin happen close together.

### Purpose

The history page answers: "What did I eat, and how did my glucose react?" It combines three data sources into a unified timeline:

1. **Meals** — all accepted meal rows from the local diary.
2. **Nightscout insulin** — read-only insulin events imported from Nightscout.
3. **Nightscout CGM** — glucose readings imported from Nightscout, shown as mini-charts.

### Event stream

The page loads meals via cursor-based pagination (`GET /meals` with `to` cursor). Nightscout context is imported on load via `POST /nightscout/import` and read via `GET /timeline`.

All events are merged and sorted by timestamp, then grouped into day sections:

```
понедельник, 28 апреля 2026
  [Food Episode 12:00–14:30]
  [Standalone meal 18:00]
  [Ungrouped insulin 22:15]
вторник, 29 апреля 2026
  ...
```

### Day headers

Sticky, full-width rows with the date in 40px font. They stay visible while scrolling through that day's events.

### Filters

Four controls at the top:

| Filter   | Type     | Options                                     |
|----------|----------|---------------------------------------------|
| Поиск    | Text     | Free text search across food names, notes   |
| От       | Date     | Start date filter                           |
| До       | Date     | End date filter                             |
| Статус   | Dropdown | активные, принятые, черновики, отмененные   |

### Food episodes

When the backend detects that meals, insulin, and glucose readings cluster within a time window (meals within 30 minutes of each other), it creates a **food episode** — a computed grouping, not a persisted entity.

An episode card contains:

**Header section** (two-column: info left, glucose chart right):

| Left side                        | Right side (260px)                     |
|----------------------------------|----------------------------------------|
| Start/end time (HH:MM, mono)    | "Глюкоза (CGM)" label + min-max range  |
| "Пищевой эпизод" title           | Mini glucose chart                     |
| Event count, kcal, carbs total   |                                        |

**Mini glucose chart** (`MiniGlucoseChart`):

- SVG, 80px tall, fits the 260px right column.
- X-axis: real time scale (not index-based). Shows time ticks at regular intervals.
- Y-axis: min/max glucose values (mmol/L) on the left.
- Curve: polyline of all CGM points in the episode window (60 min before first meal through 180 min after last).
- Food markers: orange dots placed **on the curve** at each meal's `eaten_at` time, using linear interpolation between CGM points. Meal times shown as labels below the X-axis.
- The chart is compact by design — enough to see the glucose response shape and where food landed.

**Inner rows** (below header):

Each meal in the episode shows as a clickable row: time, title, source badge, carbs, kcal. Clicking opens the right detail panel.

Insulin events from Nightscout show as read-only rows: time, "Инсулин из Nightscout", units.

### Standalone meals

Meals not grouped into an episode render as regular `MealRow` components (same as on the Журнал page): time, thumbnail, title, macros, source/status.

### Ungrouped insulin

Nightscout insulin events not linked to any food episode show as simple rows with time, label, and units.

### Right panel

Same `SelectedMealPanel` as on the Журнал page. Opens when any meal row or episode meal line is clicked. Allows editing name, date/time, weight, repeating by weight, duplicating, and syncing to Nightscout.

### Infinite scroll

A sentinel element at the bottom triggers `fetchNextPage()` via `IntersectionObserver`. A "Загрузить ещё" button is shown as fallback.

---

## Статистика (`/stats`, StatsPage)

Dashboard with aggregate metrics. Read-only display of backend-computed data.

### KPI row

Four tiles across the top:

| KPI                    | Value           | Comparison                    |
|------------------------|-----------------|-------------------------------|
| Углеводы сегодня       | Total carbs (g) | Week average                  |
| Ккал сегодня           | Total kcal      | Week average                  |
| Записей сегодня        | Meal count      | Label text                    |
| Часов с последней еды  | Hours           | "последняя запись есть/нет"   |

### 30-day carbs chart

Bar chart, 900x260 viewBox. Each bar = one day's total carbs. First and last dates labeled on X-axis.

### Heatmap

7 rows (days of week: пн–вс) × 24 columns (hours). Cell opacity proportional to average carbs. Hours 0, 6, 12, 18, 23 labeled on top.

### Frequent patterns (7 days)

Table: pattern display name, token, usage count.

### Source breakdown (7 days)

Table: source kind label, count, percentage.

### Data quality (7 days)

2-column grid: counts for exact label, assumed label, restaurant DB, product DB, pattern, photo estimate, manual, low confidence. Below: list of low-confidence items with name and confidence score.

---

## База (`/database`, DatabasePage)

Product, pattern, and restaurant item management. CRUD for the autocomplete source.

### Layout

- Left: filterable item grid.
- Right: detail/edit panel (420px).

### Filters

Source filter (BK, MC, Rostic's, etc.) and type filter (patterns, products, restaurants, needs review, verified, missing image, missing nutrition).

### Item rows

Each row shows: thumbnail, name, source badge, macros per serving, review status.

### Right panel

- Detail view with all nutrition fields, aliases, image.
- Import form (paste URL for JSON import).
- Manual create form.
- Edit/delete actions.

---

## Настройки (`/settings`, SettingsPage)

Backend connection and Nightscout configuration.

### Backend connection

- Base URL input
- Bearer token input
- Connection test button (calls `GET /health`)
- OpenAPI link
- "Recalculate totals" button (admin endpoint)

### Nightscout

- Nightscout URL input
- API secret input
- Test connection button
- Sync toggles: glucose import, insulin import
- "Sync today to Nightscout" button

### Reports and export

- `Отчёт для врача`: date range inputs and A4 endocrinologist PDF generation.
- `Экспорт еды`: `Создать TXT по всей еде` exports all accepted meal days with
  rows, item details, macros, daily totals, and period totals.

### UI settings

- Clear local UI preferences

---

## Design principles

- Desktop-first, 1440×900 target.
- Off-white background `#F6F4EE`, black text `#0A0A0A`.
- No shadows, gradients, glassmorphism, or dark theme.
- Mono numbers for macros/kcal. Inter for text.
- Squared cards (0–4px radius), thin `--hairline` borders.
- Motion: 180–250ms ease-out, fade/shift only. No glow or blur.

See `docs/DESIGN.md` and `docs/design-tokens.md` for full visual system.

## Shared frontend modules

Several modules are shared across pages to avoid duplication:

### `features/meals/useMealMutations.ts`

Shared React Query mutations used by both Журнал and История:

| Hook | Purpose |
|------|---------|
| `useUpdateMealTime()` | Change `eaten_at` on a meal, invalidates meals/feed/dashboard |
| `useUpdateMealName()` | Rename meal + item + product (if label-derived), invalidates meals/feed/dashboard/autocomplete/database |
| `useDuplicateMeal()` | Clone a meal with current timestamp, status `accepted` |

### `features/meals/MealLedger.tsx`

Shared UI components exported to multiple pages:

| Export | Used by |
|--------|---------|
| `MealRow` | Журнал, История |
| `RightPanel` | Журнал, История, База |
| `SelectedMealPanel` | Журнал, История |
| `EmptyLog` | Журнал, История |
| `mealTitle`, `numberLabel`, `readableSource`, etc. | Журнал, История, База |

### `features/nightscout/useNightscout.ts`

Nightscout hooks shared across Журнал, История, Настройки.

### `api/client.ts`

Single typed API client wrapping all endpoints. Uses Tauri fetch when running in desktop, browser fetch otherwise.

### `api/queryKeys.ts`

Centralized React Query key factory. All hooks use keys from this module to ensure cache invalidation works across pages.
