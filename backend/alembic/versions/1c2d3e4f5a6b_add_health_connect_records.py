"""add owner-scoped Health Connect raw records

Revision ID: 1c2d3e4f5a6b
Revises: 0b1c2d3e4f5a
Create Date: 2026-07-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1c2d3e4f5a6b"
down_revision: str | None = "0b1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the append-safe, owner-scoped Health Connect mirror."""
    op.create_table(
        "health_connect_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.String(length=255), nullable=False),
        sa.Column("record_type", sa.String(length=100), nullable=False),
        sa.Column("client_record_id", sa.String(length=255), nullable=True),
        sa.Column(
            "client_record_version",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("data_origin", sa.String(length=255), nullable=True),
        sa.Column("recording_method", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_modified_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload",
            sa.JSON(),
            server_default=sa.text("'{}'"),
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
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "record_id",
            name="uq_health_connect_records_owner_record",
        ),
    )
    op.create_index(
        "ix_health_connect_records_owner_type_start",
        "health_connect_records",
        ["owner_id", "record_type", "start_time"],
        unique=False,
    )
    op.create_index(
        "ix_health_connect_records_owner_modified",
        "health_connect_records",
        ["owner_id", "last_modified_time"],
        unique=False,
    )


def downgrade() -> None:
    """Forward-only policy: data-preserving rollback needs a new migration."""
    return None
