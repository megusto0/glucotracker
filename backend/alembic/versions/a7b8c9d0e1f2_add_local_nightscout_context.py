"""add local nightscout context cache

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-29 19:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "nightscout_glucose_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("nightscout_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_mmol_l", sa.Float(), nullable=False),
        sa.Column("value_mg_dl", sa.Float(), nullable=True),
        sa.Column("trend", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.UniqueConstraint("source_key", name="uq_nightscout_glucose_source_key"),
    )
    op.create_index(
        "ix_nightscout_glucose_timestamp",
        "nightscout_glucose_entries",
        ["timestamp"],
    )
    op.create_index(
        "ix_nightscout_glucose_nightscout_id",
        "nightscout_glucose_entries",
        ["nightscout_id"],
    )

    op.create_table(
        "nightscout_insulin_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("nightscout_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("insulin_units", sa.Float(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("insulin_type", sa.String(), nullable=True),
        sa.Column("entered_by", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.UniqueConstraint("source_key", name="uq_nightscout_insulin_source_key"),
    )
    op.create_index(
        "ix_nightscout_insulin_timestamp",
        "nightscout_insulin_events",
        ["timestamp"],
    )
    op.create_index(
        "ix_nightscout_insulin_nightscout_id",
        "nightscout_insulin_events",
        ["nightscout_id"],
    )

    op.create_table(
        "nightscout_import_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_glucose_import_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_insulin_import_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
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
    op.drop_table("nightscout_import_state")
    op.drop_index(
        "ix_nightscout_insulin_nightscout_id",
        table_name="nightscout_insulin_events",
    )
    op.drop_index(
        "ix_nightscout_insulin_timestamp",
        table_name="nightscout_insulin_events",
    )
    op.drop_table("nightscout_insulin_events")
    op.drop_index(
        "ix_nightscout_glucose_nightscout_id",
        table_name="nightscout_glucose_entries",
    )
    op.drop_index(
        "ix_nightscout_glucose_timestamp",
        table_name="nightscout_glucose_entries",
    )
    op.drop_table("nightscout_glucose_entries")
