# ADR-006 · Error hygiene, reactivity, and restart resilience

> Companion to ADR-005. Hand both to the agent together — ADR-005 simplifies the architecture, ADR-006 enforces the discipline that makes the architecture actually work in production. This document is shorter and more prescriptive than the others; it's a hygiene contract, not a design.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-10 |
| Affects | every layer that can throw, observe, or render state. Specifically: `data/repository/`, `data/sync/`, `data/api/`, every ViewModel under `ui/feature/`, all composables that render error or status copy. |
| Risk | Low — defensive coding and observer correctness. No architectural change. |

---

## 1 · Context — the bugs that ADR-005 alone doesn't fix

Field evidence from 9 screenshots taken 2026-05-10 09:45–09:55:

**1.1 — Raw exceptions reaching the UI.** Record screen for a stuck capture displayed:

```
ошибка · Connect timeout has expired
[url=http://192.168.3.6:8000/meals?from=2026-05-08T17%3A53%3A38.101Z
&to=2026-05-11T17%3A53%3A38.101Z&limit=50&offset=0,
connect_timeout=unknown ms]
```

This is `ex.toString()` from a Ktor `HttpRequestTimeoutException` rendered into the UI. It leaks: the internal server URL, the user's local IP, the exception class structure, the request query parameters, the timeout configuration ("unknown ms" means timeout isn't even configured). Per the brand voice, none of this is acceptable user-facing copy.

**1.2 — `CancellationException` rendered as error state.** After force-restart, the same record showed:

```
ошибка · Job was cancelled
```

A coroutine `CancellationException` is the normal mechanism by which Android tears down work when the process dies. WorkManager is designed to retry the work transparently. Surfacing the cancellation as an error state is a defect.

**1.3 — Three surfaces show three different states for the same item.** At 09:49–09:50:
- `Today` row: "Фото · 09:49 · в очереди"
- `OutboxInspector`: "Очередь пуста · 0 записи"
- top banner: "Синхр. · 1 в очереди"

Three different views, three different state descriptions. The UI is reading from at least three independent paths instead of one shared `Flow`.

**1.4 — Reactivity broken in foreground.** User report (verbatim): "i only get update when i click in and out of draft forcing updates". Translation: the Record screen does not observe the meal/outbox state reactively. Cache is updated in Room, but the composable doesn't re-collect. The user has to leave and return to the screen to force a recomposition.

**1.5 — Stale errors persist after the underlying issue resolves.** After network returns to a previously-offline device, the error message ("Connect timeout has expired") stays on the Record screen unchanged. Either the worker isn't retrying, or the retry succeeds but the error string isn't cleared, or the cleared state isn't reaching the UI (linked to 1.4).

ADR-005 collapses the multi-step pipeline. None of the bugs above need that collapse to be fixable; they're software-quality issues that survive any architectural rework if the discipline isn't enforced.

## 2 · Decisions

### 2.1 — Errors are translated, never displayed raw

A central function `translateError(throwable: Throwable): UserError` is the **only** way an error reaches the UI. `UserError` is:

```kotlin
data class UserError(
  val code: String,           // stable machine-readable, e.g. "server_unreachable"
  val message: String,        // user-safe Russian, ≤ 80 chars
  val severity: Severity,     // Info | Warn | Error
  val retryable: Boolean,     // does the UI offer "Повторить"?
)
```

Every layer that catches throwables wraps them through `translateError`. ViewModels expose `Flow<UserError?>`, never `Flow<Throwable?>`. Composables render `UserError.message`, never anything else.

**Mapping table** (lives in `data/error/ErrorTranslator.kt`):

| Caught | Code | Message |
|---|---|---|
| `HttpRequestTimeoutException` / `SocketTimeoutException` | `server_unreachable` | "сервер не отвечает · повторим автоматически" |
| `UnknownHostException` / `NoRouteToHostException` | `no_network` | "нет соединения · подключись к сети" |
| `ConnectException` | `server_unreachable` | "сервер не отвечает · повторим автоматически" |
| `CancellationException` (from anywhere except user-initiated cancel) | n/a — **NOT shown as error**. State stays `Queued`. |
| HTTP 401 (not auto-handled by refresh) | `auth_lost` | "нужно войти заново" |
| HTTP 4xx other | `request_rejected` | "сервер не принял запись" |
| HTTP 5xx | `server_error` | "ошибка на сервере · повторим автоматически" |
| Any other | `unknown` | "что-то пошло не так · повторить" |

