# ADR-011 · Outbox-meal reconciliation

> Closes the gap between ADR-005 (server-side idempotency) and ADR-006 (client-side single-source-of-truth). Both ADRs assumed the matching question — "did the server end up with my capture?" — was answered correctly at runtime. Real screenshots show it isn't. ADR-011 adds the reconciliation mechanism that links outbox items to server meals after the fact.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-11 |
| Affects | `data/sync/OutboxProcessor`, `data/sync/MealReconciler` (new), `MealsRemote` and `OutboxRemote` API; backend `meals.py` (lookup-by-key endpoint); both flavors share the code |
| Risk | Low — additive logic on the sync path; no schema changes |

---

## Context — what the screenshots showed

A user captured 4 photos at 03:02–03:38. After ~3 hours, the app shows:

- **Today (Image 2):** all 4 captures appear as successful meals with full nutrition values (Хлеб ржаной 187 ккал, Окрошка на квасе 375 ккал, etc.). Server clearly processed them.
- **История (Images 3, 5):** EACH timestamp has TWO entries — one successful meal row AND one "Фото · ошибка · что-то пош... · не отправилось" outbox row. Same minute, same thumbnail.
- **Очередь (Image 1):** 4 items in «НЕ ОТПРАВИЛИСЬ», all marked `что-то пошло не так · повторить`. Same 4 captures.
- **Banner (all screens):** «4 не отправилось · посмотреть».

The data exists. The user sees their meals. But the queue and the History list insist 4 things failed. The discrepancy is structural: the **outbox** and the **meals cache** are two separate sources of truth for "what was captured", and there's nothing that reconciles them after the fact.

The root cause is one of:

- **(a) Old multi-step pipeline still partially active** (ADR-005 not fully implemented): photo upload + estimate succeed on server, but a later step (e.g., final `GET /meals/{id}`) times out or 5xx's. The outbox marks failure; the meal exists.
- **(b) New single-call pipeline (ADR-005) with response loss**: `POST /v1/meals/from-photo` succeeds server-side (meal row written, idempotency_key recorded), but the client never sees the `202 Accepted` response (network drop, app killed mid-parse). Outbox marks failure; the meal exists.

In both cases, ADR-005's `idempotency_key` correctly prevents *server-side* duplicates. What's missing is the **client-side acknowledgment** that the work is already done.

## Decisions

### 2.1 — Server: lookup endpoint by idempotency_key

Add a server endpoint that returns a meal by its client-generated idempotency_key:

```
GET /v1/meals?idempotency_key=<uuid>
→ 200 OK
  { "meal": { ... } }    if found
→ 404 Not Found
  if not found
```

Single concern, fast lookup against the unique partial index on `(user_id, idempotency_key)` (per ADR-005 §3.1). User-scoped: returns only meals for the authenticated user.

