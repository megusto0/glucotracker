"""add persisted AI model provenance to meals

Revision ID: 2d3e4f5a6b7c
Revises: 1c2d3e4f5a6b
Create Date: 2026-07-15 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2d3e4f5a6b7c"
down_revision: str | None = "1c2d3e4f5a6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add provenance and backfill the model behind existing meal contents."""
    op.add_column("meals", sa.Column("model_used", sa.String(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE meals
            SET model_used = (
                SELECT COALESCE(ai_runs.model_used, ai_runs.model)
                FROM ai_runs
                WHERE ai_runs.meal_id = meals.id
                  AND ai_runs.status = 'success'
                  AND (
                    ai_runs.request_type = 'initial_estimate'
                    OR ai_runs.promoted_by_action = 'replace_current'
                  )
                ORDER BY
                  CASE
                    WHEN ai_runs.promoted_by_action = 'replace_current' THEN 1
                    ELSE 0
                  END DESC,
                  ai_runs.created_at DESC
                LIMIT 1
            )
            WHERE model_used IS NULL
            """
        )
    )


def downgrade() -> None:
    """Forward-only policy: preserve provenance on rollback requests."""
    return None
