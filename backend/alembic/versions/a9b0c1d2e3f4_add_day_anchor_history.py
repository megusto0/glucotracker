"""add day anchor history

Revision ID: a9b0c1d2e3f4
Revises: f2a3b4c5d6e7
Create Date: 2026-05-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "day_anchor_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("anchor_weekday_minutes", sa.Integer(), nullable=True),
        sa.Column("anchor_weekend_minutes", sa.Integer(), nullable=True),
        sa.Column("basis", sa.String(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from <= effective_to",
            name="ck_day_anchor_history_effective_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_day_anchor_history_user_from",
        "day_anchor_history",
        ["user_id", "effective_from"],
    )


def downgrade() -> None:
    """Forward-only project policy: leave recorded anchor history intact."""
    return None
