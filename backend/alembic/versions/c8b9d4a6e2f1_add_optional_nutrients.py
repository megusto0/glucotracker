"""add optional nutrients

Revision ID: c8b9d4a6e2f1
Revises: b4e7d2f9c8a1
Create Date: 2026-04-28 03:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8b9d4a6e2f1"
down_revision: str | None = "b4e7d2f9c8a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "nutrient_definitions",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    nutrient_definitions = sa.table(
        "nutrient_definitions",
        sa.column("code", sa.String),
        sa.column("display_name", sa.String),
        sa.column("unit", sa.String),
        sa.column("category", sa.String),
    )
    op.bulk_insert(
        nutrient_definitions,
        [
            {
                "code": "sodium_mg",
                "display_name": "Sodium",
                "unit": "mg",
                "category": "mineral",
            },
            {
                "code": "caffeine_mg",
                "display_name": "Caffeine",
                "unit": "mg",
                "category": "stimulant",
            },
            {
                "code": "sugar_g",
                "display_name": "Sugar",
                "unit": "g",
                "category": "carbohydrate",
            },
            {
                "code": "potassium_mg",
                "display_name": "Potassium",
                "unit": "mg",
                "category": "mineral",
            },
            {
                "code": "iron_mg",
                "display_name": "Iron",
                "unit": "mg",
                "category": "mineral",
            },
            {
                "code": "calcium_mg",
                "display_name": "Calcium",
                "unit": "mg",
                "category": "mineral",
            },
            {
                "code": "magnesium_mg",
                "display_name": "Magnesium",
                "unit": "mg",
                "category": "mineral",
            },
        ],
    )
    op.create_table(
        "meal_item_nutrients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meal_item_id", sa.Uuid(), nullable=False),
        sa.Column("nutrient_code", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "evidence_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "assumptions_json",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_meal_item_nutrients_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["meal_item_id"],
            ["meal_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["nutrient_code"],
            ["nutrient_definitions.code"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "meal_item_id",
            "nutrient_code",
            name="uq_meal_item_nutrients_item_code",
        ),
    )
    op.create_index(
        "ix_meal_item_nutrients_meal_item_id",
        "meal_item_nutrients",
        ["meal_item_id"],
    )
    op.create_index(
        "ix_meal_item_nutrients_nutrient_code",
        "meal_item_nutrients",
        ["nutrient_code"],
    )
    op.add_column(
        "patterns",
        sa.Column(
            "nutrients_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "nutrients_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("products", "nutrients_json")
    op.drop_column("patterns", "nutrients_json")
    op.drop_index(
        "ix_meal_item_nutrients_nutrient_code",
        table_name="meal_item_nutrients",
    )
    op.drop_index(
        "ix_meal_item_nutrients_meal_item_id",
        table_name="meal_item_nutrients",
    )
    op.drop_table("meal_item_nutrients")
    op.drop_table("nutrient_definitions")
