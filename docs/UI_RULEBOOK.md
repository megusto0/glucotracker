# UI Rulebook

Last updated: 2026-05-05

This is the current visual source of truth for the desktop app after the global
redesign. Historical prototype notes are archived or left in `mockup*` folders
as reference only.

## Design Philosophy

1. Editorial, not dashboard.
2. Hairlines over boxes.
3. Numbers in mono, prose in sans, titles in serif.
4. Warm clinical calm, not blue SaaS.
5. Sparse real data should look intentional.

## Tokens

Use `desktop/src/App.css` tokens.

Core palette:

- `--bg`: warm off-white page background
- `--surface`: white surface
- `--surface-2`: warm surface
- `--shade`: quiet empty fill
- `--ink`: primary text
- `--ink-2`: softened text
- `--ink-3`: secondary text and graphite UI accents
- `--ink-4`: muted labels and axes
- `--hairline`: default divider
- `--hairline-2`: stronger divider/input border
- `--accent`: amber, food/carbs only
- `--good`: sage, in-range/positive state
- `--warn`: muted brick, warnings/out-of-range

Avoid adding new chromatic colors. Differentiate with lightness/saturation of
existing tokens when needed.

## Typography

- `--serif`: page titles, date titles, card titles.
- `--sans`: body text, buttons, navigation.
- `--mono`: numbers, times, units, IDs.

Typical sizes:

- 9px: small-caps labels and chart ticks.
- 10-11px: secondary metadata.
- 12-13px: body and buttons.
- 14-18px: compact card titles.
- 22-32px: KPI values and section statements.
- 40px-ish: page-level hero titles when space allows.

Do not make compact panel/card headings hero-sized.

## Layout

- Sidebar is fixed at 200px.
- Main content scrolls in `.gt-main`.
- Pages own padding, usually `28px 40px 56px`.
- Cards use `border: 1px solid var(--hairline)`, no shadows.
- Prefer full-width page bands or hairline-separated sections over nested
  cards.
- Do not put cards inside cards unless it is a repeated item or modal/panel.

## Components

### Buttons

Use compact buttons:

- height 28-30px
- 12px text
- hairline border
- no uppercase by default
- no black filled background for routine actions

`.btn.dark` is now a stronger outline, not a heavy black pill. Use black fills
sparingly and only when the action must visually dominate its row.

### Segmented Controls

Active state should use subtle `surface-2` plus inset/hairline indication, not a
black filled tab.

### Cards

Cards:

- `background: var(--surface-2)` or `--surface`
- `border: 1px solid var(--hairline)`
- `border-radius: var(--radius-lg)`
- no shadow

### Tags

Tags are small status labels, not navigation.

- 10px
- uppercase
- 2px radius
- 2px 6px padding

## Page Rules

Journal:

- food name/photo dominate
- carbs and kcal primary
- protein/fat/fiber secondary
- macro split bars are supporting detail

History:

- food episode cards dominate
- insulin-only rows are muted
- CGM sparkline remains inside episode cards

Glucose:

- chart density changes with time range/data scale
- raw CGM and normalized display are visually distinct
- meals/events should not overcrowd long ranges

Stats:

- low-data mode uses summaries
- charts focus actual tracked days when there are fewer than 14 valid days
- current incomplete day is not included in period calorie balance
- TIR is normal 0-100 stacked bars
- daypart cards are always six 4-hour slots
- heatmap is always 6x7 4-hour blocks

Settings:

- compact tools, not large CTA blocks
- explanatory copy must not overlap headings
- right column aligns with main column height when possible

## Do Not

- Do not use gradient/orb decoration.
- Do not use dark blue/purple SaaS palettes.
- Do not use black filled buttons as routine emphasis.
- Do not use huge cards for every page section.
- Do not leave empty month-wide chart axes for one tracked day.
- Do not show `--%` as a main KPI value.
- Do not show raw float artifacts.
