# Screens

Last updated: 2026-05-05

Routes are defined in `desktop/src/app/routes.tsx`.

## Shell

`Shell.tsx` renders:

- fixed 200px left sidebar
- scrollable `.gt-main`
- route content with page-owned padding

`Sidebar.tsx` contains:

- brand
- Journal, History, Glucose, Stats, Product DB, Settings navigation
- mini glucose widget when backend/Nightscout data exists
- connection footer

## Journal `/`

Primary food logging screen.

Main responsibilities:

- selected local day navigation
- manual food input
- photo flow and Gemini draft review
- accepted meal rows
- draft rows
- right-side selected meal panel
- Nightscout day sync affordance

Current row hierarchy:

- meal time and photo/name are dominant
- carbs and kcal are primary numeric values
- protein/fat/fiber and macro split bar are secondary
- micro-bars must never overpower the meal name/photo

Selected meal panel must show a compact summary before edit controls:

- name
- kcal
- carbs/protein/fat/fiber
- weight
- source
- confidence

## History `/feed`

Timeline of accepted food episodes and standalone events.

Rules:

- food episodes remain visually dominant
- CGM sparkline stays inside each food episode card
- insulin-only rows are muted
- History is projection-only; do not merge meals to build the view

## Glucose `/glucose`

Glucose dashboard and sensor context.

Current behavior:

- raw CGM remains stored unchanged
- normalization is display-only
- chart adapts by density:
  - short ranges show detailed events
  - longer ranges aggregate meals/events
  - sparse data avoids huge empty regions
- sensor panel and fingerstick forms are contextual tools, not primary page
  content

## Stats `/stats`

Nutrition, calorie balance, TIR, dayparts, and meal timing.

Real-data rules:

- fewer than 3 valid tracked days: summary mode, not full trend charts
- fewer than 14 valid days: charts focus actual tracked days
- current incomplete day is excluded from period calorie balance
- calorie balance is labelled relative to TDEE
- TIR renders normal 0-100 stacked bars
- daypart glucose profile always renders six 4-hour cards
- meal heatmap stays exactly 6x7, one 4-hour block per cell

## Product DB `/database`

Local product and pattern database.

Responsibilities:

- browse saved products/patterns
- product detail panel
- manual product creation
- import panel
- "use in journal" action

Backend remains source of product math and aliases.

## Settings `/settings`

Integration and local configuration screen.

Responsibilities:

- Nightscout URL/secret and sync flags
- backend URL/token checks
- theme selection
- TDEE profile fields
- endocrinologist PDF report
- TXT food diary export
- OpenAPI link

Settings buttons should stay compact and low-contrast. Avoid black filled
buttons except where a single row truly needs one primary destructive/commit
action.
