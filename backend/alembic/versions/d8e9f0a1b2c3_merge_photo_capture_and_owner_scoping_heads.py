"""merge photo capture and owner scoping heads

Revision ID: d8e9f0a1b2c3
Revises: 0a1b2c3d4e5f, c7e8f9a0b1c2
Create Date: 2026-05-10 12:30:00.000000
"""

from collections.abc import Sequence

revision: str = "d8e9f0a1b2c3"
down_revision: str | tuple[str, str] | None = (
    "0a1b2c3d4e5f",
    "c7e8f9a0b1c2",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge migration branches without schema changes."""
    return None


def downgrade() -> None:
    """Forward-only project policy: do not unmerge migration branches."""
    return None
