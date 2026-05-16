# ADR-016 - Durable photo and product image storage

| | |
| --- | --- |
| Status | Proposed |
| Date | 2026-05-13 |
| Affects | `backend/glucotracker/infra/storage/`, `api/routers/photos.py`, photo/product image models |
| Risk | Medium - private user photos move from local disk to object storage |

---

## Context

`docs/architecture.md` section `Backend` says the backend owns photo upload,
Gemini calls, AI run audit, and photo draft acceptance. `docs/architecture.md`
section `Runtime Data` says local photos and product images must not be
committed.

The current backend stores uploads through filesystem helpers under
`backend/glucotracker/infra/storage/`, rooted at `PHOTO_STORAGE_DIR` /
`GLUCOTRACKER_PHOTO_STORAGE_DIR`.

Render service disks are not an acceptable source of truth for private photos.
Files can disappear across redeploys, restarts, or instance replacement.

## Decision

Introduce a backend-owned storage adapter boundary and use Supabase Storage for
production photos/product images.

Required adapter shape:

```text
PhotoStorage
  save_upload(file) -> storage_key
  open_for_read(storage_key) -> bytes/stream + metadata
  delete(storage_key)
  exists(storage_key)
```

Implementations:

| Environment | Adapter |
| --- | --- |
| Local default | Filesystem |
| Tests | Filesystem/temp directory |
| Production | Supabase Storage |

The database stores stable storage keys, not public URLs. Existing API routes
such as `/photos/{photo_id}/file` remain backend routes. The backend fetches the
object and streams it to authenticated clients after user scoping checks.

## Privacy and access

- Supabase buckets for user photos must be private.
- Supabase service-role or secret storage credentials stay backend-only.
- Clients must not receive durable signed URLs unless a separate ADR explicitly
  accepts that access pattern.
- Photo bytes must not be logged, sent to crash reports, or exposed in exception
  messages.

## Migration

1. Add storage adapter interface while keeping the filesystem implementation as
   default.
2. Convert photo/product-image code to depend on the adapter.
3. Add Supabase Storage implementation behind env config.
4. Add a one-off migration script that uploads existing local files and updates
   stored paths/keys transactionally.
5. Keep a dry-run mode that reports missing files and duplicate keys.
6. Only switch production to Supabase Storage after the migration report is
   clean.

## Consequences

Positive:

- Photos survive Render redeploys and instance replacement.
- Local development remains simple.
- Backend continues to enforce auth and user scoping before photo reads.

Negative:

- Photo reads become network-dependent in production.
- Upload/delete error handling must distinguish DB failure from storage failure.
- Existing path fields may need a compatibility layer during migration.

## Acceptance criteria

- Local photo capture and file serving still work without Supabase credentials.
- Production stores new photos in Supabase Storage.
- `/photos/{photo_id}/file` behavior is unchanged for clients.
- Deleting a meal/photo deletes or tombstones the corresponding object according
  to the chosen retention policy.
