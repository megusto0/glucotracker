# ADR-014 - Hosted backend target architecture

| | |
| --- | --- |
| Status | Proposed |
| Date | 2026-05-13 |
| Affects | `backend/`, `desktop/`, `android-concept/`, deployment configuration |
| Risk | Medium - changes runtime ownership without changing the public API |

---

## Context

The current product can run completely locally, but the desired target is a
backend that is available without a developer machine being online.

Relevant constraints:

- Per `CONCEPT.md` section 1, the backend is the single source of truth and the
  mobile client works through the same API as desktop.
- Per `docs/architecture.md` section `Backend`, the backend owns accepted meal
  totals, auth, photo upload, Gemini, Nightscout, feature gates, and OpenAPI.
- Per `docs/architecture.md` section `Desktop`, desktop is a replaceable client
  over the backend API and must not mutate SQLite directly.
- Per `docs/architecture.md` section `Runtime Data`, `backend/data/`,
  `*.db`, local photos, and `.env` are runtime data and must not be committed.

The hosted target must not move product authority into Android, Tauri, Supabase
client SDKs, or Nightscout.

## Decision

Adopt a hosted backend target:

```text
Android / Tauri
  -> HTTPS OpenAPI
Render FastAPI backend
  -> SQLAlchemy
Supabase Postgres
  -> durable object storage
Supabase Storage
```

Render hosts the FastAPI application. Supabase is infrastructure for Postgres
and private object storage. Clients continue to call the backend API only.

Local development remains supported:

```text
Android / Tauri dev
  -> http://127.0.0.1:8000
Local FastAPI backend
  -> SQLite or local Postgres
Local filesystem storage
```

No public client should receive Supabase service-role credentials, direct
database credentials, Gemini keys, or Nightscout secrets.

## Migration sequence

1. Make database configuration explicit for local SQLite, local Postgres, and
   Supabase Postgres.
2. Make photo/product-image storage adapter-based, with local filesystem and
   Supabase Storage implementations.
3. Add Render deployment configuration and a production startup path.
4. Split web runtime from periodic/background runtime where needed.
5. Add client environment switching for local and hosted API base URLs.
6. Cut over clients to the Render URL only after migrations, storage, and health
   checks are verified.

## Consequences

Positive:

- The app can be used without a local backend process.
- Android and Tauri share one backend and one database.
- Nightscout and Gemini remain backend-side.
- Local development remains fast and isolated.

Negative:

- Production no longer tolerates filesystem-only photo storage.
- Deployments need migration discipline.
- Background workers need explicit hosting behavior.
- Supabase/Postgres behavior must be tested separately from SQLite behavior.

## Non-goals

- Do not replace backend auth with Supabase Auth.
- Do not expose Supabase tables directly to Android or Tauri.
- Do not make clients calculate accepted nutrition totals.
- Do not change the OpenAPI surface unless a migration step explicitly requires
  it.

## Acceptance criteria

- The hosted backend can serve all existing clients through the same OpenAPI
  contract.
- Local backend startup still works without Supabase credentials.
- Production runtime does not depend on files under `backend/data/`.
- Secrets live only in backend/Render environment variables.
