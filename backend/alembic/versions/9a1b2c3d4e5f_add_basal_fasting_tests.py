"""add basal fasting test runs

Forward-only and additive: a new table, nothing dropped or rewritten.

Revision ID: 9a1b2c3d4e5f
Revises: 8d9e0f1a2b3c
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9a1b2c3d4e5f"
down_revision = "8d9e0f1a2b3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "basal_fasting_tests",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("window_start_hour", sa.Integer(), nullable=False),
        sa.Column("window_end_hour", sa.Integer(), nullable=False),
        sa.Column("planned_hours", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default="running",
            nullable=False,
        ),
        sa.Column("abort_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_basal_fasting_tests_owner_started",
        "basal_fasting_tests",
        ["owner_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_basal_fasting_tests_owner_started",
        table_name="basal_fasting_tests",
    )
    op.drop_table("basal_fasting_tests")
