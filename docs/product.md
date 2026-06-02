# Product

Status: source of truth
Last updated: 2026-05-31
Owner/area: product scope and invariants

Glucotracker is a personal food diary for a family setup with two user roles:

- `gluco` - food diary plus glucose/Nightscout context for a person with type 1
  diabetes;
- `food` - food diary subset without glucose code or glucose responses.

Tarelka is the Android food flavor. It is a subset of Glucotracker, not a
redesign.

## Product Does

- logs meals, photos, food items, macros, kcal, products, templates, and history;
- supports photo estimation through backend-owned Gemini calls;
- stores accepted records and totals on the backend;
- imports Nightscout CGM/insulin events as read-only context for `gluco` users;
- sends accepted meals to Nightscout as diary-only treatments when requested;
- manages gluco-only sensor sessions, fingerstick calibration context, and
  corrupt-sensor exclusion for analytics/display paths;
- supports day review of food/insulin context links with persisted episode
  snapshots and CGM anchors where data exists;
- provides an informational digital twin research mode for fitted parameters and
  reconstructed curves;
- builds statistics, deterministic insights, and doctor-facing reports;
- supports offline-first Android capture through local cache and outbox.

## Product Does Not

- recommend insulin dose, bolus, correction, target glucose, or treatment;
- expose public registration;
- expose Gemini keys or Nightscout secrets to frontend code;
- let clients recompute accepted totals, product math, TDEE, TIR, or report
  aggregates;
- include glucose surfaces in the food flavor.

## Client Scope

Per `CONCEPT.md` §1, mobile is "capture and glance"; desktop owns deep review,
configuration, imports, OpenAPI, PDF/TXT export, and richer editing.

Current split:

- Desktop: journal, history, glucose dashboard, stats, product DB, settings,
  Nightscout credentials, insulin-link review, twin research mode, PDF report,
  TXT export, OpenAPI link.
- Android gluco: login, Today, Glucose, History, More, capture, record, outbox,
  local-first cache.
- Android food/Tarelka: login, Today, History, Base, More, capture, record,
  outbox, no glucose surfaces.

## Source Of Truth Rules

- Backend is source of truth for accepted data.
- Pending Android rows can show local values from input time, but accepted totals
  come from the backend after sync.
- Raw CGM values are immutable. Any normalization is display-only.
- Excluding a corrupt sensor hides that interval from eligible analytics/display
  paths but does not delete raw CGM rows.
- Digital twin output is reconstructed/informational context, not CGM truth and
  not a dosing basis.
- `eaten_at` is a local wall-clock meal/capture time and must not shift through
  UTC conversion.
- Editing `eaten_at` is a backend mutation that recomputes both old and new day
  totals.
- Photos and product images are private user data and must not be logged.

## User-Owned Vs Shared

User-owned: meals, photos, drafts, daily totals, glucose, fingersticks, templates,
favorites, goals, Nightscout settings, activity/profile data, reports.

Shared: global products and aliases where `owner_id IS NULL`. Private products
are visible only to their owner.

`needs verification`: the prompt-level invariant says restaurants are shared.
Current backend models do not expose a first-class `Restaurant` table; restaurant
metadata appears on products/imported product records. Treat any future
restaurant table as shared only after code confirms it.

## Language

All user-facing app copy is Russian. Documentation may use English technical
terms where they match code names, but UI strings should not be invented in
docs.
