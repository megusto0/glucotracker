"""Helpers for merging duplicate saved products."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.infra.db.models import Product, ProductAlias, utc_now

LABEL_PRODUCT_SOURCE_KINDS = {"label_calc", "label_exact", "label_partial"}


def source_photo_product_key(product: Product) -> tuple[str, str] | None:
    """Return a conservative duplicate key for products derived from one photo."""
    if not product.image_url or not product.image_url.startswith("/photos/"):
        return None
    if product.source_kind not in LABEL_PRODUCT_SOURCE_KINDS:
        return None
    return (product.image_url, (product.brand or "").casefold())


def collapse_duplicate_source_photo_products(
    products: Iterable[Product],
) -> list[Product]:
    """Return products with duplicate photo-label rows collapsed for display/search."""
    grouped: dict[tuple[str, str], list[Product]] = {}
    passthrough: list[Product] = []

    for product in products:
        key = source_photo_product_key(product)
        if key is None:
            passthrough.append(product)
            continue
        grouped.setdefault(key, []).append(product)

    collapsed = passthrough
    for group in grouped.values():
        collapsed.append(_canonical_product(group))
    return collapsed


def merge_duplicate_source_photo_products(session: Session, target: Product) -> None:
    """Merge products that came from the same label photo into target."""
    target_key = source_photo_product_key(target)
    if target_key is None:
        return

    duplicates = session.scalars(
        select(Product)
        .where(Product.id != target.id, Product.image_url == target.image_url)
        .options(selectinload(Product.aliases), selectinload(Product.items))
    ).all()
    for duplicate in duplicates:
        if source_photo_product_key(duplicate) != target_key:
            continue
        _merge_product_into_target(session, target, duplicate)


def _canonical_product(products: list[Product]) -> Product:
    """Choose the row that should represent duplicate photo-label products."""
    return sorted(
        products,
        key=lambda product: (
            0 if product.items else 1,
            -product.updated_at.timestamp() if product.updated_at else 0,
            -(product.usage_count or 0),
            product.name.casefold(),
        ),
    )[0]


def _merge_product_into_target(
    session: Session,
    target: Product,
    duplicate: Product,
) -> None:
    """Move aliases, usage counters, and meal item links to target."""
    existing_aliases = {alias.alias.casefold() for alias in target.aliases}
    for alias in duplicate.aliases:
        normalized = alias.alias.strip()
        if normalized and normalized.casefold() not in existing_aliases:
            target.aliases.append(ProductAlias(alias=normalized))
            existing_aliases.add(normalized.casefold())

    for item in duplicate.items:
        item.product_id = target.id

    target.usage_count = (target.usage_count or 0) + (duplicate.usage_count or 0)
    if duplicate.last_used_at and (
        target.last_used_at is None or duplicate.last_used_at > target.last_used_at
    ):
        target.last_used_at = duplicate.last_used_at
    target.updated_at = utc_now()

    session.flush()
    session.delete(duplicate)
