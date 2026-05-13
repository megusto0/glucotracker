"""add single-call photo capture fields

Revision ID: 0a1b2c3d4e5f
Revises: f9e1a2b3c4d5
Create Date: 2026-05-10 08:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: str | None = "f9e1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column("meals", sa.Column("estimate_status", sa.String(32), nullable=True))
    op.add_column("meals", sa.Column("estimate_error", sa.String(), nullable=True))
    op.add_column(
        "meals",
        sa.Column("photo_idempotency_key", sa.String(64), nullable=True),
    )
    op.create_index(
        "ux_meals_owner_photo_idempotency_key",
        "meals",
        ["owner_id", "photo_idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ux_meals_owner_photo_idempotency_key", table_name="meals")
    op.drop_column("meals", "photo_idempotency_key")
    op.drop_column("meals", "estimate_error")
    op.drop_column("meals", "estimate_status")
