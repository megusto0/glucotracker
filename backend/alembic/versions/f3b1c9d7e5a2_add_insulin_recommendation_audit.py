"""Persist insulin recommendations and linked actual-dose actions.

Revision ID: f3b1c9d7e5a2
Revises: d0e1f2a3b4c5
"""

import sqlalchemy as sa

from alembic import op

revision = "f3b1c9d7e5a2"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insulin_recommendation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("meal_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("calculation_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("meal_key", sa.String(length=1024), nullable=False),
        sa.Column("method_version", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total_recommended_units", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_insulin_recommendation_runs_owner_created",
        "insulin_recommendation_runs",
        ["owner_id", "created_at"],
    )
    op.create_index(
        "ix_insulin_recommendation_runs_owner_meal",
        "insulin_recommendation_runs",
        ["owner_id", "meal_at"],
    )
    op.create_table(
        "insulin_recommendation_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recommendation_run_id",
            sa.Uuid(),
            sa.ForeignKey("insulin_recommendation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("insulin_event_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("insulin_units", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_insulin_recommendation_actions_owner_run",
        "insulin_recommendation_actions",
        ["owner_id", "recommendation_run_id", "created_at"],
    )
    with op.batch_alter_table("nightscout_insulin_events") as batch:
        batch.add_column(sa.Column("recommendation_run_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_nightscout_insulin_recommendation_run",
            "insulin_recommendation_runs",
            ["recommendation_run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration: preserve insulin audit history")
