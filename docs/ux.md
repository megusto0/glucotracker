# UX

Status: source of truth
Last updated: 2026-05-13
Owner/area: interaction model, UI states, copy rules

Glucotracker is a repeated-use food diary, not a marketing surface and not a
medical recommendation engine. It should feel calm, precise, and fast.

Per `CONCEPT.md` §6, tab switches are instant, record open is fade + 8 px up for
180 ms, bottom sheets use a short Material spring, and there is no decorative
animation.

## Interaction Principles

- Fast entry beats decorative layout.
- Names, photos, and timestamps are higher priority than micro-visualizations.
- Numbers must be formatted predictably.
- Empty, sparse, stale, and offline states are normal states.
- Read-only medical context must stay passive and informational.
- Gestures are accelerators, never the only path.

## Loading And Empty States

- Journal empty day: show a short Russian prompt to use capture/text entry.
- Stats with fewer than 3 valid tracked days: show a summary/low-data state, not
  full trend claims.
- Glucose without CGM data: show `Нет данных...` copy, not fake chart points.
- Missing goals: show `цель не задана`, not failure language.
- Missing optional nutrients: render an em dash or omit the optional line; do not
  turn unknown values into zero.

## Offline And Pending

- Mobile mutations commit to local outbox first.
- Pending rows are visually distinct from accepted rows.
- Pending rows never mix into headline totals.
- The top banner stays discreet: queue/stale/stuck context, no blocking overlay.
- Stuck state offers explicit retry/delete/open actions in the inspector.

Current Android row-state vocabulary is derived from `OutboxState` and
`ui/format/RowState.kt`.

## Error Hygiene

- User-facing errors must be short, Russian, and actionable.
- `CancellationException` and process death must not become scary user copy.
- `401` means auth refresh/login flow, not a data error.
- `403 feature_disabled` means role capability, not expired auth.
- Network restoration should trigger retry; the user should not have to wait for
  a long periodic worker slot when the app can observe connectivity.

## Number Formatting

Use existing helpers instead of inline formatting:

- desktop: `desktop/src/utils/nutritionFormat.ts`;
- Android: `ui/format/NutritionFormat.kt`.

Rules:

- kcal: integer;
- grams: integer or one decimal;
- mmol/L: one decimal, comma decimal in Russian UI;
- kg: two decimals, comma decimal in Russian UI;
- percentages: integer;
- signed kcal: typographical minus `−`, not hyphen-minus;
- numbers, times, units, and IDs use mono type.

## Copy Boundaries

Use observational language:

- `наблюдаемый`
- `информационно`
- `контекст`
- `данных мало`
- `по последним дням`

Avoid:

- recommendations;
- praise/blame;
- streak pressure;
- dose/bolus/correction instructions;
- treatment advice;
- food judgement.

## Accessibility

Per `CONCEPT.md` §7:

- interactive touch targets are at least 44 dp/px equivalent;
- color is never the only carrier of information;
- KPI numbers must not clip at large dynamic font sizes;
- TalkBack/VoiceOver date labels should be semantic, e.g. `5 мая 2026, вторник`.
