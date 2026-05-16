# Data Model

Status: source of truth
Last updated: 2026-05-13
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
| `meals` | user-owned | Main accepted/draft food record. Contains totals, status, source, Nightscout sync fields, AI categories, postprandial response, photo idempotency key. |
| `meal_items` | user-owned through meal | Item-level nutrients and product/photo links. |
| `meal_item_nutrients` | user-owned through item | Optional detailed nutrients. Unknown values stay `null`. |
| `photos` | user-owned | Private uploaded image metadata and path. |
| `ai_runs` | user-owned through meal/photo | Gemini audit payloads, model routing, normalized items. |
| `patterns`, `pattern_aliases` | user-owned | User templates/patterns. |
| `products`, `product_aliases` | shared or private | `owner_id IS NULL` means global; `owner_id = user` means private. |
| `daily_totals` | user-owned | Backend-owned daily nutrition totals. |
| `meal_audit_events` | user-owned | Meal mutation/audit history. |
| `nightscout_settings` | user-owned, gluco-only | Masked settings response; secret is write-only. |
| `nightscout_glucose_entries` | user-owned, gluco-only | Read-only imported CGM cache. Raw values are immutable. |
| `nightscout_insulin_events` | user-owned, gluco-only | Read-only imported insulin treatment context. |
| `nightscout_import_state` | user-owned, gluco-only | Import watermark. |
| `sensor_sessions` | user-owned, gluco-only | Sensor lifecycle and calibration context. |
| `fingerstick_readings` | user-owned, gluco-only | Manual glucose readings. |
| `cgm_calibration_models` | gluco-only | Display/normalization support. |
| `user_profile`, `daily_activity` | user-owned | Activity/TDEE context for calorie balance. |
| `non_typical_periods`, `day_anchor_history` | user-owned | Adaptive day-rhythm learning and overrides. |

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
tables, user profile/activity, photo idempotency, meal categorization, user
goals, day anchors, and postprandial response.
