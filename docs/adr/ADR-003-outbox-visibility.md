# ADR-003 · Outbox state visibility and stuck-item recovery

> Companion to ADR-001 and ADR-002. Hand all three to the agent alongside the original prompt files. This document amends `T3`, `T5`, `T11`, `T12`, and the offline banner spec from `AND-4`.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-10 |
| Affects | `glucotracker-android-prompts.md` (T3, T5, T11, T12), `glucotracker-multiuser-foodflavor-prompts.md` (AND-4 banner) |
| Risk | Low to medium — adds a new terminal state and a new sheet, but no schema-breaking change. |

---

## 1 · Context

Screenshots from 2026-05-10 spanning **00:05 → 04:53** (almost five hours, real device, real backend) all show the same banner copy:

```
Синхр. · 2 в очереди
```

Five hours, the same two items, no change. This is silent failure: the queue counter is honest, but the *meaning* of "в очереди" is ambiguous. The user has no way to find out which records are stuck, why they're stuck, or what to do. Worst case: the user took a meal photo, sees the row appear in Today, walks away believing it's saved — and several hours later it still hasn't reached the server.

The current contract in `T3` says: *"cap at 5 attempts with exponential backoff, then leave in Queued and surface a banner."* But:

- "Leave in Queued" means the periodic 15-minute worker keeps retrying forever in some implementations, attempts counter or no.
- The banner copy doesn't distinguish actively-retrying from given-up.
- There is no per-row indicator that an estimate has been pending for hours.
- The queue inspector specced in `T11` exists but isn't reachable from the banner.
- No notification fires when an item permanently fails.

The user's trust in auto-sync — which is the entire premise of "capture and walk away" UX — collapses the moment the queue counter gets stuck. ADR-003 fixes the state model, the visibility surface, and the recovery affordances together.

## 2 · Decisions

### 2.1 — One terminal state: `Stuck`

Add `Stuck` as an explicit terminal state on `OutboxItem.state`:

```
Queued       — never sent yet
Uploading    — multipart in flight
Estimating   — server received, Gemini working
Confirmed    — server returned canonical meal (terminal success)
Stuck        — exceeded retry budget; needs user action (terminal failure)
```

`Conflict` from earlier specs is folded into `Stuck`. The user-facing distinction between "server said 409" vs "5xx exhausted" vs "Gemini timed out" doesn't help — it's all the same situation: this item is not going through automatically, you need to look at it.

Transition rules:

- **Upload exhaustion.** 5 upload attempts with exponential backoff (1, 2, 4, 8, 16 min) → next failure → `Stuck`.
- **Estimate timeout.** An item in `Estimating` for > 10 minutes wall-clock → `Stuck`. (Gemini routinely returns within 60–180 seconds; ten minutes is generous.)
- **Server rejection.** Any 4xx response (except 401, which triggers token refresh) → immediately `Stuck`. No retry, since 4xx means the request is wrong.
- **Stuck items never auto-retry.** Only the user can retry, by tapping in the queue inspector. This is intentional: silent infinite retry is the bug we're fixing.
- **Stuck items are never auto-discarded.** Storage is cheap; user data is precious. The item sits in the queue inspector indefinitely until the user resolves it.

### 2.2 — Banner state matrix

The bottom `GTOfflineBanner` (from `AND-4`) becomes a state machine driven by three inputs: network status, active-queue depth, stuck-queue depth.

| Network | Active queue | Stuck queue | Banner copy | Tone | Tappable? |
|---|---|---|---|---|---|
| online | 0 | 0 | (hidden) | — | — |
| online | ≥ 1 | 0 | `Синхр. · N в очереди` | muted | yes → inspector |
| offline > 60s | 0 | 0 | `Нет сети · данные на HH:MM` | warn | no |
| offline > 60s | ≥ 1 | 0 | `Нет сети · N в очереди` | warn | yes → inspector |
| any | any | ≥ 1 | `N не отправилось · посмотреть` | warn-bold | yes → inspector |

The "stuck queue ≥ 1" row dominates: even if there's also active sync happening, the warn-bold copy takes priority because it requires user action. "Active queue" and "stuck queue" are separately counted.

The banner becoming **tappable** is the most important change. A persistent indicator without a drill-down is a bug, not a feature.

### 2.3 — Queue inspector becomes the recovery surface

The "Очередь синхронизации" sheet originally specced in `T11` becomes the only place the user goes to understand and act on outbox state. It's reachable from:

- Tap on the bottom `GTOfflineBanner` (new — primary entry point).
- More → "Очередь синхронизации" (existing).
- Notification tap (new — see §2.5).

