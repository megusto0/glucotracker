"""add restaurant import metadata

Revision ID: d2f3a4b5c6d
Revises: c8b9d4a6e2f1
Create Date: 2026-04-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2f3a4b5c6d"
down_revision: str | None = "c8b9d4a6e2f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column("patterns", sa.Column("per_100g_kcal", sa.Float(), nullable=True))
    op.add_column("patterns", sa.Column("per_100g_carbs_g", sa.Float(), nullable=True))
    op.add_column(
        "patterns",
        sa.Column("per_100g_protein_g", sa.Float(), nullable=True),
    )
    op.add_column("patterns", sa.Column("per_100g_fat_g", sa.Float(), nullable=True))
    op.add_column("patterns", sa.Column("source_name", sa.String(), nullable=True))
    op.add_column("patterns", sa.Column("source_file", sa.String(), nullable=True))
    op.add_column("patterns", sa.Column("source_page", sa.Integer(), nullable=True))
    op.add_column(
        "patterns",
        sa.Column("source_confidence", sa.String(), nullable=True),
    )
    op.add_column(
        "patterns",
        sa.Column("is_verified", sa.Boolean(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("patterns", "is_verified")
    op.drop_column("patterns", "source_confidence")
    op.drop_column("patterns", "source_page")
    op.drop_column("patterns", "source_file")
    op.drop_column("patterns", "source_name")
    op.drop_column("patterns", "per_100g_fat_g")
    op.drop_column("patterns", "per_100g_protein_g")
    op.drop_column("patterns", "per_100g_carbs_g")
    op.drop_column("patterns", "per_100g_kcal")
