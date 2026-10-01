"""Distinguish server-inferred insulin dose links from explicit client links.

Revision ID: a4e2f1c9d8b7
Revises: f3b1c9d7e5a2
"""

import sqlalchemy as sa

from alembic import op

revision = "a4e2f1c9d8b7"
down_revision = "f3b1c9d7e5a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insulin_recommendation_actions",
        sa.Column(
            "link_source",
            sa.String(length=20),
            server_default="explicit",
            nullable=False,
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration: preserve insulin audit history")
