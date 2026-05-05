# Testing And Verification

Last updated: 2026-05-05

Use checks that match the change.

## Backend

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

For activity/dashboard work:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_nightscout_dashboard.py
```

## Desktop

Run from `desktop/`:

```powershell
npm run build
npm test -- --run
```

Known note: older frontend tests may fail if MSW handlers do not cover newer
activity/profile endpoints. Build is the minimum required check for UI-only
TypeScript/CSS changes.

## Tauri

Run from `desktop/src-tauri/`:

```powershell
cargo check
```

## Manual UI Checks

Start desktop dev server:

```powershell
cd desktop
npm run dev -- --host 127.0.0.1 --port 5173
```

Check:

- Journal row hierarchy with real meals and photos.
- History food episode cards with CGM sparkline and muted insulin rows.
- Glucose page at 3h, 6h, 12h, 24h, and 7d ranges.
- Stats with zero, one, two, and many tracked days.
- Settings button contrast and column alignment.

## Data Safety

Do not commit runtime data:

- `backend/data/`
- `desktop/data/`
- SQLite files
- local photos/product images
- generated repair dumps
