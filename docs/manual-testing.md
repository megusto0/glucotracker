# Manual Testing

## Backend Health

```bash
cd backend
uvicorn glucotracker.main:app
curl http://localhost:8000/health
```

Expected result: HTTP 200 with `{"status":"ok"}`.

## Desktop Shell

```bash
cd desktop
npm run tauri dev
```

Expected result: an empty Glucotracker window with the off-white app background.

## Journal Date And Repeat UI

### Selected-day creation

1. Open the Журнал page.
2. Navigate to an older day, for example 28 April 2026.
3. Add a manual entry or upload a photo and save the meal.

Expected result: the created meal appears on the selected older day, not
automatically on today. This is intentional backfill behavior.

### Date/time correction

1. Click the meal row to open the right panel.
2. Change `Дата и время записи` to today's date/time.
3. Click `Сохранить дату`.

Expected result: the meal moves to the selected new day after queries refresh.
Daily totals for the old and new day are recalculated by the backend.

### Quick repeat one recognized package

Use an accepted label item whose evidence contains multiple identical packages,
for example `Халва подсолнечная глазированная ×3` with `60 г` total and
`20 г` per package.

1. Open the accepted meal in the right panel.
2. In `Повтор по весу`, find `Быстро из распознанного количества`.
3. Click `Добавить 1 упаковку`.

Expected result: the UI calls `POST /meal_items/{id}/copy_by_weight` with
`grams=20`. Backend creates a new accepted meal for one package, copies the
photo/source context, and scales totals from the original label item.

## Pre-commit

```bash
pre-commit run --all-files
```

Expected result: Ruff and Prettier complete without errors.

## Photo Estimation With Real Gemini

Set a backend token, Gemini key, and optional storage directory:

```bash
cd backend
export GLUCOTRACKER_TOKEN=dev
export GEMINI_API_KEY=your-key
export GEMINI_MODEL=gemini-2.5-flash
export GEMINI_CHEAP_MODEL=gemini-2.5-flash-lite
export GEMINI_FREE_TEST_MODEL=gemini-3.1-flash-lite-preview
export GEMINI_FALLBACK_MODEL=gemini-3-flash-preview
export PHOTO_STORAGE_DIR=./data/photos
uvicorn glucotracker.main:app
```

In another shell, create a photo draft meal:

```bash
export TOKEN=dev
export BASE=http://localhost:8000
curl -X POST "$BASE/meals" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Photo test\",\"source\":\"photo\",\"status\":\"draft\",\"items\":[]}"
```

Use the returned meal id in the scenarios below. Each scenario should be reviewed by calling `/estimate`, checking the suggestions, then sending reviewed items to `/accept`.

### Scenario 1: LABEL_FULL Chocolate Bar

Use a clear photo where the nutrition facts and net weight are both visible.

```bash
curl -X POST "$BASE/meals/{meal_id}/photos" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/chocolate-label-full.jpg;type=image/jpeg"

curl -X POST "$BASE/meals/{meal_id}/estimate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scenario_hint":"LABEL_FULL"}'
```

Expected result: suggested item has `source_kind=label_calc` and `calculation_method=label_visible_weight_backend_calc`. Carbs, protein, fat, fiber, and kcal are scaled by the backend from visible per-100g or per-100ml label facts and visible package size.

### Scenario 1b: LABEL_FULL Split Russian Candy Wrappers

Use a clear photo with two identical wrapped candies where one wrapper shows
nutrition per 100 g and another wrapper shows net weight. Recommended fixture
path once a real photo is available:

```text
docs/manual-testing/label-split-two-candies.jpg
```

Expected visible facts:

- 2 candies visible.
- 30 g net weight on each candy wrapper.
- 62 g carbs per 100 g.
- 4.5 g protein per 100 g.
- 16 g fat per 100 g.
- 410 kcal per 100 g.

Expected backend-calculated result:

- total weight: 60 g.
- carbs: 62 g / 100 g _ 30 g _ 2 = 37.2 g total.
- protein: 2.7 g total.
- fat: 9.6 g total.
- kcal: 246 kcal total.

Expected response: suggested item has `source_kind=label_calc`,
`calculation_method=label_split_visible_weight_backend_calc`, evidence says the
nutrition facts and net weight were read from different identical packages, and
assumptions include "Обе упаковки считаются одинаковым продуктом".

### Scenario 2: LABEL_PARTIAL Drink

Use a drink photo where nutrition facts are readable but the bottle or carton size is not visible.

```bash
curl -X POST "$BASE/meals/{meal_id}/photos" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/drink-label-partial.jpg;type=image/jpeg"

curl -X POST "$BASE/meals/{meal_id}/estimate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scenario_hint":"LABEL_PARTIAL"}'
```

Expected result: suggested item has `source_kind=label_calc` and `calculation_method=label_assumed_weight_backend_calc`. The assumption reason appears in `assumptions`, and backend totals are calculated from visible label facts plus Gemini's assumed weight or volume.

### Scenario 3: PLATED Chicken, Potato, Greens

Use a plated meal photo with chicken, potato, and greens visible. Include a plate, fork, card, hand, or other reference object if possible.

```bash
curl -X POST "$BASE/meals/{meal_id}/photos" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/plated-chicken-potato-greens.jpg;type=image/jpeg"

curl -X POST "$BASE/meals/{meal_id}/estimate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scenario_hint":"PLATED"}'
```

Expected result: suggested item has `source_kind=photo_estimate` and `calculation_method=visual_estimate_gemini_mid`. The response includes `reference_detected`, confidence, assumptions, evidence, and image quality warnings for review.

### Scenario 4: PLATED Tortilla/Lavash With Known Component

Create or save a local component first:

```text
Тортилья 40 г
aliases: тортилья, лаваш, tortilla, wrap base
source_kind: personal_component
serving: 40 g
carbs_per_serving: 24 g
protein_per_serving: 4 g
fat_per_serving: 4 g
kcal_per_serving: 150
```

Then estimate a photo of one tortilla/lavash wrap with chicken, vegetables, and sauce.

Expected result:

- Gemini returns one plated item with a `component_estimates` entry for the tortilla/lavash known component.
- Backend keeps one draft row for the coherent wrap, not separate rows for tortilla/chicken/vegetables/sauce.
- Suggested item has `calculation_method=visual_estimate_with_known_component`.
- `evidence.known_component.raw_model_estimate` keeps the model's raw macro estimate.
- `evidence.known_component.final_backend_adjusted_values` uses saved component values where known.
- The UI shows `Компоненты`, `Оценка модели`, and `Итог после корректировки`.
- If the component is missing, the item keeps the visual estimate and shows `Углеводная основа не найдена в базе. Значение оценено визуально.`
