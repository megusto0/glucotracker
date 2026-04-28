# Workers

Glucotracker currently uses simple in-process worker helpers, not an external
queue. Daily total recalculation is scheduled into a process-local set and
drained synchronously by API mutations before the database transaction commits.

Limitations:

- Pending work is not durable across process crashes.
- Multiple backend processes do not share an in-process queue.
- Long backfills should be run through `POST /admin/recalculate` or direct CLI
  scripts rather than relying on mutation-triggered recalculation.

Manual recovery:

1. Start the backend with the normal database configured.
2. Call `POST /admin/recalculate?from=YYYY-MM-DD&to=YYYY-MM-DD`.
3. Re-run for any affected ranges after bulk imports, manual DB edits, or crash
   recovery.
