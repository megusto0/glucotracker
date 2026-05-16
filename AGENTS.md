# Glucotracker — Agent Instructions

Glucotracker: personal food diary for a person with type 1 diabetes.
Three projects in one repo: `backend/` (FastAPI), `desktop/` (Tauri 2 + React), `android-concept/` (Jetpack Compose).
Windows environment. PowerShell commands below.

## Key Documents

Read before non-trivial work:
- `CONCEPT.md` — mobile screens, design system, interactions
- `tokens.css` — color values (mirrored in `ui/design/tokens/GTColors.kt`)
- `glucotacker mobile.html` + `screens.jsx` + `design-canvas.jsx` — visual mockups
- `docs/openapi.json` — backend API contract (the only legitimate API surface)
- `docs/architecture.md` — repo layout, backend/desktop layers, data ownership

Quote relevant sections by number for non-trivial decisions
("per CONCEPT.md §5.2, hairline borders are 0.5px and never shadowed").

---

## Quick Dev Commands

**Backend** (from `backend/`):
```
.\.venv\Scripts\Activate.ps1
$env:GLUCOTRACKER_TOKEN = "dev"
uvicorn glucotracker.main:app --reload          # start server
.\.venv\Scripts\python.exe -m ruff check .       # lint
.\.venv\Scripts\python.exe -m pytest -q           # all tests
.\.venv\Scripts\python.exe -m pytest tests/test_api_meals.py  # single file
```
Launcher: `run-backend.cmd` (creates venv, runs migrations, starts uvicorn).

**Desktop** (requires backend at `http://127.0.0.1:8000`):
```
cd desktop; npm install; npm run tauri dev
npm run build                                    # tsc + vite
npm test -- --run                                # vitest
```
Regenerate API types after backend changes:
```
cd backend; .\.venv\Scripts\python.exe -c "import json; from pathlib import Path; from glucotracker.main import app; Path('../docs/openapi.json').write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding='utf-8')"
cd ..\desktop; npm run api:types
```

**Android** (from `android-concept/`):
```
.\gradlew.bat assembleDebug
.\gradlew.bat lint
.\gradlew.bat test
.\gradlew.bat installDebug
```

Pre-commit hooks: ruff check + ruff format + prettier (see `.pre-commit-config.yaml`).

---

## Repo Layout

```
backend/              FastAPI + SQLAlchemy/Alembic + Gemini + Nightscout (Python ≥3.11)
  glucotracker/
    main.py             FastAPI app and router registration
    api/routers/        REST endpoints
    application/        use cases (photo estimation, drafts, Nightscout, reports)
    domain/             deterministic business rules
    infra/db/           SQLAlchemy models, session, seed data
    infra/gemini/       Gemini prompts and client
    config.py           pydantic-settings, all env vars with defaults
  tests/                in-memory SQLite, no external services needed
desktop/              Tauri 2 + React + TypeScript + Tailwind
  src/api/client.ts     hand-written API wrapper over generated OpenAPI types
  src/api/generated/    schema.d.ts generated from docs/openapi.json
  src/features/*        page-level behavior
  src/design/primitives/Button.tsx  compact button primitive
android-concept/      Jetpack Compose mobile app
  app/src/main/.../ui/design/tokens/  GTColors, GTTypography, GTSpacing, GTShapes
  app/src/main/.../ui/format/         NutritionFormat helpers
  app/src/main/.../data/api/          OpenApiJson config, PhotoUploadClient
  app/src/main/.../data/sync/         OutboxWorkScheduler, OutboxProcessor
  app/src/main/.../data/cache/        CachePruneScheduler
docs/                 architecture, API contract, testing guide, UI rulebook
scripts/              OpenAPI export, sync scripts, report generators
mockup/, mockup-prototype/  historical redesign material (reference only)
```

---

## Backend Architecture

- Config via pydantic-settings with `GLUCOTRACKER_` prefix. Only `GLUCOTRACKER_TOKEN` needed for local dev.
- **DB sessions are sync** — `get_session` yields a sync `Session` from an async FastAPI dependency. This is intentional to avoid QueuePool starvation (see `docs/architecture.md`).
- Gemini keys/models are backend-only. Never expose to frontend.
- Tests use in-memory SQLite with foreign keys enabled (`tests/conftest.py`). No external services needed.
- `pytest-asyncio` mode is `auto` (configured in `pyproject.toml`).

---

## Android Architecture

**Stack**: Single-activity Compose, Hilt DI (uses **kapt**, not KSP), Ktor, Room (kapt), DataStore, WorkManager, CameraX, Coil 3, kotlinx-datetime, Compose Canvas.

