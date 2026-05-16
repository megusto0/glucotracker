"""Backfill nullable product categories with deterministic keyword rules."""

from __future__ import annotations

from glucotracker.application.product_categories import categorize_text
from glucotracker.infra.db.models import Product
from glucotracker.infra.db.session import get_session_factory


def main() -> None:
    """Assign categories to uncategorized products without exposing them to clients."""
    session = get_session_factory()()
    try:
        products = session.query(Product).filter(Product.category.is_(None)).all()
        updated = 0
        for product in products:
            category = categorize_text((product.name, product.brand))
            if category is None:
                continue
            product.category = category
            updated += 1
        session.commit()
        print(f"updated={updated}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
