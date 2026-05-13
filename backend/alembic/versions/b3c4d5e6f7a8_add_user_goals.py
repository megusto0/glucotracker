"""add user goals

Revision ID: b3c4d5e6f7a8
Revises: a9b0c1d2e3f4
Create Date: 2026-05-11 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("kcal_goal_per_day", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("protein_goal_g_per_day", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("carb_goal_g_per_day", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("fat_goal_g_per_day", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "goals_setup_completed",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "goals_setup_completed")
    op.drop_column("users", "fat_goal_g_per_day")
    op.drop_column("users", "carb_goal_g_per_day")
    op.drop_column("users", "protein_goal_g_per_day")
    op.drop_column("users", "kcal_goal_per_day")
