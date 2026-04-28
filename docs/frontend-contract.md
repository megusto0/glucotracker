# Frontend Contract

The frontend is replaceable. Any generated desktop UI can be deleted and rebuilt without changing the backend, database schema, or API semantics.

## Boundary

- The backend owns business rules, persistence, external integration secrets, and API semantics.
- The frontend owns presentation, local UI state, navigation, and user interaction flow.
- The frontend must communicate with the backend only through REST + JSON endpoints documented in `docs/api-contract.md` and exposed through FastAPI OpenAPI.
- The frontend must not rely on desktop-only backend behavior, local database access, filesystem shortcuts, or Tauri commands for core API behavior.
- New frontends must use backend-calculated meal and item totals. The frontend may display draft estimates, but final macro math, optional nutrient rows, accepted meal totals, and daily totals are backend-owned.

## Generated Client

- TypeScript clients should be generated from the backend OpenAPI document.
- Regenerating the client must be treated as a mechanical step, not as a place to hand-edit API semantics.
- If generated types disagree with desired frontend behavior, fix the backend schema or API contract first.
- Future Kotlin/Compose clients must be able to consume the same REST + JSON API without desktop-specific assumptions.
- `/meals/{id}/estimate` returns AI draft suggestions without saving them.
- `/meals/{id}/estimate_and_save_draft` saves AI draft suggestions as editable draft journal rows. Multiple unrelated estimated items are returned as separate `created_drafts`.
- `/meals/{id}/accept` is the key endpoint for AI draft review. A frontend reviewing Gemini draft suggestions should send the final edited item list to that endpoint and use the backend response as source-of-truth state.

## Photo Estimation Flow

New frontends should implement the photo review flow as REST calls:

- Create or load a draft photo meal.
- Upload images with `POST /meals/{id}/photos`.
- Call `POST /meals/{id}/estimate` to get backend-normalized suggestions. When the UI knows the capture type, send `scenario_hint` as `LABEL_FULL`, `LABEL_PARTIAL`, or `PLATED`; otherwise omit it and let the backend use its default model route.
- For multi-photo estimates, render `source_photos` as the ordered photo manifest and use each suggested item's `evidence.source_photo_ids`, `evidence.source_photo_indices`, and `evidence.primary_photo_id` to show the correct source image. Do not assume the first uploaded image belongs to every item.
- If `estimate_and_save_draft` returns multiple `created_drafts`, show them as separate draft journal rows and separate review cards. Do not combine unrelated photos into one UI meal total.
- If the backend returns Russian review warnings such as "Загружено несколько фото, найден один объект. Проверьте результат." or "Позиция не связана с конкретным фото.", show them in the draft panel before the user accepts the meal.
- Display `suggested_items`, assumptions, evidence, warnings, confidence, and suggested totals.
- Let the user edit a pending item list in UI state.
- Submit the reviewed item list to `POST /meals/{id}/accept`.
- Render the returned meal as source-of-truth state.

For `LABEL_FULL` and `LABEL_PARTIAL`, the frontend must not calculate package totals from label facts. Gemini extracts visible facts and size assumptions; the backend calculates item macros and optional nutrients such as caffeine/sodium/sugar from per-100g, per-100ml, or per-serving facts. New frontends may show the extracted facts from `evidence`, but backend totals remain authoritative. Unknown nutrient amounts are `null`, not zero.

For `PLATED` meals, replacement frontends should render `evidence.component_estimates` and `evidence.known_component` when present. These fields explain whether a reusable component such as tortilla/lavash was matched to a saved product or pattern. The UI may show model raw component values beside backend-adjusted values, but it must not redo or override known-component math locally. Manual corrections for carbs, protein, fat, fiber, kcal, or grams should be sent back through normal item edit/product save endpoints so the backend can reuse them on future estimates.

Model selection is not frontend-owned. The backend routes `LABEL_FULL` to a lite model, `LABEL_PARTIAL` and `PLATED` to the default Flash model, retries temporary Gemini `503` overload errors with bounded backoff, and then uses configured fallback models. Frontends must not request Pro models automatically. If estimation fails with a retryable overload message, the UI should keep pending/uploaded photos and offer a repeat action rather than making the user attach the same images again.

