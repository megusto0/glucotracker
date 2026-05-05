# Frontend Replacement Audit

glucotracker keeps product logic in the backend. The Tauri desktop UI is one
replaceable client over the REST API.

## Backend Endpoints Used By Desktop UI

- `GET /health`
- `GET /openapi.json`
- `GET /meals`
- `POST /meals`
- `GET /meals/{id}`
- `DELETE /meals/{id}`
- `PUT /meals/{id}/items`
- `GET /autocomplete`
- `POST /meals/{id}/photos`
- `GET /photos/{id}/file`
- `POST /meals/{id}/estimate_and_save_draft`
- `POST /meals/{id}/accept`
- `POST /meals/{id}/discard`
- `GET /dashboard/today`
- `GET /dashboard/range`
- `GET /dashboard/heatmap`
- `GET /dashboard/top_patterns`
- `GET /dashboard/source_breakdown`
- `GET /dashboard/data_quality`
- `GET /nightscout/status`
- `POST /admin/recalculate`

The UI does not call product CRUD endpoints yet, even though they exist in the
backend contract.

## Generated API Client

- OpenAPI source: `docs/openapi.json`
- Generated TypeScript schema: `desktop/src/api/generated/schema.d.ts`
- Lightweight runtime wrapper: `desktop/src/api/client.ts`
- Query key definitions: `desktop/src/api/queryKeys.ts`

Regenerate the schema with:

```bash
cd desktop
npm run api:types
```

## Purely Visual Files

These files are mostly presentation and can be replaced freely when building a
new frontend:

- `desktop/src/App.css`
- `desktop/src/app/Shell.tsx`
- `desktop/src/components/StatusText.tsx`
- `desktop/src/design/tokens.ts`
- `desktop/src/design/primitives/Button.tsx`
- `desktop/src/design/primitives/Metric.tsx`
- Most JSX markup and CSS classes in route components

## App Interaction Logic

These files contain client-side interaction and API orchestration. A replacement
frontend can discard them, but it should reproduce their API flow semantics:

- `desktop/src/api/client.ts`
- `desktop/src/api/queryKeys.ts`
- `desktop/src/features/settings/settingsStore.ts`
- `desktop/src/features/settings/useSettingsChecks.ts`
- `desktop/src/features/autocomplete/useAutocomplete.ts`
- `desktop/src/features/meals/useMeals.ts`
- `desktop/src/features/feed/feedService.ts`
- `desktop/src/features/stats/useDashboard.ts`
- Route containers under `desktop/src/features/*/*Page.tsx`

## Meal Calculation Boundary

Meal totals, accepted item totals, label arithmetic, daily totals, dashboard
aggregates, and Gemini draft normalization are backend responsibilities. The
desktop UI displays backend values. Any local draft editing preview is
non-authoritative and must be saved through backend endpoints such as
`POST /meals/{id}/accept` or `PUT /meals/{id}/items`.

## Nightscout Secrets

Nightscout URL and API secret live only on the backend. The desktop UI only
calls `GET /nightscout/status` and shows configured/not configured state. It
does not store or transmit Nightscout secrets.

## Known UI Limitations

- Product management endpoints exist but do not have a full desktop UI yet.
- Pattern management UI is not implemented; autocomplete consumes backend
  pattern search.
- Feed duplication currently uses `POST /meals` with copied item values as a
  client fallback. A backend duplicate endpoint would make this cleaner.
- Stats charts are intentionally minimal SVGs. A future frontend could add
  richer drill-down interactions while keeping the same dashboard endpoints.
- Settings are stored in localStorage for this desktop client. A future client
  can choose another local storage mechanism without changing backend state.
- Photo draft review is functional but can be refined with better editing
  controls and image inspection.
