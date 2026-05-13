# Reports And Export

Status: source of truth
Last updated: 2026-05-13
Owner/area: endocrinologist PDF, TXT food diary

Reports are backend-owned aggregations rendered/saved by desktop.

## Endocrinologist Report

API:

```http
GET /reports/endocrinologist?from=YYYY-MM-DD&to=YYYY-MM-DD&glucose_mode=raw|normalized
```

This endpoint is gluco-only and requires the `glucose` feature.

Backend aggregation lives in
`backend/glucotracker/application/endocrinologist_report.py`. Desktop rendering
lives in `desktop/src/features/reports/EndocrinologistReportPdf.tsx` and
`desktop/src/features/settings/EndocrinologistReportSection.tsx`.

## Report Windows

Current report constants:

- meal cluster window: 30 minutes;
- insulin link window: 30 minutes before to 90 minutes after a food episode;
- glucose window: 60 minutes before to 180 minutes after;
- report slots: `Завтрак`, `Обед`, `Ужин`, `Поздний приём`,
  `Перекусы (все окна)`;
- glucose modes: raw CGM or display-normalized.

Adaptive day anchors come from the user's learned/manual schedule.

## Report Contents

The backend returns presentation-ready data:

- period/generated labels;
- chips and low-data warning;
- KPI tiles;
- glycemic profile;
- adaptive schedule banner;
- meal profile rows;
- daily rows;
- bottom metrics;
- notes/footer text.

Desktop renders a one-page A4 PDF and saves it through the Tauri file dialog.

## TXT Food Diary Export

Desktop-only flow in `FoodDiaryExportSection.tsx`:

1. Fetch all accepted meals from `/meals` with pagination.
2. Build text via `desktop/src/utils/mealTextReport.ts`.
3. Save locally through Tauri.

The TXT export includes accepted meals only, grouped by day, with item-level
macros and period totals.

## Safety Rules

- Use `Наблюдаемый`, not "recommended".
- CGM/insulin values are context for discussion with a doctor.
- No dosing, bolus, correction, or treatment recommendations.

## Needs Verification

- Exact PDF visual layout should be verified with a generated sample after report
  schema changes.
