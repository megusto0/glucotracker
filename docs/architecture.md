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

FastAPI routers are grouped here by resource. Routers should describe HTTP boundaries and delegate real rules to domain services when those services are added.

### `backend/glucotracker/domain`

Domain entities and services belong here. This layer should describe food diary concepts and rules without depending on FastAPI, SQLite, Tauri, or external service SDKs.

### `backend/glucotracker/infra/db`

SQLAlchemy engine, session, metadata, and model mapping code belongs here. Database work should use SQLAlchemy 2.0 APIs instead of SQLite-specific shortcuts so a later Postgres migration remains straightforward.

### `backend/glucotracker/infra/gemini`

Gemini integration code belongs here if optional AI-assisted features are added later. Gemini credentials must stay in backend environment configuration and must not be exposed to frontend clients.

### `backend/glucotracker/infra/nightscout`

Nightscout integration code belongs here for future read-only import or correlation workflows. Nightscout URL, token, and related settings must stay in backend environment configuration and must not be exposed to frontend clients.

### `backend/glucotracker/infra/storage`

Server-side file storage adapters belong here. The first implementation can stay local, while the interface can later support object storage if needed.

### `backend/glucotracker/workers`

Background jobs and scheduled maintenance tasks belong here. Workers should depend on backend services and infrastructure adapters, not on desktop behavior.

### `desktop`

The desktop app is a Tauri 2 shell around a React + TypeScript + Tailwind webview. It should communicate with the backend through REST + JSON and generated OpenAPI client types rather than local-only assumptions.

### `docs`

Long-lived project decisions, API contracts, and design tokens live here so both desktop and future Android work can share the same reference points.

### `scripts`

Project automation and helper scripts belong here. Scripts should support setup, generated clients, migrations, and maintenance without embedding business logic.
