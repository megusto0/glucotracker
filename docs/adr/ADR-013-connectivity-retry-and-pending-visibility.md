# ADR-013 · Connectivity-driven retry and pending-state visibility

> Closes a gap that survived ADR-005 / ADR-006 / ADR-011: when network restores, pending captures don't automatically retry. The user has to manually tap «Повторить» or wait up to 15 minutes for the periodic worker. Three concrete mechanisms make pending captures resolve themselves without user action, and a row-state taxonomy lets the user see what the system is actually doing.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-12 |
| Affects | `data/sync/OutboxProcessor`, new `data/connectivity/ConnectivityMonitor`, `app/MainActivity` lifecycle hook, row-state rendering on Today/History/Inspector |
| Risk | Low — additive triggers and visibility; no schema changes |

---

## Context — what the screenshots showed

A photo captured at 03:53 over a flaky/offline connection. At 04:01 (8 minutes later):

- Network **is** available (Nightscout pulled fresh glucose 5,3 with sparkline updates).
- Photo still shows `ждёт сети · 8 мин назад` in the queue inspector.
- Today's KPIs show 0 (the meal hasn't been processed).
- The «УЖЕ СОХРАНЕНО · 5» section confirms ADR-011 reconciliation is working for older zombies — that path is healthy.

User report: "If I send a photo when I have no internet, doesn't look like it tries to send it when I have internet."

The diagnosis: between the moment network restored and the next periodic worker slot, the photo sits idle. ADR-003 §3.2 specced `PeriodicWorkRequest` at 15-minute intervals as the fallback. That's the only thing waking the worker right now. The connectivity-triggered immediate retry mentioned in ADR-003 §2.5 either isn't implemented or doesn't reach the WorkManager scheduler.

Also: from the user's seat, the row reads "ждёт сети 8 мин назад" with no indication of whether the system is *currently attempting*, *waiting for next slot*, or *genuinely offline*. The three states look identical. Without visibility into what's happening, the only available action is manual retry — which defeats the offline-first promise of the architecture.

## Decisions

### 2.1 — Native WorkManager network constraint

All photo-upload work requests are enqueued with explicit network constraints:

```kotlin
val request = OneTimeWorkRequestBuilder<OutboxUploadWorker>()
  .setInputData(workDataOf("outbox_item_id" to itemId.toString()))
  .setConstraints(
    Constraints.Builder()
      .setRequiredNetworkType(NetworkType.CONNECTED)
      .build()
  )
  .setBackoffCriteria(
    BackoffPolicy.EXPONENTIAL,
    30, TimeUnit.SECONDS
  )
  .build()

workManager.enqueueUniqueWork(
  "outbox-upload-${itemId}",
  ExistingWorkPolicy.KEEP,    // never queue duplicate work for same item
  request
)
```

With `NetworkType.CONNECTED`, the OS itself holds the work in deferred state when offline and fires it within seconds of connectivity restoring. No custom retry-on-connectivity glue needed for this part.

`enqueueUniqueWork` with `ExistingWorkPolicy.KEEP` ensures double-tapping «Повторить» or queueing the same item from multiple sites doesn't pile up redundant work — only one upload attempt per item is ever scheduled at a time.

### 2.2 — Connectivity callback for immediate sweep

Register a `ConnectivityManager.NetworkCallback` in the Application's `onCreate`:

```kotlin
class GTApplication : Application() {
  @Inject lateinit var outboxRepository: OutboxRepository
  @Inject lateinit var workManager: WorkManager

  override fun onCreate() {
    super.onCreate()
    val cm = getSystemService(ConnectivityManager::class.java)
    cm.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
      override fun onAvailable(network: Network) {
        scope.launch {
          // 1. Revert any items in Stuck whose last error was network-related.
          //    They get one fresh try; if it fails again on real network, back to Stuck.
          outboxRepository.revertNetworkStuckItems()

          // 2. Kick a one-time sweep that re-enqueues every Queued item.
          workManager.enqueueUniqueWork(
            "outbox-connectivity-sweep",
            ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<OutboxSweepWorker>().build()
          )
        }
      }
    })
  }
}
```

`OutboxSweepWorker` iterates the outbox and enqueues per-item upload work (which respects the network constraint from §2.1).

Why both this callback AND the WorkManager constraint? Because:
- The constraint handles unique items already in WorkManager's queue.
- The callback handles items that **failed and transitioned to Stuck** before constraints became relevant — those need to come out of Stuck before any worker will pick them up.
- The callback also unblocks edge cases where the worker has already exhausted retries but network was the issue all along.

`revertNetworkStuckItems` queries for outbox items with `state = Stuck` AND `lastErrorCode IN ('server_unreachable', 'no_network')` (the codes from ADR-006 §2.1) and sets them to `Queued`, clearing error fields per ADR-006 §2.4.

