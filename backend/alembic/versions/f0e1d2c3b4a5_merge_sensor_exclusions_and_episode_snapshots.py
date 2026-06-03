"""merge sensor exclusions and episode snapshots heads

Revision ID: f0e1d2c3b4a5
Revises: e2f3a4b5c6d7, e7f8a9b0c1d2
Create Date: 2026-06-02 23:40:00.000000
"""

from collections.abc import Sequence

revision: str = "f0e1d2c3b4a5"
down_revision: str | Sequence[str] | None = ("e2f3a4b5c6d7", "e7f8a9b0c1d2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge migration heads without changing schema or data."""
    return None


def downgrade() -> None:
    """Forward-only policy: data-preserving rollback requires a new migration."""
    return None
