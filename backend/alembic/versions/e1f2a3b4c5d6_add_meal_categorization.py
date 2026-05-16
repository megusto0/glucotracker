"""add meal categorization columns, user anchors, non-typical periods

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-05-10 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("meals", sa.Column("ai_categories", sa.JSON(), nullable=True))
    op.add_column("meals", sa.Column("derived_categories", sa.JSON(), nullable=True))
    op.add_column(
        "meals",
        sa.Column("categorized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_meals_taste",
        "meals",
        [sa.text("(ai_categories->>'taste_profile')")],
    )
    op.create_index(
        "idx_meals_role",
        "meals",
        [sa.text("(derived_categories->>'meal_role')")],
    )
    op.create_index(
        "idx_meals_window",
        "meals",
        [sa.text("(derived_categories->>'meal_window')")],
    )

    op.add_column(
        "users",
        sa.Column("day_anchor_weekday_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("day_anchor_weekend_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("day_anchor_user_override_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "day_anchor_last_shift_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("day_anchor_basis", sa.Text(), nullable=True),
    )

    op.create_table(
        "non_typical_periods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_date <= end_date", name="start_before_end"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_non_typical_periods_user",
        "non_typical_periods",
        ["user_id", "start_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_non_typical_periods_user", table_name="non_typical_periods")
    op.drop_table("non_typical_periods")

    op.drop_column("users", "day_anchor_basis")
    op.drop_column("users", "day_anchor_last_shift_at")
    op.drop_column("users", "day_anchor_user_override_minutes")
    op.drop_column("users", "day_anchor_weekend_minutes")
    op.drop_column("users", "day_anchor_weekday_minutes")

    op.drop_index("idx_meals_window", table_name="meals")
    op.drop_index("idx_meals_role", table_name="meals")
    op.drop_index("idx_meals_taste", table_name="meals")
    op.drop_column("meals", "categorized_at")
    op.drop_column("meals", "derived_categories")
    op.drop_column("meals", "ai_categories")
