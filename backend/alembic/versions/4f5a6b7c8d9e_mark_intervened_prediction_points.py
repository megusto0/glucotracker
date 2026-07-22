"""mark intervened no-input prediction points

Revision ID: 4f5a6b7c8d9e
Revises: 3e4f5a6b7c8d
Create Date: 2026-07-20 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4f5a6b7c8d9e"
down_revision: str | None = "3e4f5a6b7c8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add non-comparable intervention status without altering old outcomes."""
    column = sa.Column(
        "intervention_detected",
        sa.Boolean(),
        server_default=sa.text("false"),
        nullable=False,
    )
    status_values = (
        "evaluation_status IN "
        "('pending', 'evaluated', 'missing', 'intervened')"
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("glucose_prediction_points") as batch_op:
            batch_op.add_column(column)
            batch_op.drop_constraint(
                "ck_glucose_prediction_points_status",
                type_="check",
            )
            batch_op.create_check_constraint(
                "ck_glucose_prediction_points_status",
                status_values,
            )
        return

    op.add_column("glucose_prediction_points", column)
    op.drop_constraint(
        "ck_glucose_prediction_points_status",
        "glucose_prediction_points",
        type_="check",
    )
    op.create_check_constraint(
        "ck_glucose_prediction_points_status",
        "glucose_prediction_points",
        status_values,
    )


def downgrade() -> None:
    """Forward-only policy: preserve prospective evaluation history."""
    return None
