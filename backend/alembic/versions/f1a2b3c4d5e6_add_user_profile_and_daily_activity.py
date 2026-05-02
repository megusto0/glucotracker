"""add user profile and daily activity tables

Revision ID: f1a2b3c4d5e6
Revises: b8c9d0e1f2a3
Create Date: 2026-05-01 23:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("age_years", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(6), nullable=True),
        sa.Column(
            "activity_level",
            sa.String(16),
            server_default="moderate",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_table(
        "daily_activity",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("steps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("kcal_burned", sa.Float(), server_default="0", nullable=False),
        sa.Column("heart_rate_avg", sa.Float(), nullable=True),
        sa.Column("heart_rate_rest", sa.Float(), nullable=True),
        sa.Column(
            "source",
            sa.String(32),
            server_default="gadgetbridge",
            nullable=False,
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_daily_activity_date", "daily_activity", ["date"])


def downgrade() -> None:
    op.drop_index("ix_daily_activity_date", table_name="daily_activity")
    op.drop_table("daily_activity")
    op.drop_table("user_profile")
