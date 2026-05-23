"""add meal insulin links

Revision ID: c2d3e4f5a6b7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user-reviewed many-to-many food/insulin links."""
    op.create_table(
        "meal_insulin_links",
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
        sa.Column("meal_id", sa.Uuid(), nullable=False),
        sa.Column("insulin_event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=20),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.CheckConstraint(
            "source in ('manual', 'auto')",
            name="ck_meal_insulin_links_source",
        ),
        sa.ForeignKeyConstraint(
            ["insulin_event_id"],
            ["nightscout_insulin_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["meal_id"], ["meals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "meal_id",
            "insulin_event_id",
            name="uq_meal_insulin_links_owner_meal_insulin",
        ),
    )
    op.create_index(
        "ix_meal_insulin_links_owner_insulin",
        "meal_insulin_links",
        ["owner_id", "insulin_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_meal_insulin_links_owner_meal",
        "meal_insulin_links",
        ["owner_id", "meal_id"],
        unique=False,
    )


def downgrade() -> None:
    """Forward-only project policy: keep reviewed link data intact."""
    return None
