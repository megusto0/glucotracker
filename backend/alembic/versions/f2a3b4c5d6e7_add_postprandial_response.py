"""add postprandial response columns to meals

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-10 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meals",
        sa.Column("postprandial_response", sa.JSON(), nullable=True),
    )
    op.add_column(
        "meals",
        sa.Column(
            "postprandial_computed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_meals_glycemic_response",
        "meals",
        [sa.text("(postprandial_response->>'glycemic_response')")],
    )
    op.create_index(
        "idx_meals_hypo_recovery",
        "meals",
        [sa.text("(postprandial_response->>'is_hypo_recovery')")],
    )


def downgrade() -> None:
    op.drop_index("idx_meals_hypo_recovery", table_name="meals")
    op.drop_index("idx_meals_glycemic_response", table_name="meals")
    op.drop_column("meals", "postprandial_computed_at")
    op.drop_column("meals", "postprandial_response")
