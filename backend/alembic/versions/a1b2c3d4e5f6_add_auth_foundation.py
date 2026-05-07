"""add auth foundation

Revision ID: a1b2c3d4e5f6
Revises: f9e1a2b3c4d5
Create Date: 2026-05-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f9e1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def upgrade() -> None:
    """Apply the migration."""
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("username", sa.String(length=80), nullable=False),
            sa.Column("password_hash", sa.String(length=512), nullable=False),
            sa.Column(
                "role",
                sa.String(length=5),
                server_default="gluco",
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "feature_flags",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
            sa.CheckConstraint("role IN ('gluco', 'food')", name="ck_users_role"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=False)

    if not _has_table("refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "issued_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("device_label", sa.String(length=120), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        )
        op.create_index(
            "ix_refresh_tokens_user_id",
            "refresh_tokens",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            "ix_refresh_tokens_expires_at",
            "refresh_tokens",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    """Revert the migration."""
    if _has_table("refresh_tokens"):
        op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
        op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
        op.drop_table("refresh_tokens")

    if _has_table("users"):
        op.drop_index("ix_users_username", table_name="users")
        op.drop_table("users")