For existing photo meals, replacement UIs should support comparison re-estimation through `/meals/{id}/reestimate`. This endpoint returns a proposal only; it must not be treated as saved state until the user applies it with `/meals/{id}/apply_estimation_run/{run_id}`. The safe default for meals with manual corrections is `save_as_draft`, not replacing the current accepted meal.

## Autocomplete

Future frontends should use `GET /autocomplete` for pattern/product suggestions instead of duplicating prefix parsing, alias matching, fuzzy-ish contains matching, usage sorting, or product lookup locally.

The UI may pass raw user input such as `bk:во`, `mc:big`, `сырок`, `product:сырок`, `my:сырок`, or an empty string. The backend decides whether to search a pattern namespace, products, or both, and returns display-ready suggestions with `kind`, `token`, macros, optional `image_url`, `usage_count`, and `matched_alias`. Frontends should treat that response as the source of search behavior and only handle presentation, highlighting, keyboard selection, thumbnail rendering, and insertion. `image_url` is display metadata only and must not affect item macros or meal totals.

For remembered packaged products, frontends may show `Запомнить продукт` for accepted label-calculated items and call `POST /meal_items/{id}/remember_product` with user aliases. Selecting a saved product from autocomplete must create a `product_db` meal item using backend-returned product values; it must not call Gemini or require a photo.

## Nightscout

Nightscout is optional and must not block local saving, editing, accepting, dashboard display, photo estimation, products, or patterns. Frontends should treat `GET /nightscout/status` as capability discovery. If `configured=false` or a sync endpoint returns 503 `Nightscout not configured`, the UI should keep the local meal saved and show sync as unavailable rather than failing the meal workflow.

Frontends must not add insulin fields or dosing behavior around Nightscout sync. Glucotracker sync creates diary-only carb treatments from accepted backend totals.

## Dashboard

Dashboard metrics come from backend accepted meals and `daily_totals`. Frontends should not recalculate dashboard totals, optional nutrient coverage, or source quality metrics locally; use the `/dashboard/*` endpoints and render their responses.

## Replacing The Frontend

A replacement UI should start from the backend OpenAPI document, generate a client, and treat generated request/response types as the integration boundary. For TypeScript, run the configured OpenAPI generation command from `desktop/` after exporting or serving the backend schema. For another client, generate an equivalent REST client from `docs/openapi.json` or from `/openapi.json` on a running backend.

The replacement UI should implement meal editing as server-owned state transitions:

- Create a draft meal or load a draft meal created from the Gemini/photo flow.
- Display draft items, assumptions, evidence, warnings, and confidence values returned by the backend.
- Let the user edit the item list locally as pending UI state.
- Submit the final reviewed list to `POST /meals/{id}/accept`.
- Render the returned meal response and its backend-calculated totals.

New UIs must not depend on Tauri commands, desktop filesystem paths, local database access, or hand-maintained copies of backend schema semantics. If a generated client does not expose a shape the UI needs, update the backend API/schema and regenerate the client.

## Database And Images

Food database management should prefer `GET /database/items` for unified pattern/product/restaurant rows. Do not duplicate alias ranking, quality warning rules, or source classification in the frontend when the backend can expose it.

Meal rows should use backend image hints:

- `meal.thumbnail_url` for the primary row thumbnail.
- `meal.items[].image_url` or `meal.items[].source_image_url` for item-level fallback imagery.
- Uploaded meal photos are still loaded through `GET /photos/{id}/file` with bearer auth.

If an image URL fails to render, the UI should show a neutral placeholder and keep the ledger row layout stable.

## Secrets

- The bearer token is user-provided configuration and is sent as an HTTP bearer token when protected endpoints are added.
- Gemini API keys must live only on the backend.
- Nightscout URL, token, and related settings must live only on the backend.
- Frontend code must not embed Gemini credentials, Nightscout credentials, or backend deployment secrets.

## Replacement Checklist

- A replacement frontend can discover routes from OpenAPI.
- A replacement frontend can call all user-facing behavior over REST + JSON.
- A replacement frontend uses backend totals and does not recalculate accepted meal macros or optional nutrient totals as source-of-truth state.
- A replacement frontend does not need to know the database engine.
- A replacement frontend does not need to know whether the backend is serving the Tauri desktop client, a future Android app, or another client.