Alternatively, the existing `GET /v1/meals/{id}` could include `idempotency_key` in its response (per ADR-005 §3.1 it's already a column). But that requires the client to know `meal_id` first; the situations this ADR addresses are exactly those where the client **doesn't** know `meal_id`. So a separate by-key lookup is needed.

### 2.2 — Client: retry-time precheck

Before any retry of a `Stuck` outbox item, check the server first:

```kotlin
suspend fun retryStuckItem(item: OutboxItem) {
  // Precheck: maybe server already has it
  val existingMeal = mealsApi.getByIdempotencyKey(item.idempotencyKey).getOrNull()
  if (existingMeal != null) {
    // Server has it. We've been retrying something already done.
    outboxRepository.markConfirmed(item.id, mealId = existingMeal.id)
    cachedMealsDao.upsert(existingMeal)
    return  // do NOT re-upload
  }
  // No server record. Genuine retry.
  uploadAndProcess(item)
}
```

This precheck runs on:
- Manual «Повторить» button from inspector.
- Automatic retry by `OutboxProcessor` for items not yet in `Stuck`.
- App-launch reconciliation pass.

Cost: one extra HTTP GET per retry attempt. Cheap, especially compared to a full multipart upload.

### 2.3 — Client: post-sync reconciliation

After every `MealsRemote.refresh()` (the call that pulls meals from server into the cache), pass the received meals to a `MealReconciler`:

```kotlin
class MealReconciler @Inject constructor(
  private val outboxDao: OutboxDao,
  private val cachedMealsDao: CachedMealsDao,
) {
  suspend fun reconcileBatch(meals: List<RemoteMeal>) {
    for (meal in meals) {
      val key = meal.idempotencyKey ?: continue
      val outboxItem = outboxDao.findByIdempotencyKey(key) ?: continue
      if (outboxItem.state == OutboxState.Confirmed) continue
      // Found an outbox item that thinks it's still pending,
      // but the server already has the meal. Link them.
      outboxDao.update(
        id = outboxItem.id,
        state = OutboxState.Confirmed,
        linkedMealId = meal.id,
        errorCode = null,
        errorMessage = null,
      )
    }
  }
}
```

This runs every time meals are fetched — on app foreground, on FCM push, on periodic background sync, on manual pull-to-refresh. Cheap (single Room query per meal with idempotency_key). Idempotent (Confirmed → Confirmed is a no-op).

The effect on the user: within seconds of opening the app, ghost-stuck items resolve themselves silently. The banner depth drops, the queue empties, no user action required.

### 2.4 — App-launch reconciliation pass

On app cold-start, before the UI renders Today, run an explicit reconciliation pass for any outbox items currently in `Stuck`, `Uploading`, or `Queued`:

```kotlin
class OutboxStartupReconciler @Inject constructor(
  private val outboxDao: OutboxDao,
  private val mealsApi: MealsApi,
  private val reconciler: MealReconciler,
) : Initializer<Unit> {
  override fun create(context: Context) {
    runBlocking(Dispatchers.IO) {
      val pending = outboxDao.findInStates(
        listOf(OutboxState.Stuck, OutboxState.Uploading, OutboxState.Queued)
      )
      for (item in pending) {
        val server = mealsApi.getByIdempotencyKey(item.idempotencyKey).getOrNull()
        if (server != null) {
          outboxDao.update(item.id, state = OutboxState.Confirmed,
                           linkedMealId = server.id, errorCode = null, errorMessage = null)
        }
      }
    }
  }
}
```

This extends the `OnStartupReconciler` from ADR-006 §3.5 (which reverted stale `Uploading` items to `Queued`). The new behavior takes priority: if server has it, it's `Confirmed`; otherwise apply the existing stale-uploading logic.

For users hitting the bug shown in the screenshots, this means: **next launch of the app, the 4 ghost-stuck items resolve and disappear from the queue**. No manual «Повторить» needed.

### 2.5 — UI deduplication in History

The History list currently shows both meals (from `cached_meals`) and outbox items (from `outbox_items`) interleaved by capture time. This produces the visible duplicates. Apply deduplication at the query layer:

```sql
-- Pseudocode for the History repository query
SELECT * FROM cached_meals WHERE owner_id = ? AND DATE(eaten_at) = ?
UNION ALL
SELECT * FROM outbox_items WHERE owner_id = ?
  AND DATE(captured_at) = ?
  AND linked_meal_id IS NULL          -- exclude outbox items with a server counterpart
  AND state != 'Confirmed'             -- defensively exclude Confirmed too
ORDER BY captured_at DESC
```

The `outbox_items.linked_meal_id` column is set by the reconciler when it links the two. If non-null, the outbox item represents a logical capture that already exists as a `cached_meals` row — show the meal, hide the outbox row.

Conversely: if a `cached_meals` row has an `idempotency_key` matching a `Stuck` outbox item that hasn't been linked yet (edge case during a partial sync), prefer showing the meal and suppress the outbox row in the same way.

### 2.6 — UI representation of «true stuck» vs «zombie stuck»

Some outbox items are genuinely failed (server never accepted them). Others are zombies (server has the meal; client just didn't realize). The inspector should distinguish:

- **Genuine stuck** (`linked_meal_id IS NULL`, server has nothing): three actions — Повторить, Открыть в журнале (creates a draft for manual filling), Удалить.
- **Zombie stuck** (`linked_meal_id IS NOT NULL`, server has the meal): one action — «Очистить из очереди». No retry (would just duplicate work that's done). «Открыть в журнале» opens the linked meal directly.

After §2.4 launches reconciliation runs, the zombie cases should auto-clear in most situations. But the inspector still needs to handle the edge case where reconciliation hasn't yet completed but the user is looking at the queue.

Visual difference: zombie-stuck items render with a different status copy — «уже сохранено · убрать из очереди» — and a single button. Doesn't shout «ошибка» when nothing is actually wrong.

## Specifications

### 3.1 — `OutboxItem` schema additions

```sql
ALTER TABLE outbox_items
  ADD COLUMN linked_meal_id  TEXT NULL,           -- set when reconciliation finds a match
  ADD COLUMN reconciled_at   INTEGER NULL;         -- timestamp of reconciliation (debugging)
```

`linked_meal_id` is the server's meal id, stored as text (UUID). Migration: forward-only, default NULL. All existing rows start with NULL until next reconciliation pass.

### 3.2 — `MealsApi` additions

```kotlin
interface MealsApi {
  // existing endpoints...

  suspend fun getByIdempotencyKey(key: UUID): Result<RemoteMeal?>
}
```

Implementation hits `GET /v1/meals?idempotency_key=<uuid>`. Returns:
- `Result.success(meal)` on 200,
- `Result.success(null)` on 404,
- `Result.failure(...)` on any other error (5xx, network, etc. — these are retried by the caller).

A network failure on this precheck does NOT mark the outbox item more-stuck. The precheck is an optimization, not a precondition. If it fails, the caller proceeds to the original upload-and-process flow.

### 3.3 — Reconciliation surfaces

| Surface | Trigger | What it does |
|---|---|---|
| `MealReconciler.reconcileBatch` | every meals fetch (foreground, FCM, periodic) | links outbox items to fetched meals by idempotency_key |
| `OutboxStartupReconciler` | app cold start | for each non-Confirmed outbox item, GETs by idempotency_key; links if found |
| `OutboxProcessor.retryStuckItem` | manual «Повторить» or auto-retry | precheck before upload; link if server has it |

Each surface uses the same primitive (server lookup by idempotency_key) and the same link operation. Tested independently.

### 3.4 — Inspector copy and behavior

Replaces ADR-003 §2.3 inspector item layout for zombie-stuck items:

```
─────────────────────────────────────────────
ЗОМБИ-СОСТОЯНИЕ · 1                      ← new section, separate from «НЕ ОТПРАВИЛИСЬ»

[📷] Хлеб ржаной                              03:38
     уже сохранено · можно убрать            3 ч назад
     [Убрать из очереди]    [Открыть в журнале]
─────────────────────────────────────────────
НЕ ОТПРАВИЛИСЬ · 2                       ← actual stuck items only

[📷] Без названия                            04:15
     что-то пошло не так · повторить        12 мин назад
     [Повторить]  [Открыть в журнале]  [Удалить]
─────────────────────────────────────────────
```

Zombie section appears above "НЕ ОТПРАВИЛИСЬ" so the user sees the easy-to-clean ones first. After «Убрать из очереди» the item is just deleted from `outbox_items` — the linked meal in `cached_meals` is untouched.

Header copy: «Уже сохранено» (not «успех») — neutral, factual, doesn't celebrate. Brand-voice consistent with ADR-006.

### 3.5 — Banner depth calculation

The bottom banner (per ADR-006 §2.2) currently counts active queue + stuck items. After ADR-011, the stuck count excludes zombies:

```
banner_count_active = COUNT(outbox WHERE state IN (Queued, Uploading) AND linked_meal_id IS NULL)
banner_count_stuck  = COUNT(outbox WHERE state = Stuck AND linked_meal_id IS NULL)
```

Zombies are not counted in either. If the user has 4 ghost-stuck items and nothing else, the banner is silent until the inspector itself shows the zombie section.

This means: **opening the app after this fix ships, the user's current «4 не отправилось» banner becomes empty within seconds** (post-sync reconciliation links all 4 to existing meals). The 4 items move to «Уже сохранено» section briefly, then disappear after one user tap.

## Implementation tasks

One PR.

1. **Schema migration** per §3.1. Forward-only; backfill is NULL for existing rows.
2. **Backend endpoint** `GET /v1/meals?idempotency_key=<uuid>` per §2.1. Tested against the unique partial index from ADR-005.
3. **`MealsApi.getByIdempotencyKey`** per §3.2.
4. **`MealReconciler`** class per §2.3. Single method `reconcileBatch(meals)`. Unit-tested with fixture meals + fixture outbox states.
5. **Hook reconciliation into every meals fetch** — wrap `MealsRemote.refresh()`, FCM-driven `MealRefreshWorker`, and periodic background sync with a post-fetch `reconciler.reconcileBatch(result.meals)`.
6. **Retry precheck** per §2.2: insert the lookup-first step into `OutboxProcessor` before any `Stuck`-item retry, and inside the regular retry loop for non-`Stuck` items (as an optimization; doesn't change correctness there).
7. **`OutboxStartupReconciler`** per §2.4. Replaces the existing ADR-006 §3.5 startup reconciler — the new one does its job AND the new lookup. Lives in `androidx.startup`.
8. **History query update** per §2.5 to suppress outbox rows that have `linked_meal_id IS NOT NULL`.
9. **Inspector zombie section** per §3.4. New status copy, new button «Убрать из очереди» that deletes the outbox row.
10. **Banner count update** per §3.5.
11. **Tests:**
    - Unit: `MealReconciler.reconcileBatch` correctly transitions Stuck → Confirmed when fed a matching meal; ignores non-matching meals; idempotent.
    - Unit: `getByIdempotencyKey` returns null on 404, propagates errors on 5xx.
    - Integration: seed 1 outbox item in Stuck with idempotency_key=K, seed 1 meal with idempotency_key=K. Run reconciliation. Outbox state is Confirmed, `linked_meal_id` is set.
    - Integration on real data: replay the user's bug scenario — 4 captures, server has all 4 meals, 4 outbox items in Stuck. After app cold start, all 4 transition to Confirmed; banner depth = 0; History shows 4 meals (not 8 entries).
    - UI snapshot: Inspector with 2 zombie + 1 genuine stuck renders both sections correctly.

## Section overrides

- ADR-003 §2.3 inspector layout extended with the «Уже сохранено» section per §3.4 of this ADR.
- ADR-005 §2.5 ("Idempotency is structural") was correct but incomplete — this ADR adds the matching client-side lookup that uses the idempotency_key for reconciliation, not just for server-side dedup.
- ADR-006 §3.5 startup reconciler is replaced by §2.4 here.
- ADR-006 §2.2 banner state matrix unchanged but its inputs change per §3.5 (zombies don't count).

## Acceptance

- **The screenshot bug self-heals.** Given the user's current state (4 zombie-stuck outbox items, 4 corresponding meals on server), launching the app post-fix:
  - within 5 seconds, all 4 outbox items transition to Confirmed (state) with `linked_meal_id` set,
  - the bottom banner becomes silent,
  - History shows 4 entries (the meals), not 8 (no duplicates),
  - the inspector «Очередь» is empty.
- **No user action required.** The reconciliation is automatic on launch. The "Уже сохранено" section is only seen by users who happen to open the inspector during the brief window between launch and reconciliation completion.
- **Retry safety.** Pressing «Повторить» on a meal that already exists on server (idempotency_key match) does not re-upload. The outbox item links to the existing meal and goes to Confirmed.
- **Genuine failures still surface correctly.** An outbox item with no server counterpart stays Stuck, shows in «НЕ ОТПРАВИЛИСЬ», and offers Повторить / Открыть в журнале / Удалить per ADR-003.
- **History deduplication.** A timestamp with both a meal and an outbox item shows ONE entry (the meal), not two.
- **Banner correctness.** Banner depth equals the count of outbox items in `Queued | Uploading | Stuck` with `linked_meal_id IS NULL`. Zombies don't contribute.

## Out-of-band asks

1. **What about meals captured before idempotency_key was introduced?** Per ADR-005 §3.1, the `idempotency_key` column was added with a NULL backfill for pre-existing meals. Those meals can't be reconciled with old outbox items — but pre-ADR-005 outbox items also lack the key, so there's nothing to reconcile. No special handling; old data is what it is. Confirm acceptable.

2. **Anchor 03:02 visible on the Мой ритм screen.** Separate issue from this ADR; covered by ADR-010-followup §7.1. Recommended user action right now: set manual override to 13:00 in the «Начало дня» field on the same screen. Five-second fix while waiting for the algorithmic improvement.

3. **Hour-rounded display not applied yet.** ADR-010-followup §3.2 specified that displayed times round to nearest hour. The current Мой ритм screen still shows `03:02` — that ADR may not be implemented yet. Verify against the followup's implementation tasks.

4. **Should `reconciled_at` be exposed in the UI?** Per §3.1, the timestamp is stored for debugging. Default: not shown in UI. Helpful only for triaging reconciliation issues in support tickets.

5. **Should the reconciler also act on the desktop (Tauri) client?** This ADR is written assuming Android; the desktop has its own outbox/sync code per the original architecture. The same logic applies. If the desktop suffers from the same bug, port the reconciler there. Tracking this separately to avoid scope creep here.