**Layers**: `ui → domain → data`. Domain is pure Kotlin (no Android imports).
- `domain/model/` + `domain/repository/` — business models and repository interfaces
- `data/local/` — Room DAOs, entities
- `data/api/` — OpenAPI generated client + `OpenApiJson` (configured `Json` instance) + `PhotoUploadClient`
- `data/repository/` — repository implementations (local-first `Flow<T>`)
- `data/sync/` — `OutboxWorkScheduler`, `OutboxProcessor`
- `data/cache/` — `CachePruneScheduler`
- `ui/design/tokens/` — `GTColors`, `GTTypography`, `GTSpacing`, `GTShapes`
- `ui/design/GTTheme.kt` — `GT` accessor object (`GT.colors`, `GT.type`, `GT.space`, `GT.shapes`)
- `ui/format/` — `NutritionFormat.kt` helpers (use these, never inline number formatting)

**OpenAPI codegen**: The `generateApiClient` Gradle task runs `openapi-generator-cli` with `jvm-ktor` library target, wired to `preBuild`. Generated Kotlin sources land in `build/generated/openapi/`. The task post-processes generated files to patch `JsonElement` types and inject the `OpenApiJson` instance into `ApiClient.kt`. If the generated client breaks after an OpenAPI spec change, check the string replacements in `app/build.gradle.kts`.

**State**: ViewModel + StateFlow. UI consumes State; sends Intents.
**Repositories** return `Flow<T>`. Network errors map to a typed Result.

### Design System (CONCEPT.md §5, tokens.css)

Access via `GT.colors`, `GT.type`, etc. inside `@Composable` scope.

Colors (defined in `GTColors.kt`):
`bg #f6f4ef` `surface #fbfaf6` `surface2 #ffffff` `ink #25241f` `ink2 #4a4842`
`muted #8a857a` `hairline #e6e2d6` `hairline2 #d8d3c4`
`accent #5e6f3a` `good #6b8a5a` `warn #c98a55` `bad #2d3340` `info #6b7a92`

DO NOT add new colors. Differentiate by lightness/opacity.

Typography: Serif (PT Serif) for titles/hero (22–32sp). Sans (Inter) for body/buttons (11–14sp). Mono (JetBrains Mono) for every number, time, unit, ID. Numbers ALWAYS in mono.

Cards: surface fill, 0.5dp hairline border, 10dp radius, NO shadow.
Buttons: 28–30dp tall, outline only. Black-fill (`--ink`) ONLY on: (a) central FAB, (b) "Принять" in photo draft flow.
Tags: 22dp tall, 6dp radius, 0.5dp border, 11sp medium. Active tag: ink fill + light text.

### Number Formatting (ui/format/NutritionFormat.kt)

Use these helpers, never inline:
- kcal: integer, locale separator
- grams: integer or one decimal
- mmol/L: one decimal, comma decimal in ru
- kg: two decimals, comma decimal in ru
- percentages: integer
- signed kcal: typographical minus "−" (U+2212), never hyphen-minus

### Animations (CONCEPT.md §6)

Tab switches: instant. Record open: fade + 8dp up, 180ms. BottomSheet: Material spring ~250ms. Just-added row: bg highlight 1500ms ease-out. No decorative animation.

### Accessibility (CONCEPT.md §7)

Min touch target 44dp. Color never sole information carrier. Dynamic font: KPI numbers must not clip at xx-large. TalkBack: serif date as "5 мая 2026, вторник".

---

## Product Invariants (non-negotiable)

1. **Backend is source of truth for accepted records.** Client never recalculates nutrition totals, daily totals, calorie balance, TDEE, TIR, or product math. For PENDING records, client displays local values from input time. When server confirms, replace atomically. Pending and accepted items are NEVER conflated in headline totals: show accepted totals from server plus "+ N в очереди" hint.
2. **INFORMATIONAL ONLY.** Never recommend insulin dose, bolus, correction, target glucose, or treatment decision. Nightscout insulin = read-only context.
3. CGM raw values are immutable. Normalization is display-only.
4. Local wall-clock meal times must NOT shift through UTC conversion.
5. Editing `eaten_at` triggers backend mutation recomputing both old and new day totals.
6. Photos and product images are user-private. Never log or include in crash reports.
7. `eaten_at` = wall-clock shutter moment (camera) or EXIF DateTimeOriginal (gallery, fallback: file mtime, then "now"). Preserved unchanged through outbox → estimate → accept → server pipeline. User can edit explicitly; no automatic step rewrites it.

## Scope Invariants

- Mobile is CAPTURE-AND-GLANCE. Desktop owns deep editing, imports, PDF/TXT exports, Nightscout URL/secret config, OpenAPI.
- Where a feature is absent, render dotted-bordered hint "Доступно в десктоп-версии." (CONCEPT.md §2). Never silently hide.
- All user-facing copy in Russian. Use strings from CONCEPT.md and desktop UI; do not invent new ones.
- All Russian strings in `res/values/strings.xml`. Do not hardcode in composables.

## Offline-First Principle

