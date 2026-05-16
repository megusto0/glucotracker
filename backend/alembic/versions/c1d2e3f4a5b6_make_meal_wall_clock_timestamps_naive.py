"""make meal wall-clock timestamps naive

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-05-16 21:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WALL_CLOCK_COLUMNS = (
    ("meals", "eaten_at", False),
    ("photos", "taken_at", True),
    ("meal_audit_events", "eaten_at", True),
)


def upgrade() -> None:
    """Store user-entered meal/photo times as local wall-clock timestamps."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, column, nullable in WALL_CLOCK_COLUMNS:
        nullable_sql = "DROP NOT NULL" if nullable else "SET NOT NULL"
        op.execute(
            sa.text(
                f"""
                ALTER TABLE {table}
                ALTER COLUMN {column} TYPE timestamp without time zone
                USING ({column} AT TIME ZONE 'UTC'),
                ALTER COLUMN {column} {nullable_sql}
                """
            )
        )


def downgrade() -> None:
    """Restore timezone-aware storage for the affected columns."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, column, nullable in WALL_CLOCK_COLUMNS:
        nullable_sql = "DROP NOT NULL" if nullable else "SET NOT NULL"
        op.execute(
            sa.text(
                f"""
                ALTER TABLE {table}
                ALTER COLUMN {column} TYPE timestamp with time zone
                USING ({column} AT TIME ZONE 'UTC'),
                ALTER COLUMN {column} {nullable_sql}
                """
            )
        )
