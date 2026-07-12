# Architecture

Status: source of truth
Last updated: 2026-05-31
Owner/area: backend, desktop, Android architecture

Glucotracker is a three-client-family repository around one backend:

- `backend/` - FastAPI, SQLAlchemy/Alembic, auth, Gemini, Nightscout, reports,
  workers, tests.
- `desktop/` - Tauri 2 + React + TypeScript desktop client.
- `android-concept/` - single-activity Jetpack Compose app with `gluco` and
  `food` product flavors.
- `docs/` - current source-of-truth documentation and generated API schema.

Per `CONCEPT.md` §1, mobile is for capture and glance; desktop keeps deep
editing, imports, Nightscout credentials, OpenAPI access, and report/export
work.

## Backend

The backend is the product authority. It owns:

- accepted meal totals, daily totals, calorie balance, TDEE context, and product
  math;
- auth, user roles, feature gates, and user-owned data scoping;
- photo upload, Gemini calls, AI run audit, and photo draft acceptance;
- Nightscout settings, read-only CGM/insulin cache, meal sync to Nightscout, and
  background imports;
- glucose dashboard, fingersticks, sensor sessions, display-only calibration,
  corrupt-sensor exclusion, postprandial analysis, and report aggregation;
- food/insulin link review episodes and persisted glucose snapshots around
  meals when CGM data exists;
- digital twin research-mode parameter fitting and reconstructed curves;
- validated per-user IOB/COB timing fits with append-only audit history and
  population fallback;
- OpenAPI generation.

Key entry points:

- `backend/glucotracker/main.py` registers routers and may start the Nightscout
  importer, anchor recompute worker, and postprandial sweeper when enabled.
- `backend/glucotracker/api/routers/` exposes REST endpoints.
- `backend/glucotracker/api/openapi.py` annotates OpenAPI with auth, scoped, and
  role metadata.
- `backend/glucotracker/api/dependencies/` verifies JWTs and feature gates.
- `backend/glucotracker/application/` coordinates use cases.
- `backend/glucotracker/domain/` contains deterministic rules and enums.
- `backend/glucotracker/infra/db/` contains SQLAlchemy models, sessions, seed
  data, and migrations.
- `backend/glucotracker/infra/gemini/` owns Gemini clients and prompt schemas.

`get_session` yields a sync SQLAlchemy `Session` from an async dependency. Keep
that shape; it avoids QueuePool starvation during FastAPI dependency cleanup.

### On-board timing personalization

Per `CONCEPT.md` §1, IOB/COB is informational-only. The owner-scoped
`on_board_model_fits` table stores versioned accepted/rejected timing fits;
`OnBoardRepository` is the only persistence/training read boundary. Fitting uses
completed raw-CGM days asynchronously or as part of the existing twin fit flow.
The glucose dashboard only loads an active validated fit and falls back to the
population model, so a read request never trains or writes a model. See
[`iob-cob-models.md`](iob-cob-models.md) for gates and model details.

### Time Semantics

Meal and photo capture times are local wall-clock product data, not absolute
instants. `meals.eaten_at`, `photos.taken_at`, and
`meal_audit_events.eaten_at` are stored as timezone-naive datetimes
(`timestamp without time zone` on Postgres). Tauri and Android should send
`YYYY-MM-DDTHH:MM:SS` for local meal/capture times. If an older client sends an
offset-aware value, the backend converts it to `GLUCOTRACKER_APP_TIMEZONE` and
then stores the local wall time. These fields must not shift through UTC
conversion.

Absolute event timestamps such as `created_at`, `updated_at`, refresh-token
expiry, Nightscout import timestamps, CGM readings, and worker timestamps remain
timezone-aware UTC values (`TIMESTAMPTZ` on Postgres).

## Auth And Users

The backend is multi-user. `/auth/login`, `/auth/refresh`, `/auth/logout`, and
`/auth/me` are the auth surface. Passwords are argon2id hashes. Access tokens are
JWTs with a 15 minute TTL; refresh tokens live 30 days and only their SHA-256 hash
is stored server-side.

User roles are `gluco` and `food`. `gluco` has glucose, Nightscout, and insulin
context features. `food` has no glucose features. Feature-disabled responses must
be `403` with `{"code": "feature_disabled", "feature": "<name>"}`.

There is no public register endpoint. Users are created by
`python -m glucotracker.cli create-user --username <name> --role gluco|food`.

## API Contract

The legitimate API surface is [`openapi.json`](openapi.json). Regenerate both API
artifacts after backend route/schema changes:

```powershell
bash scripts/export-openapi.sh
```

If PowerShell cannot execute the shell script, use the direct FastAPI export
fallback in the root [`README.md`](../README.md). Android currently consumes
[`openapi.yaml`](openapi.yaml); desktop consumes `openapi.json`.

## Desktop

Desktop is a replaceable client over the backend API.

Key files:

- `desktop/src/app/routes.tsx` - `/login`, `/`, `/feed`, `/stats`, `/glucose`,
  `/twin`, `/insulin-links`, `/database`, `/settings`.
- `desktop/src/app/Shell.tsx` - shell and navigation.
- `desktop/src/api/client.ts` - handwritten wrapper over generated OpenAPI
  types.
- `desktop/src/api/generated/schema.d.ts` - generated from `docs/openapi.json`.
- `desktop/src/features/*` - page-level behavior.
- `desktop/src/features/reports/` - React PDF report rendering.
- `desktop/src/utils/mealTextReport.ts` - TXT food diary export.

Desktop may format and visualize data, but it must not own accepted nutrition
math or mutate SQLite directly.

## Android

Android is local-first and flavor-aware:

- shared code lives in `android-concept/app/src/main/`;
- glucose code lives in `src/gluco/`;
- Tarelka/food flavor branding and no-op glucose bindings live in `src/food/`;
- generated OpenAPI clients land under `build/generated/openapi*`; the food
  generated client is pruned of glucose-related symbols during Gradle codegen;
- Room caches meals, day totals, products, templates, outbox rows, and gluco-only
  CGM cache;
- WorkManager handles outbox and cache pruning.

The food flavor must compile without glucose feature code except the shared no-op
surface contracts required for dependency injection. This is enforced by Gradle
class/resource scans.

## Runtime Data

Never commit runtime data:

- `backend/data/`
- `desktop/data/`
- `*.db`, `*.sqlite*`
- local photos/product images
- crash dumps
- `.env`

## Implementation Notes

`needs verification`: the current code still contains scoped SQL in several
routers/services rather than a strict repository-only boundary. See
[`doc-audit.md`](doc-audit.md) for the unresolved scoping documentation issues.
