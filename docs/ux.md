# UX

Last updated: 2026-05-05

## Product Posture

Glucotracker is a work tool for repeated daily logging, review, and context.
It should feel calm, editorial, and precise. It is not a marketing site, a SaaS
dashboard, or a medical recommendation engine.

## Interaction Principles

- Fast daily entry matters more than decorative layout.
- Names, photos, and timestamps beat micro-visualizations.
- Numbers are useful only when formatted predictably.
- Empty and sparse data are normal states.
- Read-only medical context must be clearly passive.

## Real Data Resilience

The UI must remain stable with:

- one day of data
- no data
- missing macro targets
- missing glucose slots
- long decimals from backend math
- sparse CGM
- empty activity/TDEE profile
- outlier calorie balance days

Use summaries, dashes, "нет данных", or "нет цели" instead of fake precision.

## Number Formatting

- kcal: integer
- grams: integer or max 1 decimal
- mmol/L: 1 decimal
- kg: 2 decimals, comma in Russian UI
- percentages: integer
- no binary floating point artifacts

Use `desktop/src/utils/nutritionFormat.ts` rather than ad hoc `toFixed` in page
components.

## Hierarchy

Journal rows:

1. time
2. photo/name/source/status
3. carbs and kcal
4. protein/fat/fiber
5. macro split bar
6. actions

History:

1. food episode card
2. episode summary and CGM sparkline
3. meal lines
4. muted insulin-only lines

Stats:

1. date/verdict
2. KPIs
3. primary charts
4. secondary profiles
5. data quality/footer context

## Buttons

Buttons should be compact and quiet:

- default: hairline border, surface background
- primary: slightly stronger graphite border/text, usually no black fill
- destructive/danger: warn text and soft warn border
- icon-only: square 28-30px

Avoid making routine actions visually compete with the page title or content.

## Safety Copy

When describing Nightscout insulin or observed glucose context, use passive
phrasing:

- "read-only context"
- "observed"
- "informational"
- "not used for dose calculation"

Do not use:

- "recommended"
- "dose"
- "bolus"
- "correction" as an instruction
- "treatment advice"
