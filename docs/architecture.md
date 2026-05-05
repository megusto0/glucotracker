# Architecture

Last updated: 2026-05-05

## Repository Layout

- `backend/` - FastAPI backend, SQLAlchemy models, Alembic migrations,
  application services, Gemini integration, Nightscout integration, tests.
- `desktop/` - Tauri 2 desktop client, React UI, TypeScript API client, local
  file save flows.
- `mockup/` and `mockup-prototype/` - historical redesign source material. They
  are references, not current product docs.
- `docs/` - current working documentation plus `docs/archive/` for stale
  references.

## Backend Layers

Backend is the product authority.

- `glucotracker/main.py` registers the FastAPI app and routers.
- `api/routers/` exposes REST resources.
- `application/` coordinates use cases such as photo estimation, drafts,
  Nightscout, glucose dashboard, reports, and daily totals.
- `domain/` contains deterministic business rules.
- `infra/db/` contains SQLAlchemy models, session helpers, seed data, and
  database utilities.
- `infra/gemini/` owns Gemini prompts/client integration.

Do not move product math into the desktop client.

## Database Session Note

`backend/glucotracker/infra/db/session.py::get_session` is an async FastAPI
dependency that yields a sync SQLAlchemy `Session`. This is intentional: cleanup
must not depend on an available worker thread, otherwise a burst of sync
endpoints can starve the SQLAlchemy QueuePool.

## Desktop Layers

- `desktop/src/app/routes.tsx` defines page routes.
- `desktop/src/app/Shell.tsx` applies theme and renders the sidebar plus main
  scroll area.
- `desktop/src/App.css` is the main token and component stylesheet.
- `desktop/src/api/client.ts` is the hand-written API wrapper over generated
  OpenAPI types.
- `desktop/src/features/*` owns page-level behavior.
- `desktop/src/components/*` contains reusable shell primitives.
- `desktop/src/design/primitives/Button.tsx` is the compact button primitive
  used by newer screens.

The UI is allowed to derive view-only aggregates for chart rendering, but final
nutrition totals and accepted meal math must come from backend responses.

## Data Ownership

Backend owns:

- accepted meal totals
- daily totals
- calorie balance and TDEE context
- product/label math
- report aggregation
- Nightscout import and read-only insulin/CGM context
- glucose dashboard data

Frontend owns:

- selected date/range
- panel open/closed state
- hover/selection state
- formatting and visual fallback for missing data
- local file dialogs for PDF/TXT export

## Local Runtime Data

Local databases, photos, product images, and Nightscout repair dumps live under
runtime data directories such as `backend/data/` or `desktop/data/`. They are
ignored by git and must not be committed.

## Medical Safety Boundary

The app can show observed context, e.g. carbs, CGM, insulin event history, TIR,
and observed ratios. It must not recommend insulin, corrections, boluses,
treatment changes, or medical decisions.
