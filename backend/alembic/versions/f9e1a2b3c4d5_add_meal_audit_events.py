"""add meal audit events

Revision ID: f9e1a2b3c4d5
Revises: d51c2bbf9096
Create Date: 2026-05-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f9e1a2b3c4d5"
down_revision: str | None = "d51c2bbf9096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "meal_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("meal_id", sa.Uuid(), nullable=True),
        sa.Column("eaten_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("total_kcal", sa.Float(), nullable=True),
        sa.Column("total_carbs_g", sa.Float(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_meal_audit_events_meal_id",
        "meal_audit_events",
        ["meal_id"],
        unique=False,
    )
    op.create_index(
        "ix_meal_audit_events_event_at",
        "meal_audit_events",
        ["event_at"],
        unique=False,
    )
    op.create_index(
        "ix_meal_audit_events_eaten_at",
        "meal_audit_events",
        ["eaten_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_meal_audit_events_eaten_at", table_name="meal_audit_events")
    op.drop_index("ix_meal_audit_events_event_at", table_name="meal_audit_events")
    op.drop_index("ix_meal_audit_events_meal_id", table_name="meal_audit_events")
    op.drop_table("meal_audit_events")
