"""Add a stored picture to a meal item.

Stock from the fridge is not a row in ``products`` — its id is synthesised for
the mobile client — so ``MealItem.source_image_url`` has nothing to inherit
from and an entry logged from the fridge showed the empty-photo glyph while its
picture sat one screen away. The column lets a client that already knows the
picture send it along with the entry.

Revision ID: b1c2d3e4f5a6
Revises: ab3c4d5e6f70
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "ab3c4d5e6f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meal_items", sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("meal_items", "image_url")
