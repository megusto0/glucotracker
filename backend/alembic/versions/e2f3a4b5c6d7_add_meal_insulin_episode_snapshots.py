"""add meal insulin episode snapshots

Revision ID: e2f3a4b5c6d7
Revises: d4e5f6a7b8c9
Create Date: 2026-05-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "meal_insulin_episode_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("episode_key", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column(
            "meal_ids_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "insulin_event_ids_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "link_pairs_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("total_carbs_g", sa.Float(), server_default="0", nullable=False),
        sa.Column("total_kcal", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "total_insulin_units",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("glucose_minus_30_mmol_l", sa.Float(), nullable=True),
        sa.Column(
            "glucose_minus_30_at",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
        sa.Column("glucose_minus_30_source", sa.String(length=20), nullable=True),
        sa.Column("glucose_plus_2h_mmol_l", sa.Float(), nullable=True),
        sa.Column(
            "glucose_plus_2h_at",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
        sa.Column("glucose_plus_2h_source", sa.String(length=20), nullable=True),
        sa.Column(
            "snapshot_json",
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
        sa.CheckConstraint(
            (
                "kind in ('food', 'correction', 'mixed', 'unresolved', "
                "'manual', 'food_only')"
            ),
            name="ck_meal_insulin_episode_snapshots_kind",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "date",
            "episode_key",
            name="uq_meal_insulin_episode_snapshots_owner_date_key",
        ),
    )
    op.create_index(
        "ix_meal_insulin_episode_snapshots_owner_date",
        "meal_insulin_episode_snapshots",
        ["owner_id", "date"],
        unique=False,
    )


def downgrade() -> None:
    """Forward-only policy: data-preserving rollback requires a new migration."""
    return None
