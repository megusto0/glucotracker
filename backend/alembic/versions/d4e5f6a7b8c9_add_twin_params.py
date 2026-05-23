"""add digital twin params and fit log

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-23 14:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "twin_params",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("icr_morning", sa.Float(), nullable=True),
        sa.Column("icr_day", sa.Float(), nullable=True),
        sa.Column("icr_evening", sa.Float(), nullable=True),
        sa.Column(
            "morning_start_minutes",
            sa.Integer(),
            server_default="360",
            nullable=False,
        ),
        sa.Column(
            "day_start_minutes",
            sa.Integer(),
            server_default="660",
            nullable=False,
        ),
        sa.Column(
            "evening_start_minutes",
            sa.Integer(),
            server_default="1080",
            nullable=False,
        ),
        sa.Column("isf", sa.Float(), nullable=True),
        sa.Column("dia_minutes", sa.Integer(), server_default="270", nullable=False),
        sa.Column(
            "carb_duration_minutes",
            sa.Integer(),
            server_default="180",
            nullable=False,
        ),
        sa.Column(
            "baseline_drift_per_hour",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_fit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fit_data_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fit_data_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fit_train_window_count", sa.Integer(), nullable=True),
        sa.Column("last_fit_holdout_window_count", sa.Integer(), nullable=True),
        sa.Column("last_fit_train_mae_mmol", sa.Float(), nullable=True),
        sa.Column("last_fit_holdout_mae_mmol", sa.Float(), nullable=True),
        sa.Column("last_fit_method", sa.String(), nullable=True),
        sa.Column("last_fit_converged", sa.Boolean(), nullable=True),
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
        sa.CheckConstraint(
            "morning_start_minutes < day_start_minutes "
            "AND day_start_minutes < evening_start_minutes",
            name="ck_twin_params_slot_order",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", name="uq_twin_params_owner"),
    )
    op.create_index(
        "ix_twin_params_owner_id",
        "twin_params",
        ["owner_id", "id"],
        unique=False,
    )
    op.create_table(
        "twin_fit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "fit_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("data_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "params_snapshot",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("train_window_count", sa.Integer(), nullable=True),
        sa.Column("holdout_window_count", sa.Integer(), nullable=True),
        sa.Column("train_mae_mmol", sa.Float(), nullable=True),
        sa.Column("holdout_mae_mmol", sa.Float(), nullable=True),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("converged", sa.Boolean(), nullable=True),
        sa.Column("iterations", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_twin_fit_log_owner_fit_at",
        "twin_fit_log",
        ["owner_id", "fit_at"],
        unique=False,
    )


def downgrade() -> None:
    """Forward-only policy: data-preserving rollback requires a new migration."""
    return None