Inspector layout (full-screen route, not a sheet — it's a real surface, not a quick peek):

```
←  Очередь                                  3 записи
─────────────────────────────────────────────────
АКТИВНЫЕ · 2

[📷] Творог со сметаной                  03:32
     отправляется · попытка 2 из 5       29 мин назад
     ───────────────────────────────────────
[📷] Без названия                          04:15
     ждёт сети                          18 мин назад
     ───────────────────────────────────────

НЕ ОТПРАВИЛИСЬ · 1

[📷] Без названия                         01:47
     оценка не пришла за 10 минут      3 ч назад
     [Повторить]  [Открыть в журнале]  [Удалить]
─────────────────────────────────────────────────
```

For each item:

- Thumbnail (photo if available; brand mark if text/template entry).
- Name (template name, autocomplete name, or `Без названия` for unfinished photo entries).
- Capture time (the original shutter/text-entry timestamp, mono).
- State line, plain Russian — "ждёт сети", "отправляется · попытка 2 из 5", "оценивается", "оценка не пришла за 10 минут", "сервер отклонил: <error>", etc.
- Time since the item entered the queue, mono `--muted` ("3 ч назад", "29 мин назад").
- For `Stuck` items, three buttons: `Повторить` (force a retry — resets attempts counter, returns to `Queued`), `Открыть в журнале` (opens the row in the Today/History view, useful for context), `Удалить` (drops the outbox item AND the local journal row, with confirmation sheet).
- For active items, no buttons — they're working. Optional small "x" to cancel and discard.

Two sections, separated by a header row: "АКТИВНЫЕ · N" and "НЕ ОТПРАВИЛИСЬ · N". Empty sections are hidden.

### 2.4 — Per-row aging on Today and History

ADR-001 §2.3 defined two pending sub-states for the meal row's number area: `оценивается ···` and `ждёт сети`. After ADR-003, the row picks up an **aging dimension** — the same text gains a warning tone after a threshold:

| Time pending | Number area | Tone |
|---|---|---|
| 0 → 10 min | `оценивается ···` or `ждёт сети` | mono `--muted` (calm) |
| > 10 min | `оценка не пришла` or `давно ждёт сети` | mono `--warn` (terracotta) |

Tap on a warn-tone row → opens the queue inspector, scrolled to that item.

This means the user can spot a stuck record from Today directly, without remembering to check the inspector. The 10-minute threshold matches §2.1's estimate timeout: a row that's been "оценивается" for ten minutes is, by §2.1, already promoted to `Stuck` server-side.

### 2.5 — Notification on permanent failure (opt-in, off by default)

Add a fourth notification kind to the medical flavor's set (and the food flavor's set, both):

- **Channel id:** `outbox_stuck`
- **Copy:** `Запись не отправилась · посмотреть` (Russian, no nutrition values, no glucose values, no medical language).
- **Trigger:** at most once per "stuck event" — when items transition from `Estimating`/`Uploading`/`Queued` into `Stuck`. If three items become stuck simultaneously (e.g., after a long offline period), one notification fires with `Запись не отправилась` (singular even if N > 1, to avoid alarm).
- **Tap behavior:** opens the queue inspector directly.
- **Default:** OFF. Visible in More → Уведомления as `Сообщать, если запись не дошла`. The banner is the primary signal; the notification is the user's opt-in escalation for users who don't open the app daily.

## 3 · Specifications

### 3.1 — `OutboxItem` schema additions

```kotlin
data class OutboxItem(
  val id: UUID,
  val capturedAt: Instant,
  val source: Source,
  val localPhotoPath: String?,
  val optimisticName: String?,
  val optimisticWeightG: Int?,

  // existing
  val state: OutboxState,           // Queued | Uploading | Estimating | Confirmed | Stuck
  val attempts: Int,
  val lastAttemptAt: Instant?,
  val nextAttemptAt: Instant?,      // for exp backoff scheduling

  // ADDED by ADR-003
  val enteredCurrentStateAt: Instant,    // wall-clock when state last changed
  val lastErrorCode: String?,            // optional, e.g. "estimate_timeout", "server_4xx"
  val lastErrorMessage: String?,         // optional human-readable Russian; safe to display
)
```

Migration: add nullable columns; backfill `enteredCurrentStateAt = createdAt` for existing rows.

### 3.2 — Worker scheduling

`OutboxProcessor` runs in three modes:

1. **Immediate** — connectivity-driven `OneTimeWorkRequest`. Picks up items in `Queued` and items in `Uploading` whose `nextAttemptAt < now`.
2. **Periodic** — `PeriodicWorkRequest` every 15 minutes, same pickup logic. Catches edge cases where the connectivity callback was missed (Doze mode, app idle).
3. **Manual** — triggered by the inspector's `Повторить` button on a `Stuck` item. Resets `attempts = 0`, `state = Queued`, kicks an immediate work request.