### 2.3 — Foreground-triggered retry

When the user opens the app, run an immediate check: if there are pending items AND network is available, kick a sweep. Don't wait for the periodic worker.

```kotlin
class MainActivity : ComponentActivity() {
  @Inject lateinit var connectivityChecker: ConnectivityChecker
  @Inject lateinit var outboxRepository: OutboxRepository
  @Inject lateinit var workManager: WorkManager

  override fun onStart() {
    super.onStart()
    lifecycleScope.launch {
      val hasPending = outboxRepository.observeActiveCount().first() > 0
      if (hasPending && connectivityChecker.isOnline()) {
        workManager.enqueueUniqueWork(
          "outbox-foreground-sweep",
          ExistingWorkPolicy.KEEP,
          OneTimeWorkRequestBuilder<OutboxSweepWorker>().build()
        )
      }
    }
  }
}
```

Three triggers now cover the bases:
1. **Item enqueued → individual work request fires** (with network constraint).
2. **Network restored → connectivity callback sweep**.
3. **App opened → foreground sweep**.

Plus the existing periodic 15-min fallback for cases where none of the above fire (e.g., app killed + system Doze for hours).

### 2.4 — Pending-state row vocabulary expansion

The current row state on Today / Inspector shows opaque "ждёт сети" for everything between "queued" and "successfully uploaded". Split this into states that **describe what's actually happening right now**:

| Row state | When | Copy on the row |
|---|---|---|
| `Just queued` | `state=Queued`, `attempts=0` | `в очереди · отправим скоро` |
| `Trying now` | `state=Uploading`, within last 30s of `lastAttemptAt` | `пробуем сейчас` |
| `Waiting for retry, online` | `state=Queued`, `nextAttemptAt > now`, network available | `следующая попытка через {N} сек` |
| `Waiting for network` | `state=Queued`, network unavailable | `ждёт сети` |
| `Estimating` | server has the meal, `estimate_status=estimating` | `оценивается ···` |
| `Estimating but slow` | `estimating > 10 min` (per ADR-008 §2.5) | `оценка задерживается` |
| `Stuck` | terminal (cap reached or 4xx) | `ошибка · повторить` |
| `Confirmed` | meal arrived in cache | render meal values per ADR-001 |

The categorization is computed by the row composable from `(OutboxItem.state, lastAttemptAt, nextAttemptAt, ConnectivityStatus, linked meal estimate_status)` — all of which are already in scope.

«ждёт сети» now ONLY appears when the device is genuinely offline. When online with retry scheduled, the user sees a count-down: `следующая попытка через 12 сек` (auto-decrements). The countdown updates every second while the screen is in foreground; off-foreground it stops re-rendering (no battery drain).

This is the most important change for user perception. The system is doing the same work; the user simply now knows what stage it's in.

### 2.5 — Periodic worker cadence adapts to outbox state

ADR-003 §3.2 specced `PeriodicWorkRequest` at 15 minutes. Keep that as the safety-net baseline. Add a second `PeriodicWorkRequest`:

- **Standard** (always running): 15-minute interval. Reconciliation + estimation status checks (per ADR-011).
- **Active recovery** (only running when outbox has pending items): 5-minute interval. Same sweep logic. Cancelled when outbox empty.

Implementation: a `Flow<Boolean>` listening to `outboxRepository.observeActiveCount() > 0`; on transition to true, enqueue the 5-min periodic; on transition to false, cancel it.

The 5-min cadence is the "background safety net" — but with §2.1, §2.2, §2.3 firing first, the safety net should rarely be the thing that resolves a pending item. It exists for edge cases (Doze mode, app force-stopped, connectivity callback missed).

### 2.6 — Inspector grammar and copy polish

Visible bug: inspector header reads «1 записи». Russian grammar requires «1 запись» (singular nominative) or «1 запись в очереди» — never «1 записи» (singular genitive without a counted-noun form).

```kotlin
fun pluralizeRecord(count: Int): String = when {
  count % 10 == 1 && count % 100 != 11 -> "$count запись"
  count % 10 in 2..4 && count % 100 !in 12..14 -> "$count записи"
  else -> "$count записей"
}
```

Russian numeric agreement rule: 1 → запись, 2-4 → записи, 5+ → записей, plus the 11-14 exception. Helper covers the inspector header AND the bottom banner: «1 запись · посмотреть» instead of «1 в очереди» reads more naturally.

