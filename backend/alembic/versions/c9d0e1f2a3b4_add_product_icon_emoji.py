"""Add semantic fallback icons to products.

Revision ID: c9d0e1f2a3b4
Revises: b1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("icon_emoji", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "icon_emoji")
