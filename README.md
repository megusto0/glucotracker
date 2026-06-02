# Glucotracker

Status: source of truth
Last updated: 2026-05-31
Owner/area: repository entry point

Glucotracker is a personal food diary backend with desktop and Android clients.
It supports two roles over one backend:

- `gluco` - food diary plus glucose/Nightscout context;
- `food` - food diary subset shipped as the Android Tarelka flavor without
  glucose feature code.

Start with the maintained documentation map:

- [docs/README.md](docs/README.md)

## Important Boundaries

- Backend is the source of truth for accepted meals, totals, product math,
  Nightscout context, reports, and API semantics.
- Clients may show pending local rows, but they do not mix pending values into
  accepted headline totals.
- Gemini is backend-only.
- Nightscout insulin is read-only context.
- No insulin doses, boluses, corrections, target-glucose instructions, or
  treatment recommendations.

## Quick Commands

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

Desktop:

```powershell
cd desktop
npm run build
npm test -- --run
```

Android:

```powershell
cd android-concept
.\gradlew.bat assembleGlucoDebug assembleFoodDebug
.\gradlew.bat lint
.\gradlew.bat testGlucoDebug testFoodDebug
```

Regenerate API artifacts after backend API changes:

```powershell
bash scripts/export-openapi.sh
cd desktop
npm run api:types
```

If `bash` is unavailable in PowerShell, export from the FastAPI app directly:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "import json, yaml; from pathlib import Path; from glucotracker.main import app; schema = app.openapi(); Path('../docs/openapi.json').write_text(json.dumps(schema, indent=2, sort_keys=True) + '\n', encoding='utf-8'); Path('../docs/openapi.yaml').write_text(yaml.safe_dump(schema, allow_unicode=True, sort_keys=True), encoding='utf-8')"
cd ..\desktop
npm run api:types
```

Android consumes `docs/openapi.yaml` as well as desktop's `docs/openapi.json`,
so both artifacts must stay in sync.

## Docs

Current source-of-truth docs live in [docs/](docs/). Archived prompts, old specs,
screenshots, PDF samples, and temporary notes are under
[docs/archive/](docs/archive/).
