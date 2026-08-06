"""add persisted meal half of the insulin recommendation

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b
Create Date: 2026-08-06 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8d9e0f1a2b3c"
down_revision: str | None = "7c8d9e0f1a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store the food component so it is not rebuilt on every request.

    The correction half is deliberately absent: it depends on glucose and
    insulin on board at the moment of asking.
    """
    op.create_table(
        "insulin_recommendation_caches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("meal_key", sa.String(length=1024), nullable=False),
        sa.Column("method_version", sa.String(length=120), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "result_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "meal_key",
            "method_version",
            name="uq_insulin_recommendation_cache_owner_meals_version",
        ),
    )
    op.create_index(
        "ix_insulin_recommendation_cache_owner_computed",
        "insulin_recommendation_caches",
        ["owner_id", "computed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Forward-only policy: preserve derived results."""
    return None
