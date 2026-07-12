"""Schema tests for the forward-only personalized on-board migration."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def _alembic_config(backend_dir: Path, db_path: Path) -> Config:
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return config


def test_on_board_fit_migration_creates_owner_scoped_table_and_indexes(
    tmp_path: Path,
) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "on-board-migration.sqlite3"
    config = _alembic_config(backend_dir, db_path)

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        schema = inspect(engine)
        assert "on_board_model_fits" in schema.get_table_names()
        columns = {
            column["name"] for column in schema.get_columns("on_board_model_fits")
        }
        indexes = {
            index["name"]: tuple(index["column_names"])
            for index in schema.get_indexes("on_board_model_fits")
        }
        foreign_keys = schema.get_foreign_keys("on_board_model_fits")
    finally:
        engine.dispose()

    assert {
        "id",
        "owner_id",
        "kind",
        "scope_key",
        "model_version",
        "params_json",
        "metrics_json",
        "status",
        "active",
        "fitted_at",
        "created_at",
    }.issubset(columns)
    assert indexes["ix_on_board_model_fits_owner_active"] == (
        "owner_id",
        "kind",
        "scope_key",
        "active",
    )
    assert indexes["ix_on_board_model_fits_owner_fitted_at"] == (
        "owner_id",
        "fitted_at",
    )
    assert any(
        foreign_key["constrained_columns"] == ["owner_id"]
        and foreign_key["referred_table"] == "users"
        for foreign_key in foreign_keys
    )

    command.downgrade(config, "f0e1d2c3b4a5")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        assert "on_board_model_fits" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
