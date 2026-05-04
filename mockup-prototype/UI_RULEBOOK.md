# Glucotracker UI Rulebook

This document captures the design language, conventions, and interaction patterns established in the mockup. Read it before adding new pages, components, or visual changes — it's the reason this mockup looks coherent rather than generic-SaaS.

The rulebook is descriptive, not prescriptive. It reflects what the codebase actually does. If a rule here disagrees with the code, the code wins — update the rulebook.

---

## 1. Design philosophy

Three principles drive every decision:

1. **Editorial, not dashboard.** The product handles food and health. Cold blue gradients and dark mode would feel hostile. Treat each page like a magazine spread: a serif headline, a clear thesis, supporting data laid out with deliberate hierarchy.
2. **Numbers in mono, prose in sans, headlines in serif.** Three font roles, one purpose each. Mixing them on purpose creates the distinctive "glucotracker look."
3. **Hairlines over boxes.** Whenever possible, separate sections with 1px lines instead of solid backgrounds or shadows. The page should feel like a printed page, not a stack of cards.

If a new screen reads like Datadog or Stripe, something went wrong. It should read like a Bloomberg Businessweek page.

---

## 2. Design tokens

All tokens live in `src/styles.css` under `:root{}`. Use `var(--token-name)` everywhere — never hardcode hex values in components.

### 2.1 Colors

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#F6F4EE` | Page background. Warm off-white. |
| `--surface` | `#FFFFFF` | Cards that need contrast against `--bg` (rare; we prefer `--surface-2`). |
| `--surface-2` | `#FBF9F3` | Default card background. Slightly creamier than page bg. |
| `--shade` | `#F0EBDF` | Empty cells (heatmap, disabled bars), tag backgrounds. |
| `--ink` | `#0A0A0A` | Primary text, primary buttons. |
| `--ink-2` | `#2A2520` | Slightly softened body text. |
| `--ink-3` | `#6B6258` | Secondary text, sub-labels. |
| `--ink-4` | `#A39A8E` | Muted text, axis labels, "lbl" small caps. |
| `--hairline` | `#E5E0D6` | Default 1px divider. |
| `--hairline-2` | `#D6D0C4` | Stronger 1px divider, input borders. |
| `--accent` | `#B8842B` | **Amber.** Carbs, food, meals. The single brand accent. |
| `--accent-soft` | `#E9D9B5` | Amber border, soft-fill. |
| `--accent-bg` | `#F4ECD8` | Amber background fill (target band, meal pills). |
| `--good` | `#4A7C3F` | Sage. In-range glucose, deficit (positive), success states. |
| `--good-soft` | `#DCE5CB` | Sage soft fill. |
| `--warn` | `#B85426` | Muted brick red. Out-of-range, low confidence. Use sparingly. |
| `--warn-soft` | `#ECCEBE` | Warn soft fill. |

#### Color rules

- **One amber, one sage, one warn.** Never introduce a fourth chromatic color. If you need to differentiate more than three categories, vary saturation/lightness on the existing tokens (e.g., `oklch(0.78 0.04 60)` vs `oklch(0.82 0.06 78)`).
- **Amber = food/carbs.** Don't reuse amber for "warning" or "highlight" — that's what makes the design coherent. If you'd like to highlight something non-food, use `--ink` or `--surface-2` background.
- **No dark mode.** This palette assumes light. Don't add dark variants without redesigning.
- **Status dots.** The `<span class="dot-marker">` pattern uses 6px circles with the four state colors above. Don't invent a new "purple" or "blue" status without discussion.

### 2.2 Typography

```css
--mono:  "JetBrains Mono", "SF Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace;
--sans:  "Inter", "Helvetica Neue", Helvetica, Arial, system-ui, sans-serif;
--serif: "Source Serif 4", "Source Serif Pro", Georgia, serif;
```

