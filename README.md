# Glucotracker

Personal food diary monorepo for a type-1 diabetic. This app is an informational journal for meals and nutrition data. It is not used for insulin dosing.

## Layout

- `backend/` - FastAPI service, SQLAlchemy/Alembic database layer, workers, and external integration adapters.
- `desktop/` - Tauri 2 desktop client with React, TypeScript, and Tailwind.
- `docs/` - Architecture, frontend contract, API contract notes, manual testing, and shared design tokens.
- `scripts/` - Project helper scripts and generated-client automation hooks.

## Backend Dev

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
uvicorn glucotracker.main:app --reload
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Protected endpoints use `GLUCOTRACKER_TOKEN`:

```powershell
$env:GLUCOTRACKER_TOKEN = "dev"
uvicorn glucotracker.main:app --reload
Invoke-RestMethod http://127.0.0.1:8000/meals -Headers @{ Authorization = "Bearer dev" }
```

Gemini photo estimation uses backend-only environment variables:

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:GEMINI_MODEL = "gemini-2.5-flash"
$env:GEMINI_CHEAP_MODEL = "gemini-2.5-flash-lite"
$env:GEMINI_FREE_TEST_MODEL = "gemini-3.1-flash-lite-preview"
$env:GEMINI_FALLBACK_MODEL = "gemini-3-flash-preview"
```

Automatic routing uses lite models for `LABEL_FULL`, `GEMINI_MODEL` for `LABEL_PARTIAL` and `PLATED`, and `GEMINI_FALLBACK_MODEL` for low-confidence retry. Pro models are not used automatically.

Nightscout sync is optional:

```powershell
$env:NIGHTSCOUT_URL = "https://your-nightscout.example"
$env:NIGHTSCOUT_API_SECRET = "your-secret"
```

When unset, local food diary behavior still works and sync endpoints return `503`.

Load pattern seeds:

```powershell
cd backend
python -m glucotracker.infra.db.seed
```

Export OpenAPI:

```powershell
cd backend
bash scripts/export-openapi.sh
```

## Desktop Dev

```powershell
cd desktop
npm install
npm run tauri dev
```

Generated API types will be produced from the FastAPI OpenAPI document when API endpoints are added:

```powershell
cd desktop
npm run api:types
```

## Pre-commit

```powershell
pre-commit install
pre-commit run --all-files
```

The hooks run Ruff for Python and Prettier for frontend, docs, and config files.

## Docker Compose

```powershell
cd backend
docker compose up --build
```

The Compose setup is intended for an Ubuntu server deployment and keeps SQLite data under `backend/data/`.
