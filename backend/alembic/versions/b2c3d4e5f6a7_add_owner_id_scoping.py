"""add owner id scoping

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRIVATE_TABLES: tuple[tuple[str, str, str], ...] = (
    ("meals", "eaten_at", "ix_meals_owner_eaten_at"),
    ("photos", "created_at", "ix_photos_owner_created_at"),
    ("patterns", "prefix", "ix_patterns_owner_prefix"),
    ("daily_totals", "date", "ix_daily_totals_owner_date"),
    ("meal_audit_events", "event_at", "ix_meal_audit_events_owner_event_at"),
    ("nightscout_settings", "id", "ix_nightscout_settings_owner_id"),
    (
        "nightscout_glucose_entries",
        "timestamp",
        "ix_nightscout_glucose_owner_timestamp",
    ),
    (
        "nightscout_insulin_events",
        "timestamp",
        "ix_nightscout_insulin_owner_timestamp",
    ),
    ("nightscout_import_state", "id", "ix_nightscout_import_state_owner_id"),
    ("sensor_sessions", "started_at", "ix_sensor_sessions_owner_started_at"),
    (
        "fingerstick_readings",
        "measured_at",
        "ix_fingerstick_readings_owner_measured_at",
    ),
    ("user_profile", "id", "ix_user_profile_owner_id"),
    ("daily_activity", "date", "ix_daily_activity_owner_date"),
)

SHARED_WITH_PRIVATE_TABLES: tuple[tuple[str, str, str], ...] = (
    ("products", "name", "ix_products_owner_name"),
    ("product_aliases", "alias", "ix_product_aliases_owner_alias"),
)

OWNER_DATE_PRIMARY_KEYS: tuple[str, ...] = ("daily_totals", "daily_activity")
NAMING_CONVENTION = {"pk": "pk_%(table_name)s"}


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _table_row_count(table_name: str) -> int:
    if not _has_table(table_name):
        return 0
    return int(
        op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM "{table_name}"')) or 0
    )


def _private_rows_exist() -> bool:
    return any(_table_row_count(table_name) > 0 for table_name, _, _ in PRIVATE_TABLES)


def _gluco_owner_id() -> object | None:
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("username", sa.String()),
        sa.column("role", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    owner_id = op.get_bind().scalar(
        sa.select(users.c.id)
        .where(users.c.role == "gluco")
        .order_by(users.c.username == "admin", users.c.created_at, users.c.username)
        .limit(1)
    )
    if owner_id is None:
        if not _private_rows_exist():
            return None
        msg = "Cannot backfill owner_id: no gluco user exists."
        raise RuntimeError(msg)
    return owner_id


def _add_owner_column(table_name: str, *, nullable: bool) -> None:
    if not _has_column(table_name, "owner_id"):
        op.add_column(
            table_name,
            sa.Column("owner_id", sa.Uuid(), nullable=nullable),
        )


def _backfill_owner(table_name: str, owner_id: object) -> None:
    table = sa.table(table_name, sa.column("owner_id", sa.Uuid()))
    op.get_bind().execute(
        table.update().where(table.c.owner_id.is_(None)).values(owner_id=owner_id)
    )


def _set_owner_not_null(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.alter_column(
            "owner_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )


def _create_index(table_name: str, index_name: str, sort_column: str) -> None:
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, ["owner_id", sort_column])


def _replace_primary_key(table_name: str, columns: list[str]) -> None:
    pk = _inspector().get_pk_constraint(table_name)
    if pk.get("constrained_columns") == columns:
        return
    with op.batch_alter_table(
        table_name,
        naming_convention=NAMING_CONVENTION,
    ) as batch:
        if pk.get("constrained_columns"):
            batch.drop_constraint(
                pk.get("name") or f"pk_{table_name}",
                type_="primary",
            )
        batch.create_primary_key(f"pk_{table_name}", columns)


def upgrade() -> None:
    """Apply the migration."""
    owner_id = _gluco_owner_id()

    for table_name, sort_column, index_name in PRIVATE_TABLES:
        if not _has_table(table_name):
            continue
        _add_owner_column(table_name, nullable=True)
        if owner_id is not None:
            _backfill_owner(table_name, owner_id)
        _set_owner_not_null(table_name)
        if table_name in OWNER_DATE_PRIMARY_KEYS:
            _replace_primary_key(table_name, ["owner_id", "date"])
        _create_index(table_name, index_name, sort_column)

    for table_name, sort_column, index_name in SHARED_WITH_PRIVATE_TABLES:
        if not _has_table(table_name):
            continue
        _add_owner_column(table_name, nullable=True)
        _create_index(table_name, index_name, sort_column)


def downgrade() -> None:
    """Revert the migration."""
    for table_name, _, index_name in (
        (*PRIVATE_TABLES, *SHARED_WITH_PRIVATE_TABLES)
    ):
        if not _has_table(table_name):
            continue
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if table_name in OWNER_DATE_PRIMARY_KEYS:
            _replace_primary_key(table_name, ["date"])
        if _has_column(table_name, "owner_id"):
            with op.batch_alter_table(table_name) as batch:
                batch.drop_column("owner_id")