| Family | When to use |
|---|---|
| `--serif` | Page titles (`<h1>`), date headers, card titles inside major sections. Always `font-weight: 400` or `500`, never bold. Letter-spacing slightly negative (`-0.01em` to `-0.02em`). |
| `--sans` | Body text, button labels, navigation. Default weight 400. |
| `--mono` | All numbers, all timestamps, all measurement units, code/IDs, kbd hints. Never use mono for prose. |

Type scale (px):

| Size | Use |
|---|---|
| 9 | `lbl` small caps, axis ticks, meta. ALWAYS letter-spaced 0.16–0.18em and `text-transform: uppercase`. |
| 10 | Sub-labels, tag text, mini-stats. |
| 11 | Body small, secondary information. |
| 13 | Body default. |
| 14–16 | `h3` card titles in serif. |
| 20–22 | Card-level h2 in serif. |
| 26–32 | Section headlines, KPI mono numbers. |
| 40 | Page-level h1 dates in serif. |

### 2.3 Spacing

There is no formal grid. Use these values consistently:

- **Page padding:** `28px 40px 56px` (top right/left bottom). The bottom is intentionally generous so footers breathe.
- **Card padding (`.card-pad`):** `18px 20px`.
- **Card head (`.card-head`):** `14px 18px` with `border-bottom: 1px solid var(--hairline)`.
- **Card-to-card vertical gap on a page:** `14px` for tight rows, `22px` between major sections.
- **Inside cards, vertical rhythm:** `8 / 14 / 22 / 36` — pick from this set, don't invent 12 or 18.
- **Border radius:** `--radius: 2px` for tags/buttons, `--radius-lg: 4px` for cards/inputs. **Never** use rounded-full except on dot markers (50%) and on lane pills where the geometry demands it.

### 2.4 Borders

- Default divider: `1px solid var(--hairline)`. This is the workhorse.
- Stronger divider (e.g., footer top): `2px solid var(--ink)`.
- Card border: `1px solid var(--hairline)`. Don't use shadows.
- Selected/active indicator: `inset 2px 0 0 var(--ink)` boxShadow. This is the **only** way to mark "this row is selected" — not background change alone.

---

## 3. Layout primitives

### 3.1 Shell (`AppShell.tsx`)

```
<div class="gt-app">
  <aside class="gt-sidebar">  ← 200px fixed
    <div class="gt-brand">…</div>
    <nav class="gt-nav">…</nav>
    <div class="gt-side-glucose">…</div>   ← live widget at bottom
    <div class="gt-side-foot">…</div>
  </aside>
  <main class="gt-main">                   ← flex: 1, scrollable
    {pageContent}
    {optional <RightPanel/>}
  </main>
</div>
```

Rules:

- **Don't add a header bar.** The sidebar handles navigation; each page provides its own `<PageHead>` inline. Adding a top bar fights the editorial style.
- **Pages own their own padding.** `.gt-main` is unpadded. The page component wraps content in either `className="gt-page"` (default `padding: 24px 32px 56px`) or an inline-styled `<div style={{ padding: '28px 40px 56px' }}>`.
- **No `max-width` on page containers.** Content grids stretch to fill the main area. If you cap width, you'll leave dead empty space on wide monitors. Cards can have a max-width if a single specific card looks bad when stretched.

### 3.2 PageHead (`components/PageHead.tsx`)

```tsx
<PageHead
  crumbs={["суббота"]}
  title="2 мая 2026 г."
  right={<button className="btn">…</button>}
/>
```

- `crumbs` are small-caps tokens above the title. They are **not** clickable navigation in the current design. If you make them clickable later, style as links.
- `title` is always serif h1. Dates as titles are a deliberate motif — keep it.
- `right` is the action area. Use 1–4 buttons, separated by `gap: 8`. More than 4 means you need a menu.

### 3.3 Page structure conventions

A page reads top → bottom in this order:

