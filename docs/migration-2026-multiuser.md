# 2026 Multi-User Backend Migration

This is the mobile breaking-change checklist for BE-1 through BE-5.

## New Endpoints

- `POST /auth/login` accepts username/password and returns access and refresh tokens.
- `POST /auth/refresh` rotates a refresh token and returns a new token pair.
- `POST /auth/logout` revokes a refresh token.
- `GET /auth/me` returns the current user id, role, resolved feature set, and profile timestamps.

## Auth Requirement

All application data endpoints now require `Authorization: Bearer <access_token>`.
Unauthenticated requests return `401` and must not fall back to a default user.

Public or bootstrap endpoints:

- `POST /auth/login`
- `POST /auth/refresh`
- `GET /health`

Mobile must treat the token as required for every food diary, dashboard,
product, pattern, photo, glucose, Nightscout, profile, activity, report, and
admin request.

## Response Shape Changes

Role-specific glucose omission:

- `GET /dashboard/today`: `gluco` users receive `current_glucose` and
  `current_glucose_at`; `food` users do not receive those keys.
- `GET /timeline`: `gluco` users receive episode `glucose`, `glucose_summary`,
  `insulin`, and top-level `ungrouped_insulin`; `food` users receive a food-only
  response without glucose or insulin fields.

User-scoped list/read endpoints now automatically return only the current user's
data:

- Meals and meal items: `/meals`, `/meals/{id}`, `/meal_items/*`.
- Photos and AI runs: `/meals/{id}/photos`, `/photos/{id}/file`,
  `/meals/{id}/ai_runs`.
- Patterns/templates: `/patterns`, `/patterns/search`, `/patterns/{id}`.
- Dashboard/history-derived food data: `/dashboard/*`, `/timeline`.
- Activity/profile data: `/profile`, `/activity/*`.
- Glucose data: `/glucose/*`, `/fingersticks/*`, `/sensors/*`.
- Nightscout settings, imports, status, and sync state: `/settings/nightscout*`,
  `/nightscout/*`, `/meals/{id}/sync_nightscout`,
  `/meals/{id}/unsync_nightscout`.
- Reports: `/reports/endocrinologist`.

Shared data behavior:

- `/products/*` is still shared, but private products are visible only to their
  owner. The effective read filter is `owner_id IS NULL OR owner_id = current_user`.
- Product aliases follow the parent product scope.
- Restaurants remain shared/global.

## Error Shape Changes

- Missing, invalid, expired, or revoked access token:
  `401` with `{"code": "unauthorized"}`.
- Role lacks a feature:
  `403` with `{"code": "feature_disabled", "feature": "<name>"}`.
- Glucose-gated feature names:
  `glucose`, `nightscout`, `insulin`.

Feature gating intentionally returns `403`, not `404`; the endpoint exists, but
the current role lacks the capability.

## Mobile Action Items

- AND-2: Add login UI for the seeded family users. There is no public register
  endpoint.
- AND-2: Store access and refresh tokens in encrypted storage, never plain
  SharedPreferences and never logs.
- AND-2: Attach `Authorization: Bearer <access_token>` to every API call except
  login, refresh, and health.
- AND-2: On `401`, run refresh-token rotation once, retry the original request,
  then send the user back to login if refresh fails.
- AND-3: Read `/auth/me` after login/refresh and persist the current `role` and
  `features`.
- AND-3: Make navigation role-aware: `food` users must not show glucose,
  Nightscout, CGM, fingerstick, sensor, insulin, or endocrinologist-report
  surfaces.
- AND-4: Use the food response variants for `/dashboard/today` and `/timeline`;
  code must check key presence rather than assuming glucose fields exist.
- AND-4: Treat `403 feature_disabled` as a stable capability response, not as an
  auth-expired state.
- AND-5: Regenerate the Kotlin API client from `docs/openapi.yaml` and update
  generated model handling for the role-specific response unions.
- AND-5: Remove the generated-client hardcoded `Bearer dev` default request
  patch and inject the current access token at runtime.
