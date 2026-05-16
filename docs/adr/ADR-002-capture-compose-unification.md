# ADR-002 · Capture compose unification & Today header cleanup

> Companion to ADR-001. Hand both to the agent alongside the original prompt files. This document amends specific UI sections and supersedes parts of `T6` further than ADR-001 already did.

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-10 |
| Affects | `glucotracker-android-prompts.md` (T5, T6), `glucotracker-multiuser-foodflavor-prompts.md` (none), `tarelka-brand-evolution-prompts.md` (TR-2), ADR-001 (compatible — no overlap) |
| Risk | Low — UI consolidation; removes routes and components rather than adding. |

---

## 1 · Problems observed in the current build

Screenshots taken on 2026-05-10 (medical flavor, but applies to both since capture is shared):

**1.1 — Today header has "Статистика →" twice.** Two adjacent rows both reach to the right edge with the same target:

- Row A: pager-indicator dots + small-caps `СЕГОДНЯ` + `Статистика →` (right-aligned)
- Row B: serif day kicker `ВОСКРЕСЕНЬЕ` + `Статистика →` (right-aligned again)

Reads as a render bug. The pager dots and the day kicker are conceptually one header.

**1.2 — Capture sheet forces a four-way choice before any action.** Tapping `+` opens a sheet with `Камера / Галерея / Текстом / Шаблон`. Even the most frequent path (typing a meal name) takes four taps: `+ → Текстом → field → Добавить`.

**1.3 — `Текстом` and `Шаблон` are separate routes for one user need.** Today:

- `Текстом` is a barebones form: one input, one `Добавить` button, **no autocomplete**.
- `Шаблон` is a search field with full autocomplete from saved templates.

The user's mental model is "I want to enter a meal." Whether it's a known item (template hit) or a new one (freeform) is something the system can decide from the input, not the user. Splitting these into two routes makes the user pre-decide something they shouldn't have to.

The autocomplete in `Шаблон` is already correct (frequency-sorted, fast, working). The fix is to put it where the user starts typing, not behind a second tap.

## 2 · Decisions

### 2.1 — One header row on Today

Collapse rows A and B from §1.1 into a single header block:

```
┌────────────────────────────────────────────────┐
│ ●○  ВОСКРЕСЕНЬЕ                  Статистика →  │   row 1: 28dp
│     10 мая 2026                       ‹  ›    │   row 2: 44dp serif date + arrows
└────────────────────────────────────────────────┘
```

- **Row 1** carries: pager dots (left), small-caps day-of-week kicker (left, after dots), screen action `Статистика →` (right). One single right-aligned target. Dots and kicker share the same baseline.
- **Row 2** carries: serif date (left), date-stepper arrows (right). No right-side action here.
- The standalone "СЕГОДНЯ" kicker line is **removed**. The pager dots together with the kicker convey the same information ("you are on the first of two pages") more compactly.
- The "Статистика →" tappable area is the right-aligned text in row 1 only. Tap and horizontal swipe both work.

Rationale: two right-edge targets stacked vertically with the same label is a readability error. Either both targets are needed (then they should be merged) or one is redundant (then it should be removed). Removing one is cheaper and the dots already signal swipeability.

### 2.2 — Single compose sheet, text-first

Tap `+` opens a `ModalBottomSheet` whose initial state is **already typing-ready**:

```
┌──────────────────────────────────────────────────┐
│      ────                                         │   sheet handle
│                                                   │
│  [📷]  [🖼]    что вы съели?           [Enter ↵] │   input row · 56dp
│  ────────────────────────────────────────────────  │   hairline
│                                                   │
│  Воппер              720 ккал            ×2      │   autocomplete row
│  Воппер Ролл         540 ккал            ×1      │
│  Атомик Воппер       710 ккал                    │
│  Атомик Воппер с курицей   630 ккал              │
│  Воппер Джуниор      370 ккал                    │
│                                                   │
│  ──── ничего не подошло ────                     │
│                                                   │
│  + Добавить как новое: «воп»                     │   freeform fallback
│                                                   │
│  bk: Burger King · mc: McDonalds · r: рестораны  │   discovery hint (first-run)
└──────────────────────────────────────────────────┘
```

