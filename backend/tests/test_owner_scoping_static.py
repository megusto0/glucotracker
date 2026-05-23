"""Static guards for repository-level owner scoping."""

from __future__ import annotations

from pathlib import Path

SCOPED_DB_MODEL_NAMES = {
    "DailyActivity",
    "DailyTotal",
    "FingerstickReading",
    "Meal",
    "MealAuditEvent",
    "MealInsulinLink",
    "NightscoutGlucoseEntry",
    "NightscoutImportState",
    "NightscoutInsulinEvent",
    "NightscoutSettings",
    "Pattern",
    "Photo",
    "Product",
    "ProductAlias",
    "SensorSession",
    "UserProfile",
}


def test_infra_db_selects_scoped_models_with_owner_id() -> None:
    """Fail if infra/db adds a scoped SELECT without an owner_id predicate."""
    infra_db = Path(__file__).parents[1] / "glucotracker" / "infra" / "db"
    failures: list[str] = []

    for path in infra_db.glob("*.py"):
        if path.name in {"models.py", "base.py", "session.py", "__init__.py"}:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            stripped = line.replace(" ", "")
            for model_name in SCOPED_DB_MODEL_NAMES:
                if f"select({model_name}" not in stripped:
                    continue
                statement_window = "\n".join(lines[index : index + 14])
                if "owner_id" not in statement_window:
                    relative_path = path.relative_to(infra_db.parent.parent)
                    failures.append(f"{relative_path}:{index + 1}")

    assert not failures, "Scoped infra/db SELECT without owner_id: " + ", ".join(
        failures
    )
