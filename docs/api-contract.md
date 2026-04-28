# API Contract

The backend exposes a REST + JSON API for a replaceable frontend. The Tauri desktop client and future Kotlin/Compose Android client must use the same API semantics.

All endpoints require `Authorization: Bearer <GLUCOTRACKER_TOKEN>` except `GET /health` and `GET /openapi.json`.

The frontend never owns final macro math. Draft estimates can be edited in the UI, but accepted meal totals, item totals returned by the API, and daily totals are backend-owned.

Optional nutrient tracking is backend-owned too. Unknown nutrient amounts are `null`, not `0`. Manual overrides have highest priority. Label/product/restaurant database values beat Gemini visual estimates. Gemini can extract visible label facts, but the backend performs deterministic per-100g/per-100ml/per-serving arithmetic. Sodium and caffeine must not be visually guessed from plated food.

## Lifecycle

1. Create a meal as a draft or accepted entry.
2. Upload one or more photos with `POST /meals/{id}/photos`.
3. Call `POST /meals/{id}/estimate` to receive Gemini draft suggestions without saving, or `POST /meals/{id}/estimate_and_save_draft` to persist draft journal rows.
4. For label photos, Gemini extracts visible facts and package size; the backend performs deterministic arithmetic for label totals.
5. The user edits draft items.
6. The frontend sends the final reviewed items to `POST /meals/{id}/accept`.
7. The backend atomically replaces items, recalculates totals, computes confidence, and sets `status=accepted`.
8. Accepted `label_calc` items are remembered in the local `products` database. The backend upserts by barcode when available, otherwise by brand/name, links the accepted `meal_item.product_id` to the remembered product, and uses the source meal photo as `product.image_url` when available.
9. Drafts can be discarded with `POST /meals/{id}/discard`.
10. Accepted meals remain editable, but every item edit or replacement recalculates backend totals.

## Enums

### `MealStatus`

- `draft`
- `accepted`
- `discarded`

### `MealSource`

- `photo`
- `pattern`
- `manual`
- `mixed`

### `ItemSourceKind`

- `photo_estimate`
- `label_calc`
- `restaurant_db`
- `product_db`
- `pattern`
- `manual`

### `PhotoReferenceKind`

- `coin_5rub`
- `card`
- `hand`
- `fork`
- `plate`
- `none`

### `PhotoScenario`

- `label_full`
- `label_partial`
- `plated`
- `barcode`
- `reference`
- `unknown`

## Models

## Restaurant Database Imports

Official restaurant data is imported as reviewable pattern rows. Importers write
YAML under `backend/pattern_seeds/` and the seed loader upserts by
`(prefix, key)`.

Prefixes:

- `bk`: Burger King official PDF.
- `rostics`: Rostic's official PDF.
- `vit`: Вкусно и точка official public menu data when available.

Imported restaurant rows include default per-serving macros plus optional
per-100g values:

- `default_grams`
- `default_kcal`
- `default_carbs_g`
- `default_protein_g`
- `default_fat_g`
- `per_100g_kcal`
- `per_100g_carbs_g`
- `per_100g_protein_g`
- `per_100g_fat_g`
- `source_name`
- `source_file`
- `source_page`
- `source_confidence`, for example `official_pdf` or
  `official_menu_partial`
- `is_verified`, default `false`

The database endpoint `GET /database/items` returns imported restaurant rows
with `source_file`, `source_page`, `source_confidence`, `is_verified`, and
`quality_warnings`. Imported rows are intentionally reviewable; frontends should
show `нужно проверить` until the user marks a row verified in a later workflow.

Autocomplete uses the same pattern search path, so `bk:воппер` and
`rostics:наггетсы` resolve imported restaurant items without Gemini.

### `Meal`

- `id`: UUID
- `eaten_at`: datetime, indexed, required
- `title`: string, nullable
- `note`: string, nullable
- `status`: `MealStatus`, default `draft`
- `source`: `MealSource`
- `total_carbs_g`: float, backend-calculated
- `total_protein_g`: float, backend-calculated
- `total_fat_g`: float, backend-calculated
- `total_fiber_g`: float, backend-calculated
- `total_kcal`: float, backend-calculated
- `confidence`: float `0..1`, nullable
- `nightscout_synced_at`: datetime, nullable
- `nightscout_id`: string, nullable
- `created_at`: datetime
- `updated_at`: datetime
- `items`: `MealItem[]`
- `photos`: `Photo[]`

### `MealItem`

