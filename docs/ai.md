# AI And Deterministic Logic

Status: source of truth
Last updated: 2026-05-13
Owner/area: Gemini usage and deterministic boundaries

Gemini is backend-only. No frontend or Android flavor may hold Gemini API keys,
model names as secrets, or direct Gemini calls.

## Gemini Uses

Confirmed code paths:

- photo estimation in `backend/glucotracker/application/photo_estimation.py` and
  `api/routers/photos.py`;
- Gemini client/model routing in `backend/glucotracker/infra/gemini/`;
- taste-profile classification in categorization code using the cheap/Flash Lite
  model path;
- AI run audit rows in `ai_runs`.

Photo estimation accepts stored photos plus optional user context, asks Gemini
for structured food evidence, then normalizes results into backend meal/item
objects.

## Deterministic Backend Logic

The backend, not the LLM, owns:

- label math and per-100g/per-serving conversion;
- product lookup and known component substitution;
- accepted meal totals and day totals;
- adaptive meal windows and day anchors;
- meal role/window derivation where rule-based;
- postprandial CGM analysis thresholds and coverage flags;
- stats insight ranking/templates;
- report aggregation and doctor-facing labels.

LLM output is evidence/input. It is not accepted nutrition truth until backend
normalization and user acceptance.

## Audit And Privacy

AI runs can store structured raw response data for debugging. Do not log local
photos or include private image bytes in crash reports. User context text should
be treated as untrusted prompt input.

## Failure Modes

- Gemini quota/auth/model errors should surface as estimate status/error on the
  meal or AI run.
- A successful Gemini response with no normalized items is still a failed
  estimation from the product user's perspective.
- Re-estimation is a backend action and should keep prior records auditable.

## Needs Verification

- Exact model defaults change through `Settings` and environment variables. Read
  `backend/glucotracker/config.py` before documenting a specific model as
  guaranteed.