`ErrorTranslator` has unit tests for every entry. Adding a new mapping requires updating the table and the tests in the same commit.

**Forbidden in user-facing strings (lint-enforced):** any URL, any IP address, the words `timeout`, `cancellation`, `cancelled`, `exception`, `null`, `connect_timeout`, any class name with `Exception` or `Error` suffix. CI greps for these and fails the build.

The Record screen, the queue inspector, the journal row warn-state, the top banner — none of these has a path to a raw `Throwable.toString()`. There is no fallback that "passes through the original message if no mapping is found"; the `unknown` row in the table catches everything else.

### 2.2 — One Flow chain per data type, observed by all surfaces

Every piece of state has exactly one `Flow` source-of-truth in a repository, exposed through a domain interface, and consumed by every ViewModel that needs it. No surface reads from a different path.

**Today / Inspector / Record / banner all observe the same `Flow<DayState>`** (or its derivative slices) from `TodayRepository`. The repository's `Flow` is a `combine` of:

```kotlin
fun observeDay(date: LocalDate): Flow<DayState> = combine(
  cachedMealsDao.observeForDay(date),         // server-confirmed meals
  outboxDao.observeActiveByCapturedDay(date), // pending captures for the day
  syncStatusFlow,                              // network + worker status
) { meals, outbox, sync -> DayState(...) }
```

UI surfaces select what they need from `DayState` via `.map { ... }.distinctUntilChanged()`. They do not query `outboxDao` or `cachedMealsDao` directly. The banner's depth count, the journal row count, and the inspector's list all derive from the same `outbox` and `meals` flows, mathematically.

**Concrete enforcement.** A custom Detekt or ArchUnit rule:
- ViewModels under `ui/feature/today/` may inject only `TodayRepository`. Direct `OutboxDao` or `CachedMealsDao` injection in a Today-related ViewModel is a build error.
- Same rule per feature: `ui/feature/sync/` only sees `OutboxRepository`, etc.

This makes "two surfaces disagree about the same item" structurally impossible: they're reading the same emission.

**Reactivity correctness.** Every Compose screen that observes a `Flow` uses `collectAsStateWithLifecycle()` (not `collectAsState`), with a `Lifecycle.State.STARTED` minimum. ViewModels expose `StateFlow` via `stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), initial)` so cold flows don't restart on every recomposition.

**The "i had to leave and come back" bug** is fixed when:
1. ViewModel uses `stateIn(WhileSubscribed)` so the flow stays warm with a 5s grace period across configuration changes.
2. The Record screen reads its meal via the same shared flow as Today, which already updates when the cache refreshes.
3. No `LaunchedEffect(Unit) { fetch() }` is used as a substitute for proper `Flow` subscription. Anywhere we see `LaunchedEffect` triggering a one-shot fetch in a screen, that's a code smell — the data should already be flowing.

### 2.3 — Restart resilience: process death produces no error state

Force-restart, OOM-kill, system reclaim, APK update — all valid termination events. The contract:

- **Outbox items must never be in a state that requires the previously-running worker to come back.** State is durable in Room. The next worker run picks up from whatever state was committed.
- **`CancellationException` is never written to `OutboxItem.lastErrorMessage`.** When a worker is cancelled (via `CancellationException`, `JobCancellationException`, or any subtype), the outbox row's state reverts to its pre-attempt state (`Queued` if it was about to upload, `Uploading` stays as `Uploading` if mid-multipart — WorkManager will retry; `Estimating` is gone per ADR-005).
- **The worker's main `try`/`catch` distinguishes cancellation explicitly:**

```kotlin
try {
  processor.processOnce()
  Result.success()
} catch (cancellation: CancellationException) {
  // do NOT mark anything failed. WorkManager will retry; the next run picks up.
  throw cancellation  // re-throw so structured concurrency unwinds correctly
} catch (other: Throwable) {
  Result.retry()  // standard retry path
}
```