- `id`: UUID
- `meal_id`: UUID
- `name`: string
- `brand`: string, nullable
- `grams`: float, nullable
- `serving_text`: string, nullable
- `carbs_g`: float
- `protein_g`: float
- `fat_g`: float
- `fiber_g`: float
- `kcal`: float
- `confidence`: float `0..1`, nullable
- `confidence_reason`: string, nullable
- `source_kind`: `ItemSourceKind`
- `calculation_method`: string, nullable
- `assumptions`: JSON array
- `evidence`: JSON object
- `warnings`: JSON array
- `pattern_id`: UUID, nullable
- `product_id`: UUID, nullable
- `photo_id`: UUID, nullable
- `position`: integer
- `nutrients`: `MealItemNutrient[]` in responses; create/update payloads may send a nutrient object keyed by nutrient code
- `created_at`: datetime
- `updated_at`: datetime

AI-estimated items include the same response fields. `assumptions`, `evidence`, `warnings`, `confidence`, and `confidence_reason` must be displayed as review context rather than treated as final user decisions.

### `NutrientDefinition`

- `code`: string primary key, e.g. `sodium_mg`
- `display_name`: string
- `unit`: string
- `category`: string
- `created_at`: datetime

Built-in definitions:

- `sodium_mg`, mg
- `caffeine_mg`, mg
- `sugar_g`, g
- `potassium_mg`, mg
- `iron_mg`, mg
- `calcium_mg`, mg
- `magnesium_mg`, mg

### `MealItemNutrient`

- `id`: UUID
- `meal_item_id`: UUID
- `nutrient_code`: string
- `amount`: float, nullable. `null` means unknown and is not counted as zero.
- `unit`: string
- `source_kind`: string, e.g. `manual`, `label_calc`, `product_db`, `restaurant_db`, `pattern`, `photo_estimate`
- `confidence`: float `0..1`, nullable
- `evidence_json`: JSON object
- `assumptions_json`: JSON array
- `created_at`: datetime
- `updated_at`: datetime

Meal item create/update accepts:

```json
{
  "nutrients": {
    "sodium_mg": {
      "amount": 720,
      "unit": "mg",
      "source_kind": "manual"
    },
    "caffeine_mg": {
      "amount": null,
      "unit": "mg"
    }
  }
}
```

### `Photo`

- `id`: UUID
- `meal_id`: UUID
- `path`: string
- `original_filename`: string, nullable
- `content_type`: string, nullable
- `taken_at`: datetime, nullable
- `scenario`: `PhotoScenario`
- `has_reference_object`: boolean
- `reference_kind`: `PhotoReferenceKind`
- `gemini_response_raw`: JSON object, nullable
- `created_at`: datetime

### `EstimateMealResponse`

Request:

- `use_patterns`: UUID array, optional
- `use_products`: UUID array, optional
- `scenario_hint`: optional `LABEL_FULL`, `LABEL_PARTIAL`, `PLATED`, `BARCODE`, or `UNKNOWN`

- `meal_id`: UUID
- `source_photos`: uploaded source photo references with `id`, `index`, `url`, `thumbnail_url`, and `original_filename`
- `suggested_items`: `MealItem[]` create payloads normalized by the backend
- `suggested_totals`: backend-calculated totals for the suggested items
- `calculation_breakdowns`: backend-prepared per-item evidence sheet for UI display
- `gemini_notes`: string
- `image_quality_warnings`: string array
- `reference_detected`: `PhotoReferenceKind`
- `ai_run_id`: UUID
- `raw_gemini_response`: JSON object, nullable, for development/debug review
- `created_drafts`: rows created by `estimate_and_save_draft`; each row has `meal_id`, `title`, `source_photo_id`, `thumbnail_url`, one `item`, and backend totals

For `LABEL_FULL` and `LABEL_PARTIAL`, Gemini returns extracted nutrition facts and visible or assumed package size separately. The backend converts those facts into `suggested_items` using `label_visible_weight_backend_calc` or `label_assumed_weight_backend_calc`.

For multi-photo estimates, the backend sends Gemini an ordered photo manifest and requires each returned item to identify `source_photo_ids`, `source_photo_indices`, and `primary_photo_id`. These values are copied into each suggested item's `evidence` object, and `photo_id` is set to the item's primary source photo when it can be resolved. Frontends should use these fields to show the correct source image per draft item. If multiple unrelated photos produce only one item, or an item cannot be linked to a source photo, the backend returns a Russian review warning in `image_quality_warnings` and/or item `warnings`.

When `estimate_and_save_draft` receives multiple unrelated `EstimatedItem` values, the backend creates one `draft` meal row per item instead of one combined meal. Same-product evidence, such as `SPLIT_LABEL_IDENTICAL_ITEMS` or `count_detected > 1`, stays as one draft row with totals for the detected count.

