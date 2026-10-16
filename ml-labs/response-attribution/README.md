# Response attribution prototype

Research prototype for the meal / insulin / activity response analyzer.
Findings: `REPORT.md`.

- `ledger.py` — loads a private CSV extract, builds food sittings, dedupes
  doses, converts everything to local wall clock, flags each sitting with an
  explicit exclusion reason.
- `superposition.py` — every meal and dose on one timeline using the backend
  kernels (`backend/glucotracker/application/twin/kernels.py`); linear in
  CSF / ISF / drift, robust least squares.
- `diagnostics.py` — reproduces the numbers in `REPORT.md`.

## Data

The extract is personal data and is never committed. It is a directory of
`live_*.csv` files produced by read-only `\copy` queries for one user:
`live_meals.csv` (accepted meals with macros), `live_insulin.csv`,
`live_cgm.csv`, `live_sensors.csv`, `live_hc.csv` (Steps / Exercise / Sleep
Health Connect rows with payload). Health Connect instants are read from the
payload (true UTC), matching `health_connect_samples.resolve_instant`.

```powershell
python diagnostics.py --data C:\path\to\extract
```

Requires numpy, pandas, scipy and the repository's `backend/` on disk (the
kernels are imported from it; no backend dependencies are needed).

## Dose backtest

`dose_backtest_server.py` runs the production meal estimator
(`insulin_recommendation._meal_estimate`) for every past sitting with history
strictly before it, read-only, on the server:

```bash
sudo -n -u postgres env APP_TIMEZONE=Europe/Samara PGOPTIONS="-c default_transaction_read_only=on" DATABASE_URL="postgresql+psycopg://postgres@/glucotracker_prod?host=/var/run/postgresql" PYTHONPATH=<project>/backend <project>/venv/bin/python dose_backtest_server.py > backtest.jsonl
```

`dose_backtest_analysis.py backtest.jsonl` compares variants against the dose
the outcome implies (given + follow-up + Δ4h / ISF, ISF 1.5 / 2.6 / 3.5), with
time-ordered evaluation. The output file is personal data; keep it out of git.
