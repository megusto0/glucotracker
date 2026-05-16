# ADR-017 - Render runtime and background workers

| | |
| --- | --- |
| Status | Proposed |
| Date | 2026-05-13 |
| Affects | Render service config, `backend/glucotracker/main.py`, workers, health checks |
| Risk | Medium - long-running jobs move from local process assumptions to hosted runtime |

---

## Context

`docs/architecture.md` section `Backend` identifies background imports,
Nightscout, photo estimation, daily totals, reports, and workers as backend
responsibilities. `backend/glucotracker/main.py` currently registers routers and
starts background workers.

Hosted deployment changes process assumptions:

- Render may restart the service.
- Multiple instances can duplicate in-process background loops.
- A web process must respond to health checks quickly.
- Long-running imports should not block request handling.

## Decision

Use Render as the FastAPI host with explicit process roles.

Initial deployment may use one Render web service if only one instance is
running:

```text
render-web
  uvicorn glucotracker.main:app --host 0.0.0.0 --port $PORT
```

As soon as background work needs stronger guarantees, split roles:

```text
render-web
  serves API only

render-worker
  Nightscout imports
  periodic maintenance
  retry sweeps
  categorization/report maintenance jobs

render-cron
  optional scheduled one-off jobs
```

Photo estimation that is triggered by a request may stay request-bound at first.
If it becomes slow or unreliable under hosted latency, move it to a durable job
queue in a later ADR.

## Runtime configuration

Production requires:

- `GLUCOTRACKER_DATABASE_URL`
- `GLUCOTRACKER_JWT_SECRET`
- Gemini credentials/model env vars
- Supabase Storage credentials if ADR-016 is implemented
- `GLUCOTRACKER_APP_TIMEZONE`
- Nightscout background import controls

The health endpoint must not require database writes, Gemini, Nightscout, or
storage access. A separate readiness check can validate database connectivity.

## Worker guardrails

- In-process recurring workers are allowed only for single-instance deployment.
- Multi-instance deployment must use a DB lease, advisory lock, external queue,
  or separate worker service.
- Failed worker iterations must log sanitized errors and continue.
- Worker logs must never include photo bytes, Nightscout secrets, JWTs, or raw
  refresh tokens.

## Consequences

Positive:

- Hosted API can be reached by every client.
- Runtime responsibilities are explicit.
- The single-service path keeps first deployment small.

Negative:

- Single-instance background loops are a temporary compromise.
- A later worker split is likely.
- Production observability becomes mandatory for Nightscout and photo pipeline
  issues.

## Acceptance criteria

- Render can boot the API and pass `/health`.
- The web process does not depend on local filesystem runtime state.
- Background imports do not run twice in a multi-instance deployment.
- Startup fails fast when required production secrets are missing.