For `PLATED` visual estimates, Gemini may return `component_estimates`. Reusable components such as tortilla/lavash, bread, rice, pasta, potato, sweet drinks, candy, cereal, bakery items, and other saved products can be marked as `component_type="carb_base"` or `component_type="known_component"` with `should_use_database_if_available=true`. The backend searches saved products/patterns and aliases for matching personal components before finalizing the item. If a match is found, known component values replace the model's raw component values per field: carbs, protein, fat, fiber, kcal, and optional nutrients when present. Unknown saved fields remain `null` and do not overwrite model values with zero. `evidence.known_component` records matched components, raw Gemini values, field sources, and backend-adjusted totals. If no match is found, the backend keeps the visual estimate and adds the Russian warning `Углеводная основа не найдена в базе. Значение оценено визуально.`

`calculation_breakdowns` is presentation-ready evidence, not a separate source of truth. It can include `count_detected`, `net_weight_per_unit_g`, `total_weight_g`, `nutrition_per_100g`, `calculated_per_unit`, `calculated_total`, `calculation_steps`, `evidence`, and `assumptions`. Frontends should render these fields as readable review context and still submit `suggested_items` to `/accept`.

Gemini model routing is backend-owned:

- Default photo estimation uses `GEMINI_MODEL`; current recommended free-limit setup is `gemini-3-flash-preview`.
- Simple label extraction / quota-saving mode can use `GEMINI_CHEAP_MODEL`.
- `LABEL_FULL` uses `GEMINI_FREE_TEST_MODEL` when configured, otherwise `GEMINI_CHEAP_MODEL`.
- `LABEL_PARTIAL` and `PLATED` use `GEMINI_MODEL`.
- Missing `scenario_hint`, `BARCODE`, and `UNKNOWN` use `GEMINI_MODEL`.
- A temporary `503 UNAVAILABLE` / high-demand Gemini error retries the same model up to `GEMINI_MAX_RETRIES_PER_MODEL`, then tries `GEMINI_FALLBACK_MODELS` and finally `GEMINI_FALLBACK_MODEL`.
- `429 RESOURCE_EXHAUSTED` is treated as quota/rate-limit for that model; it is not repeatedly retried, but configured fallback models may be tried.
- JSON/schema parse failures retry once when possible, then follow the same fallback path.
- If any item confidence is below `GEMINI_LOW_CONFIDENCE_RETRY_THRESHOLD`, the backend retries with configured fallback models.
- Pro models are not selected automatically. Automatic routing rejects model names containing `pro`.
- `ai_runs.request_summary` records `scenario_hint`, `model_requested`, `model_used`, `fallback_used`, `attempts`, `error_history`, `latency_ms`, `model_attempts`, and `routing_reason`.
- If all attempts fail, the photo meal remains a retryable draft with uploaded photos attached; no accepted meal or empty 0-macro draft is created by the estimate endpoint.

### `Product`

- `id`: UUID
- `barcode`: string, nullable
- `brand`: string, nullable
- `name`: string
- `default_grams`: float, nullable
- `default_serving_text`: string, nullable
- `carbs_per_100g`: float, nullable
- `protein_per_100g`: float, nullable
- `fat_per_100g`: float, nullable
- `fiber_per_100g`: float, nullable
- `kcal_per_100g`: float, nullable
- `carbs_per_serving`: float, nullable
- `protein_per_serving`: float, nullable
- `fat_per_serving`: float, nullable
- `fiber_per_serving`: float, nullable
- `kcal_per_serving`: float, nullable
- `source_kind`: string, default `manual`
- `source_url`: string, nullable
- `image_url`: string, nullable, display-only thumbnail metadata
- `usage_count`: integer
- `last_used_at`: datetime, nullable
- `aliases`: string array
- `created_at`: datetime
- `updated_at`: datetime

### `Pattern`

- `id`: UUID
- `prefix`: namespace string, for example `bk`
- `key`: shortcut key, unique with `prefix`
- `display_name`: string
- `default_grams`: float, nullable
- `default_carbs_g`: float
- `default_protein_g`: float
- `default_fat_g`: float
- `default_fiber_g`: float
- `default_kcal`: float
- `source_url`: string, nullable
- `image_url`: string, nullable, display-only thumbnail metadata
- `usage_count`: integer
- `last_used_at`: datetime, nullable
- `is_archived`: boolean
- `aliases`: string array
- `matched_alias`: string, nullable on search responses
- `created_at`: datetime
- `updated_at`: datetime

Patterns are personal, restaurant, or common shortcuts like `bk:whopper`. Products are packaged foods, labels, barcodes, and remembered items.