The worker NEVER picks up items in `Stuck` state automatically. It also NEVER picks up items in `Estimating` (those are server-side waits — the worker only checks status occasionally and is governed by the 10-minute hard timeout, not retries).

### 3.3 — Banner composable contract

`GTOfflineBanner` becomes:

```kotlin
@Composable
fun GTOfflineBanner(
  state: BannerState,             // sealed: Hidden | Active(n) | Offline(n) | Stuck(n) | OfflineActive(n) | etc.
  onTap: () -> Unit,              // navigates to queue inspector; ignored if state.tappable = false
  modifier: Modifier = Modifier
)
```

The composable consumes a `BannerState` derived from a `BannerStateMachine` ViewModel that combines `Flow<NetworkStatus>` and `OutboxRepository.observe()`. The state machine logic lives in `data/sync/`; the composable is dumb.

### 3.4 — Inspector route

New route `Routes.OutboxInspector`. Reached via:

- `onTap` from `GTOfflineBanner`.
- "Очередь синхронизации" entry in More (rewires existing entry from `T11`).
- Notification deep link.

Implementation in `ui/feature/sync/OutboxInspectorScreen`.

## 4 · Section overrides

### 4.1 Supersedes parts of `T3 · Outbox + sync infrastructure`

- The retry policy "cap at 5 attempts with exponential backoff, then leave in `Queued`" is replaced by §2.1: 5 attempts → `Stuck`. `Stuck` is terminal.
- The `Conflict` state in T3 is **removed and folded into `Stuck`**. Update the state enum, all references, and the conflict-resolver UI from T11 is replaced by the queue inspector's per-item actions (§2.3).
- The 10-minute estimate timeout (§2.1) is new; T3 had no upper bound on `Estimating`. Add it to `OutboxProcessorImpl`.

### 4.2 Supersedes parts of `T5 · Today + Stats`

- Pending row rendering gains the aging dimension from §2.4. The row's number area uses `--muted` for the first 10 minutes, `--warn` afterward. Tapping a warn-tone row opens the inspector at that item.

### 4.3 Supersedes parts of `T11 · More / Settings + Conflict resolver`

- The `ConflictResolverSheet` from T11 is **deleted**. Its three actions ("KeepLocal / KeepServer / KeepBoth") were specific to the old `Conflict` state; under §2.1 there is no `Conflict`, only `Stuck`, and the recovery actions are simpler: retry, view in journal, discard.
- The "Очередь синхронизации" entry in More now navigates to `Routes.OutboxInspector` (the new full-screen surface), not an inline section.

### 4.4 Supersedes parts of `T12 · Notifications`

- Adds `outbox_stuck` channel per §2.5. Default OFF.
- Updates the banned-word lint to permit "не отправилось" (functional language about delivery, not judgmental about content).

### 4.5 Supersedes parts of `AND-4 · Flavor-aware navigation`

- The `GTOfflineBanner` state machine from AND-4 is replaced by §2.2's matrix. The composable signature changes (§3.3). Tap behavior wires through to the new inspector route.

## 5 · Implementation tasks

One PR, in order. Touches both flavors symmetrically — banner and inspector live in `src/main/`.

1. **Schema migration.** Add `enteredCurrentStateAt`, `lastErrorCode`, `lastErrorMessage` to `OutboxItem`. Add `Stuck` to the state enum, remove `Conflict` (with a migration that maps any existing `Conflict` rows to `Stuck`).
2. **Worker rules.** Implement the 5-attempt cap with exp backoff (1, 2, 4, 8, 16 min) and the 10-minute `Estimating` timeout. Both transitions write `enteredCurrentStateAt` and `lastErrorCode`. Add the never-auto-retry-Stuck rule.
3. **`BannerStateMachine`.** New ViewModel combining `NetworkStatus` and `OutboxRepository.observe()` per the §2.2 matrix. Pure Kotlin, fully unit-testable.
4. **`GTOfflineBanner`.** Update signature per §3.3. Wire `onTap` to the inspector route. Add the new `Stuck`-priority warn-bold tone.
5. **`OutboxInspectorScreen`.** Per §2.3 layout. Two sections, item rows with thumbnails (resolve from `localPhotoPath` via Coil for photos, brand-mark drawable for text/template). Per-item actions are real button rows with confirmation for `Удалить`.
6. **Per-row aging on Today.** Update `GTMealRow` rendering of pending rows: read `enteredCurrentStateAt` from the linked outbox item; if `now - enteredCurrentStateAt > 10 min`, swap copy and tone per §2.4. On tap, navigate to inspector with that item id as a query param so it scrolls into view.
7. **Notification.** Add `outbox_stuck` channel. Wire trigger from the worker on any state→Stuck transition. Throttle to one notification per 10-minute window (a flurry of timeouts produces one notification, not five).
8. **Settings toggle.** Add "Сообщать, если запись не дошла" in More → Уведомления, default OFF, persisted in `SettingsStore`.
9. **Delete the conflict resolver.** Remove `ConflictResolverSheet` and any references. Update the More screen to point its "Очередь" entry to `Routes.OutboxInspector`.
10. **Tests.**
    - Unit: state machine produces every banner state correctly across the 2 × 3 × 2 = 12 input combinations from §2.2.
    - Unit: worker promotes to `Stuck` after 5th failed attempt; never auto-retries `Stuck`; promotes from `Estimating` to `Stuck` after 10 min.
    - Instrumented: airplane mode for 30 min with 1 enqueued photo → banner shows `Нет сети · 1 в очереди`; restore network → photo uploads → if Gemini takes < 10 min, item becomes `Confirmed`; if mocked to take > 10 min, item becomes `Stuck` with copy `оценка не пришла за 10 минут`.
    - Instrumented: `Stuck` item → tap inspector → tap `Повторить` → resets attempts, item returns to `Queued`, retries.
    - Paparazzi: inspector with active+stuck mix; banner in all five states from §2.2 matrix; meal row in pending state at 5 min and at 15 min ages.

