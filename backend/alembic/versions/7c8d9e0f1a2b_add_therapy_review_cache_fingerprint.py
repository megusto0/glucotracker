"""add input fingerprint to the therapy review cache

Revision ID: 7c8d9e0f1a2b
Revises: 6b7c8d9e0f1a
Create Date: 2026-08-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c8d9e0f1a2b"
down_revision: str | None = "6b7c8d9e0f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Let a stored review day say which inputs it was built from.

    Existing rows keep a NULL fingerprint, which never matches, so the first
    request for each day recalculates once and stores its digest.
    """
    op.add_column(
        "therapy_review_caches",
        sa.Column("input_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Forward-only policy: preserve derived review snapshots."""
    return None