Patterns and products may include `nutrients_json`. When a pattern/product is used to create a meal item, the backend copies those nutrient values into `meal_item_nutrients` unless a higher-priority nutrient source is present.

### `AutocompleteSuggestion`

- `kind`: `pattern`, `product`, or `command`
- `id`: UUID, nullable
- `token`: string to insert/use, such as `bk:whopper` or a barcode
- `display_name`: string
- `subtitle`: string, nullable
- `carbs_g`: float, nullable
- `protein_g`: float, nullable
- `fat_g`: float, nullable
- `kcal`: float, nullable
- `image_url`: string, nullable
- `usage_count`: integer
- `matched_alias`: string, nullable

### `DailyTotal`

- `date`: date
- `kcal`: float
- `carbs_g`: float
- `protein_g`: float
- `fat_g`: float
- `fiber_g`: float
- `meal_count`: integer
- `estimated_item_count`: integer
- `exact_item_count`: integer
- `updated_at`: datetime

Daily totals are backend-owned and include accepted meals only. Meal and item mutations schedule in-process recalculation for affected days. `POST /admin/recalculate` is the manual recovery path for backfills or crash recovery.

### Nightscout

Nightscout is optional. If `NIGHTSCOUT_URL` or `NIGHTSCOUT_API_SECRET` is missing, local meal, photo, pattern, product, autocomplete, and dashboard endpoints continue working. Sync endpoints return HTTP 503 with `Nightscout not configured`.

Synced meals are posted as Nightscout treatments with `eventType="Carb Correction"`, meal carbs/protein/fat, notes, and `enteredBy="glucotracker"`. Insulin is never included.

## Endpoint Examples

Set a token once:

```bash
TOKEN=dev
BASE=http://localhost:8000
AUTH="Authorization: Bearer $TOKEN"
```

### `GET /health`

Public health check.

```bash
curl "$BASE/health"
```

Response:

```json
{ "status": "ok", "version": "0.1.0", "db": "ok" }
```

### `GET /openapi.json`

Public OpenAPI schema for generated clients.

```bash
curl "$BASE/openapi.json"
```

### `POST /meals`

Create a meal with optional inline items. Manual and pattern meals default to `accepted`; photo and mixed meals default to `draft` unless `status` is supplied.

```bash
curl -X POST "$BASE/meals" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "eaten_at": "2026-04-28T08:30:00Z",
    "title": "Breakfast",
    "note": "Manual entry",
    "source": "manual",
    "items": [
      {
        "name": "Greek yogurt",
        "grams": 150,
        "carbs_g": 8,
        "protein_g": 15,
        "fat_g": 4,
        "fiber_g": 0,
        "kcal": 128,
        "source_kind": "manual",
        "assumptions": [],
        "evidence": {},
        "warnings": []
      }
    ]
  }'
```

### `GET /meals`

Paginated meal list. Query parameters: `from`, `to`, `limit`, `offset`, `q`, `status`.

```bash
curl -H "$AUTH" "$BASE/meals?limit=50&offset=0&q=yogurt&status=accepted"
```

Response shape:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

### `GET /meals/{id}`

Return one meal with items and photos.

```bash
curl -H "$AUTH" "$BASE/meals/{meal_id}"
```

### `PATCH /meals/{id}`

Patch `title`, `note`, `eaten_at`, or `status`. Totals are recalculated before returning.

```bash
curl -X PATCH "$BASE/meals/{meal_id}" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{ "title": "Updated breakfast", "note": "Corrected" }'
```

### `DELETE /meals/{id}`

Delete a meal. Items and photos cascade.

```bash
curl -X DELETE -H "$AUTH" "$BASE/meals/{meal_id}"
```

Response:

```json
{ "deleted": true }
```

### `POST /meals/{id}/photos`

Upload a JPEG, PNG, or WebP photo for an existing meal. Maximum size is 10 MB. The stored file path is backend-owned and should not be used by frontends for direct filesystem access.

```bash
curl -X POST "$BASE/meals/{meal_id}/photos" \
  -H "$AUTH" \
  -F "file=@/path/to/meal.jpg;type=image/jpeg"
```

Response shape:

```json
{
  "id": "22222222-2222-2222-2222-222222222222",
  "meal_id": "11111111-1111-1111-1111-111111111111",
  "path": "2026/04/22222222-2222-2222-2222-222222222222.jpg",
  "original_filename": "meal.jpg",
  "content_type": "image/jpeg",
  "taken_at": null,
  "scenario": "unknown",
  "has_reference_object": false,
  "reference_kind": "none",
  "gemini_response_raw": null,
  "created_at": "2026-04-28T12:00:00Z"
}
```

