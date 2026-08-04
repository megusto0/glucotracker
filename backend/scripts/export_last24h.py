"""Export the last N hours of owner data into a self-contained zip bundle.

Connects to the configured backend database (PostgreSQL or SQLite), pulls all
owner-scoped rows that overlap the rolling window, and writes them as JSON
files next to a README and a database manifest, then archives the whole bundle
as a single zip. Covers predicted points, glucose normalization, raw CGM,
meals with items and nutrients, fingersticks, insulin, sensor sessions,
calibration models, daily aggregates and Health Connect detail records
(heart rate, sleep, activity, respiratory/HRV metrics).

Usage
-----
Export the last 24 hours for the ``admin2`` account::

    python scripts/export_last24h.py

Override window or owner::

    EXPORT_HOURS=48 EXPORT_OWNER_USERNAME=admin python scripts/export_last24h.py

The database connection comes from ``GLUCOTRACKER_DATABASE_URL`` (see
``glucotracker/config.py``). Export destination defaults to the repository
``exports/`` directory and is configurable via ``EXPORT_DIR``.
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

EXPORT_DIR = Path(
    os.environ.get(
        "EXPORT_DIR",
        str(Path(__file__).resolve().parents[3] / "exports"),
    )
)
OWNER_USERNAME = os.environ.get("EXPORT_OWNER_USERNAME", "admin2")
HOURS = int(os.environ.get("EXPORT_HOURS", "24"))


def _json_default(value: object):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _row_dict(row) -> dict:
    """Serialize one ORM row using only its mapped column names."""
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


def _dump(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, default=_json_default, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    from sqlalchemy import select

    from glucotracker.application.glucose_normalization import (
        GlucoseNormalizationService,
    )
    from glucotracker.config import get_settings
    from glucotracker.infra.db.models import (
        CgmCalibrationModel,
        DailyActivity,
        DailyTotal,
        FingerstickReading,
        GlucosePredictionPointAudit,
        GlucosePredictionRun,
        HealthConnectRecord,
        Meal,
        MealItem,
        MealItemNutrient,
        NightscoutGlucoseEntry,
        NightscoutInsulinEvent,
        SensorSession,
        User,
    )
    from glucotracker.infra.db.session import get_session_factory

    session_factory = get_session_factory()

    heart_rate_types = {"HeartRateRecord"}
    sleep_types = {"SleepSessionRecord"}
    activity_types = {
        "StepsRecord",
        "TotalCaloriesBurnedRecord",
        "ActiveCaloriesBurnedRecord",
        "DistanceRecord",
        "ElevationGainedRecord",
        "ExerciseSessionRecord",
        "StepsCadenceRecord",
        "SpeedRecord",
    }
    metric_types = {
        "RespiratoryRateRecord",
        "HeartRateVariabilityRmssdRecord",
        "RestingHeartRateRecord",
    }
    all_health_types = heart_rate_types | sleep_types | activity_types | metric_types

    now = datetime.now(UTC)
    window_start = now - timedelta(hours=HOURS)

    bundle = EXPORT_DIR / (
        f"glucotracker_{OWNER_USERNAME}_last{HOURS}h_{now:%Y%m%d-%H%M%S}"
    )
    bundle.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    with session_factory() as session:
        owner = session.scalar(select(User).where(User.username == OWNER_USERNAME))
        if owner is None:
            raise SystemExit(f"owner username not found: {OWNER_USERNAME}")
        owner_id = owner.id
        print(f"owner: {OWNER_USERNAME} ({owner_id})")

        runs = session.scalars(
            select(GlucosePredictionRun)
            .where(
                GlucosePredictionRun.owner_id == owner_id,
                GlucosePredictionRun.created_at >= window_start,
            )
            .order_by(GlucosePredictionRun.created_at.asc())
        ).all()
        run_ids = {run.id for run in runs}
        points = session.scalars(
            select(GlucosePredictionPointAudit)
            .where(
                GlucosePredictionPointAudit.owner_id == owner_id,
                (GlucosePredictionPointAudit.target_timestamp >= window_start)
                | (GlucosePredictionPointAudit.run_id.in_(run_ids)),
            )
            .order_by(GlucosePredictionPointAudit.target_timestamp.asc())
        ).all()
        point_run_ids = {point.run_id for point in points}
        missing_runs = point_run_ids - run_ids
        if missing_runs:
            runs = list(runs) + list(
                session.scalars(
                    select(GlucosePredictionRun).where(
                        GlucosePredictionRun.id.in_(missing_runs)
                    )
                ).all()
            )
            runs.sort(key=lambda run: run.created_at)

        glucose_entries = session.scalars(
            select(NightscoutGlucoseEntry)
            .where(
                NightscoutGlucoseEntry.owner_id == owner_id,
                NightscoutGlucoseEntry.timestamp >= window_start,
            )
            .order_by(NightscoutGlucoseEntry.timestamp.asc())
        ).all()

        normalized = GlucoseNormalizationService(session, owner_id).series(
            window_start, now
        )
        normalized_payload = [
            {
                "timestamp": sample.timestamp,
                "raw_mmol_l": sample.raw_mmol_l,
                "normalized_mmol_l": sample.normalized_mmol_l,
                "bias_mmol_l": sample.bias_mmol_l,
                "bias_confidence": sample.bias_confidence,
                "sensor_session_id": sample.sensor_session_id,
                "sensor_age_days": sample.sensor_age_days,
            }
            for sample in normalized
        ]

        sensors = session.scalars(
            select(SensorSession)
            .where(
                SensorSession.owner_id == owner_id,
                SensorSession.started_at <= now,
                (SensorSession.ended_at.is_(None))
                | (SensorSession.ended_at >= window_start),
            )
            .order_by(SensorSession.started_at.asc())
        ).all()
        sensor_ids = {sensor.id for sensor in sensors}
        calibrations = session.scalars(
            select(CgmCalibrationModel).where(
                CgmCalibrationModel.sensor_session_id.in_(sensor_ids)
            )
        ).all()

        fingersticks = session.scalars(
            select(FingerstickReading)
            .where(
                FingerstickReading.owner_id == owner_id,
                FingerstickReading.measured_at >= window_start,
            )
            .order_by(FingerstickReading.measured_at.asc())
        ).all()

        insulin = session.scalars(
            select(NightscoutInsulinEvent)
            .where(
                NightscoutInsulinEvent.owner_id == owner_id,
                NightscoutInsulinEvent.timestamp >= window_start,
            )
            .order_by(NightscoutInsulinEvent.timestamp.asc())
        ).all()

        meals = session.scalars(
            select(Meal)
            .where(
                Meal.owner_id == owner_id,
                Meal.eaten_at >= _utc_to_local_naive(window_start, owner),
            )
            .order_by(Meal.eaten_at.asc())
        ).all()
        meal_ids = {meal.id for meal in meals}
        items = session.scalars(
            select(MealItem)
            .where(MealItem.meal_id.in_(meal_ids))
            .order_by(MealItem.position.asc())
        ).all()
        item_ids = {item.id for item in items}
        nutrients = session.scalars(
            select(MealItemNutrient).where(MealItemNutrient.meal_item_id.in_(item_ids))
        ).all()
        nutrients_by_item: dict[UUID, list[dict]] = {}
        for nutrient in nutrients:
            nutrients_by_item.setdefault(nutrient.meal_item_id, []).append(
                _row_dict(nutrient)
            )
        items_by_meal: dict[UUID, list[dict]] = {}
        for item in items:
            payload = _row_dict(item)
            payload["nutrients"] = nutrients_by_item.get(item.id, [])
            items_by_meal.setdefault(item.meal_id, []).append(payload)
        meals_payload: list[dict] = []
        for meal in meals:
            payload = _row_dict(meal)
            payload["items"] = items_by_meal.get(meal.id, [])
            meals_payload.append(payload)

        date_start = (window_start + _zone_offset(owner)).date()
        date_end = (now + _zone_offset(owner)).date()
        totals = session.scalars(
            select(DailyTotal).where(
                DailyTotal.owner_id == owner_id,
                DailyTotal.date >= date_start,
                DailyTotal.date <= date_end,
            )
        ).all()
        activity = session.scalars(
            select(DailyActivity).where(
                DailyActivity.owner_id == owner_id,
                DailyActivity.date >= date_start,
                DailyActivity.date <= date_end,
            )
        ).all()

        health_records = session.scalars(
            select(HealthConnectRecord)
            .where(
                HealthConnectRecord.owner_id == owner_id,
                HealthConnectRecord.record_type.in_(all_health_types),
                HealthConnectRecord.start_time <= now,
                (
                    (HealthConnectRecord.start_time >= window_start)
                    | HealthConnectRecord.end_time.is_(None)
                    | (HealthConnectRecord.end_time >= window_start)
                ),
            )
            .order_by(HealthConnectRecord.start_time.asc())
        ).all()
        health_by_type: dict[str, list[dict]] = {kind: [] for kind in all_health_types}
        for record in health_records:
            health_by_type[record.record_type].append(_row_dict(record))

        datasets: dict[str, object] = {
            "glucose_prediction_runs.json": runs,
            "glucose_prediction_points.json": points,
            "glucose_raw.json": glucose_entries,
            "glucose_normalized.json": normalized_payload,
            "sensor_sessions.json": sensors,
            "cgm_calibration_models.json": calibrations,
            "fingerstick_readings.json": fingersticks,
            "nightscout_insulin_events.json": insulin,
            "meals.json": meals_payload,
            "daily_totals.json": totals,
            "daily_activity.json": activity,
            "health_connect_heart_rate.json": health_by_type.get("HeartRateRecord", []),
            "health_connect_sleep.json": health_by_type.get("SleepSessionRecord", []),
            "health_connect_activity.json": [
                record
                for kind in sorted(activity_types)
                for record in health_by_type.get(kind, [])
            ],
            "health_connect_metrics.json": [
                record
                for kind in sorted(metric_types)
                for record in health_by_type.get(kind, [])
            ],
        }

        for filename, rows in datasets.items():
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                payload = rows
            else:
                payload = [_row_dict(row) for row in rows]
            if filename == "meals.json":
                payload = meals_payload
            counts[filename] = len(payload) if isinstance(payload, list) else 0
            _dump(bundle / filename, payload)
            print(f"  {filename}: {counts[filename]} rows")

        manifest = {
            "exported_at": now.isoformat(),
            "owner_username": OWNER_USERNAME,
            "owner_id": str(owner_id),
            "window_hours": HOURS,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "app_timezone": os.environ.get(
                "GLUCOTRACKER_APP_TIMEZONE", "Europe/Samara"
            ),
            "database": _redact_url(get_settings().database_url),
            "files": {filename: {"rows": count} for filename, count in counts.items()},
        }
        _dump(bundle / "database_manifest.json", manifest)

    readme = bundle / "README.txt"
    readme.write_text(
        "\n".join(
            [
                f"Glucotracker last {HOURS}h export for {OWNER_USERNAME}",
                f"generated {now:%Y-%m-%d %H:%M:%S} UTC",
                "",
                "Files:",
                *[f"  {name}  ({count} rows)" for name, count in counts.items()],
                "",
                "glucose_prediction_runs.json   - prediction run snapshots",
                "glucose_prediction_points.json - forecast points per horizon",
                "glucose_raw.json               - raw CGM readings from Nightscout",
                "glucose_normalized.json        - calibrated CGM (raw + bias)",
                "sensor_sessions.json           - sensor sessions covering the window",
                "cgm_calibration_models.json    - persisted calibration models",
                "fingerstick_readings.json      - fingerstick glucose readings",
                "nightscout_insulin_events.json - insulin boluses from Nightscout",
                "meals.json                     - meals with items and nutrients",
                "daily_totals.json              - accepted daily nutrition totals",
                "daily_activity.json            - steps / HR / calories by day",
                "health_connect_heart_rate.json - heart rate samples from "
                "Health Connect",
                "health_connect_sleep.json      - sleep sessions and sleep stages",
                "health_connect_activity.json   - steps, calories, distance, exercise",
                "health_connect_metrics.json    - respiratory rate, HRV, resting HR",
                "",
                "All timestamps are ISO-8601. Meal eaten_at values are local",
                "wall-clock timestamps (timezone-naive, per invariant 4).",
                "UUIDs are lowercase with dashes.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    archive = bundle.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle.iterdir()):
            zf.write(path, arcname=f"{bundle.name}/{path.name}")
    print(f"wrote {archive}")
    print(f"wrote {bundle}")


def _zone_offset(owner) -> timedelta:
    try:
        from zoneinfo import ZoneInfo

        zone_name = os.environ.get("GLUCOTRACKER_APP_TIMEZONE", "Europe/Samara")
        return ZoneInfo(zone_name).utcoffset(datetime.now(UTC))
    except Exception:
        return timedelta(hours=0)


def _redact_url(database_url: str) -> str:
    """Return a database URL with any password masked."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(database_url)
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, host = netloc.rsplit("@", 1)
        if ":" in userinfo:
            userinfo = userinfo.split(":", 1)[0] + ":<redacted>"
        netloc = f"{userinfo}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _utc_to_local_naive(value: datetime, owner) -> datetime:
    return (value + _zone_offset(owner)).replace(tzinfo=None)


if __name__ == "__main__":
    main()