- **WorkManager retry policy:** exponential backoff (per ADR-003 §2.1: 1, 2, 4, 8, 16 min). `setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)`.
- **Next-launch reconciliation:** `OnStartupReconciler` runs at app launch (in a `Initializer` from `androidx.startup`). It scans outbox items in `Uploading` state with `lastAttemptAt > 5 min ago` and reverts them to `Queued`. This handles the case where the previous process died mid-attempt and `Uploading` is stale. This is best-effort; the structural fix is ADR-005's idempotency_key, which makes a duplicate retry harmless even if the previous attempt actually succeeded server-side.

### 2.4 — Stale errors clear deterministically

`OutboxItem.lastErrorMessage` and `lastErrorCode` are cleared on these transitions:

- `Stuck` → `Queued` (manual retry from inspector or banner): cleared.
- `Queued` → `Uploading` (worker picks up): cleared.
- Any state → `Confirmed`: cleared.
- Network status changes from offline to online: a worker run is triggered; the run's first action is to clear the error fields on items it picks up.

The Record screen, when rendering an outbox-pending meal, reads `lastErrorMessage` from the live `Flow`. When the field clears, the UI updates within one frame.

The user's reported sequence ("offline → timeout error → online → still timeout error") becomes structurally impossible: as soon as connectivity returns, the worker triggers, picks up the queued item, clears the error, and either succeeds or generates a new translated error.

## 3 · Specifications

### 3.1 — `UserError` model and the translator

```kotlin
// domain/model/UserError.kt
data class UserError(
  val code: String,
  val message: String,
  val severity: Severity,
  val retryable: Boolean,
) {
  enum class Severity { Info, Warn, Error }
}

// data/error/ErrorTranslator.kt
class ErrorTranslator @Inject constructor() {
  fun translate(t: Throwable): UserError = when {
    t is CancellationException -> error("CancellationException must not be translated; check call site")
    t is HttpRequestTimeoutException -> serverUnreachable
    t is SocketTimeoutException -> serverUnreachable
    t is UnknownHostException -> noNetwork
    t is ConnectException -> serverUnreachable
    t is ResponseException && t.response.status.value == 401 -> authLost
    t is ResponseException && t.response.status.value in 400..499 -> requestRejected
    t is ResponseException && t.response.status.value in 500..599 -> serverError
    else -> unknown
  }

  private val serverUnreachable = UserError("server_unreachable", "сервер не отвечает · повторим автоматически", Severity.Warn, retryable = true)
  // ... others ...
}
```

Anywhere code currently does `errorMessage = e.message ?: e.toString()` or similar, replace with:

```kotlin
val userError = errorTranslator.translate(e)
outboxRepository.markStuck(item.id, userError.code, userError.message)
```

### 3.2 — Lifecycle-correct Flow consumption

Every `@Composable` that reads a `Flow` uses this idiom:

```kotlin
val state by viewModel.uiState.collectAsStateWithLifecycle()
```

ViewModels expose `StateFlow` via:

```kotlin
val uiState: StateFlow<TodayUiState> = repository.observeDay(date)
  .map { it.toUiState() }
  .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), TodayUiState.Loading)
```

The `WhileSubscribed(5_000)` keeps the flow warm across configuration changes (rotation, dark-mode switch) without restarting it, but cancels it 5 seconds after the last subscriber leaves — important for memory.

A custom Detekt rule rejects `collectAsState` in favor of `collectAsStateWithLifecycle` outside of `@Preview` composables.

### 3.3 — Single-source-of-truth enforcement

Repository contracts (excerpt):

```kotlin
interface TodayRepository {
  fun observeDay(date: LocalDate): Flow<CachedView<DayState>>
}

interface OutboxRepository {
  fun observe(): Flow<List<OutboxItem>>
  fun observeForDay(date: LocalDate): Flow<List<OutboxItem>>
  fun observeActiveCount(): Flow<Int>
  // mutators...
}

interface SyncRepository {
  fun observeSyncStatus(): Flow<SyncStatus>
  // ...
}
```

The `Today` `DayState` derived inside `TodayRepository.observeDay` already includes `pendingItems`, `confirmedMeals`, and `kpiTotals`. The Today ViewModel does not need a second injection of `OutboxRepository` to count pending rows.

