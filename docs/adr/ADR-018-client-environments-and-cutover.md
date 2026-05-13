# ADR-018 - Client API environments and hosted cutover

| | |
| --- | --- |
| Status | Proposed |
| Date | 2026-05-13 |
| Affects | `desktop/`, `android-concept/`, OpenAPI generation, release process |
| Risk | Low - clients keep the same backend API but change endpoint selection |

---

## Context

Per `docs/architecture.md` section `API Contract`, `docs/openapi.json` is the
legitimate API surface. Per `docs/architecture.md` section `Desktop`, desktop is
a replaceable client over the backend API. Per `docs/architecture.md` section
`Android`, Android is local-first and uses generated OpenAPI clients plus Room
and WorkManager.

The hosted backend target must allow:

- local development against `http://127.0.0.1:8000`;
- production clients against the Render HTTPS URL;
- offline Android capture/outbox behavior when the hosted backend is
  unavailable.

## Decision

Clients get explicit API environment configuration:

| Client | Local/dev | Production |
| --- | --- | --- |
| Android gluco | local backend URL from debug config | Render HTTPS URL |
| Android food | local backend URL from debug config | Render HTTPS URL |
| Tauri desktop | local backend URL from dev env | Render HTTPS URL or user/admin setting |

The API base URL is configuration, not business logic. Clients must not infer
hosted/local mode from feature behavior.

OpenAPI remains the contract. If backend routes change during hosted migration,
regenerate `docs/openapi.json`, Android API clients, and desktop generated
types in the same change.

## Offline and sync behavior

Hosted backend does not weaken offline-first requirements:

- Android still captures photos/text/templates offline into durable local
  outbox rows.
- Accepted server records still replace pending local rows atomically.
- Edits/deletes must sync through backend endpoints, not direct Supabase writes.
- Nightscout sync remains backend-owned.

When the hosted backend is unavailable, clients should show the same queue and
connectivity UX they use for local backend/network failures.

## Cutover plan

1. Deploy Render backend against a staging Supabase project.
2. Point debug clients to staging and run capture/edit/delete/Nightscout smoke
   tests.
3. Deploy production Render backend against production Supabase.
4. Release clients with hosted API URL.
5. Keep local backend support in debug/dev builds.
6. Monitor auth refresh, photo upload, estimate completion, accepted meal
   totals, and Nightscout sync.

## Consequences

Positive:

- Clients do not need Supabase database or storage credentials.
- The same app can run against local or hosted backend.
- Offline-first Android behavior remains intact.

Negative:

- Release builds need environment-specific configuration discipline.
- Hosted failures now look like network failures to clients and must be
  explained in queue/status UI.
- Test matrices must include local backend and hosted/staging backend.

## Acceptance criteria

- Android and Tauri can run against a hosted backend without local FastAPI.
- Debug builds can still run against local FastAPI.
- Clients use the same OpenAPI contract in both modes.
- No client contains Supabase service-role credentials, direct DB URLs, Gemini
  keys, or Nightscout secrets.
