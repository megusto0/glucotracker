"""merge product category and owner scoping heads

Revision ID: c7e8f9a0b1c2
Revises: a6d9c3e2f4b1, b2c3d4e5f6a7
Create Date: 2026-05-08 00:05:00.000000
"""

from collections.abc import Sequence

revision: str = "c7e8f9a0b1c2"
down_revision: str | tuple[str, str] | None = (
    "a6d9c3e2f4b1",
    "b2c3d4e5f6a7",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge migration branches without schema changes."""
    return None


def downgrade() -> None:
    """Forward-only project policy: do not unmerge migration branches."""
    return None