### `GET /photos/{id}/file`

Stream stored image bytes.

```bash
curl -H "$AUTH" "$BASE/photos/{photo_id}/file" --output photo.jpg
```

### `DELETE /photos/{id}`

Delete the database row and the stored file. Existing meal items that referenced the photo are detached from that photo.

```bash
curl -X DELETE -H "$AUTH" "$BASE/photos/{photo_id}"
```

### `POST /meals/{id}/items`

Add an item and recalculate meal totals. If `pattern_id` or `product_id` is used, backend usage counters are incremented.

```bash
curl -X POST "$BASE/meals/{meal_id}/items" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Toast",
    "carbs_g": 20,
    "protein_g": 4,
    "fat_g": 2,
    "fiber_g": 3,
    "kcal": 114,
    "source_kind": "manual"
  }'
```

### `PATCH /meal_items/{id}`

Patch an item and recalculate the parent meal totals.

```bash
curl -X PATCH "$BASE/meal_items/{item_id}" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{ "carbs_g": 22, "kcal": 122 }'
```

### `POST /meal_items/{id}/remember_product`

Persist a confirmed label-calculated item into the local product database. This is idempotent with the automatic product upsert that runs during `/meals/{id}/accept`, but lets a UI add user aliases such as `сырок`, `глазированный сырок`, or `творожный сырок`.

```bash
curl -X POST "$BASE/meal_items/{item_id}/remember_product" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{ "aliases": ["сырок", "глазированный сырок"] }'
```

### `DELETE /meal_items/{id}`

Delete an item and recalculate the parent meal totals.

```bash
curl -X DELETE -H "$AUTH" "$BASE/meal_items/{item_id}"
```

### `PUT /meals/{id}/items`

Atomically replace all items for a meal. This supports frontend edit flows without client-side patch sequencing.

```bash
curl -X PUT "$BASE/meals/{meal_id}/items" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "name": "Rice",
      "carbs_g": 45,
      "protein_g": 4,
      "fat_g": 1,
      "fiber_g": 1,
      "kcal": 205,
      "source_kind": "manual"
    }
  ]'
```

### `POST /meals/{id}/estimate`

Run Gemini estimation using all photos attached to the meal. This stores an `ai_runs` row and raw Gemini output on the first photo, but it does not save suggested items to the meal and does not accept the meal.

```bash
curl -X POST "$BASE/meals/{meal_id}/estimate" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "use_patterns": [],
    "use_products": [],
    "scenario_hint": "LABEL_FULL"
  }'
```

Response shape:

```json
{
  "meal_id": "11111111-1111-1111-1111-111111111111",
  "source_photos": [
    {
      "id": "22222222-2222-2222-2222-222222222222",
      "index": 1,
      "url": "/photos/22222222-2222-2222-2222-222222222222/file",
      "thumbnail_url": "/photos/22222222-2222-2222-2222-222222222222/file",
      "original_filename": "label.jpg"
    }
  ],
  "suggested_items": [
    {
      "name": "Chocolate bar",
      "brand": "Example",
      "grams": 50,
      "carbs_g": 28,
      "protein_g": 3,
      "fat_g": 12,
      "fiber_g": 2,
      "kcal": 230,
      "confidence": 0.93,
      "confidence_reason": "Full nutrition label and weight are visible.",
      "source_kind": "label_calc",
      "calculation_method": "label_visible_weight_backend_calc",
      "assumptions": [],
      "evidence": {
        "scenario": "LABEL_FULL",
        "item_type": "packaged_food",
        "source_photo_ids": ["22222222-2222-2222-2222-222222222222"],
        "primary_photo_id": "22222222-2222-2222-2222-222222222222",
        "source_photo_indices": [1],
        "extracted_facts": {
          "carbs_per_100g": 56,
          "visible_weight_g": 50
        }
      },
      "warnings": [],
      "position": 0
    }
  ],
  "suggested_totals": {
    "total_carbs_g": 28,
    "total_protein_g": 3,
    "total_fat_g": 12,
    "total_fiber_g": 2,
    "total_kcal": 230
  },
  "calculation_breakdowns": [
    {
      "position": 0,
      "name": "Chocolate bar",
      "count_detected": 1,
      "net_weight_per_unit_g": 50,
      "total_weight_g": 50,
      "nutrition_per_100g": {
        "carbs_g": 56,
        "protein_g": 6,
        "fat_g": 24,
        "fiber_g": 4,
        "kcal": 460
      },
      "calculated_per_unit": {
        "carbs_g": 28,
        "protein_g": 3,
        "fat_g": 12,
        "fiber_g": 2,
        "kcal": 230
      },
      "calculated_total": {
        "carbs_g": 28,
        "protein_g": 3,
        "fat_g": 12,
        "fiber_g": 2,
        "kcal": 230
      },
      "calculation_steps": [
        "1 упаковка = 50 г",
        "1 упаковки = 50 г",
        "углеводы: 56 × 50 / 100 = 28 г"
      ],
      "evidence": ["full label visible"],
      "assumptions": []
    }
  ],
  "gemini_notes": "Label readable.",
  "image_quality_warnings": [],
  "reference_detected": "none",
  "ai_run_id": "33333333-3333-3333-3333-333333333333"
}
```

