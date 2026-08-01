"""Historical replay of the glucose predictor against an owner-scoped snapshot.

Walks a support-bundle snapshot forward in time. At every anchor it deletes all
CGM, insulin, meal and fingerstick rows newer than that instant, calls the live
``GlucosePredictionService``, and scores the forecast against what actually
happened. Nothing the predictor sees postdates the anchor, so this is a genuine
out-of-sample measurement rather than a holdout inside one training run.

The predictor consumes ``TRAINING_DAYS`` (45) of history, so replay anchors only
begin once the snapshot has that much CGM behind them: a 75-day export yields
about 30 replay days, a 14-day export yields none at all.

Usage
-----
Prepare a bundle once. This converts exported ISO-8601 timestamps and dashed
UUIDs into the literals the SQLAlchemy SQLite driver expects, and recreates the
``users`` row that bundles deliberately omit::

    python scripts/replay_glucose_prediction.py --prepare bundle.sqlite3 snap.sqlite3

Then replay a build::

    REPLAY_DB=snap.sqlite3 \\
    REPLAY_BACKEND=/path/to/backend \\
    REPLAY_OUT=v8.json \\
    python scripts/replay_glucose_prediction.py

``REPLAY_BACKEND`` chooses which checkout to import ``glucotracker`` from, so two
runs over one snapshot give an A/B between builds on identical anchors.
``REPLAY_STEP`` sets anchor spacing in CGM points (default 36, i.e. 3 hours).

Reported per horizon: MAE, persistence MAE, skill, move ratio (mean absolute
predicted move over mean absolute actual move, the shrinkage diagnostic) and
interval coverage, plus a sensor-age split at 60 minutes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import statistics as st
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

FMT = "%Y-%m-%d %H:%M:%S.%f"
TRAINING_DAYS = 45
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


def _columns_matching(
    pattern: re.Pattern[str],
    columns: list[str],
    sample: list[sqlite3.Row],
) -> list[str]:
    """Return columns whose every sampled text value matches ``pattern``."""
    found = []
    for column in columns:
        seen = [row[column] for row in sample if isinstance(row[column], str)]
        if seen and all(pattern.match(value) for value in seen):
            found.append(column)
    return found


def prepare(source: str, destination: str) -> None:
    """Rewrite an exported bundle into the literals SQLAlchemy/SQLite expects."""
    shutil.copyfile(source, destination)
    connection = sqlite3.connect(destination)
    connection.row_factory = sqlite3.Row

    def datetime_expr(column: str) -> str:
        quoted = f'"{column}"'
        stripped = f"replace(replace({quoted},'T',' '),'+00:00','')"
        return (
            f"case when {quoted} is null then null else substr({stripped},1,19) || "
            f"case when instr({quoted},'.')>0 then substr({stripped},20,7) "
            f"else '.000000' end end"
        )

    tables = [
        name
        for (name,) in connection.execute(
            "select name from sqlite_master where type='table'"
        )
        if not name.startswith("_")
    ]
    for table in tables:
        columns = [
            row[1] for row in connection.execute(f'pragma table_info("{table}")')
        ]
        sample = connection.execute(f'select * from "{table}" limit 200').fetchall()
        if not sample:
            continue

        datetimes = _columns_matching(ISO, columns, sample)
        uuids = _columns_matching(UUID_RE, columns, sample)
        if datetimes:
            connection.execute(
                f'update "{table}" set '
                + ", ".join(f'"{c}"={datetime_expr(c)}' for c in datetimes)
            )
        for column in uuids:
            connection.execute(
                f'update "{table}" set "{column}"=replace("{column}",\'-\',\'\') '
                f'where length("{column}")=36'
            )
        if datetimes or uuids:
            print(f"  {table}: {len(datetimes)} datetime, {len(uuids)} uuid columns")

    owner = connection.execute(
        "select owner_id from nightscout_glucose_entries limit 1"
    ).fetchone()
    if owner is not None and "users" not in tables:
        # Bundles exclude credentials, but foreign keys still reference the row.
        connection.execute(
            "create table users (id char(32) primary key, username varchar not null,"
            " password_hash varchar not null, role varchar not null,"
            " created_at datetime, last_login_at datetime, feature_flags json,"
            " day_anchor_weekday_minutes integer, day_anchor_weekend_minutes integer,"
            " day_anchor_user_override_minutes integer,"
            " day_anchor_last_shift_at datetime, day_anchor_basis varchar,"
            " kcal_goal_per_day float, protein_goal_g_per_day float,"
            " carb_goal_g_per_day float, fat_goal_g_per_day float,"
            " goals_setup_completed boolean)"
        )
        connection.execute(
            "insert into users (id, username, password_hash, role, created_at,"
            " feature_flags, goals_setup_completed)"
            " values (?, 'replay', 'unusable', 'gluco', '2020-01-01 00:00:00.000000',"
            " '{}', 1)",
            (owner[0],),
        )
        print("  users: recreated placeholder owner row")
    if "cgm_calibration_models" not in tables:
        # Bundles omit persisted calibration models, but the dashboard eagerly
        # loads the relationship, so the table has to exist even when empty.
        connection.execute(
            "create table cgm_calibration_models (id char(32) primary key,"
            " sensor_session_id char(32) not null, model_version varchar not null,"
            " created_at datetime not null, params_json json not null,"
            " metrics_json json not null, confidence varchar not null,"
            " active boolean not null)"
        )
        print("  cgm_calibration_models: created empty table")
    connection.commit()
    print(f"prepared {destination}")


def summarize(sample: list[dict[str, float]]) -> dict[str, float | int | None]:
    """Return the accuracy, shrinkage and coverage summary for one cell."""
    mae = st.mean(abs(x["pred"] - x["truth"]) for x in sample)
    persistence = st.mean(abs(x["anchor"] - x["truth"]) for x in sample)
    move = st.mean(abs(x["pred"] - x["anchor"]) for x in sample)
    actual_move = st.mean(abs(x["truth"] - x["anchor"]) for x in sample)
    coverage = st.mean(1.0 if x["lo"] <= x["truth"] <= x["hi"] else 0.0 for x in sample)
    return {
        "n": len(sample),
        "mae": mae,
        "persistence_mae": persistence,
        "skill": 1 - mae / persistence if persistence else None,
        "move_ratio": move / actual_move if actual_move else None,
        "coverage": coverage,
    }


def main() -> None:
    snapshot = os.environ["REPLAY_DB"]
    backend = os.environ["REPLAY_BACKEND"]
    out = os.environ.get("REPLAY_OUT", "replay_out.json")
    step = int(os.environ.get("REPLAY_STEP", "36"))
    work = out + ".sqlite3"

    os.environ["GLUCOTRACKER_DATABASE_URL"] = "sqlite+pysqlite:///" + work
    os.environ.setdefault("GLUCOTRACKER_APP_TIMEZONE", "Europe/Samara")
    os.environ.setdefault("GLUCOTRACKER_JWT_SECRET", "replay-secret-replay-secret-x")
    sys.path.insert(0, backend)
    shutil.copyfile(snapshot, work)

    from sqlalchemy import create_engine, text  # noqa: PLC0415
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from glucotracker.application.glucose_prediction import (
        MODEL_VERSION,
        GlucosePredictionService,
    )

    imported = os.path.abspath(sys.modules["glucotracker"].__file__)
    if not imported.startswith(os.path.abspath(backend)):
        raise SystemExit(f"imported {imported}, expected it under {backend}")

    engine = create_engine("sqlite+pysqlite:///" + work, future=True)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    source = sqlite3.connect(snapshot)
    owner = UUID(
        source.execute(
            "select owner_id from nightscout_glucose_entries limit 1"
        ).fetchone()[0]
    )
    cgm = [
        (datetime.strptime(t, FMT), v)
        for t, v in source.execute(
            "select timestamp, value_mmol_l from nightscout_glucose_entries"
            " order by timestamp"
        )
    ]
    sensor_starts = sorted(
        datetime.strptime(t, FMT)
        for (t,) in source.execute("select started_at from sensor_sessions")
    )
    zone = ZoneInfo(os.environ["GLUCOTRACKER_APP_TIMEZONE"])
    offset_minutes = round(zone.utcoffset(cgm[-1][0]).total_seconds() / 60)
    values = dict(cgm)
    times = [t for t, _ in cgm]
    anchors = [t for t in times if t >= times[0] + timedelta(days=TRAINING_DAYS)][
        ::step
    ]
    print(f"{MODEL_VERSION} from {backend}")
    print(f"  cgm {times[0]} .. {times[-1]}; {len(anchors)} anchors")
    if not anchors:
        raise SystemExit(
            f"snapshot spans {(times[-1] - times[0]).days} days; replay needs "
            f"more than TRAINING_DAYS={TRAINING_DAYS}"
        )

    def actual_at(target: datetime, tolerance_minutes: int = 8) -> float | None:
        nearest = min(times, key=lambda t: abs((t - target).total_seconds()))
        within = abs((nearest - target).total_seconds()) <= tolerance_minutes * 60
        return values[nearest] if within else None

    def sensor_age_hours(at: datetime) -> float | None:
        prior = [start for start in sensor_starts if start <= at]
        return (at - prior[-1]).total_seconds() / 3600 if prior else None

    results: dict[int, list[dict[str, float]]] = defaultdict(list)
    failures = empty = 0
    started = time.time()
    for index, anchor in enumerate(anchors):
        cut = anchor.strftime(FMT)
        meal_cut = (anchor + timedelta(minutes=offset_minutes)).strftime(FMT)
        response = None
        # Hide the future inside one transaction and roll it back afterwards.
        # The predict path is read-only, so the same session can see the
        # uncommitted deletes without ever writing them. Restoring by file copy
        # instead would move ~240 MB per anchor and dominate the runtime.
        try:
            with session_factory() as session:
                for table, column in (
                    ("nightscout_glucose_entries", "timestamp"),
                    ("nightscout_insulin_events", "timestamp"),
                    ("fingerstick_readings", "measured_at"),
                ):
                    session.execute(
                        text(f"delete from {table} where {column} > :cut"),
                        {"cut": cut},
                    )
                # meals.eaten_at is local wall clock, not a UTC instant.
                session.execute(
                    text("delete from meals where eaten_at > :cut"), {"cut": meal_cut}
                )
                session.flush()
                try:
                    response = GlucosePredictionService(session, owner).predict(
                        mode="normalized", horizon_minutes=90, step_minutes=5
                    )
                finally:
                    session.rollback()
        except Exception as error:  # noqa: BLE001 - report and keep replaying
            failures += 1
            if failures <= 3:
                print(f"  ! {type(error).__name__}: {error}")
            continue
        if response is None or not response.points:
            empty += 1
            if empty <= 3 and response is not None:
                print("  (no forecast)", response.notes[-1][:80])
            continue

        # Score in the model's own space. The anchor bias converts a raw outcome
        # into it, and the bias is flat across a 90 minute horizon.
        bias = response.anchor_value - response.raw_anchor_value
        age = sensor_age_hours(anchor)
        for point in response.points:
            truth = actual_at(anchor + timedelta(minutes=point.horizon_minutes))
            if truth is None:
                continue
            results[point.horizon_minutes].append(
                {
                    "pred": point.display_value,
                    "truth": truth + bias,
                    "anchor": response.anchor_value,
                    "lo": point.ci_low,
                    "hi": point.ci_high,
                    "age_h": age,
                }
            )
        if (index + 1) % 20 == 0:
            rate = (time.time() - started) / (index + 1)
            remaining = rate * (len(anchors) - index - 1) / 60
            print(f"  {index + 1}/{len(anchors)}  ~{remaining:.0f} min left")

    elapsed = (time.time() - started) / 60
    print(f"\nfailed={failures} no-forecast={empty}  ({elapsed:.0f} min)")
    print(
        f"{'h':>4} {'n':>5} {'MAE':>7} {'pers':>7} {'skill':>7} {'ratio':>6} {'cov':>6}"
    )
    report: dict[str, object] = {
        "version": MODEL_VERSION,
        "backend": backend,
        "by_horizon": {},
        "by_sensor_age": {},
    }
    for horizon in range(5, 91, 5):
        sample = results.get(horizon, [])
        if not sample:
            continue
        stats = summarize(sample)
        report["by_horizon"][horizon] = stats
        print(
            f"{horizon:>4} {stats['n']:>5} {stats['mae']:>7.3f} "
            f"{stats['persistence_mae']:>7.3f} {100 * stats['skill']:>6.1f}% "
            f"{stats['move_ratio']:>6.2f} {100 * stats['coverage']:>5.1f}%"
        )

    print("\nsensor-age split at 60 minutes:")
    for label, keep in (
        ("<48h", lambda age: age is not None and age < 48),
        (">=48h", lambda age: age is not None and age >= 48),
    ):
        sample = [x for x in results.get(60, []) if keep(x["age_h"])]
        if not sample:
            continue
        stats = summarize(sample)
        report["by_sensor_age"][label] = stats
        print(
            f"  {label:>6} n={stats['n']:>4} MAE={stats['mae']:.3f} "
            f"pers={stats['persistence_mae']:.3f} skill={100 * stats['skill']:+.1f}% "
            f"ratio={stats['move_ratio']:.2f} cov={100 * stats['coverage']:.1f}%"
        )

    with open(out, "w") as handle:
        json.dump(report, handle, indent=1)
    print("wrote", out)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--prepare":
        prepare(sys.argv[2], sys.argv[3])
    else:
        main()
