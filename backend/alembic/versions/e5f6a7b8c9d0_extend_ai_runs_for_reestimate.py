"""extend ai runs for re-estimation history

Revision ID: e5f6a7b8c9d0
Revises: d2f3a4b5c6d
Create Date: 2026-04-28 13:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d2f3a4b5c6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        "ai_runs",
        sa.Column(
            "provider",
            sa.String(),
            server_default="gemini",
            nullable=False,
        ),
    )
    op.add_column("ai_runs", sa.Column("model_requested", sa.String(), nullable=True))
    op.add_column("ai_runs", sa.Column("model_used", sa.String(), nullable=True))
    op.add_column(
        "ai_runs",
        sa.Column("fallback_used", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "ai_runs",
        sa.Column("status", sa.String(), server_default="success", nullable=False),
    )
    op.add_column(
        "ai_runs",
        sa.Column(
            "request_type",
            sa.String(),
            server_default="initial_estimate",
            nullable=False,
        ),
    )
    op.add_column(
        "ai_runs",
        sa.Column(
            "source_photo_ids",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "ai_runs",
        sa.Column("normalized_items_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_runs",
        sa.Column(
            "error_history_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "ai_runs",
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_runs",
        sa.Column("promoted_by_action", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("ai_runs", "promoted_by_action")
    op.drop_column("ai_runs", "promoted_at")
    op.drop_column("ai_runs", "error_history_json")
    op.drop_column("ai_runs", "normalized_items_json")
    op.drop_column("ai_runs", "source_photo_ids")
    op.drop_column("ai_runs", "request_type")
    op.drop_column("ai_runs", "status")
    op.drop_column("ai_runs", "fallback_used")
    op.drop_column("ai_runs", "model_used")
    op.drop_column("ai_runs", "model_requested")
    op.drop_column("ai_runs", "provider")
