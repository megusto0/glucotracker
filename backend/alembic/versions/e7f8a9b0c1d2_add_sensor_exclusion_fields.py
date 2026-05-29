"""add sensor exclusion fields

Revision ID: e7f8a9b0c1d2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-29 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    """Apply the migration."""
    if not _has_column("sensor_sessions", "excluded_from_analytics"):
        op.add_column(
            "sensor_sessions",
            sa.Column(
                "excluded_from_analytics",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if not _has_column("sensor_sessions", "exclusion_reason"):
        op.add_column(
            "sensor_sessions",
            sa.Column("exclusion_reason", sa.String(), nullable=True),
        )


def downgrade() -> None:
    """Revert the migration."""
    if _has_column("sensor_sessions", "exclusion_reason"):
        op.drop_column("sensor_sessions", "exclusion_reason")
    if _has_column("sensor_sessions", "excluded_from_analytics"):
        op.drop_column("sensor_sessions", "excluded_from_analytics")