The frontend should show `suggested_items`, `assumptions`, `evidence`, `warnings`, and confidence fields for review, then submit the user-reviewed list to `POST /meals/{id}/accept`.

### `POST /meals/{id}/estimate_and_save_draft`

Same estimation behavior as `/estimate`, but persists editable draft journal rows. One detected item creates one draft meal. Multiple unrelated detected items create multiple draft meals returned in `created_drafts`. One same-product count estimate, such as two identical candies, remains one draft meal.

```bash
curl -X POST "$BASE/meals/{meal_id}/estimate_and_save_draft" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "use_patterns": [],
      "use_products": [],
      "scenario_hint": "PLATED"
    }'
```

### `POST /meals/{id}/reestimate`

Re-run Gemini estimation for an existing meal that already has source photos. This creates a comparison proposal and an `ai_runs` history row; it does not overwrite current meal items.

Request:

```json
{
  "model": "gemini-3-flash-preview",
  "mode": "compare"
}
```

Allowed `model` values are `default`, `gemini-3-flash-preview`, `gemini-2.5-flash`, and `gemini-3.1-flash-lite-preview`.

Response includes `current_items`, `proposed_items`, `current_totals`, `proposed_totals`, `diff`, `ai_run_id`, `model_used`, and `fallback_used`. If the meal has no photos, the endpoint returns `400` with `У этой записи нет фото для переоценки`.

### `POST /meals/{id}/apply_estimation_run/{run_id}`

Apply a stored re-estimation proposal.

```json
{
  "apply_mode": "replace_current"
}
```

`replace_current` replaces current meal items, preserves photos, recalculates backend totals, and marks the AI run as promoted. `save_as_draft` creates a new draft meal from proposed items so the original accepted meal remains unchanged.

### `GET /meals/{id}/ai_runs`

Returns AI estimation history for the meal, including model metadata, normalized proposal items, error history, and promotion metadata.

### `POST /meals/{id}/accept`

Canonical endpoint for accepting Gemini draft suggestions. The frontend sends the final reviewed item list; the backend replaces items, recalculates totals, and sets `status=accepted`.

For accepted `label_calc` items, the backend also remembers the item in the local product database. This is backend-owned so replaceable frontends do not need to duplicate product-upsert rules. For visible label facts, per-100g values and per-serving values are copied from the accepted item evidence; unknown fields remain `null`. If the accepted item references an uploaded photo, the product row receives an authenticated backend photo URL such as `/photos/{photo_id}/file`; frontends must load it through the API client with Bearer auth rather than as an unauthenticated raw image URL.

```bash
curl -X POST "$BASE/meals/{meal_id}/accept" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "name": "Pasta",
        "carbs_g": 68,
        "protein_g": 12,
        "fat_g": 5,
        "fiber_g": 4,
        "kcal": 365,
        "source_kind": "photo_estimate",
        "confidence": 0.72
      }
    ]
  }'
```

### `POST /meals/{id}/discard`

Set a meal to `discarded`.

```bash
curl -X POST -H "$AUTH" "$BASE/meals/{meal_id}/discard"
```

### `GET /patterns`

List active patterns.

```bash
curl -H "$AUTH" "$BASE/patterns?limit=50&offset=0"
```

### `POST /patterns`

Create a reusable shortcut.

```bash
curl -X POST "$BASE/patterns" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "prefix": "bk",
    "key": "whopper",
    "display_name": "Whopper",
    "default_grams": 270,
    "default_carbs_g": 51,
    "default_protein_g": 28,
    "default_fat_g": 35,
    "default_fiber_g": 3,
    "default_kcal": 635,
    "source_url": "https://origin.bk.com/pdfs/nutrition.pdf",
    "aliases": ["воппер", "вопер", "whopper"]
  }'
```

### `GET /patterns/{id}`

Return one pattern, including archived patterns by id.

```bash
curl -H "$AUTH" "$BASE/patterns/{pattern_id}"
```

