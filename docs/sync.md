# Sync And Reconciliation

Status: source of truth
Last updated: 2026-05-31
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

`captured_at` is a local wall-clock value. Clients should send it without a
trailing `Z`, for example `2026-05-16T20:10:00`; the backend stores the same
wall time as `meals.eaten_at` and `photos.taken_at`. Offline outbox replay must
preserve the original capture wall time unchanged rather than replacing it with
sync time.

The older multi-call flow still exists for compatibility/desktop/manual flows:

- `POST /meals`
- `POST /meals/{meal_id}/photos`
- `POST /meals/{meal_id}/estimate_and_save_draft`
- `POST /meals/{meal_id}/accept`

## Reconciliation

Idempotency prevents duplicate server meals when a client loses the response.
Android reconciliation links local outbox items to server meals by idempotency
where possible, then marks local rows confirmed.

Manual `POST /meals` may send an optional `idempotency_key`. The backend stores
that key on `meals.photo_idempotency_key`, scoped by `current_user.id`, and
`GET /meals?idempotency_key=...` returns the matching meal for exact Android
reconciliation. New Android manual rows generate one key when the outbox row is
created and reuse it for every retry.

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

Sensor sessions are explicit lifecycle records. Imported CGM gaps do not close a
sensor by themselves; a user action or a new manual sensor session is needed.
Creating a new manual sensor closes any previous open session for that user.
When a sensor is marked corrupt/excluded, the exclusion window is persisted on
the sensor session and applies to backend glucose visibility paths that route
through the current dashboard/timeline filtering logic.

The `/timeline/insulin-links` day-review workflow persists episode snapshots.
When CGM data exists for an episode, the snapshot stores glucose around the food
episode at `-30m` and `+2h` together with the rest of the assembled food/insulin
context.

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

## Needs Verification

- On the current checked-out branch, some raw aggregation paths still read CGM
  rows directly. Verify corrupt-sensor exclusion before claiming every stats or
  report path hides excluded sensor data.
