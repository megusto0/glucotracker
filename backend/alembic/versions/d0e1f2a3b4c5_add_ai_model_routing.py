"""Add private model routing preferences.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

import sqlalchemy as sa

from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_model_routing",
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("models_json", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration: preserve model routing preferences")