- Read paths are local-first. Repositories return `Flow<T>`, emit cached data immediately, refresh from network in background.
- Product DB and templates mirrored in Room. Autocomplete works in airplane mode.
- Last 14 days meals + last 6 hours CGM cached offline. Older data → "нет данных".
- Photo capture, text input, template input work offline end-to-end. Mutation is durable in outbox on commit.
- Network unavailable > 60s → discreet "нет сети · данные на HH:MM" kicker. Never blocking overlay.
- Pending vs accepted rows visually distinguishable (status icon, no "принято" tag on pending).

## Agent Behavior

- If a screen needs an endpoint not in `docs/openapi.json`, STOP and ask. Do not invent endpoints or stub mock data.
- If you need a new color, font, or radius, STOP and ask.
- Prefer extending existing GT primitives over creating new ones.
- Every commit message: `feat(today): KPI 2x2 grid` / `fix(...)` format.
- When unsure between two approaches, write the trade-off in PR description and pick the simpler one.

## Data Safety

Never commit: `backend/data/`, `desktop/data/`, `*.db`, `*.sqlite*`, `.env`, local photos, product images, crash dumps. `local.properties` must use escaped backslashes (`C\:\\`) on Windows.

System prompt addendum
```
You are evolving an existing Glucotracker codebase to support two users
(diabetic + non-diabetic) over one backend, with the non-diabetic user
running a separate Android product flavor that ships without any
glucose-related code.

ALL invariants from the original B.1 system prompt remain in force.
ADDITIONAL invariants for this work:

MULTI-USER INVARIANTS:
  1. The backend is now multi-user. Every read of user-owned data
     (meals, photos, drafts, daily totals, glucose, fingersticks,
     templates, favorites, goals, Nightscout settings) MUST filter
     by current_user_id. There is no "anonymous" or "default" user
     after BE-2 lands.
  2. Products, product aliases, and restaurants are SHARED. They are
     accessible to all users. A product may have owner_id = NULL
     (global) or owner_id = some user (private to that user).
     Read query is always: WHERE owner_id IS NULL OR owner_id = :uid.
  3. owner_id is enforced in REPOSITORIES, not at endpoint level. An
     endpoint must NOT issue a raw SELECT against a scoped table.
     Repositories take user_id as a required parameter and refuse
     queries without it.
  4. Cross-user data leaks are the worst possible bug class. Every PR
     that touches a scoped repository must include a parametrized
     two-user isolation test for that repository.
  5. Migrations are FORWARD-ONLY and NON-DESTRUCTIVE. No DROP COLUMN,
     no DROP TABLE, no destructive UPDATE without a backup hook. The
     existing database has months of real personal data; treat it as
     production.

FEATURE-GATING INVARIANTS:
  6. User.role is enum: "gluco" | "food". A food user receiving any
     glucose-related response is a critical bug.
  7. Glucose-related endpoints (/glucose/*, /nightscout/*,
     /cgm/*, /fingersticks/*, /sensor-sessions/*, glucose fields
     embedded in /history responses) return HTTP 403 with body
     {"code": "feature_disabled", "feature": "glucose"} for food
     users. Not 404. Not silent removal. 403 with a stable code.
  8. The food Android flavor must contain ZERO glucose code in its
     compiled APK. This is enforced by source-set separation:
     glucose code lives in src/gluco/, never in src/main/. The food
     flavor's APK is verified by a build-time class scan.

AUTHENTICATION INVARIANTS:
  9. Passwords are stored as argon2id hashes. Never plaintext, never
     bcrypt, never sha-anything.
 10. Access tokens (JWT) have a short TTL (15 min). Refresh tokens
     have a long TTL (30 days) and are stored hashed server-side
     so they can be revoked. Logout invalidates the refresh token
     server-side.
 11. Mobile clients store tokens in EncryptedSharedPreferences (or
     DataStore + Tink). Never in plain SharedPreferences, never on
     disk in cleartext, never logged.
 12. /auth/register is NOT a public endpoint. User creation is done
     by an admin command (CLI script) at seed time. The app does not
     expose any "sign up" UI. This is a family tool, not a public
     SaaS.

DESIGN CONTINUITY:
 13. The food flavor is a SUBSET, not a redesign. Same warm editorial
     design system, same primitives, same fonts, same palette. The
     only differences are: 4 tabs instead of 5, no glucose surfaces,
     simpler Settings, different app name + icon.
 14. Brand-level changes (app name, launcher icon, splash) are
     flavor-scoped resources only. Do not change shared design tokens.

AGENT BEHAVIOR ADDITIONS:
  - When unsure whether a table or field is "personal" or "shared",
    STOP and ask. Default assumption: personal. Mark shared only when
    explicitly justified.
  - When in doubt about a query in a scoped repository, write the
    isolation test first; let it drive the implementation.
  - Never run a destructive migration even in development. If you
    need to "fix" a migration, write a new one that rolls forward.
