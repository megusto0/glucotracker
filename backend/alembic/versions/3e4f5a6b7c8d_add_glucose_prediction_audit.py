"""add prospective glucose prediction audit

Revision ID: 3e4f5a6b7c8d
Revises: 2d3e4f5a6b7c
Create Date: 2026-07-17 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3e4f5a6b7c8d"
down_revision: str | None = "2d3e4f5a6b7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable forecast snapshots and mutable outcome fields."""
    op.create_table(
        "glucose_prediction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_value_mmol_l", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("algorithm", sa.String(length=120), nullable=False),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("step_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "model_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "inputs_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "notes_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "anchor_timestamp",
            "model_version",
            "horizon_minutes",
            "step_minutes",
            name="uq_glucose_prediction_runs_owner_anchor_model_config",
        ),
    )
    op.create_index(
        "ix_glucose_prediction_runs_owner_generated",
        "glucose_prediction_runs",
        ["owner_id", "generated_at"],
    )

    op.create_table(
        "glucose_prediction_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("target_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("predicted_value_mmol_l", sa.Float(), nullable=False),
        sa.Column("ci_low_mmol_l", sa.Float(), nullable=False),
        sa.Column("ci_high_mmol_l", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("predicted_band", sa.String(length=20), nullable=False),
        sa.Column(
            "evaluation_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("actual_glucose_entry_id", sa.Uuid(), nullable=True),
        sa.Column("actual_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_value_mmol_l", sa.Float(), nullable=True),
        sa.Column("signed_error_mmol_l", sa.Float(), nullable=True),
        sa.Column("absolute_error_mmol_l", sa.Float(), nullable=True),
        sa.Column("baseline_absolute_error_mmol_l", sa.Float(), nullable=True),
        sa.Column("direction_correct", sa.Boolean(), nullable=True),
        sa.Column("within_interval", sa.Boolean(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "evaluation_status IN ('pending', 'evaluated', 'missing')",
            name="ck_glucose_prediction_points_status",
        ),
        sa.ForeignKeyConstraint(
            ["actual_glucose_entry_id"],
            ["nightscout_glucose_entries.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["glucose_prediction_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "horizon_minutes",
            name="uq_glucose_prediction_points_run_horizon",
        ),
    )
    op.create_index(
        "ix_glucose_prediction_points_owner_target",
        "glucose_prediction_points",
        ["owner_id", "target_timestamp"],
    )
    op.create_index(
        "ix_glucose_prediction_points_status_target",
        "glucose_prediction_points",
        ["evaluation_status", "target_timestamp"],
    )


def downgrade() -> None:
    """Forward-only policy: preserve prediction history."""
    return None