### `PATCH /patterns/{id}`

Patch pattern fields. If `aliases` is supplied, aliases are replaced.

```bash
curl -X PATCH "$BASE/patterns/{pattern_id}" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{ "display_name": "Whopper", "aliases": ["воппер"] }'
```

### `DELETE /patterns/{id}`

Soft delete a pattern by setting `is_archived=true`.

```bash
curl -X DELETE -H "$AUTH" "$BASE/patterns/{pattern_id}"
```

### `GET /patterns/search`

Prefix-aware search. Query is split on the first colon. `bk:во` filters to prefix `bk` and matches `во` against key prefix, display name contains, and alias prefix. Archived patterns are hidden. Responses include `matched_alias` when an alias matched.

```bash
curl -H "$AUTH" "$BASE/patterns/search?q=bk:%D0%B2%D0%BE&limit=20"
```

### `GET /products`

Paginated product list. `q` searches brand, name, and barcode.

```bash
curl -H "$AUTH" "$BASE/products?q=cracker&limit=50&offset=0"
```

### `POST /products`

Create a manually saved packaged food.

```bash
curl -X POST "$BASE/products" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "barcode": "4601234567890",
    "brand": "Example Foods",
    "name": "Whole grain crackers",
    "default_grams": 30,
    "default_serving_text": "6 crackers",
    "carbs_per_100g": 62,
    "protein_per_100g": 11,
    "fat_per_100g": 9,
    "fiber_per_100g": 7,
    "kcal_per_100g": 410,
    "source_kind": "manual",
    "aliases": ["crackers"]
  }'
```

### `GET /products/{id}`

Return one product.

```bash
curl -H "$AUTH" "$BASE/products/{product_id}"
```

### `PATCH /products/{id}`

Patch product fields. If `aliases` is supplied, aliases are replaced.

```bash
curl -X PATCH "$BASE/products/{product_id}" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{ "name": "Seed crackers", "aliases": ["seed crackers"] }'
```

### `GET /products/search`

Search name, brand, barcode, and aliases.

```bash
curl -H "$AUTH" "$BASE/products/search?q=seed&limit=20"
```

### `GET /nutrients/definitions`

Return the optional nutrient catalog. The catalog includes built-in sodium, caffeine, sugar, potassium, iron, calcium, and magnesium definitions.

```bash
curl -H "$AUTH" "$BASE/nutrients/definitions"
```

### `POST /products/from_label`

Create or update a packaged product from manually confirmed label facts. If `barcode` exists, it is used as the primary upsert key; otherwise the backend matches by brand/name.

```bash
curl -X POST "$BASE/products/from_label" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "barcode": "4601234567890",
    "brand": "Burn",
    "name": "Peach Mango Zero Sugar",
    "default_grams": 500,
    "default_serving_text": "500 ml",
    "carbs_per_100g": 0,
    "protein_per_100g": 0,
    "fat_per_100g": 0,
    "fiber_per_100g": 0,
    "kcal_per_100g": 1,
    "source_kind": "label_manual",
    "aliases": ["burn zero peach mango"]
  }'
```

### `GET /autocomplete`

 Unified suggestion endpoint for future frontends. If `q` includes a pattern prefix like `bk:`, the backend searches that pattern namespace first. Product prefixes `product:`, `products:`, `prod:`, and `my:` search saved products. Without a prefix, the backend returns recent/frequent matching patterns and products. Frontends should prefer this endpoint over duplicating search logic locally.

```bash
curl -H "$AUTH" "$BASE/autocomplete?q=bk:%D0%B2%D0%BE&limit=20"
```

Response shape:

```json
[
  {
    "kind": "pattern",
    "id": "11111111-1111-1111-1111-111111111111",
    "token": "bk:whopper",
    "display_name": "Whopper",
    "subtitle": "bk:whopper",
    "carbs_g": 51,
    "protein_g": 28,
    "fat_g": 35,
    "kcal": 635,
    "image_url": "https://cdn.prod.website-files.com/631b4b4e277091ef01450237/65947c9a2edd7ddb328fd61f_Whopper.png",
    "usage_count": 3,
    "matched_alias": "воппер"
  }
]
```

### `GET /database/items`

Unified local food database view for replaceable frontends. It combines active
patterns and products into ledger rows for database management.

Query params:

- `q`: search display name, token, barcode, source, and aliases.
- `source`: `all`, `bk`, `mc`, `home`, `products`, `manual`.
- `type`: `all`, `patterns`, `products`, `restaurants`, `needs_review`.
- `needs_review`: optional boolean shortcut for rows with quality warnings.
- `limit`, `offset`: paginated result.

