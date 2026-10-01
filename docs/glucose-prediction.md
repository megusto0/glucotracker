# Glucose forecasts: incumbent v8 and experimental v9

V8 remains the default. V9 is implemented for research but disabled by default:
matched historical evaluation did not demonstrate an accuracy gain. It is also
excluded from insulin-dose inputs. The worker/snapshot serving improvements and
audit availability fixes apply to the default v8 deployment as well.

## 1. Boundaries

The forecast describes **no additional food or insulin after its CGM anchor**.
Per CONCEPT §1, raw CGM remains immutable and all calculations stay on the
backend. Every snapshot and model artifact is scoped to one user. This version
does not change ICR, ISF, insulin/carb kinetic constants or therapy settings.

`GlucoseTrendProjectionService` has an explicit allowlist of the previous
forecast versions. V9 is excluded. Once previous forecasts expire, the existing
`no_forecast` path applies in dosing consumers; they cannot silently adopt a
research model. Promoting a forecast to that allowlist is a separate change.

## 2. Training and availability

The experimental `glucose_prediction_experimental.GlucosePredictionService.predict(as_of=...)`
applies a knowledge cutoff when
loading observations. Raw CGM uses `created_at`: Nightscout re-import can change
`updated_at` without changing a reading. Mutable meal/insulin/health records
are conservatively omitted when their current revision postdates the cutoff.
Within the training matrix, food, insulin and wearable features also respect
when the currently stored revision was available at that historical anchor.

Heart rate, activity and sleep have explicit availability and age features.
Observed zero calories differs from a missing activity stream. Sleep/exercise
intervals are filtered for availability before merging overlaps. An indexed
availability lookup avoids scanning the entire wearable history for every
training row. There is no whole-history median resting pulse that could expose
later observations to earlier rows.

The learned slopes, variation and target changes use raw CGM differences
within a sensor. Later fingerstick calibration cannot rewrite those features
or targets. The output uses the anchor's currently known correction for display.
Absolute glucose is excluded from the shape learner. Sensor replacement windows
are excluded; uncalibrated anchors are explicitly identified in the notes.

Chronological selection/test boundaries purge overlapping target windows,
including the eight-minute CGM match tolerance. Current-day labels are not used.
On short histories, a chronological row split is permitted, with the same purge;
insufficient eligible samples produce an unavailable forecast.

V9's small LightGBM shape model learns the residual of the known-input kinetic
scenario. Selection includes zero residual contribution. Quantile models remain
separate from the central prediction. Historical metrics describe fit validation,
not a guarantee of prospective or clinical accuracy.

## 3. Prospective calibration

Audit queries require the run generation, target, matched observation and
outcome evaluation to be known by the cutoff. A previous anchor alone is not
sufficient. Late recorded interventions are batch-checked again when reading
calibration samples. This filtering does not rewrite the original forecast or
its existing outcome row.

A correction needs at least five local days. Its weight/offset are selected on
older days, shrunk toward no correction, and accepted only if the following two
days improve their average and neither worsens. Days have equal weight, so a
burst of overlapping forecast requests cannot supply independent-day evidence.
V9 does not mix its calibration with outcomes from previous model versions.

## 4. Serving and artifacts

`GlucosePredictionWorker` checks once a minute for fresh CGM for each gluco user.
It produces the canonical 90-minute trajectory at five-minute spacing and skips
an already saved anchor. Training runs in the worker thread. It is registered
in both the dedicated worker entry point and the optional web-worker lifecycle.
Use the dedicated process with `GLUCOTRACKER_RUN_BACKGROUND_TASKS_IN_WEB=false`
in the hosted deployment, as before.

The worker and endpoint share one model selector. The default remains the
existing `glucose_prediction.py` v8 implementation. Only an explicit
`GLUCOTRACKER_EXPERIMENTAL_GLUCOSE_PREDICTION_ENABLED=true` switches both to v9;
leave it false for normal use. V8 still fits once per new anchor in the worker
and retains its historical feature/training limitations. Its audit reads benefit
from the shared causal outcome filters, but it does not support historical replay.

`GET /glucose/prediction` reads the saved snapshot and does not train or write.
Its existing `mode`, `horizon_minutes` and `step_minutes` parameters are preserved;
non-five-minute grids interpolate the saved trajectory. Such interpolation does
not create a new independently trained horizon. A snapshot older than 15 minutes
or invalidated by subsequent food/insulin is not served. Before the first worker
result, the endpoint returns the existing response schema with an empty point
list and a Russian availability note.

The existing run JSON stores the full response; v9 additionally stores actual
input features and knowledge cutoff. No database migration is required. Old run
JSON remains valid, but serving requires a snapshot produced by the new worker.

V9 trained artifacts contain JSON and LightGBM text, never pickle. Their signature
includes owner, implementation source, training arrays, known-input effects,
horizons, row timestamps and splits. Atomic writes use private temporary files;
owner directories and an eight-entry memory cache keep users separate. Corrupt
or mismatched artifacts are rebuilt. A disk-cache write failure leaves a usable
in-memory fit. The cache survives worker restarts when disk storage is available.

Set `GLUCOTRACKER_PREDICTION_MODEL_DIR` to a writable private directory, for example
`runtime/prediction_models`; the default is `./data/prediction_models`. Artifacts
contain personal model information and must not be committed.

## 5. Evaluation and limitations

The 2026-09-22 read-only comparison selected the first saved v8 run with an
evaluated 90-minute outcome in each six-hour local block. Of 47 anchors,
46 remained after excluding the partial September 22 local day, spanning 13
days. Intervening food/insulin was rechecked per horizon. The results below
compare saved v8 predictions with a conservative v9 historical reconstruction;
they are exploratory, selected for available outcomes, not prospective evidence.

| Horizon | V8 MAE | V9 MAE | Persistence MAE |
| ------- | -----: | -----: | --------------: |
| 15 min  |  0.406 |  0.437 |           0.535 |
| 30 min  |  0.757 |  0.839 |           0.880 |
| 60 min  |  1.169 |  1.357 |           1.411 |
| 90 min  |  2.099 |  2.195 |           2.276 |

Errors are mmol/L against raw CGM. V9 was worse at every reported horizon;
therefore it was not promoted. This comparison does not isolate which individual
change caused the difference. Do not tune repeatedly against these same anchors
and describe the result as independent validation. New, later-day evidence is
required for a future replacement decision.

`backend/scripts/replay_glucose_prediction.py` targets v9 and calls `as_of` on a read-only
SQLite working snapshot, instead of deleting future rows. It requires an explicit
owner for multi-user snapshots, scores at the returned forecast's actual anchor,
uses the same visible-CGM matching as the prospective audit, and excludes later
interventions per horizon. Older predictor checkouts without `as_of` are not
compatible with this revised harness.

A snapshot cannot reconstruct overwritten or deleted historical versions.
Conservative revision filtering may therefore remove context that an earlier
forecast actually had. Sensor-exclusion annotations are also current metadata.
The immutable prospective audit remains the reference for real-time accuracy.

These changes identify missing wearable data and prevent historical backfill
from masquerading as live context. They do not repair a disconnected phone or
establish that wearable synchronization has resumed. Interval coverage must be
measured separately by horizon and regime; an overall coverage percentage is
not a guarantee on large excursions.

For a replacement decision, compare on matched anchors and later whole days:
MAE, P90, interval width/coverage, data availability and errors after food/sensor
changes. An experimental residual learner must not be promoted merely because
its unit tests pass. Personal evaluation snapshots and results stay outside Git.
