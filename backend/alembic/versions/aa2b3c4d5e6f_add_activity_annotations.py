"""add owner-scoped activity annotations

Forward-only and additive: raw Health Connect records remain untouched.

Revision ID: aa2b3c4d5e6f
Revises: 9a1b2c3d4e5f
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "aa2b3c4d5e6f"
down_revision = "9a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_annotations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("activity_type", sa.String(length=24), nullable=False),
        sa.Column(
            "remember_no_steps_rule",
            sa.Boolean(),
            server_default="0",
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
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "owner_id",
            "start_at",
            "end_at",
            name="uq_activity_annotations_owner_span",
        ),
    )
    op.create_index(
        "ix_activity_annotations_owner_start",
        "activity_annotations",
        ["owner_id", "start_at"],
    )


def downgrade() -> None:
    # Forward-only migration: production annotations are never dropped.
    pass