```bash
curl -H "$AUTH" "$BASE/database/items?q=воппер&type=restaurants"
```

Response item shape:

```json
{
  "id": "11111111-1111-1111-1111-111111111111",
  "kind": "restaurant",
  "prefix": "bk",
  "key": "whopper",
  "token": "bk:whopper",
  "display_name": "Whopper",
  "subtitle": "bk:whopper",
  "image_url": "https://example.test/whopper.png",
  "image_cache_path": null,
  "carbs_g": 51,
  "protein_g": 28,
  "fat_g": 35,
  "fiber_g": 3,
  "kcal": 635,
  "default_grams": 270,
  "usage_count": 3,
  "last_used_at": "2026-04-28T10:00:00Z",
  "source_name": "Burger King",
  "source_url": "https://origin.bk.com/pdfs/nutrition.pdf",
  "source_confidence": null,
  "is_verified": false,
  "aliases": ["воппер", "whopper"],
  "nutrients_json": {
    "sodium_mg": { "amount": 980, "unit": "mg" }
  },
  "quality_warnings": []
}
```

Meal responses also expose frontend-safe image hints:

- `meal.thumbnail_url`: first uploaded meal photo URL or first linked
  pattern/product image.
- `meal.items[].image_url`: image inherited from the linked pattern/product.
- `meal.items[].source_image_url`: original linked pattern/product image.
- `meal.items[].image_cache_path`: reserved for future local cached images.

### `GET /nightscout/status`

Return optional Nightscout status. This endpoint does not fail when Nightscout is unset.

```bash
curl -H "$AUTH" "$BASE/nightscout/status"
```

Unset response:

```json
{ "configured": false, "status": null }
```

### `POST /meals/{id}/sync_nightscout`

Sync an accepted meal to Nightscout. Draft and discarded meals return 409. Already-synced meals return 409 with the current `nightscout_id`. If Nightscout is unset, returns 503 with `Nightscout not configured`.

```bash
curl -X POST -H "$AUTH" "$BASE/meals/{meal_id}/sync_nightscout"
```

### `POST /meals/{id}/unsync_nightscout`

Delete the remote Nightscout treatment and clear local sync fields. If the meal has no `nightscout_id`, returns 409.

```bash
curl -X POST -H "$AUTH" "$BASE/meals/{meal_id}/unsync_nightscout"
```

### `POST /admin/recalculate`

Backfill backend-owned daily totals for an inclusive date range.

```bash
curl -X POST \
  -H "$AUTH" \
  "$BASE/admin/recalculate?from=2026-04-01&to=2026-04-30"
```

### `GET /dashboard/today`

Return today's aggregate totals, last accepted meal, current week averages, previous week averages, and optional nutrient totals with coverage. Week averages are calculated over days that have accepted meals, not empty calendar days. Nutrient totals skip `null` unknown values; `coverage` is known item count divided by accepted item count.

```bash
curl -H "$AUTH" "$BASE/dashboard/today"
```

### `GET /dashboard/range`

Return daily rows plus summary totals and averages for an inclusive date range. Summary averages are calculated over days that have accepted meals, not empty calendar days. Daily rows and summary include optional nutrient totals with coverage.

```bash
curl -H "$AUTH" "$BASE/dashboard/range?from=2026-04-01&to=2026-04-30"
```

### `GET /dashboard/heatmap`

Aggregate accepted meals by `day_of_week` and `hour`. `day_of_week` uses Python weekday values, where Monday is `0`.

```bash
curl -H "$AUTH" "$BASE/dashboard/heatmap?weeks=4"
```

### `GET /dashboard/top_patterns`

Return used patterns in accepted meals ordered by count.

```bash
curl -H "$AUTH" "$BASE/dashboard/top_patterns?days=7&limit=10"
```

### `GET /dashboard/source_breakdown`

Return accepted meal item counts grouped by `source_kind`.

```bash
curl -H "$AUTH" "$BASE/dashboard/source_breakdown?days=7"
```

### `GET /dashboard/data_quality`

Return counts for exact labels, assumed labels, restaurant/product DB, pattern, visual estimate, manual entries, and low-confidence items.

```bash
curl -H "$AUTH" "$BASE/dashboard/data_quality?days=7"
```

## Seed Data

Pattern seeds live in `backend/pattern_seeds/` and are loaded idempotently by `(prefix, key)`.

```bash
cd backend
python -m glucotracker.infra.db.seed
```

## OpenAPI Export

Export the generated schema to `docs/openapi.json`:

```bash
cd backend
./scripts/export-openapi.sh
```

Frontend clients should be generated from this file or from the live `/openapi.json` endpoint.