Mechanics:

- Sheet opens at 80% screen height. Top of the sheet body is the **input row**; field is auto-focused, keyboard slides up automatically.
- **Left of the field**: two compact icon buttons — camera (`📷`) and gallery (`🖼`). Tap → existing camera/gallery flows from the original `T6`. The sheet dismisses on this tap to avoid double-overlay.
- **Right of the field**: a send-icon button (`↑` or chevron). Visible only when the field is non-empty. Tap = same as pressing Enter on the keyboard.
- **Body**: autocomplete results list, rendered live as the user types (debounce 50ms, local-first per the offline-first principle).
  - Sorted: exact-prefix matches first, then by `usage_count` descending. The frequency badge (`×2`, `×1`) on the right shows how many times the user has used that template.
  - Tap a row → enqueues `CapturedMeal(source = Template, optimisticName = template.name, optimisticWeightG = template.default_grams)`, sheet dismisses, row appears at top of Today (per ADR-001).
  - When tapping a template, all server values are known immediately — the row is **Confirmed** on creation, not Pending. No `оценивается` state for template hits. Only the network round-trip to register the meal causes a brief Pending state if offline; per ADR-001 this is communicated in the row's number area.
- **Freeform fallback**: when no autocomplete row exactly matches, the bottom of the list shows `+ Добавить как новое: «{text}»`. Pressing Enter on the keyboard does the same thing. Either path enqueues `CapturedMeal(source = Text, optimisticName = text, localPhotoPath = null)` — server estimates calories from text, identical pipeline to photo (Pending → Estimating → Confirmed per ADR-001).
- **Discovery hint** below the body: a small one-line muted hint `bk: Burger King · mc: McDonalds · r: рестораны`, shown only the first three times the user opens the sheet, then collapsed to a tiny `?` icon next to the input.

The four-button picker from the current implementation is **removed**. The `Текстом` and `Шаблон` routes are **removed** — they merge into this sheet.

### 2.3 — Brand prefixes as namespace filters

The autocomplete query parser recognizes a leading `<word>:` token as a brand or category filter:

| Prefix | Filter |
|---|---|
| `bk:` | products with `brand_slug = "bk"` (Burger King) |
| `mc:` | `brand_slug = "mc"` (McDonalds) |
| `kfc:` | `brand_slug = "kfc"` |
| `r:` | any product where `kind = "restaurant"` |
| `p:` | products only — exclude restaurant items, exclude templates |
| `t:` | templates only — user-saved combinations |

Parser rules:

- The prefix matches at the very start of the input, before any non-`:` character.
- The text after the colon is the actual search query (may be empty, in which case all items in that namespace surface, frequency-sorted).
- An unknown prefix (e.g. `xyz:`) falls through to a normal search, treating the whole input as the query string.
- Prefixes are case-insensitive (`BK:` and `bk:` are equivalent).
- Prefixes are not localized — they're typing shortcuts. The user types ASCII colon-separated tokens regardless of the keyboard layout.

The set above ships with the first version. New prefixes are added by the user (via Base) when they save a product with a custom `brand_slug`. A future setting may let the user define ad-hoc aliases (`закусочная: → r:zakuska`); flag this as a follow-up, not v1.

## 3 · Specific UI primitives

### 3.1 — `GTComposeSheet` (new)

Replaces the current capture-picker sheet. Lives in `ui/feature/capture/`. Hilt-provided regardless of flavor.

- Container: `ModalBottomSheet`, target peek height `80%`, drag handle visible.
- Top row: 56dp tall, `Row` with `verticalAlignment = CenterVertically`.
  - 2 × `IconButton` (32dp) for camera and gallery, 8dp gap.
  - `BasicTextField` filling remaining space, focus requested on launch (`LaunchedEffect { focusRequester.requestFocus() }`). Placeholder: `что вы съели?` in `--muted`.
  - `IconButton` (32dp) for send, visible only when input is non-empty.
