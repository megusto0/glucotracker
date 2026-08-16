"""add insulin therapy history to owner-scoped twin parameters

Forward-only and additive: existing parameter and treatment rows are untouched.

Revision ID: ab3c4d5e6f70
Revises: aa2b3c4d5e6f
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "ab3c4d5e6f70"
down_revision = "aa2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "twin_params",
        sa.Column(
            "insulin_therapy",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Forward-only migration: production therapy history is never dropped.
    pass