The `OutboxInspectorViewModel` injects `OutboxRepository`. The banner-state ViewModel injects `OutboxRepository.observeActiveCount() + observeStuckCount()` plus `SyncRepository.observeSyncStatus()`. Same source — every count consistent.

**Architecture test (ArchUnit)** at `app/src/test/.../ArchitectureTest.kt`:

```kotlin
@Test fun todayViewModels_only_use_TodayRepository() {
  classes()
    .that().resideInAPackage("..ui.feature.today..")
    .and().areAssignableTo(ViewModel::class.java)
    .should().onlyDependOnClassesThat().resideInAnyPackage(
      "..domain..", "..ui.feature.today..", "kotlinx.coroutines..", "kotlin.."
    )
    .check(allClasses)
}
```

Repeated per feature package. CI fails on violation.

### 3.4 — Worker resilience contract

`OutboxWorker.doWork()` skeleton:

```kotlin
override suspend fun doWork(): Result {
  return try {
    val processor = buildProcessor()
    processor.processOnce()
    Result.success()
  } catch (cancellation: CancellationException) {
    // Process death, system reclaim, user-cancelled work — all valid.
    // Outbox state is durable in Room; the next run resumes.
    // Do NOT translate, do NOT mark anything failed.
    throw cancellation
  } catch (transient: Throwable) {
    val translated = errorTranslator.translate(transient)
    // Stuck-state decision is per-item inside processor; here we just request retry.
    if (runAttemptCount < MAX_ATTEMPTS) Result.retry() else Result.failure()
  }
}
```

`processor.processOnce()` per-item logic also catches `CancellationException` separately and re-throws without state mutation:

```kotlin
for (item in queue.retryableItems()) {
  try {
    process(item)
  } catch (cancellation: CancellationException) {
    throw cancellation  // unwind without touching item's state
  } catch (other: Throwable) {
    val ue = errorTranslator.translate(other)
    queue.markStuckOrRetry(item.id, ue, isStuckCondition(item, other))
  }
}
```

### 3.5 — Startup reconciler

```kotlin
class OutboxStartupReconciler @Inject constructor(
  private val outboxDao: OutboxDao,
  private val clock: Clock,
) : Initializer<Unit> {
  override fun create(context: Context) {
    runBlocking {
      val cutoff = clock.now() - 5.minutes
      outboxDao.revertStaleUploadingToQueued(cutoff)
    }
  }
  override fun dependencies() = emptyList<Class<out Initializer<*>>>()
}
```

Registered in `AndroidManifest.xml` via `androidx.startup`. Runs on app launch before any UI. Idempotent.

## 4 · Section overrides

### 4.1 Supersedes parts of `T3 · Outbox + sync infrastructure`

- The retry/error handling paragraph in T3 is amended by §2.1 (translation), §2.4 (stale clearing), §3.4 (worker resilience).
- T3's bare `OutboxItem.errorMessage: String?` becomes `errorCode: String?` + `errorMessage: String?` per §2.4. Translation produces both atomically.

### 4.2 Supersedes parts of `T5 · Today + Stats`

- T5 specified `TodayRepository` and various separate observers. §3.3 of this ADR consolidates: Today reads only from `TodayRepository`; Inspector reads from `OutboxRepository`; banner combines via a derived ViewModel. Single source per feature.

### 4.3 Compatible with `ADR-003 · Outbox state visibility`

- ADR-003 §2.3's `lastErrorMessage` field is exactly what §2.1 of this ADR is filling correctly via the translator. Compatible.

### 4.4 Compatible with `ADR-005 · Single-call photo capture`

- ADR-005's reduction in moving parts makes §2.4 (stale-error clearing) easier — fewer states means fewer transitions to handle. Both ADRs strengthen each other.

## 5 · Implementation tasks

One PR, in order:

