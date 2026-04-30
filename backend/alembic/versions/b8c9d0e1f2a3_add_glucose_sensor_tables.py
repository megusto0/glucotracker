"""add glucose sensor calibration tables

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-30 01:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "sensor_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), server_default="manual", nullable=False),
        sa.Column("vendor", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "expected_life_days",
            sa.Float(),
            server_default="15",
            nullable=False,
        ),
        sa.Column("notes", sa.String(), nullable=True),
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
    op.create_index(
        "ix_sensor_sessions_started_at",
        "sensor_sessions",
        ["started_at"],
    )
    op.create_index(
        "ix_sensor_sessions_ended_at",
        "sensor_sessions",
        ["ended_at"],
    )

    op.create_table(
        "fingerstick_readings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("glucose_mmol_l", sa.Float(), nullable=False),
        sa.Column("meter_name", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fingerstick_readings_measured_at",
        "fingerstick_readings",
        ["measured_at"],
    )

    op.create_table(
        "cgm_calibration_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sensor_session_id", sa.Uuid(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.Column("confidence", sa.String(), server_default="low", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["sensor_session_id"],
            ["sensor_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cgm_calibration_models_sensor",
        "cgm_calibration_models",
        ["sensor_session_id"],
    )
    op.create_index(
        "ix_cgm_calibration_models_active",
        "cgm_calibration_models",
        ["active"],
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index(
        "ix_cgm_calibration_models_active",
        table_name="cgm_calibration_models",
    )
    op.drop_index(
        "ix_cgm_calibration_models_sensor",
        table_name="cgm_calibration_models",
    )
    op.drop_table("cgm_calibration_models")
    op.drop_index(
        "ix_fingerstick_readings_measured_at",
        table_name="fingerstick_readings",
    )
    op.drop_table("fingerstick_readings")
    op.drop_index("ix_sensor_sessions_ended_at", table_name="sensor_sessions")
    op.drop_index("ix_sensor_sessions_started_at", table_name="sensor_sessions")
    op.drop_table("sensor_sessions")
