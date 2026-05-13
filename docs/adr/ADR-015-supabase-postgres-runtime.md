# ADR-015 - Supabase Postgres as production database

| | |
| --- | --- |
| Status | Proposed |
| Date | 2026-05-13 |
| Affects | `backend/glucotracker/config.py`, `infra/db/session.py`, Alembic migrations, tests |
| Risk | Medium - persistent production data moves from local SQLite to Postgres |

---

## Context

The backend currently defaults to:

```text
sqlite:///./data/glucotracker.sqlite3
```

`docs/architecture.md` section `Backend` says the backend owns auth, user roles,
feature gates, user-owned data scoping, meal totals, photos, Gemini, and
Nightscout integration. The database therefore contains production personal
data, not a cache.

The multi-user invariants also require user-owned reads to be scoped by
`current_user_id`, with repositories taking `user_id` for scoped data.
Cross-user leaks are the highest-risk bug class.

## Decision

Use Supabase Postgres as the production SQL database, accessed only by the
FastAPI backend through SQLAlchemy.

The backend keeps env-based database selection:

| Environment | Database |
| --- | --- |
| Local default | SQLite under `backend/data/` |
| Local parity/dev | Local Postgres or Supabase branch/project |
| Production | Supabase Postgres |
| Tests | Existing SQLite tests plus targeted Postgres smoke tests |

Supabase Data API, PostgREST, Realtime, and client-side table access are not
part of the product runtime. If a table is in an exposed schema, RLS should
still be treated as defense in depth, but authorization remains enforced by
backend auth and scoped repositories.

## Implementation requirements

- Add a Postgres driver dependency if missing.
- Normalize accepted SQLAlchemy URLs, including Supabase URLs.
- Keep SQLite-specific connect args and write locking limited to SQLite.
- Configure SQLAlchemy pool settings for hosted Postgres explicitly.
- Run Alembic migrations against Supabase before serving traffic.
- Add a production-safe command for:

```powershell
alembic upgrade head
uvicorn glucotracker.main:app --host 0.0.0.0 --port $env:PORT
```

If migrations are run during Render startup, they must be idempotent and safe
for a single active deploy. For multiple instances, migration execution should
move to a one-off deploy job.

## Data safety

All migrations remain forward-only and non-destructive. No migration may drop
tables/columns or rewrite user data without an explicit backup and rollback
plan.

Before cutover:

1. Backup the local SQLite database.
2. Create Supabase project/database.
3. Apply Alembic migrations to an empty Supabase database.
4. Import local data with a verified script.
5. Run two-user isolation tests.
6. Run smoke tests for auth, meals, photos, Nightscout settings, and daily
   totals.

## Consequences

Positive:

- Production data is durable and independent from Render instances.
- Multi-client access converges on one backend database.
- Postgres gives stronger production behavior than a hosted SQLite file.

Negative:

- SQLite-only query assumptions become bugs.
- Connection pooling and deploy-time migrations need care.
- Local tests alone are no longer enough for production confidence.

## Acceptance criteria

- Local `uvicorn glucotracker.main:app --reload` still works with default SQLite.
- Production can boot using only env vars and a Supabase Postgres URL.
- Alembic can upgrade a clean Supabase database.
- Scoped repository tests cover at least two users for touched user-owned data.
