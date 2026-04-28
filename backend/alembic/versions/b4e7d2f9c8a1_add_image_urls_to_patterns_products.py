"""add image urls to patterns and products

Revision ID: b4e7d2f9c8a1
Revises: 9a2add58b5be
Create Date: 2026-04-28 02:56:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4e7d2f9c8a1"
down_revision: str | None = "9a2add58b5be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column("patterns", sa.Column("image_url", sa.String(), nullable=True))
    op.add_column("products", sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("products", "image_url")
    op.drop_column("patterns", "image_url")
