"""scope nightscout source keys by owner

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-05-28 00:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "nightscout_glucose_entries",
        "uq_nightscout_glucose_source_key",
        "uq_nightscout_glucose_owner_source_key",
    ),
    (
        "nightscout_insulin_events",
        "uq_nightscout_insulin_source_key",
        "uq_nightscout_insulin_owner_source_key",
    ),
)


def _unique_constraint_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    """Apply the migration."""
    for table_name, legacy_name, owner_scoped_name in TABLE_CONSTRAINTS:
        constraint_names = _unique_constraint_names(table_name)
        if not constraint_names:
            continue
        with op.batch_alter_table(table_name) as batch:
            if legacy_name in constraint_names:
                batch.drop_constraint(legacy_name, type_="unique")
            if owner_scoped_name not in constraint_names:
                batch.create_unique_constraint(
                    owner_scoped_name,
                    ["owner_id", "source_key"],
                )


def downgrade() -> None:
    """Revert the migration."""
    for table_name, legacy_name, owner_scoped_name in TABLE_CONSTRAINTS:
        constraint_names = _unique_constraint_names(table_name)
        if not constraint_names:
            continue
        with op.batch_alter_table(table_name) as batch:
            if owner_scoped_name in constraint_names:
                batch.drop_constraint(owner_scoped_name, type_="unique")
            if legacy_name not in constraint_names:
                batch.create_unique_constraint(legacy_name, ["source_key"])
