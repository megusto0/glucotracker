# Frontend Replacement Guide

The desktop UI in `desktop/` is one replaceable implementation of the Glucotracker API. The backend, database schema, REST semantics, Gemini routing, Nightscout behavior, and macro totals are the product core.

## Replace This UI

1. Keep `backend/` and `docs/openapi.json`.
2. Delete or ignore `desktop/src/app`, `desktop/src/features`, and the current UI components.
3. Generate a new client from `docs/openapi.json` or from `GET /openapi.json` on a running backend.
4. Store the backend URL and bearer token in the new frontend's local settings.
5. Send every protected request with `Authorization: Bearer <token>`.
6. Treat meal totals, item totals, daily totals, dashboard metrics, pattern search, product search, Gemini estimation, and Nightscout sync as backend-owned behavior.

## TypeScript Client

The current desktop app generates OpenAPI types into:

```bash
cd desktop
npm run api:types
```

Generated files live under `desktop/src/api/generated/` and should not be hand edited. The small wrapper at `desktop/src/api/client.ts` is the only place this UI binds generated API types to runtime HTTP calls.

## Required Boundaries

- New frontends should call hooks or services around the generated API client, not scatter raw HTTP calls through components.
- Frontends must not access SQLite, photo storage, local backend files, Gemini keys, or Nightscout secrets.
- Frontends must not calculate accepted meal totals or dashboard totals locally.
- The only acceptable frontend summing is a clearly marked temporary preview for unsaved edits. Backend responses are authoritative after save or accept.
- AI review flows should call `/meals/{id}/estimate`, let the user review returned items, then call `/meals/{id}/accept`.
- New frontends should use `/autocomplete` rather than reimplementing pattern/product matching.

## Nightscout

Nightscout is optional. If `GET /nightscout/status` returns `configured=false`, or sync endpoints return `503 Nightscout not configured`, the UI should keep local save/edit flows available and show sync as unavailable.
