# Data Model

Status: source of truth
Last updated: 2026-05-31
Owner/area: backend persistence and Android local cache

This is a practical map, not a full schema dump. Use
[`openapi.json`](openapi.json), SQLAlchemy models, and Alembic migrations for
field-level truth.

## Backend Core Entities

Defined primarily in `backend/glucotracker/infra/db/models.py`.

| Entity/table | Ownership | Notes |
| --- | --- | --- |
| `users` | shared account table | `role` is `gluco` or `food`; stores goals and day-anchor fields. |
| `refresh_tokens` | user-owned | Server stores token hashes only; logout/refresh revoke rows. |
| `meals` | user-owned | Main accepted/draft food record. Contains totals, status, source, Nightscout sync fields, AI categories, postprandial response, client idempotency key (`photo_idempotency_key`). |
| `meal_items` | user-owned through meal | Item-level nutrients and product/photo links. |
| `meal_item_nutrients` | user-owned through item | Optional detailed nutrients. Unknown values stay `null`. |
| `photos` | user-owned | Private uploaded image metadata and path. |
| `ai_runs` | user-owned through meal/photo | Gemini audit payloads, model routing, normalized items. |
| `patterns`, `pattern_aliases` | user-owned | User templates/patterns. |
| `products`, `product_aliases` | shared or private | `owner_id IS NULL` means global; `owner_id = user` means private. |
| `daily_totals` | user-owned | Backend-owned daily nutrition totals. |
| `meal_audit_events` | user-owned | Meal mutation/audit history. |
| `meal_insulin_links` | user-owned, gluco-only | Manual/auto links between meals and imported insulin context. |
| `meal_insulin_link_reviews` | user-owned, gluco-only | Marks insulin events that have been manually reviewed in the day-link workflow. |
| `meal_insulin_episode_snapshots` | user-owned, gluco-only | Persisted review episodes with food, insulin, link pairs, totals, and optional `-30m`/`+2h` glucose anchors plus snapshot JSON. |
| `nightscout_settings` | user-owned, gluco-only | Masked settings response; secret is write-only. |
| `nightscout_glucose_entries` | user-owned, gluco-only | Read-only imported CGM cache. Raw values are immutable. |
| `nightscout_insulin_events` | user-owned, gluco-only | Read-only imported insulin treatment context. |
| `nightscout_import_state` | user-owned, gluco-only | Import watermark. |
| `sensor_sessions` | user-owned, gluco-only | Sensor lifecycle, calibration context, and `excluded_from_analytics`/`exclusion_reason` for corrupt sensors. |
| `fingerstick_readings` | user-owned, gluco-only | Manual glucose readings. |
| `cgm_calibration_models` | user-owned through sensor session, gluco-only | Display/normalization support. |
| `twin_params` | user-owned, gluco-only | Per-user informational digital twin parameters and last fit metrics. |
| `twin_fit_log` | user-owned, gluco-only | Append-only history for twin parameter changes and fitting runs. |
| `user_profile`, `daily_activity` | user-owned | Activity/TDEE context for calorie balance. |
| `non_typical_periods`, `day_anchor_history` | user-owned | Adaptive day-rhythm learning and overrides. |

## Time Columns

Glucotracker separates local wall-clock product times from absolute event
instants:

| Column | Meaning | Storage |
| --- | --- | --- |
| `meals.eaten_at` | User-visible meal/capture time and journal day assignment. | Naive local wall-clock; Postgres `timestamp without time zone`. |
| `photos.taken_at` | Original camera/gallery capture wall time when known. | Naive local wall-clock; Postgres `timestamp without time zone`. |
| `meal_audit_events.eaten_at` | Audit snapshot of the meal wall time. | Naive local wall-clock; Postgres `timestamp without time zone`. |
| `created_at`, `updated_at`, token expiry, worker/import timestamps | Absolute system events. | Timezone-aware UTC; Postgres `TIMESTAMPTZ`. |
| CGM/fingerstick/sensor timestamps | Gluco timeline events imported or entered as instants. | Timezone-aware UTC in storage; rendered through app-local presentation helpers. |

Clients should send `eaten_at` and photo capture times as local datetime strings
without a trailing `Z`, for example `2026-05-16T20:10:00`. The backend accepts
offset-aware legacy values and converts them to `GLUCOTRACKER_APP_TIMEZONE`
before storing the local wall time.

## Status Enums

Core food enums are in `backend/glucotracker/domain/entities.py`:

- `MealStatus`: draft/accepted flow;
- `MealSource`: manual/photo/etc.;
- `ItemSourceKind`: item provenance;
- `PhotoReferenceKind` and `PhotoScenario`: photo evidence classification;
- `NightscoutSyncStatus`: local Nightscout send state;
- `MealWindow`, `MealRole`, `TasteProfile`, `PreMealState`,
  `GlycemicResponse`: categorization and postprandial semantics.

## Scoping Rules

Every user-owned read must be scoped by current user. Products and aliases use:

```sql
WHERE owner_id IS NULL OR owner_id = :current_user_id
```

`needs verification`: prompt-level architecture says scoping must be enforced in
repositories, not endpoints. Current backend has several router/service-level
queries that filter by `current_user.id` directly. That is acceptable as current
implementation documentation, but it is an implementation status mismatch for
future multi-user hardening.

## Android Local Cache

Shared Android Room DB (`src/main/.../data/local/Entities.kt`) stores:

- `cached_meals` plus FTS;
- `cached_day_totals`;
- `cached_products` plus FTS;
- `cached_templates` plus FTS;
- durable `outbox` rows.

Gluco-only Room DB (`src/gluco/.../data/local/GlucoseCacheDatabase.kt`) stores
cached glucose readings and is excluded from the food flavor except for no-op
surface contracts.

Cache budgets:

- meals: keep last 14 local days;
- products: prune unused products after 90 days;
- glucose: keep last 6 hours in the gluco cache.

## Migrations

Migrations are forward-only and non-destructive by project invariant. The current
Alembic history includes auth, owner scoping, Nightscout cache/settings, sensor
tables and exclusion flags, CGM calibration, user profile/activity, photo
idempotency, meal categorization, user goals, day anchors, postprandial
response, meal-insulin link snapshots, and digital twin tables.
