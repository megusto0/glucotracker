"""add personalized IOB and COB fit history

Revision ID: 0b1c2d3e4f5a
Revises: f0e1d2c3b4a5
Create Date: 2026-07-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0b1c2d3e4f5a"
down_revision: str | None = "f0e1d2c3b4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only, owner-scoped on-board fit history."""
    op.create_table(
        "on_board_model_fits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("scope_key", sa.String(length=96), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column(
            "params_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "metrics_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("training_from", sa.DateTime(timezone=False), nullable=True),
        sa.Column("training_to", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("day_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("validation_mae_mmol", sa.Float(), nullable=True),
        sa.Column("baseline_mae_mmol", sa.Float(), nullable=True),
        sa.Column(
            "confidence",
            sa.String(length=12),
            server_default=sa.text("'none'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="0", nullable=False),
        sa.Column(
            "fitted_at",
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
        sa.CheckConstraint(
            "kind in ('iob', 'cob')",
            name="ck_on_board_model_fits_kind",
        ),
        sa.CheckConstraint(
            "confidence in ('none', 'low', 'medium', 'high')",
            name="ck_on_board_model_fits_confidence",
        ),
        sa.CheckConstraint(
            "status in ('accepted', 'rejected', 'insufficient_data')",
            name="ck_on_board_model_fits_status",
        ),
        sa.CheckConstraint(
            "sample_count >= 0 AND day_count >= 0",
            name="ck_on_board_model_fits_counts",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_on_board_model_fits_owner_active",
        "on_board_model_fits",
        ["owner_id", "kind", "scope_key", "active"],
        unique=False,
    )
    op.create_index(
        "ix_on_board_model_fits_owner_fitted_at",
        "on_board_model_fits",
        ["owner_id", "fitted_at"],
        unique=False,
    )


def downgrade() -> None:
    """Forward-only policy: data-preserving rollback needs a new migration."""
    return None
