# Photo model overview and personal priority

Desktop `/ai-models` is linked from «Модели». Per CONCEPT §1, detailed model
configuration belongs to Desktop. It uses existing typography, colors and
buttons (CONCEPT §5); keyboard move buttons complement native drag and drop.

The authenticated `GET /ai/models?days=30` reads the current user's saved AI
runs through their meals. `PUT /ai/models` saves an ordered list of provider,
model and enabled flag, with a revision to reject concurrent edits (409).
These endpoints are recorded in OpenAPI and generated Desktop types. Both food
and gluco accounts can manage their own food-estimation models. Credentials
and provider connections stay on the server. There is no cross-user settings
editor and no other user's AI history is exposed.

The same response includes newest-first request history, 30 entries per page
via `history_offset`. Each entry shows time, result, total duration and
expandable provider attempts with safe error categories. Older records may
have only the final model and total chain duration; unavailable attempt timing
is shown as such. History uses the same owner and period filters as statistics.

## Meaning of the numbers

- Attempts include real calls and retries, not skipped models.
- Success means a structured estimation result was parsed; it does not measure
  nutritional accuracy against weighed food or a verified reference.
- Average duration is measured around each provider attempt, including response
  parsing, excluding retry backoff. Failed and successful timed attempts are
  included. The number of timed samples is shown when available. The primary
  duration on each card is instead the mean of saved whole-request durations,
  grouped by the final recorded model. It includes retries, fallback and
  backoff, so it is not the latency of that model's individual call.
- Provider response wait is now recorded separately for each new Gemini SDK
  call, Grok HTTP request, and OpenAI Codex response stream, including failed
  calls that reached the provider. The page shows this next to the entire
  attempt duration and aggregates its mean per model. Older audit rows have no
  provider-response timestamp, so this metric begins with new estimates.
- Confidence is the mean item confidence reported by a model, averaged across
  recorded successful attempts; the sample count is shown. It is not an
  independent accuracy score. Historical rows without it show no value.
- Legacy runs without an attempt list contribute their recorded error entries
  and final success; retries absent from the original audit cannot be recreated.
- Error groups are fixed categories, counts and latest timestamps. Raw provider
  messages, prompts, photo identifiers, credentials and response bodies are not
  returned. HTTP authentication, quota, timeout, parse and service errors remain
  distinguishable when the original metadata permits it.
- Gemini pause deadlines come from the existing shared cooldown store. A timeout
  is a failed request; a pause is a current routing exclusion. Grok/OpenAI have
  no persistent circuit breaker in the existing implementation.
- Availability means server credentials/feature configuration is present,
  not that a remote provider has just passed a probe. Loading the page makes no
  provider requests and does not refresh OAuth credentials.

Periods are 1–90 days, with a maximum of the newest 5000 AI runs. Truncation is
explicit. Querying does not load the raw response body. The page refreshes every
15 seconds and preserves pending edits; switching accounts resets the draft.

## Routing

Until a user saves a list, the existing Gemini/default fallback chain remains
unchanged. Saving replaces the automatic chain for that user. Enabled models
are tried in order across Gemini, Grok and OpenAI Codex. Gemini retains bounded
retries, the primary/fallback API key slots and persistent cooldowns. Provider
feature flags and the existing automatic Gemini Pro restriction remain in force.
Models without configured access are skipped. Adding an identifier does not
create credentials or confirm provider support; unsupported identifiers produce
ordinary request errors. A low-confidence result may trigger another attempt;
if none succeeds with sufficient confidence, the first valid candidate is kept.
Explicit re-estimation model overrides retain their existing behavior.

Initial, background and repeated photo estimates load the owner's preference.
Requests already running keep their captured list. Defaults, credentials and
another user's order are not changed by saving. Existing AI run JSON is extended
with attempt latency and confidence; no audit history is rewritten.

## Rollout

Apply the additive Alembic migration `d0e1f2a3b4c5` before starting the updated
backend. It creates `ai_model_routing` keyed by `owner_id` and follows the existing
`c9d0e1f2a3b4` revision. Then restart the backend and update/build Desktop. No
paid test call was performed as part of this implementation. The migration was
already present on the live database; the web service was restarted and the
authenticated history endpoint was checked against stored runs. The
forward-only migration does not delete existing data.

## Validation of this change

- Backend routing/provider/photo-flow/isolation suite: 82 passed. Six additional
  error-category cases also passed (17 tests in the final overview module run).
- Desktop model-page and API-client tests: 8 passed; TypeScript/Vite build passed.
- Request-history update: backend overview tests 17 passed, Desktop model-page
  tests 5 passed, TypeScript/Vite build passed. Live API returned 200 with
  210 owner-scoped requests in the selected 30-day period and 30 entries on
  each of the first two pages. All 210 saved request durations now contribute
  to the clearly labelled whole-request averages of their final models.
- Provider-response timing update: 51 focused backend tests and 5 Desktop
  model-page tests passed; TypeScript/Vite build passed. Live authenticated API
  returns the new nullable response-timing fields without making a paid model
  request.
- Browser with isolated SQLite/API and synthetic records: statistics and pause
  rendered; saving changed actual routing preferences and survived reload;
  no horizontal overflow at the Desktop minimum width of 900px.
- Additive migration applied successfully to an isolated SQLite database;
  Alembic reports a single head, `d0e1f2a3b4c5`.
- The broader existing `App.test.tsx` suite is not green: 50 failures in this
  working copy; an isolated HEAD checkout with the same dependencies has 51
  failures. It includes stale login/navigation expectations and missing insight
  request handlers. This change does not claim that the whole UI suite passes.
