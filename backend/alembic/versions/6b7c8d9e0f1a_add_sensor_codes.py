"""Add owner-scoped scanned sensor Data Matrix codes.

Revision ID: 6b7c8d9e0f1a
Revises: 5a6b7c8d9e0f
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6b7c8d9e0f1a"
down_revision: str | None = "5a6b7c8d9e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the additive sensor-code inventory table."""
    op.create_table(
        "sensor_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("sensor_session_id", sa.Uuid(), nullable=True),
        sa.Column("raw_payload", sa.String(length=512), nullable=False),
        sa.Column("gtin", sa.String(length=14), nullable=False),
        sa.Column("manufactured_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("lot_number", sa.String(length=64), nullable=True),
        sa.Column("serial_number", sa.String(length=64), nullable=False),
        sa.Column(
            "scanned_at",
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
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sensor_session_id"],
            ["sensor_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "raw_payload",
            name="uq_sensor_codes_owner_payload",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "gtin",
            "serial_number",
            name="uq_sensor_codes_owner_gtin_serial",
        ),
    )
    op.create_index(
        "ix_sensor_codes_owner_scanned_at",
        "sensor_codes",
        ["owner_id", "scanned_at"],
        unique=False,
    )
    op.create_index(
        "ix_sensor_codes_sensor_session_id",
        "sensor_codes",
        ["sensor_session_id"],
        unique=False,
    )


def downgrade() -> None:
    """This production-data migration is intentionally forward-only."""
    pass
