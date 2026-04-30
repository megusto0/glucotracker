# Architecture

Glucotracker is a personal food diary for logging meals and nutrition data for a type-1 diabetic. The application is informational only and is not used for insulin dosing.

## Fixed Stack Decisions

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, and SQLite.
- Database portability: SQLite is the first storage target, but database access must stay behind SQLAlchemy patterns so the schema can move to Postgres later without rewriting application code.
- Backend deployment: Docker Compose on an Ubuntu server.
- Desktop client: Tauri 2 with React, TypeScript, and Tailwind in the webview.
- Future Android client: a separate Kotlin/Compose app that consumes the same backend API.
- API style: REST over JSON with no desktop-specific assumptions.
- Auth: one bearer token supplied by the user through `.env`; no OAuth and no users table.
- Gemini API keys live only on the backend.
- Nightscout settings live only on the backend.

## Critical Architectural Rule

The frontend is replaceable. The backend, database schema, and API semantics must not depend on generated desktop UI code. If the Tauri frontend is deleted and rebuilt, the backend should continue to serve the same REST + JSON contract and generated OpenAPI types.

## Folder Rationale

### `backend/glucotracker/api`

REST route modules, schemas, dependencies, and OpenAPI helpers live here. Endpoints should return JSON and should remain client-neutral so the desktop and future Android clients can use the same API.

### `backend/glucotracker/api/routers`

FastAPI routers are grouped here by resource. Routers should describe HTTP boundaries, validate request/response semantics, and delegate orchestration to application services and deterministic rules to domain services.

### `backend/glucotracker/application`

Application services live here. This layer coordinates use cases such as photo estimation, draft creation, product memory, daily-total recalculation, and Nightscout sync. Application services may compose domain rules and infrastructure adapters, while keeping routers thin and client-neutral.

### `backend/glucotracker/domain`

Domain entities and services belong here. This layer should describe food diary concepts and deterministic rules without depending on FastAPI, SQLite, Tauri, or external service SDKs.

### `backend/glucotracker/infra/db`

SQLAlchemy engine, session, metadata, and model mapping code belongs here. Database work should use SQLAlchemy 2.0 APIs instead of SQLite-specific shortcuts so a later Postgres migration remains straightforward.

### `backend/glucotracker/infra/gemini`

Gemini integration code belongs here if optional AI-assisted features are added later. Gemini credentials must stay in backend environment configuration and must not be exposed to frontend clients.

### `backend/glucotracker/infra/nightscout`

Nightscout integration code belongs here for optional meal sync and read-only context import. Nightscout URL, token, and related settings must stay in backend environment/configured settings and must not be exposed to frontend clients.

### `backend/glucotracker/application/nightscout_context.py`

Nightscout glucose and insulin context is imported into local backend-owned tables, then used to build computed timeline episodes. Food entries remain normal meal rows; the backend groups accepted meals into food episodes by time windows and links nearby read-only Nightscout context for display. These episodes are computed API responses, not persisted meal replacements.

### `backend/glucotracker/application/glucose_dashboard.py`

The glucose dashboard owns sensor-quality and display-calibration semantics.
Raw Nightscout CGM rows remain immutable local facts. Fingerstick readings and
sensor sessions are stored as separate backend-owned tables, and calibration
models are persisted as derived display metadata. Normalized glucose is only a
view layer value (`raw + offset + drift * sensor_age_days`) and must not replace
raw CGM in history, reports, daily totals, or Nightscout import tables.

Sensor quality is phase-aware. The backend classifies sensor age as warmup
(`<48h`), stable (`48h..12d`), or end of life (`>=12d`). Fingerstick residuals
from the first 48 hours are reported as warmup metrics; stable offset/drift
prefers points after 48 hours and only falls back to points after 12 hours with
lower confidence. First-12-hour residuals must never dominate stable display
normalization.

The desktop `/glucose` page is a presentation client for this API. It can choose
a range, render raw/smoothed/normalized series, add manual fingerstick readings,
edit sensor-session metadata, and request recalculation. It must not implement
its own sensor-quality math or use normalized values for medical decisions.

### `backend/glucotracker/application/endocrinologist_report.py`

The endocrinologist report data model is backend-owned. The backend reads accepted meals plus local Nightscout CGM/insulin context, builds food episodes, calculates report KPIs, meal-profile rows, daily rows, completeness notes, and safety footer text, then exposes that presentation-ready JSON through `GET /reports/endocrinologist`.

The desktop PDF generator must stay presentational: it may choose a date range, trigger Nightscout import, call the report endpoint, render the one-page A4 PDF, and save it locally. It must not duplicate observed ratio, TIR, food-episode grouping, insulin-linking, or glucose-window math.

Report rows are computed on demand from local raw facts for now. Do not persist report snapshots unless we need audit history or performance caching; if that becomes necessary, cache deterministic daily/episode facts rather than PDF-specific layout rows.

### `backend/glucotracker/infra/storage`

Server-side file storage adapters belong here. The first implementation can stay local, while the interface can later support object storage if needed.

### `backend/glucotracker/workers`

Background jobs and scheduled maintenance tasks belong here. Workers should depend on application services and infrastructure adapters, not on desktop behavior.

### `desktop`

The desktop app is a Tauri 2 shell around a React + TypeScript + Tailwind webview. It should communicate with the backend through REST + JSON and generated OpenAPI client types rather than local-only assumptions.

### `docs`

Long-lived project decisions, API contracts, and design tokens live here so both desktop and future Android work can share the same reference points.

### `scripts`

Project automation and helper scripts belong here. Scripts should support setup, generated clients, migrations, and maintenance without embedding business logic.
