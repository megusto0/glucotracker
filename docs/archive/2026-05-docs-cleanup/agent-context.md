# Agent Context

Last updated: 2026-05-05

This is the short orientation note for future agents. The current source of
truth for product and UI work is:

- `docs/architecture.md`
- `docs/screens.md`
- `docs/ux.md`
- `docs/UI_RULEBOOK.md`
- `docs/testing.md`

Older contracts, screenshots, generated OpenAPI dumps, PDF samples, and
prototype-era notes live under `docs/archive/2026-05-redesign/`.

## Product

Glucotracker is a personal food diary and glucose context tool for a person with
type 1 diabetes. It logs food, photos, macros, calories, local products,
patterns, CGM context, read-only insulin events from Nightscout, activity/TDEE
context, statistics, and export/report artifacts.

It is informational only. Never add insulin dose recommendations, bolus advice,
correction advice, treatment decisions, or medical conclusions.

## Current Architecture Rule

The backend owns product semantics. The desktop app is a client.

Backend owns:

- database schema and migrations
- REST API semantics and OpenAPI-generated types
- Gemini photo estimation and normalization
- product memory, known components, autocomplete, and label math
- accepted meal totals, daily totals, calorie balance, reports
- Nightscout sync/import and read-only food episode projection
- glucose dashboard data, sensor sessions, fingersticks, and display-only CGM
  normalization

Frontend owns:

- Tauri/React shell and page layout
- editorial UI hierarchy and responsive rendering
- local interaction state
- API calls through `desktop/src/api/client.ts`
- formatting for display only

The frontend must not recalculate accepted nutrition totals or mutate SQLite
directly.

## Stack

- Backend: Python 3.12-compatible, FastAPI, SQLAlchemy 2, Alembic, SQLite.
- Desktop: Tauri 2, React, TypeScript, Tailwind, TanStack Query, Zustand.
- AI: Gemini through backend only.
- Reports: backend aggregates data; desktop renders/saves PDF/TXT.

## Recent Global UI Redesign

The active desktop UI is the warm editorial redesign, not the old generic
dashboard. Key files:

- `desktop/src/App.css` - design tokens, shell, buttons, cards, journal rows.
- `desktop/src/app/Shell.tsx` - app shell and theme application.
- `desktop/src/components/Sidebar.tsx` - fixed left nav and mini glucose widget.
- `desktop/src/design/primitives/Button.tsx` - compact button primitive.
- `desktop/src/features/chat/ChatPage.tsx` - Journal.
- `desktop/src/features/feed/FeedPage.tsx` - History.
- `desktop/src/features/glucose/GlucosePage.tsx` - Glucose dashboard.
- `desktop/src/features/stats/StatsPage.tsx` - Stats.
- `desktop/src/features/database/DatabasePage.tsx` - Product DB.
- `desktop/src/features/settings/SettingsPage.tsx` - Settings and exports.
- `desktop/src/utils/nutritionFormat.ts` - safe display number formatting.

## Safety And Data Invariants

- Unknown optional nutrients are `null`, not `0`.
- Raw Nightscout CGM is immutable. Normalized CGM is display-only.
- Nightscout insulin is read-only context. Do not create editable insulin
  treatments in Glucotracker.
- Food episodes are projections over accepted meals, CGM, and read-only insulin
  events. Do not merge or replace meals to build History.
- Local wall-clock meal times must not shift through UTC conversion.
- Editing `eaten_at` must recalculate totals for both old and new days through
  backend mutations.
- Repeat-by-weight sends grams to backend. Backend scales macros.
- Sodium/caffeine must not be visually guessed from plated food.
- Activity/TDEE and calorie balance are context, not medical guidance.

## Current UI Data Rules

- kcal: integer.
- grams: integer or one decimal.
- mmol/L: one decimal.
- kg: two decimals with comma in Russian UI.
- percentages: integer.
- Never show floating point artifacts.
- Stats calorie deficit/profit excludes the current incomplete day.
- Stats charts must degrade gracefully with sparse or missing real data.

## Important Commands

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Desktop:

```powershell
cd desktop
npm test -- --run
npm run build
```

Tauri:

```powershell
cd desktop\src-tauri
cargo check
```

OpenAPI types:

```powershell
cd backend
.\scripts\export-openapi.sh
cd ..\desktop
npm run api:types
```