1. `PageHead` (small label + serif title + right actions)
2. Optional headline statement (a serif `h2` with the day's main verdict)
3. KPI row or hero card (4 metrics or a wide info bar)
4. Primary visualization (chart, list, table)
5. Secondary content (episodes, related items)
6. Footer with quality/context metadata

Don't shuffle this. If a page genuinely doesn't have a verdict, skip step 2 — don't replace it with a placeholder.

---

## 4. Component primitives

### 4.1 Card (`.card`)

```html
<div class="card">
  <div class="card-head">
    <div>
      <div class="lbl">контекст графика</div>
      <h3>Активность · эпизоды</h3>
    </div>
    <SegmentedControl … />
  </div>
  <div class="card-pad">…content…</div>
</div>
```

- Always: `background: var(--surface-2)` (or `--surface` if you specifically want whiter), `border: 1px solid var(--hairline)`, `border-radius: var(--radius-lg)` (4px).
- A card-head is optional but encouraged for any card with structured content.
- **Never use shadows.** No `box-shadow: 0 4px 12px rgba(...)`. The hairline border is the entire visual weight of the card.

### 4.2 KPI strip (`.kpi`)

```html
<div class="kpi">
  <div>
    <div class="lbl">углеводы</div>
    <div class="kpi-val">111<span class="u">г</span></div>
    <div class="pbar accent"><i style="width: 49%"/></div>
    <div class="kpi-sub">цель 225 г · <span class="mono">49%</span></div>
  </div>
  <div>…</div>  ← repeat
</div>
```

- Always 4 columns. Don't make it 3 or 5.
- Each item: `lbl` (uppercase 9px) → big mono number → optional thin `pbar` → small sub-text.
- Items separated by vertical hairlines (`border-right`).
- Padding inside each item: `14px 20px`. The first child still has `padding-left: 0` so the strip aligns flush left with the page edge — text inside items 2–4 has 20px breathing room from the divider.

### 4.3 Tags (`.tag`)

```html
<span class="tag">обычный</span>
<span class="tag accent">амбер</span>
<span class="tag good">в цели</span>
<span class="tag solid">чёрный</span>
```

- Small pills for status, never for navigation.
- Variants: `.accent` (amber bg), `.good` (sage), `.warn` (brick), `.solid` (ink).
- Padding `2px 6px`, font 10px. If you're tempted to make a "big tag," it's actually a button — use `<button class="btn">`.

### 4.4 Buttons

```html
<button class="btn"><Icon size={13}/> Действие</button>
<button class="btn dark">Основное действие</button>
<button class="btn icon"><Icon size={14}/></button>
<button class="btn-link">просмотр истории →</button>
```

- Default `.btn`: 1px hairline border, surface background. Hover darkens slightly.
- `.btn.dark`: ink background, white text. Use for the **single** primary action per row.
- `.btn.icon`: square icon-only.
- `.btn-link`: text-only with subtle underline. For "see more" affordances inside cards.

Icons inside buttons: always 13–14px. Always from `components/Icons.tsx` — don't import lucide-react ad-hoc.

### 4.5 Segmented control

```tsx
<SegmentedControl items={["RAW", "СГЛАЖ.", "НОРМ."]} value={mode} onChange={setMode} />
```

- 2–5 items max. More than 5 → use a `<select>` or different paradigm.
- Items are short labels (1–2 words). If you need full sentences, this is the wrong control.

### 4.6 Right panel (`RightPanel`)

```tsx
{showSomething && (
  <RightPanel onClose={() => setShowSomething(false)}>
    <div className="lbl">…</div>
    <h2>…</h2>
    <div className="panel-section">…</div>
  </RightPanel>
)}
```

- Used in: `JournalPage` (selected meal, autocomplete), `GlucosePage` (sensor details).
- Width fixed at 340px, slides in from right with a 220ms cubic-bezier animation.
- Conditional render — when closed, completely unmounted (so animations replay on open).
- The panel sits as a sibling of the scrollable main area inside a flex container at the page root:

```tsx
return (
  <div style={{ display: 'flex', height: '100%' }}>
    <div style={{ flex: 1, overflow: 'auto' }}>
      <div className="gt-page">…page content…</div>
    </div>
    {showPanel && <RightPanel onClose={…}>…</RightPanel>}
  </div>
)
```

This is the **only** correct way to do the right panel. Don't try to position it absolutely — it must reflow the main content.

### 4.7 Sidebar live widget (`gt-side-glucose`)

The sidebar shows a compact glucose widget at the bottom (above the user avatar). Visible on every page; clicking navigates to `/glucose`. Its purpose is to keep glucose value visible while the user is on Journal/Stats/etc.

If you're tempted to add another always-visible widget (sensor, calories, …), think hard — the sidebar is not a dashboard. One widget max.

---

## 5. Interaction patterns

### 5.1 Selectable rows (`.clickable-row`)

When a row can be clicked to select/expand:

```tsx
<div
  className="row clickable-row"
  onClick={() => setSelected(i)}
  style={{
    background: selected === i ? "var(--surface-2)" : "transparent",
    boxShadow: selected === i ? "inset 2px 0 0 var(--ink)" : "none",
    paddingLeft: selected === i ? 8 : 0,
    marginLeft: selected === i ? -8 : 0,
    cursor: 'pointer',
  }}
>
```

The `paddingLeft + marginLeft` trick: when selected, the row "extends" 8px to the left visually (into the card's edge) so the 2px ink bar appears flush with the card. The content stays in the same horizontal position because the padding compensates.

Hover state is provided by `.clickable-row:hover { background: var(--surface-2); }` in CSS.

### 5.2 Hover linkage (cross-component)

The Glucose page has the most sophisticated example: hovering an episode row in one card highlights the corresponding pill in another card AND draws a peak indicator on the chart. This pattern is described in detail in §6.

**General rule:** if two visualizations show the same entity, hovering one should highlight the other. Use a single `useState<number>(-1)` for the hovered entity index, lifted to the parent component.

### 5.3 Sliding panels vs modals

- **Right-slide panel** (RightPanel): for navigational drill-in (selected meal details, sensor settings). The user might switch between several items of the same kind. Doesn't block the rest of the page.
- **Modal dialogs:** not currently in the design. If you need one (destructive confirmation, etc.), don't reach for `<Dialog/>` from a UI library. Inline the confirmation in the right panel or use an inline expand.

### 5.4 Animations

Keep them minimal and purposeful. Allowed:

- Right panel slide-in: 220ms cubic-bezier(.2,.7,.3,1).
- Hover transitions on cards: 150ms ease.
- Color/transform changes on hover: 150ms.

Forbidden:

- Page transitions / route fades.
- Bouncy / spring physics.
- Skeleton shimmer (not yet used; if added, keep subtle).
- Anything over 250ms.

---

## 6. Case study: the glucose chart

This is the most complex visualization in the mockup. It demonstrates several patterns. Read it carefully before changing.

### 6.1 Three-density rendering

The chart adapts based on `timeRange` (selected via SegmentedControl):

```ts
const density: 'full' | 'compact' | 'aggregate' =
  timeRange === '7Д' ? 'aggregate' :
  (timeRange === '12Ч' || timeRange === '24Ч') ? 'compact' :
  'full'
```

| Density | Time range | Lane 1 (meals) | Lane 2 (insulin) | Lane 3 (calibration) |
|---|---|---|---|---|
| `full` | 3Ч / 6Ч | Pill spanning meal duration, dots inside for each event, `21,7 г` above, `2 события · 14:07` below | Vertical tick + outline badge `1.6 ЕД` + time below | Diamond + value `9,9 ммоль` inline + time below |
| `compact` | 12Ч / 24Ч | Single circle, radius scales with carbs, no labels (hover for tooltip) | 2px tick, no badge (hover for tooltip) | 8px diamond, no label (hover for tooltip) |
| `aggregate` | 7Д | Per-day vertical bar, total g above, `5 приёмов` below | Per-day bar, total ED above | Per-day count, single number centered |

**Why the modes differ:** the visualization should answer the question relevant to the zoom level. At 6Ч, the user wants to see "what did I eat and how did glucose respond." At 7Д, the user wants "what's my pattern by day." Forcing the same paradigm at all zooms produces an unreadable mess.

**When extending:** if you add new event kinds (steps, sleep, etc.), implement all three modes. Don't render them only at one zoom and leave the others empty.

### 6.2 Layout geometry

The entire chart is one SVG with a viewBox. Coordinates are in SVG units, not pixels.

```
chartTop      = 18                       ← top of glucose curve area
chartH        = 220                      ← curve height
chartBottom   = 238                      ← bottom of curve
                ↓ 26px gap
lanesTop      = 264                      ← top of lanes zone
laneH         = 30                       ← height of each lane
laneGap       = 30                       ← gap BETWEEN lanes
                                            (must be ≥28 to fit
                                             a below-label + above-label)
lane1Y        = 264                      ← Питание
lane2Y        = 324                      ← Инсулин
lane3Y        = 384                      ← Калибровка
lanesBottom   = 414
                ↓ axisH = 32
H             = 446                      ← total viewBox height
```

**Critical rule:** `laneGap` must accommodate text on both sides (below-label of lane N + above-label of lane N+1). Currently 30px, which fits font-9 + font-10 + ~11px breathing room. If you reduce it, text will overlap — this happened during development and was specifically called out.

### 6.3 Hover linkage

State lives in `GlucosePage`:

```tsx
const [hoveredEpisode, setHoveredEpisode] = useState<number>(-1)
```

Three hover triggers all share this single state:

1. **Episode row** in the bottom card (`onMouseEnter` → `setHoveredEpisode(i)`)
2. **Meal pill** inside the chart's lane 1 (`onMouseEnter` → `setHoveredEpisode(idx)`)
3. **Day column** in 7Д aggregate mode (same)

When `hoveredEpisode >= 0` and density is `'full'` or `'compact'`:

- The matching pill turns from `--accent-bg` to `--accent` (solid amber).
- A **range fill** appears on the chart: `<rect x={iToX(iStart)} y={chartTop} width={x2-x1} height={chartH} fill="var(--accent)" opacity="0.10"/>`.
- A **peak marker** is drawn on the curve at `iToX(peakI)`: a 4px white circle with amber stroke, plus the text `пик 8.5`.
- A **dotted connector** runs vertically from the peak point on the curve down to the pill — visually tying cause to effect.

In `'aggregate'` mode the linkage is different: the entire 7Д column gets a faint amber background `opacity="0.05"`, and the bars in that column become darker.

### 6.4 Time-axis labels

Adapt to timeRange:

| Range | Labels |
|---|---|
| 3Ч | `15:00, 15:30, 16:00, …, 18:00` |
| 6Ч | `12:00, 13:00, …, 18:00` |
| 12Ч | `08, 10, 12, …, 20` |
| 24Ч | `00, 04, 08, 12, 16, 20, 24` |
| 7Д | `пн, вт, ср, чт, пт, сб, вс` |

Always 7 labels. Computed positions: `padL + (i / (xLabels.length - 1)) * innerW`.

### 6.5 Connecting events to data

The data structure for meals:

```ts
type MealEpisode = {
  iStart: number   // chart index where meal began
  iEnd: number     // chart index where meal ended (same as iStart for instant meals)
  peakI: number    // chart index of glucose response peak (computed offline)
  carbs: number
  label: string    // "14:07" or "15:43–16:04"
  events: Array<{ i: number; name: string; c: number }>
}
```

`iStart` and `iEnd` together encode duration. `peakI` is **not** auto-computed in the mockup — it's hand-set per episode. In production, derive it from the CGM curve in a window after `iEnd`.

Each meal's `events[]` is the actual list of food items grouped into this meal. Display rules:

- **Full mode:** render dots inside the pill at `iToX(event.i)`, sized by `event.c / totalCarbs`.
- **Compact mode:** ignore events; draw a single circle at the pill midpoint, sized by total carbs.
- **Aggregate mode:** ignore events; show count `meals` and totals.

---

## 7. Mock data conventions

All mock data lives in `src/mock/`:

- `glucose.ts` — CGM curve generators, episodes
- `meals.ts` — today's meal list
- `products.ts` — food database items
- `sensors.ts` — current and previous sensors
- `stats.ts` — weekly/monthly aggregates

When adding a new mock dataset:

- Use deterministic data when you can. Random heatmaps (`Math.random()`) are acceptable for visual filler but make the page look different on every reload — bad for review.
- Numbers should be plausible for an adult tracking glucose: carbs 5–80g per meal, glucose 4–12 mmol/L, insulin 0.5–6 ED per dose.
- Use Russian product names (Сырок, Лаваш, Кола Ориджинал…) — the product is Russian-language.

---

## 8. Anti-patterns

Things this codebase deliberately doesn't do, with reasons:

| Anti-pattern | Why we don't |
|---|---|
| Box shadows on cards | Reads as "modal," breaks editorial feel. Hairlines suffice. |
| Bright accent colors (full saturation blue/red/green) | Clashes with the warm palette. We use `oklch(...)` adjusted shades. |
| Tooltip libraries (react-tooltip etc.) | Native `<title>` element on SVG covers all current needs. If we add HTML tooltips later, build a single shared component. |
| Charting libraries (recharts, chart.js, …) | Hand-rolled SVG gives us editorial typography control. The charts here are bespoke for a reason — adding a chart lib would force generic styling. |
| Page transitions, route animations | Distracting. We want fast scan, not "smooth UX." |
| Mobile-first layouts | Currently desktop-only. KPI strip would need stacking; right panel would need to overlay; charts would need redrawing. Don't bolt on responsive without redesigning. |
| `style={{}}` for things that have a CSS class | Use `className`. Inline styles are reserved for dynamic values (selected state, computed widths) or component-level layout. |
| Importing icons from random places | All icons via `import { I } from '../components/Icons'`. Adding a new icon means adding it to `Icons.tsx`. |

---

## 9. Adding a new page — checklist

1. Create `src/pages/MyPage.tsx`.
2. Add route in `App.tsx`.
3. Add nav item in `components/Sidebar.tsx` with an icon from `Icons.tsx`.
4. Use `<PageHead crumbs={...} title="..." right={...} />`.
5. Wrap content in `<div className="gt-page">` OR `<div style={{ padding: '28px 40px 56px' }}>`. Don't add `maxWidth`.
6. If the page has selectable items, follow §5.1 (selected row pattern).
7. If it has a detail view, use `RightPanel` (§4.6).
8. KPI strip if there are 4 key metrics; otherwise hero card.
9. Footer with quality/context metadata if data quality matters on this page.
10. Run `npx tsc --noEmit` before committing — TypeScript errors are common with chart geometry.
11. Verify all six existing pages still render after your change.

---

## 10. Files to read before extending

If you're touching the design system, read these in order:

1. `src/styles.css` — all tokens and component classes.
2. `src/components/AppShell.tsx` and `Sidebar.tsx` — the shell.
3. `src/components/PageHead.tsx`, `RightPanel.tsx`, `SegmentedControl.tsx` — the building blocks.
4. `src/pages/StatsPage.tsx` — the cleanest example of the editorial layout.
5. `src/pages/GlucosePage.tsx` — the most complex interaction case (chart + lanes + hover).
6. `src/pages/JournalPage.tsx` — meal list + selectable row + right panel pattern.

If you understand those six files, you can extend the rest.