(Banner copy was specced as «1 в очереди» in ADR-003 §2.2 which works because «в очереди» is uncountable. But the inspector's «1 записи» is wrong. Use the pluralize helper everywhere a count of records appears.)

## Specifications

### 3.1 — `ConnectivityChecker` and `ConnectivityMonitor`

```kotlin
interface ConnectivityChecker {
  fun isOnline(): Boolean
  fun observeStatus(): Flow<ConnectivityStatus>
}

sealed class ConnectivityStatus {
  data object Online : ConnectivityStatus()
  data object Offline : ConnectivityStatus()
  data object Restoring : ConnectivityStatus()   // transition state, brief
}
```

`isOnline()` returns the current cached value from the connectivity callback (no synchronous network probe).

`observeStatus()` emits whenever `onAvailable`, `onLost`, or `onUnavailable` fires.

The single `ConnectivityMonitor` lives in `Application` scope, owns the callback registration, and exposes the flow. Other components inject `ConnectivityChecker` for testability.

### 3.2 — `OutboxRepository.revertNetworkStuckItems`

```kotlin
suspend fun revertNetworkStuckItems(): Int {
  val networkErrorCodes = setOf("server_unreachable", "no_network", "connect_timeout")
  return outboxDao.revertStuck(networkErrorCodes)  // returns count reverted
}
```

The SQL:

```sql
UPDATE outbox_items
SET state = 'Queued',
    last_error_code = NULL,
    last_error_message = NULL,
    next_attempt_at = NULL,
    entered_current_state_at = ?
WHERE state = 'Stuck'
  AND last_error_code IN ('server_unreachable', 'no_network', 'connect_timeout')
  AND linked_meal_id IS NULL    -- don't touch zombie-stuck items per ADR-011
```

Returns count of rows updated. If non-zero, that becomes the message in a transient toast: «Возобновили {N} {записей|записи|запись}». Optional; can be silent.

### 3.3 — Row state computation

```kotlin
fun computeRowState(
  item: OutboxItem,
  linkedMeal: Meal?,
  connectivity: ConnectivityStatus,
  now: Instant
): RowState = when {
  item.state == OutboxState.Confirmed && linkedMeal != null ->
    when (linkedMeal.estimateStatus) {
      "estimating" -> {
        val elapsed = now - linkedMeal.estimateStartedAt
        if (elapsed > Duration.minutes(10)) RowState.EstimatingButSlow
        else RowState.Estimating
      }
      "succeeded" -> RowState.MealValues(linkedMeal)
      else -> RowState.Stuck(item.lastErrorMessage)
    }
  item.state == OutboxState.Stuck -> RowState.Stuck(item.lastErrorMessage)
  item.state == OutboxState.Uploading -> {
    val sinceLastAttempt = now - (item.lastAttemptAt ?: now)
    if (sinceLastAttempt < Duration.seconds(30)) RowState.TryingNow
    else RowState.WaitingForRetry(
      secondsLeft = ((item.nextAttemptAt ?: now) - now).inWholeSeconds.coerceAtLeast(0)
    )
  }
  item.state == OutboxState.Queued -> when (connectivity) {
    ConnectivityStatus.Offline -> RowState.WaitingForNetwork
    else -> {
      if (item.attempts == 0) RowState.JustQueued
      else RowState.WaitingForRetry(
        secondsLeft = ((item.nextAttemptAt ?: now) - now).inWholeSeconds.coerceAtLeast(0)
      )
    }
  }
  else -> RowState.Unknown
}
```

The composable observes `combine(item, linkedMeal, connectivity, ticker(1s))` and emits new `RowState` per second while visible, only when state changes (use `distinctUntilChanged`).

### 3.4 — Adaptive periodic worker

```kotlin
class OutboxScheduler @Inject constructor(
  private val workManager: WorkManager,
  private val outboxRepository: OutboxRepository,
  private val scope: CoroutineScope,
) {
  init {
    scope.launch {
      outboxRepository.observeActiveCount()
        .map { it > 0 }
        .distinctUntilChanged()
        .collect { hasPending ->
          if (hasPending) enqueueActiveRecoveryPeriodic()
          else cancelActiveRecoveryPeriodic()
        }
    }
  }

  private fun enqueueActiveRecoveryPeriodic() {
    val request = PeriodicWorkRequestBuilder<OutboxSweepWorker>(
      5, TimeUnit.MINUTES,
      1, TimeUnit.MINUTES    // flex interval
    )
      .setConstraints(
        Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
      )
      .build()
    workManager.enqueueUniquePeriodicWork(
      "outbox-active-recovery",
      ExistingPeriodicWorkPolicy.KEEP,
      request
    )
  }

  private fun cancelActiveRecoveryPeriodic() {
    workManager.cancelUniqueWork("outbox-active-recovery")
  }
}
```

The 15-min standard periodic continues separately (it does reconciliation per ADR-011, not just outbox sweeps).

## Implementation tasks

One PR.

1. **WorkManager constraints** per §2.1. Verify every code path that enqueues photo-upload work uses `NetworkType.CONNECTED` and `enqueueUniqueWork`. Audit for redundant enqueue points.
2. **`ConnectivityMonitor`** per §3.1. Registered in Application's `onCreate`.
3. **`revertNetworkStuckItems` SQL** per §3.2. Exposed on `OutboxRepository`.
4. **Connectivity callback** per §2.2 in Application. On `onAvailable`, revert network-stuck + sweep.
5. **Foreground retry** per §2.3 in `MainActivity.onStart`.
6. **Row state vocabulary** per §2.4 + §3.3. Refactor row composables on Today and Inspector to consume `RowState` instead of raw outbox state.
7. **Adaptive periodic worker** per §2.5 + §3.4.
8. **Pluralize helper** per §2.6. Apply to inspector header AND any other spot showing record counts.
9. **Tests:**
   - Unit: `computeRowState` produces correct output for every (state, connectivity) combination in §3.3.
   - Unit: `revertNetworkStuckItems` reverts only items with matching error codes AND `linked_meal_id IS NULL`.
   - Unit: pluralize 0, 1, 2, 4, 5, 11, 21, 22, 25 → correct Russian.
   - Integration: airplane-mode toggle + photo capture flow. Sequence:
     1. Enable airplane mode.
     2. Capture photo → row appears as `JustQueued` → `WaitingForNetwork` (within 5s when WorkManager realizes constraint isn't met).
     3. Disable airplane mode → within 2 seconds, row transitions to `TryingNow`.
     4. Mock server to succeed → row becomes `Estimating` → `MealValues`.
     5. End-to-end takes <5 seconds after airplane-mode disable.
   - Integration: airplane mode for 30 min + 1 photo, then re-enable. Same outcome.

## Acceptance

- **No manual «Повторить» needed in the airplane-mode case.** Capture offline → enable airplane mode for 5+ min → disable → within seconds, photo uploads automatically. User doesn't open the inspector at all.
- **Row state distinguishes online-waiting from offline.** Toggle airplane mode while viewing Today with a pending row. Row reads `ждёт сети` when offline; reads `следующая попытка через N сек` when online but between attempts; reads `пробуем сейчас` during an attempt.
- **Countdown updates.** `следующая попытка через 12 сек` counts down to 11, 10, 9... in real time on Today.
- **Grammar correct.** Inspector header reads `1 запись`, `2 записи`, `5 записей` per Russian numeric agreement.
- **Adaptive periodic.** Confirm via WorkManager log/inspector tool: when outbox is empty, only `outbox-periodic-15m` is scheduled; when ≥1 pending, `outbox-active-recovery` (5-min) is ALSO scheduled. Cancellation on empty.
- **No spurious enqueues.** Capturing a photo, then immediately tapping «Повторить» from inspector should NOT create two upload work entries. `enqueueUniqueWork` with `KEEP` policy means the second call is a no-op.

## Section overrides

- ADR-003 §2.5 (transitions) mentioned the connectivity-online trigger; §2.2 here is the implementation that fulfills it.
- ADR-003 §3.2 (worker scheduling) is extended by §3.4 (adaptive periodic). 15-min standard stays; 5-min adaptive runs only during pending state.
- ADR-006 §3.4 (worker resilience) is unchanged; this ADR adds new entry points for the same worker logic.
- ADR-011 (reconciliation) is unaffected; reconciliation runs in the standard 15-min periodic.

## Out-of-band asks

1. **Battery impact of 1-second ticker for countdown.** §3.3 ticks every 1 second while a pending row is visible. For a row stuck for 90 seconds, that's 90 redraws. Compose handles this efficiently in practice (only the countdown text recomposes), but verify on a low-end device. Default if delegated: ship; revisit only if measured drain is meaningful.

2. **Should `OutboxSweepWorker` be a separate worker class or just re-enqueue per-item work?** §2.2 implies a sweep worker that re-enqueues per-item. Could also be a direct iteration that calls each item's work. Default: separate sweep worker for clarity; reuses the per-item upload worker for actual upload.

3. **What if multiple photos are captured offline?** All get the same network constraint, all fire near-simultaneously when network returns. With FCM-driven completion (per ADR-005 §2.4), this is fine. But Gemini concurrent quota might be a concern — server-side rate limit if needed. Default: don't worry until observed.

4. **Pluralize helper coverage.** §2.6 covers `запись`. Other countable nouns in the app (e.g., «эпизоды» in stats, «приёмы» in Tarelka) have the same grammatical issue. Audit and extend the helper. Out of scope here; tracking as separate polish.

5. **Should «следующая попытка через N сек» round to higher units for long waits?** A 14-minute wait shouldn't show 847 seconds. Default rule: `< 60s` → seconds, `60s..600s` → "через N минут", `>600s` → "через ~15 минут" (round-to-quarter). Implement at the formatter level.