- Hairline divider below input row.
- Body: `LazyColumn` of autocomplete rows. Each row 48dp tall: name (sans 14sp), kcal (mono 12sp `--muted`), frequency badge right-aligned (mono 11sp inside a 22dp pill). Hairline between rows.
- Freeform fallback row: when no exact match, a final 48dp row with `+ Добавить как новое: «{text}»` styled like an autocomplete row but with `--ink` text and no frequency badge.
- Footer hint: 24dp tall muted line with prefix tips, shown for first three sessions.

### 3.2 — `TodayHeader` (replace existing two-row header)

Lives in `ui/feature/today/`. Single composable with two `Row`s in a `Column`:

- Row 1 (kicker): 28dp tall.
  - Left: pager dots (4dp circles, 4dp gap, ink fill for active, hairline-only for inactive).
  - 6dp gap.
  - Small-caps kicker text (`ВОСКРЕСЕНЬЕ`), 9.5sp, letterSpacing 1.4sp, `--muted`.
  - Spacer fills middle.
  - Right: `TextButton("Статистика →")` 11.5sp `--ink-2` — single instance.
- Row 2 (date): 44dp tall.
  - Left: serif date `10 мая 2026`, 28sp, `--ink`.
  - Spacer.
  - Right: two outlined arrow buttons (28dp), `‹` and `›`, with the previous-day arrow always enabled and the next-day arrow disabled when on today.
- Spacing: 12dp between rows. 12dp top padding, 16dp bottom padding (separates the header block from the KPI grid).

The current "СЕГОДНЯ / Статистика →" pager-indicator row is **removed entirely**. The dots are now part of row 1.

## 4 · Section overrides

### 4.1 Supersedes parts of `T5 · Today + Stats`

- The Today layout uses `TodayHeader` (§3.2). The old separate `PagerIndicatorRow` and `DayKickerRow` composables are deleted; `TodayHeader` replaces both.
- The Today loading state — currently a centered "Загрузка" text on otherwise-empty screen (visible in screenshot 2) — is replaced by skeleton rendering of the header and KPI placeholders. Empty content area should never show only "Загрузка". Render the date kicker, the date itself, and 4 hairline-bordered empty KPI cards while data loads.

### 4.2 Supersedes parts of `T6 · Capture flow` (already amended by ADR-001)

ADR-001 collapsed the two-step outbox pipeline into a single `CapturedMeal`. ADR-002 further changes the entry surface:

- The original `T6` deliverables list `CaptureSheet` (4-button picker), `PhotoCaptureScreen`, `DraftScreen` (already removed by ADR-001), `TextInputScreen`, `TemplateScreen`. After this ADR:
  - `CaptureSheet` (4-button picker) → **deleted**, replaced by `GTComposeSheet` (§3.1).
  - `TextInputScreen` → **deleted**. Its function lives inside `GTComposeSheet`.
  - `TemplateScreen` → **deleted**. Its autocomplete lives inside `GTComposeSheet`.
  - `PhotoCaptureScreen` → unchanged. Reached via the camera icon in the compose sheet.
  - Gallery import flow → unchanged. Reached via the gallery icon.
  - Routes `Routes.TextInput` and `Routes.Template` → removed from `Routes.kt` and `GTNavHost`.
- `ProductsRepository.searchLocal(query)` already exists from `T2`. The compose sheet uses it directly. Add a parameter for the parsed prefix filter:
  - `fun searchLocal(query: String, prefix: BrandPrefix? = null): Flow<List<AutocompleteItem>>`
  - `BrandPrefix` is an enum with the values from §2.3.
  - The repository implementation does the SQL join with `brand_slug` server-side once per query.

### 4.3 Supersedes parts of `TR-2 · Today redesign` (Tarelka)

- The food-flavor `TodayHeader` follows §3.2 exactly, with the brand lockup `• Tarelka` rendered above row 1 of the header (per `TR-1`). The right-side action in row 1 stays as `Статистика →`.

## 5 · Implementation tasks

One PR, in order:

