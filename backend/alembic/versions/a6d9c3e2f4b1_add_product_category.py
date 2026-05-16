"""add product category

Revision ID: a6d9c3e2f4b1
Revises: d51c2bbf9096
Create Date: 2026-05-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a6d9c3e2f4b1"
down_revision: str | None = "d51c2bbf9096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column("products", sa.Column("category", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Forward-only project policy: do not drop the added column."""
    return None
