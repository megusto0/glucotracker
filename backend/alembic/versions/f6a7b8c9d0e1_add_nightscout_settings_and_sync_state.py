"""add nightscout settings and sync state

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-28 22:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        "meals",
        sa.Column(
            "nightscout_sync_status",
            sa.Enum(
                "not_synced",
                "synced",
                "failed",
                "skipped",
                name="nightscout_sync_status",
                native_enum=False,
            ),
            server_default="not_synced",
            nullable=False,
        ),
    )
    op.add_column(
        "meals",
        sa.Column("nightscout_sync_error", sa.String(), nullable=True),
    )
    op.add_column(
        "meals",
        sa.Column(
            "nightscout_last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_table(
        "nightscout_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("api_secret", sa.String(), nullable=True),
        sa.Column("sync_glucose", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "show_glucose_in_journal",
            sa.Boolean(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "import_insulin_events",
            sa.Boolean(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("allow_meal_send", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "confirm_before_send",
            sa.Boolean(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("autosend_meals", sa.Boolean(), server_default="0", nullable=False),
        sa.Column(
            "last_status_check_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("nightscout_settings")
    op.drop_column("meals", "nightscout_last_attempt_at")
    op.drop_column("meals", "nightscout_sync_error")
    op.drop_column("meals", "nightscout_sync_status")
