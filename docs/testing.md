# Testing And Verification

Status: source of truth
Last updated: 2026-05-31
Owner/area: local verification

Use checks that match the change. For docs-only changes, run link checks and
review generated Markdown. For code changes, use the relevant project checks
below.

## Backend

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

High-risk focused tests:

- auth/JWT: `tests/test_auth.py`, `tests/test_api_auth.py`
- user isolation: `tests/test_user_isolation.py`, `tests/test_shared_products.py`,
  `tests/test_isolation_meta.py`
- feature gating: `tests/test_feature_gating.py`
- OpenAPI export: `tests/test_openapi_export.py`
- meals/photos/Gemini: `tests/test_api_meals.py`,
  `tests/test_api_photo_capture.py`, `tests/test_api_photos_gemini.py`
- Nightscout/glucose: `tests/test_api_glucose.py`,
  `tests/test_api_latest_reading.py`, `tests/test_api_nightscout_dashboard.py`,
  `tests/test_nightscout_background.py`
- categorization/postprandial: `tests/test_categorization.py`,
  `tests/test_postprandial.py`
- insulin links: `tests/test_insulin_links.py`
- digital twin: `tests/api/test_twin_params.py`,
  `tests/application/twin/test_repository_isolation.py`,
  `tests/application/twin/test_estimator.py`, `tests/application/twin/test_fitter.py`
- reports: `tests/test_api_reports.py`

## Desktop

From `desktop/`:

```powershell
npm run build
npm test -- --run
```

After backend schema changes:

```powershell
npm run api:types
```

Tauri/Rust check:

```powershell
cd desktop\src-tauri
cargo check
```

## Android

From `android-concept/`:

```powershell
.\gradlew.bat assembleGlucoDebug assembleFoodDebug
.\gradlew.bat lint
.\gradlew.bat testGlucoDebug testFoodDebug
```

Food flavor checks are especially important because the APK must not expose
glucose classes or strings. Current Gradle tasks include food class/resource
scans and Tarelka color-scope checks:

```powershell
.\gradlew.bat verifyFoodDebugNoGlucoseClasses verifyTarelkaColorScope verifyFoodHasNoGlucose
```

## OpenAPI

Regenerate API artifacts after backend route/schema changes:

```powershell
bash scripts/export-openapi.sh
cd desktop
npm run api:types
```

If `bash` is not available in PowerShell, export directly:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "import json, yaml; from pathlib import Path; from glucotracker.main import app; schema = app.openapi(); Path('../docs/openapi.json').write_text(json.dumps(schema, indent=2, sort_keys=True) + '\n', encoding='utf-8'); Path('../docs/openapi.yaml').write_text(yaml.safe_dump(schema, allow_unicode=True, sort_keys=True), encoding='utf-8')"
cd ..\desktop
npm run api:types
```

Both paths update `docs/openapi.json` and `docs/openapi.yaml`.

## Documentation

For docs edits:

- check that every new document starts with status, last updated, and owner/area;
- keep archived files linked from the archive README;
- run a Markdown link check or the PowerShell link check from `doc-audit.md`;
- ensure root `README.md` points to `docs/README.md`.

## Data Safety

Do not commit:

- `backend/data/`
- `desktop/data/`
- `*.db`, `*.sqlite*`
- local photos/product images
- crash dumps
- `.env`
