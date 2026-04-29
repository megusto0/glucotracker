# Agent Context

Last updated: 2026-04-29

This is the short future-agent orientation note. For full detail, read
`docs/project-explainer.txt`, `docs/architecture.md`, `docs/api-contract.md`,
and `docs/frontend-contract.md`.

## Project TLDR

Glucotracker is a personal food diary for a type-1 diabetic. It logs meals,
macros, calories, photos, product labels, restaurant shortcuts, saved products,
daily totals, and optional Nightscout sync. It is informational only.

Never add insulin dosing, bolus, correction, treatment, or medical decision
recommendations.

## Core Rule

The backend is the product. The frontend is replaceable.

Backend owns:

- database schema and migrations
- REST API semantics and OpenAPI contract
- application-service orchestration
- macro and nutrient math
- draft, accept, discard, and re-estimate lifecycle
- Gemini normalization and model-routing behavior
- product memory and autocomplete semantics
- daily totals and dashboard data
- Nightscout sync, local import, and timeline boundaries

The Tauri desktop app is one client. A future Android client should consume the
same backend API without backend changes for desktop-specific behavior.

## Stack

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, SQLite.
- AI: backend-only Gemini integration through `google-genai`.
- Desktop: Tauri 2, React, TypeScript, Tailwind, TanStack Query, Zustand.
- Tests: backend pytest/ruff; desktop Vitest/build.

## Main User Flow

1. User creates a meal manually, from autocomplete, from a saved product, from a
   pattern, or by uploading photos.
2. Photo meals start as drafts.
3. Backend stores photos, calls Gemini if configured, normalizes the response,
   and calculates deterministic totals.
4. UI shows evidence, assumptions, confidence, warnings, and editable items.
5. User accepts or discards the draft.
6. Accepted meals count in daily totals. Drafts do not.
7. Accepted label-derived items can be remembered into the local product DB.

## Safety And Data Invariants

- Unknown optional nutrients are `null`, not `0`.
- Manual overrides beat product, restaurant, pattern, and Gemini estimates.
- Label/product/restaurant data beats visual estimates.
- Backend recalculates accepted totals; frontend does not own final macro math.
- Accepting `label_calc` items recalculates totals from label evidence and
  extracted facts; client-submitted label totals are not authoritative.
- Known-component replacement must require specific aliases or terms. Generic
  overlap such as `base`, `component`, or Russian `osnova` is not enough.
- Gemini API keys and Nightscout secrets stay backend-only.
- Nightscout insulin is imported as read-only context only; do not turn it into
  dosing advice or editable glucotracker treatment data.
- Food episodes are computed projections over accepted meal rows, local CGM,
  and read-only Nightscout insulin context. Do not merge or replace meals when
  building the history timeline.
- Multi-photo estimation must preserve photo identity.
- Unrelated photos should not be merged into one food item.
- Local wall-clock meal times should not be shifted through UTC conversion.
- Sodium and caffeine should not be visually guessed from plated food.

## Important Paths

- `backend/glucotracker/main.py` - FastAPI app and router registration.
- `backend/glucotracker/api/routers/` - REST endpoints by resource.
- `backend/glucotracker/application/` - use-case orchestration services.
- `backend/glucotracker/domain/` - food diary rules and deterministic logic.
- `backend/glucotracker/domain/known_components.py` - saved component matching guardrails.
- `backend/glucotracker/infra/db/` - SQLAlchemy models/session/seed helpers.
- `backend/glucotracker/infra/gemini/client.py` - Gemini prompt/client logic.
- `backend/glucotracker/application/photo_estimation.py` - photo estimate flow.
- `backend/glucotracker/application/product_memory.py` - accepted label product upserts.
- `backend/glucotracker/application/nightscout_sync.py` - optional Nightscout sync orchestration.
- `backend/glucotracker/application/nightscout_context.py` - local Nightscout import and computed food episodes.
- `desktop/src/features/chat/ChatPage.tsx` - main journal/photo draft screen.
- `desktop/src/features/meals/MealLedger.tsx` - meal rows and detail panels.
- `desktop/src/features/meals/useMealMutations.ts` - shared meal mutations (updateMealName, updateMealTime, duplicateMeal).
- `desktop/src/api/client.ts` - desktop API wrapper.

## Verification Commands

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Desktop:

```powershell
cd desktop
npm test -- --run
npm run build
```

OpenAPI generation:

```powershell
cd backend
.\scripts\export-openapi.sh
cd ..\desktop
npm run api:types
```

## Existing Longer References

- `docs/project-explainer.txt` - detailed domain, flow, Gemini, and UX notes.
- `docs/architecture.md` - stack decisions and layering rules.
- `docs/api-contract.md` - backend API contract.
- `docs/frontend-contract.md` - UI behavior contract.
- `docs/DESIGN.md` - visual design direction.