1. **Routes & navigation.** Remove `TextInput` and `Template` routes from `Routes.kt`. Update `GTNavHost`. Delete `TextInputScreen.kt` and `TemplateScreen.kt` files.
2. **Build `GTComposeSheet`.** Per §3.1. Re-use `ProductsRepository.searchLocal` and the existing autocomplete model.
3. **Wire FAB.** The center FAB's onClick now opens `GTComposeSheet` directly (was: opened the 4-button picker). Delete the picker sheet code.
4. **Brand prefix parser.** Add `BrandPrefix` enum + `parsePrefix(text: String): Pair<BrandPrefix?, String>` in `data/repository/`. Wire into `searchLocal`.
5. **Build `TodayHeader`.** Per §3.2. Delete `PagerIndicatorRow` and `DayKickerRow`, replace with `TodayHeader` in `TodayScreen`.
6. **Loading state fix.** Replace `Box(centered Text("Загрузка"))` with skeleton header + 4 KPI placeholders during `TodayState.Loading`.
7. **Discovery hint.** Add `compose_sheet_open_count` to DataStore. Render the prefix hint footer when `open_count < 3`. After three opens, hint becomes a small `?` icon next to the input that reveals the same line on tap.
8. **Tests.** Update Paparazzi snapshots for Today (header collapsed, no double "Статистика"). Add new snapshots for `GTComposeSheet` in three states: empty, typing-with-results, typing-with-no-match-showing-freeform-fallback. Update `T6` instrumented tests to drive through the new sheet.

## 6 · Acceptance

- **No double action.** Today screen's header has exactly one `Статистика →` clickable target, located in the kicker row. Verified by Compose UI test asserting `onAllNodesWithText("Статистика").assertCountEquals(1)` on the Today route.
- **Compose sheet starts typing-ready.** Tap `+`, observe within 250ms: sheet visible, keyboard up, text field focused, cursor blinking. Compose UI test waits for `IS_FOCUSED == true` on the text field after tapping the FAB.
- **Routes deleted.** Codebase search for `TextInputScreen`, `TemplateScreen`, `Routes.TextInput`, `Routes.Template` returns zero matches. CI grep test.
- **One-tap template.** From any state, tap `+` → type `воп` → tap `Воппер Ролл` → the sheet dismisses and a row appears in Today with the template's values, all within ~600ms on a warm cache. The row is in `Confirmed` state immediately if online; in `Pending · waiting` if offline.
- **One-tap freeform.** Tap `+` → type `салат с тунцом` (no template match) → press Enter → row appears in Today in `Pending · estimating` state (online) or `Pending · waiting` (offline). After Gemini responds, values populate per ADR-001.
- **Prefix filter works.** Tap `+` → type `bk:` → autocomplete shows only Burger King items, frequency-sorted. Type `bk:воп` → only Burger King items matching `воп`. Empty `bk:` shows top BK templates by frequency.
- **Skeleton on Today loading.** Cold app launch shows skeleton header + 4 empty KPI cards with shimmer (or static hairline placeholders), not the "Загрузка" centered text.

## 7 · Out-of-band asks

1. **Brand prefix character set.** §2.3 chose colons. Some Russian users type colons by switching to English layout. Confirm this is acceptable, or propose an alternative (e.g. `bk/`, `bk.`). Default if delegated: stick with `:`, it's a known pattern from search engines and command lines.
2. **Discovery hint copy and lifetime.** §3.1 shows the prefix hint for first three sessions. Confirm count and exact copy. Default: copy as written, count = 3.
3. **What happens when the user types `bk:` and there are no Burger King items in their database yet.** §2.3 implies "show empty list and the freeform fallback". Confirm this is the desired behavior (vs. showing a one-liner like "У вас пока нет шаблонов из Burger King"). Default: empty list + freeform fallback, no special copy.
4. **Camera/gallery icon set.** §3.1 uses outline-style 20dp icons (camera and image-frame). The medical flavor's existing icons inside `PhotoCaptureScreen` follow that style; reuse them. Confirm before importing any new asset.
5. **Sheet height.** §3.1 says 80%. On a 6.7" screen the autocomplete list will have plenty of room; on a 5.0" screen with the keyboard up, it may feel cramped. Confirm 80% or propose `WindowInsets`-aware sizing that gives the list ≥40% of the visible (above-keyboard) area.