## 6 · Acceptance

- **No silent failure.** A photo enqueued and never reaching the server becomes `Stuck` within at most 5 retry attempts × 16 min ≈ 30 minutes (worst case) of capture; for `Estimating`-stuck items, within 10 min. The banner reflects the situation; the user can tap to act.
- **Banner is always tappable when non-empty.** Excluding the "online + queue empty" state, every banner permutation is tappable and routes to `OutboxInspectorScreen`.
- **Stuck never auto-retries.** Manual test: force a 4xx server response on an upload, verify the item enters `Stuck` after the 4xx response (not after retries — 4xx is immediate). Verify `lastAttemptAt` does not change for 24 hours unless the user taps `Повторить`.
- **Per-row aging visible.** With network on but Gemini mocked to delay 15 min, a row's number area changes from `оценивается ···` (`--muted`) to `оценка не пришла` (`--warn`) at minute 10. Tap on the warn row opens the inspector scrolled to that item.
- **Notification opt-in.** Default OFF: no `outbox_stuck` notifications fire even when items become Stuck. Toggle ON: a stuck event produces exactly one notification within ~30 sec; tap navigates to inspector.
- **No conflict resolver.** Codebase grep for `ConflictResolver`, `KeepLocal`, `KeepServer`, `KeepBoth` returns zero matches in `src/main/`, `src/food/`, `src/gluco/` after this PR.
- **Banner copy correctness.** With 1 stuck and 1 active item present, banner reads `1 не отправилось · посмотреть` (warn-bold), NOT `Синхр. · 2 в очереди`. Stuck dominates.
- **Real-device replication.** The original screenshot scenario (banner stuck at "Синхр. · 2 в очереди" for hours) is no longer possible: either items become `Confirmed` or they become `Stuck`, and `Stuck` produces a different banner.

## 7 · Out-of-band asks

1. **Can the backend distinguish "Gemini took too long" from "the photo upload itself failed"?** §2.1 treats them both as routes to `Stuck`, but the user-facing copy differs (`оценка не пришла` vs `не удалось загрузить фото`). If the server response shape doesn't carry this distinction, the client labels everything as `оценка не пришла` and we accept the imprecision. Confirm or adjust.
2. **Should `Повторить` on a `Stuck` item that previously got a 4xx response do anything different from one that timed out?** §2.1 says retry resets attempts and returns to `Queued`. For 4xx items, retrying without changing the request will fail again. Two options: (a) always retry; (b) for 4xx items, the inspector shows `Открыть в журнале` first, encouraging the user to edit the record before retry. Default if delegated: (a), simpler; the user will figure it out from the second failure.
3. **Local-only delete vs server delete for `Стuck` items.** Tapping `Удалить` on a `Stuck` item should drop the local journal row AND the outbox item, since the server never accepted the record in the first place. Confirm. (For comparison: `Удалить` on a `Confirmed` row enqueues a new `DeleteMeal` outbox item, since the server has it.)
4. **Notification count.** §2.5 says "one notification per stuck event, throttled to 10-minute window". Confirm or propose alternate throttling (e.g., one per day max).
5. **Should the inspector show a global "Повторить все" button?** Useful when 5 items got stuck because Wi-Fi briefly broke, and they're all retryable. Default if delegated: yes, but disabled when there are zero `Stuck` items, and the action requires confirmation ("Повторить все 5 записей?").