1. **`UserError` and `ErrorTranslator`** per §3.1. Unit tests for every mapping. Lint rule rejecting raw `Throwable` in user-facing fields.
2. **Worker rewrite** per §3.4. `CancellationException` unwinds cleanly without state mutation. Per-item translation goes through `ErrorTranslator`.
3. **Banned-words lint** per §2.1: any user-facing string containing URL/IP/`Exception` substring fails the build.
4. **Lifecycle-correct collection.** Sweep every `@Composable` for `collectAsState`, replace with `collectAsStateWithLifecycle`. Sweep ViewModels for raw `flow` exposure, wrap with `stateIn(WhileSubscribed(5_000))`.
5. **Architecture test** per §3.3. ArchUnit module-boundary tests in CI.
6. **Repository consolidation.** `TodayRepository.observeDay` produces a `DayState` that combines outbox + cached meals + sync status. Today / Inspector / banner ViewModels refactored to consume it (or its slices).
7. **Stale-error clearing** per §2.4. `markUploading`, `markConfirmed`, manual `Повторить`, and connectivity-online events all clear `errorCode` + `errorMessage` atomically in one transaction.
8. **Startup reconciler** per §3.5. Reverts stale `Uploading` items to `Queued` at app launch.
9. **Tests:**
   - Unit: `ErrorTranslator` for every entry in §2.1's table.
   - Unit: cancellation through worker doesn't mutate outbox state.
   - Instrumented: capture offline → wait → user opens Record screen → translated error visible. Restore network → worker fires → error clears within 1s on the same screen, no manual leave-and-return required.
   - Instrumented: capture, force-stop the app (`adb shell am force-stop`), restart the app — outbox item is in `Queued`, no `Job was cancelled` text anywhere in the UI, worker re-runs and completes.
   - Architecture: `OutboxInspectorViewModel` and `TodayViewModel` cannot compile if they accidentally import each other's repositories.
10. **Manual verification with the bug screenshots:**
    - The exact "Connect timeout has expired [url=...]" error string never appears anywhere — replaced by "сервер не отвечает · повторим автоматически".
    - "Job was cancelled" never appears in any user-visible context.
    - With one captured photo pending, the journal row, the inspector, and the banner all show the same item state.

## 6 · Acceptance

- **No raw exceptions in UI.** A grep over all source files for `e.message`, `throwable.toString()`, `it.localizedMessage`, etc. inside Composable or ViewModel scopes returns zero hits. All such accesses live in `ErrorTranslator` only.
- **No URLs or IPs in user-facing strings.** Lint catches.
- **Three-surface consistency.** With one item in any pending state, programmatic check: Today's row count for that item, Inspector's "Активные" count, and banner depth are all `1`. Test repeatable across the matrix of states.
- **Reactivity without leave-and-return.** Manual: capture, observe pending row in journal. Mock the worker to succeed. Within 2 seconds, journal row updates to confirmed values, with no user interaction. Repeat on the Record screen if open: numbers populate without leaving the screen.
- **Force-stop transparency.** Manual: capture, `adb shell am force-stop com.glucotracker.mobile`, relaunch. Expected: outbox item is back to `Queued` (revert from stale `Uploading`), worker runs, item completes. No "Job was cancelled" text. No error message of any kind.
- **Stale-error self-heal.** Manual: enable airplane mode, capture, wait 90s. Open Record screen — see translated server-unreachable message. Disable airplane mode. Within 5s of network return, the error message disappears from Record screen without user interaction; worker retries; item progresses to `Confirmed`.

## 7 · Out-of-band asks

1. **Backend connect_timeout.** The bug message says `connect_timeout=unknown ms` — Ktor isn't configured with explicit timeouts. Set `engine { requestTimeout = 30.seconds; connectTimeoutMillis = 10_000 }` (or equivalent for the chosen engine). Confirm or adjust before §3.4 ships.
2. **`androidx.startup` vs `Application.onCreate`.** §3.5 uses startup for the reconciler. If the project doesn't already include `androidx.startup-runtime`, add it. Confirm.
3. **ArchUnit dependency.** §3.3's enforcement uses ArchUnit. If you don't want a new test dep, a simpler variant is a `gradle :app:check` task that greps imports. Default if delegated: ArchUnit; the dep is small and the rules read better.
4. **Russian copy review.** The translated messages in §2.1 are drafts. Confirm or revise — especially "повторим автоматически" (informational reassurance) vs "повторить" (action button). Default if delegated: as written.
5. **Breaking out `OutboxItem.lastErrorCode` vs `lastErrorMessage`.** §3.1 splits them; existing migrations may already have only one field. Confirm whether the Room migration is acceptable or whether to keep one combined field. Default: split for testability; migrate forward.
