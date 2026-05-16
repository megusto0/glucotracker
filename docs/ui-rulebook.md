# UI Rulebook

Status: source of truth
Last updated: 2026-05-13
Owner/area: visual system and components

The visual source of truth is the warm editorial design system shared by desktop
and Android. Per `CONCEPT.md` §5, do not add colors, shadows, fonts, or radii
without an explicit design decision.

## Palette

Core mobile tokens mirror `tokens.css` and Android `GTColors.kt`:

| Token | Hex | Use |
| --- | --- | --- |
| `bg` | `#f6f4ef` | page/app background |
| `surface` | `#fbfaf6` | cards and sheets |
| `surface2` | `#ffffff` | raised surfaces without shadow |
| `ink` | `#25241f` | primary text, active tag fill, limited black fill |
| `ink2` | `#4a4842` | secondary text |
| `muted` | `#8a857a` | metadata, labels, axes |
| `hairline` | `#e6e2d6` | 0.5 dp/px borders and dividers |
| `hairline2` | `#d8d3c4` | stronger border |
| `accent` | `#5e6f3a` | olive, carbs/goal progress |
| `good` | `#6b8a5a` | in-range/positive state |
| `warn` | `#c98a55` | warning, surplus, conflict |
| `bad` | `#2d3340` | graphite/navy emphasis |
| `info` | `#6b7a92` | info/fingerstick context |

Desktop has additional CSS aliases in `desktop/src/App.css`; keep them visually
mapped to this palette.

## Food Flavor Accent

Tarelka/food flavor may use `#D97E4A` only in `android-concept/app/src/food/`
brand-scoped resources/code. Shared `src/main/` and `src/gluco/` must not use
that color. Gradle verifies this.

## Typography

- Serif (`PT Serif`) for screen titles, dates, and editorial headings.
- Sans (`Inter`) for body text, labels, buttons.
- Mono (`JetBrains Mono`) for every number, time, unit, and ID.

Do not use hero-sized type inside compact panels, rows, cards, or sidebars.

## Surfaces

Cards:

- surface fill;
- 0.5 dp/px hairline border;
- 10 px/dp radius on mobile, existing desktop radius tokens on desktop;
- no shadow.

Prefer full-width bands, hairline sections, or repeated item cards. Do not nest
cards inside cards except for modals/panels or repeated item groups.

## Buttons

Default buttons:

- 28-30 px/dp tall;
- outline/hairline border;
- compact sans text;
- no routine black fill.

Black fill `ink` is allowed only for:

- central capture FAB;
- `Принять` in the photo draft flow.

Destructive actions use warn text/border, not red filled buttons.

## Chips And Tags

- 22 px/dp tall;
- 6 px/dp radius on Android tags;
- 0.5 dp/px border;
- 11 sp/px medium text;
- active tag: `ink` fill plus light text.

Tags are status labels, not heavy navigation.

## Icons

- outline only;
- current-color;
- no emoji-as-icons;
- use existing icon libraries where available.

## Layout Stability

- Text must not overlap or clip at mobile and desktop widths.
- KPI numbers must survive large dynamic font settings.
- Fixed-format controls need stable dimensions.
- Sparse charts should collapse to intentional low-data states, not empty
  month-wide axes.

## Do Not

- Do not use gradients/orbs/bokeh decoration.
- Do not introduce new chromatic colors.
- Do not use black filled buttons for routine actions.
- Do not fake data to make charts look full.
- Do not show `--%` or raw floating point artifacts as primary values.
- Do not let food flavor brand assets leak into shared/gluco resources.
