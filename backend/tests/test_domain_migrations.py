"""Tests for applying Alembic migrations to a fresh SQLite database."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_alembic_upgrade_head_creates_core_schema(tmp_path: Path) -> None:
    """The migration stack creates all core tables on a fresh SQLite DB."""
    backend_dir = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "glucotracker.sqlite3"
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_config.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{db_path.as_posix()}",
    )

    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {
        "ai_runs",
        "daily_totals",
        "meal_items",
        "meal_item_nutrients",
        "meals",
        "nutrient_definitions",
        "pattern_aliases",
        "patterns",
        "photos",
        "product_aliases",
        "products",
    }.issubset(tables)
