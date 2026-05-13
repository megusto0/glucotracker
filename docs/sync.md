# Sync And Reconciliation

Status: source of truth
Last updated: 2026-05-13
Owner/area: Android outbox, backend sync, Nightscout

Glucotracker uses local-first Android reads/mutations and backend-owned accepted
records. The client may show pending local rows, but server-confirmed records
replace them atomically.

## Android Outbox

Android stores durable mutations in Room `outbox`. Main states:

- `Queued`
- `Uploading`
- `Confirmed`
- `Stuck`

Legacy states such as `Sending`, `Sent`, `Estimating`, and `Conflict` are mapped
by converters for old rows.

WorkManager handles retries. Connectivity callbacks and foreground retries
attempt to shorten the wait after the network returns. The outbox inspector is
the user-visible recovery surface.

## Photo Capture Flow

Current normal photo capture is one canonical backend request:

```http
POST /meals/from-photo
```

Multipart fields:

- `photo`
- `captured_at`
- `idempotency_key`
- `source` = `camera` or `gallery`
- `context` optional

Backend behavior:

1. Scope lookup by `current_user.id` and `photo_idempotency_key`.
2. If a matching meal exists, return it.
3. Save the photo privately.
4. Create a draft photo meal with `estimate_status = estimating`.
5. Return `202 Accepted`.
6. Run Gemini estimation in a background task.
7. Persist accepted results or an estimate error on the backend meal.

The older multi-call flow still exists for compatibility/desktop/manual flows:

- `POST /meals`
- `POST /meals/{meal_id}/photos`
- `POST /meals/{meal_id}/estimate_and_save_draft`
- `POST /meals/{meal_id}/accept`

## Reconciliation

Idempotency prevents duplicate server meals when a client loses the response.
Android reconciliation links local outbox items to server meals by idempotency
where possible, then marks local rows confirmed.

`needs verification`: ADR-011 specified a dedicated idempotency lookup. Current
OpenAPI does not show a separate `GET /meals?idempotency_key=...` parameter in
the visible endpoint list; current Android code reconciles from cached meals with
`photoIdempotencyKey`. Verify before depending on a server-side lookup contract.

## Nightscout

Nightscout is optional and gluco-only.

Backend owns:

- masked settings at `/settings/nightscout`;
- connection test;
- status and day status;
- local import of glucose/insulin context;
- background import loop when enabled;
- manual meal sync/unsync to Nightscout;
- timeline food episodes with local Nightscout context.

Imported Nightscout insulin is read-only context. Glucotracker does not create
insulin dose recommendations.

## Cache And Prune

Android cache pruning runs daily:

- meal cache older than 14 local days is pruned;
- unused products older than 90 days are pruned;
- orphaned local photo files are swept when no outbox row references them;
- gluco-only glucose cache keeps the last 6 hours.

## Failure Policy

- Network unavailable: keep UI usable and show a discreet banner.
- Backend accepted data wins over pending local data.
- Gemini failure is a backend meal estimate status, not an Android outbox state.
- Stuck rows need explicit user recovery actions.
