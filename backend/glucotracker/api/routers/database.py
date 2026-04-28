"""Unified local food database endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import DatabaseItemPageResponse, DatabaseItemResponse
from glucotracker.infra.db.models import MealItem, Pattern, Product
from glucotracker.infra.db.product_merge import collapse_duplicate_source_photo_products

router = APIRouter(
    tags=["database"],
    dependencies=[Depends(verify_token)],
)

RESTAURANT_PREFIXES = {"bk", "mc", "rostics", "vit"}
SOURCE_NAMES = {
    "bk": "Burger King",
    "mc": "McDonald's",
    "rostics": "Rostic's",
    "vit": "Вкусно и точка",
    "home": "Домашнее",
    "my": "Домашнее",
}


def _contains(value: str | None, query: str) -> bool:
    """Return true when value contains query case-insensitively."""
    return bool(value and query in value.casefold())


def _macro_mismatch(
    carbs_g: float | None,
    protein_g: float | None,
    fat_g: float | None,
    kcal: float | None,
) -> bool:
    """Return whether kcal differs materially from 4/4/9 macro estimate."""
    if carbs_g is None or protein_g is None or fat_g is None or not kcal:
        return False
    estimated = carbs_g * 4 + protein_g * 4 + fat_g * 9
    return abs(kcal - estimated) > max(80, kcal * 0.25)


def _pattern_kind(pattern: Pattern) -> str:
    """Classify pattern rows for the database UI."""
    if pattern.prefix.casefold() in RESTAURANT_PREFIXES:
        return "restaurant"
    return "pattern"


def _pattern_warnings(pattern: Pattern) -> list[str]:
    """Return lightweight quality warnings for pattern rows."""
    warnings: list[str] = []
    if not pattern.image_url:
        warnings.append("нет картинки")
    if pattern.default_kcal <= 0 and any(
        value > 0
        for value in (
            pattern.default_carbs_g,
            pattern.default_protein_g,
            pattern.default_fat_g,
        )
    ):
        warnings.append("нет ккал")
    if pattern.default_carbs_g <= 0 and pattern.default_kcal > 50:
        warnings.append("нет углеводов")
    if _macro_mismatch(
        pattern.default_carbs_g,
        pattern.default_protein_g,
        pattern.default_fat_g,
        pattern.default_kcal,
    ):
        warnings.append("ккал не сходятся с БЖУ")
    if not pattern.is_verified:
        warnings.append("нужно проверить")
    if not pattern.source_url and _pattern_kind(pattern) == "restaurant":
        warnings.append("нет источника")
    return warnings


def _product_amount(product: Product, serving: float | None, per_100g: float | None):
    """Return serving amount when available, otherwise derive from per-100g."""
    if serving is not None:
        return serving
    if per_100g is not None and product.default_grams:
        return round(per_100g * product.default_grams / 100, 1)
    return per_100g


def _product_warnings(product: Product) -> list[str]:
    """Return lightweight quality warnings for product rows."""
    warnings: list[str] = []
    kcal = _product_amount(product, product.kcal_per_serving, product.kcal_per_100g)
    carbs = _product_amount(product, product.carbs_per_serving, product.carbs_per_100g)
    protein = _product_amount(
        product,
        product.protein_per_serving,
        product.protein_per_100g,
    )
    fat = _product_amount(product, product.fat_per_serving, product.fat_per_100g)
    if not _product_image_url(product):
        warnings.append("нет картинки")
    if kcal is None:
        warnings.append("нет ккал")
    if carbs is None:
        warnings.append("нет углеводов")
    if _macro_mismatch(carbs, protein, fat, kcal):
        warnings.append("ккал не сходятся с БЖУ")
    if product.source_kind == "manual":
        warnings.append("нужно проверить")
    return warnings


def _photo_file_url(photo_id: object) -> str | None:
    """Return the authenticated photo endpoint for stored meal photos."""
    return f"/photos/{photo_id}/file" if photo_id is not None else None


def _product_image_url(product: Product) -> str | None:
    """Return a product image, falling back to accepted item source photos."""
    if product.image_url:
        return product.image_url
    for item in product.items:
        url = _photo_file_url(item.photo_id)
        if url is not None:
            return url
    return None


def _pattern_response(pattern: Pattern) -> DatabaseItemResponse:
    """Convert a pattern ORM row into a database item response."""
    aliases = [alias.alias for alias in pattern.aliases]
    return DatabaseItemResponse(
        id=pattern.id,
        kind=_pattern_kind(pattern),  # type: ignore[arg-type]
        prefix=pattern.prefix,
        key=pattern.key,
        token=f"{pattern.prefix}:{pattern.key}",
        display_name=pattern.display_name,
        subtitle=f"{pattern.prefix}:{pattern.key}",
        image_url=pattern.image_url,
        carbs_g=pattern.default_carbs_g,
        protein_g=pattern.default_protein_g,
        fat_g=pattern.default_fat_g,
        fiber_g=pattern.default_fiber_g,
        kcal=pattern.default_kcal,
        default_grams=pattern.default_grams,
        usage_count=pattern.usage_count,
        last_used_at=pattern.last_used_at,
        source_name=pattern.source_name
        or SOURCE_NAMES.get(pattern.prefix, pattern.prefix.upper()),
        source_url=pattern.source_url,
        source_file=pattern.source_file,
        source_page=pattern.source_page,
        source_confidence=pattern.source_confidence,
        is_verified=pattern.is_verified,
        aliases=aliases,
        nutrients_json=pattern.nutrients_json,
        quality_warnings=_pattern_warnings(pattern),
    )


def _product_response(product: Product) -> DatabaseItemResponse:
    """Convert a product ORM row into a database item response."""
    aliases = [alias.alias for alias in product.aliases]
    carbs = _product_amount(product, product.carbs_per_serving, product.carbs_per_100g)
    protein = _product_amount(
        product,
        product.protein_per_serving,
        product.protein_per_100g,
    )
    fat = _product_amount(product, product.fat_per_serving, product.fat_per_100g)
    fiber = _product_amount(product, product.fiber_per_serving, product.fiber_per_100g)
    kcal = _product_amount(product, product.kcal_per_serving, product.kcal_per_100g)
    return DatabaseItemResponse(
        id=product.id,
        kind="product",
        token=product.barcode,
        display_name=product.name,
        subtitle=" · ".join(
            part
            for part in (product.brand, product.barcode, product.source_kind)
            if part
        )
        or product.source_kind,
        image_url=_product_image_url(product),
        carbs_g=carbs,
        protein_g=protein,
        fat_g=fat,
        fiber_g=fiber,
        kcal=kcal,
        default_grams=product.default_grams,
        usage_count=product.usage_count,
        last_used_at=product.last_used_at,
        source_name=product.brand or product.source_kind,
        source_url=product.source_url,
        aliases=aliases,
        nutrients_json=product.nutrients_json,
        quality_warnings=_product_warnings(product),
    )


def _matches_query(item: DatabaseItemResponse, q: str | None) -> bool:
    """Return whether an item matches the database search query."""
    if not q:
        return True
    query = q.casefold().strip()
    values = [
        item.display_name,
        item.subtitle,
        item.token,
        item.prefix,
        item.key,
        item.source_name,
        *item.aliases,
    ]
    return any(_contains(value, query) for value in values)


def _matches_source(item: DatabaseItemResponse, source: str | None) -> bool:
    """Return whether an item matches the UI source filter."""
    if not source or source == "all":
        return True
    value = source.casefold()
    if value in {"products", "product", "продукты"}:
        return item.kind == "product"
    if value in {"manual", "ручное"}:
        return item.source_name == "manual" or item.kind == "product"
    if value in {"home", "домашнее"}:
        return item.prefix in {"home", "my"}
    return item.prefix == value


def _matches_type(item: DatabaseItemResponse, type_filter: str | None) -> bool:
    """Return whether an item matches the UI type filter."""
    if not type_filter or type_filter == "all":
        return True
    value = type_filter.casefold()
    if value in {"needs_review", "review", "требуют проверки"}:
        return bool(item.quality_warnings)
    if value in {"missing_image", "без картинки"}:
        return "нет картинки" in item.quality_warnings
    if value in {"missing_nutrition", "без бжу"}:
        return any(
            warning in item.quality_warnings
            for warning in ("нет ккал", "нет углеводов")
        )
    if value in {"verified", "проверено"}:
        return item.is_verified
    if value in {"unverified", "не проверено"}:
        return not item.is_verified
    if value in {"patterns", "pattern", "шаблоны"}:
        return item.kind == "pattern"
    if value in {"products", "product", "продукты"}:
        return item.kind == "product"
    if value in {"restaurants", "restaurant", "рестораны"}:
        return item.kind == "restaurant"
    return True


def _sort_key(item: DatabaseItemResponse) -> tuple[int, int, float, str]:
    """Sort frequently used and recently used items first."""
    last_used = item.last_used_at
    timestamp = last_used.timestamp() if isinstance(last_used, datetime) else 0
    return (
        0 if item.usage_count else 1,
        -(item.usage_count or 0),
        -timestamp,
        item.display_name.casefold(),
    )


@router.get(
    "/database/items",
    response_model=DatabaseItemPageResponse,
    operation_id="listDatabaseItems",
)
def list_database_items(
    session: SessionDep,
    type_filter: str | None = Query(default=None, alias="type"),
    source: str | None = None,
    q: str | None = None,
    needs_review: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DatabaseItemPageResponse:
    """List local pattern and product database rows for desktop management."""
    patterns = session.scalars(
        select(Pattern)
        .where(Pattern.is_archived.is_(False))
        .options(selectinload(Pattern.aliases))
    ).all()
    products = session.scalars(
        select(Product).options(
            selectinload(Product.aliases),
            selectinload(Product.items).load_only(MealItem.photo_id),
        )
    ).all()
    products = collapse_duplicate_source_photo_products(products)

    rows = [
        *(_pattern_response(pattern) for pattern in patterns),
        *(_product_response(product) for product in products),
    ]
    if needs_review is True:
        type_filter = "needs_review"
    filtered = [
        item
        for item in rows
        if _matches_query(item, q)
        and _matches_source(item, source)
        and _matches_type(item, type_filter)
    ]
    filtered.sort(key=_sort_key)
    page = filtered[offset : offset + limit]
    return DatabaseItemPageResponse(
        items=page,
        total=len(filtered),
        limit=limit,
        offset=offset,
    )
