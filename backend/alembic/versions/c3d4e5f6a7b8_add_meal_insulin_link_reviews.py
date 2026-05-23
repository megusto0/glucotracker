"""add meal insulin link reviews

Revision ID: c3d4e5f6a7b8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-23 00:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create manual review markers for insulin link overrides."""
    op.create_table(
        "meal_insulin_link_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("insulin_event_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["insulin_event_id"],
            ["nightscout_insulin_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "insulin_event_id",
            name="uq_meal_insulin_link_reviews_owner_insulin",
        ),
    )
    op.create_index(
        "ix_meal_insulin_link_reviews_owner_insulin",
        "meal_insulin_link_reviews",
        ["owner_id", "insulin_event_id"],
        unique=False,
    )


def downgrade() -> None:
    """Forward-only project policy: keep reviewed override data intact."""
    return None
