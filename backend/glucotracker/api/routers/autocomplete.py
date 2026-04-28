"""Unified autocomplete endpoint for replaceable frontends."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.routers.patterns import search_pattern_rows
from glucotracker.api.schemas import AutocompleteSuggestion
from glucotracker.domain.nutrition import calculate_item_from_per_100g
from glucotracker.infra.db.models import Product
from glucotracker.infra.db.product_merge import collapse_duplicate_source_photo_products

router = APIRouter(
    tags=["autocomplete"],
    dependencies=[Depends(verify_token)],
)

PRODUCT_PREFIXES = {"product", "products", "prod", "my"}
PERSONAL_PATTERN_PREFIXES = {"my", "home"}
RESTAURANT_PATTERN_PREFIXES = {"bk", "mc", "rostics", "vit"}


def _normalized(value: str | None) -> str:
    """Return a casefolded search value."""
    return (value or "").casefold().strip()


def _text_match_rank(values: list[str], q: str) -> int:
    """Rank text matches for mixed autocomplete sorting."""
    query = _normalized(q)
    if not query:
        return 3
    normalized_values = [_normalized(value) for value in values if value]
    if any(value == query for value in normalized_values):
        return 0
    if any(value.startswith(query) for value in normalized_values):
        return 1
    if any(query in value for value in normalized_values):
        return 5
    return 9


def _product_matched_alias(product: Product, q: str) -> str | None:
    """Return a product alias matched by the query, if any."""
    query = _normalized(q)
    if not query:
        return None

    exact = [
        alias.alias for alias in product.aliases if alias.alias.casefold() == query
    ]
    if exact:
        return exact[0]

    prefix = [
        alias.alias
        for alias in product.aliases
        if alias.alias.casefold().startswith(query)
    ]
    return prefix[0] if prefix else None


def _product_matches(product: Product, q: str) -> bool:
    """Return whether a product matches an autocomplete query."""
    query = _normalized(q)
    if not query:
        return True
    return _text_match_rank(_product_search_values(product), query) < 9


def _product_search_values(product: Product) -> list[str]:
    """Return searchable product text fields."""
    return [
        product.barcode or "",
        product.brand or "",
        product.name,
        *[alias.alias for alias in product.aliases],
    ]


def _product_match_rank(product: Product, q: str) -> int:
    """Return product match rank for autocomplete sorting."""
    return _text_match_rank(_product_search_values(product), q)


def _pattern_search_values(pattern) -> list[str]:
    """Return searchable pattern text fields."""
    return [
        pattern.key,
        f"{pattern.prefix}:{pattern.key}",
        pattern.display_name,
        *[alias.alias for alias in pattern.aliases],
    ]


def _pattern_match_rank(pattern, q: str) -> int:
    """Return pattern match rank for autocomplete sorting."""
    return _text_match_rank(_pattern_search_values(pattern), q)


def _pattern_source_rank(pattern) -> int:
    """Prioritize personal patterns over restaurant database rows."""
    prefix = pattern.prefix.casefold()
    if prefix in PERSONAL_PATTERN_PREFIXES:
        return 0
    if prefix in RESTAURANT_PATTERN_PREFIXES:
        return 2
    return 1


def _product_sort_key(product: Product) -> tuple:
    """Sort products by previous usage and recency."""
    last_used = product.last_used_at
    null_rank = 1 if last_used is None else 0
    timestamp_rank = -last_used.timestamp() if isinstance(last_used, datetime) else 0
    return (
        -(product.usage_count or 0),
        null_rank,
        timestamp_rank,
        product.name.casefold(),
    )


def _product_macros(product: Product) -> dict[str, float | None]:
    """Return best available product macros for autocomplete suggestions."""
    if product.default_grams is not None and product.carbs_per_100g is not None:
        scaled = calculate_item_from_per_100g(
            product.carbs_per_100g,
            product.protein_per_100g,
            product.fat_per_100g,
            product.fiber_per_100g,
            product.kcal_per_100g,
            product.default_grams,
        )
        return {
            "carbs_g": float(scaled["carbs_g"]),
            "protein_g": float(scaled["protein_g"]),
            "fat_g": float(scaled["fat_g"]),
            "kcal": float(scaled["kcal"]),
        }
    return {
        "carbs_g": product.carbs_per_serving,
        "protein_g": product.protein_per_serving,
        "fat_g": product.fat_per_serving,
        "kcal": product.kcal_per_serving,
    }


def _product_rows(session: SessionDep, q: str, *, limit: int) -> list[Product]:
    """Search products for autocomplete."""
    statement = select(Product).options(
        selectinload(Product.aliases),
        selectinload(Product.items),
    )
    products = [
        product
        for product in collapse_duplicate_source_photo_products(
            session.scalars(statement).all()
        )
        if _product_matches(product, q)
    ]
    products.sort(
        key=lambda product: (
            _product_match_rank(product, q),
            *_product_sort_key(product),
        )
    )
    return products[:limit]


def _pattern_suggestion(
    pattern_row: tuple,
    q: str = "",
) -> tuple[AutocompleteSuggestion, int, datetime | None, int, int]:
    """Convert a pattern row into a sortable autocomplete suggestion."""
    pattern, matched_alias = pattern_row
    return (
        AutocompleteSuggestion(
            kind="pattern",
            id=pattern.id,
            token=f"{pattern.prefix}:{pattern.key}",
            display_name=pattern.display_name,
            subtitle=f"{pattern.prefix}:{pattern.key}",
            carbs_g=pattern.default_carbs_g,
            protein_g=pattern.default_protein_g,
            fat_g=pattern.default_fat_g,
            kcal=pattern.default_kcal,
            image_url=pattern.image_url,
            usage_count=pattern.usage_count,
            matched_alias=matched_alias,
        ),
        pattern.usage_count,
        pattern.last_used_at,
        _pattern_match_rank(pattern, q),
        _pattern_source_rank(pattern),
    )


def _product_suggestion(
    product: Product,
    q: str,
) -> tuple[AutocompleteSuggestion, int, datetime | None, int, int]:
    """Convert a product row into a sortable autocomplete suggestion."""
    macros = _product_macros(product)
    token = product.barcode or product.name
    subtitle_parts = [
        part for part in [product.brand, product.default_serving_text] if part
    ]
    return (
        AutocompleteSuggestion(
            kind="product",
            id=product.id,
            token=token,
            display_name=product.name,
            subtitle=" · ".join(subtitle_parts) if subtitle_parts else None,
            carbs_g=macros["carbs_g"],
            protein_g=macros["protein_g"],
            fat_g=macros["fat_g"],
            kcal=macros["kcal"],
            image_url=product.image_url,
            usage_count=product.usage_count,
            matched_alias=_product_matched_alias(product, q),
        ),
        product.usage_count,
        product.last_used_at,
        _product_match_rank(product, q),
        0,
    )


def _suggestion_sort_key(
    row: tuple[AutocompleteSuggestion, int, datetime | None, int, int],
) -> tuple:
    """Sort combined suggestions by match quality, ownership, usage, and recency."""
    suggestion, usage_count, last_used, match_rank, source_rank = row
    null_rank = 1 if last_used is None else 0
    timestamp_rank = -last_used.timestamp() if isinstance(last_used, datetime) else 0
    return (
        match_rank,
        source_rank,
        -(usage_count or 0),
        null_rank,
        timestamp_rank,
        suggestion.kind,
        suggestion.display_name.casefold(),
    )


@router.get(
    "/autocomplete",
    response_model=list[AutocompleteSuggestion],
    operation_id="autocomplete",
)
def autocomplete(
    session: SessionDep,
    q: str = "",
    limit: int = Query(default=20, ge=1, le=100),
) -> list[AutocompleteSuggestion]:
    """Return unified pattern and product suggestions for frontends."""
    prefix = ""
    suffix = q
    if ":" in q:
        raw_prefix, raw_suffix = q.split(":", 1)
        prefix = raw_prefix.strip().casefold()
        suffix = raw_suffix.strip()

    if prefix in PRODUCT_PREFIXES:
        rows = [
            _product_suggestion(product, suffix)
            for product in _product_rows(session, suffix, limit=limit)
        ]
        if prefix == "my":
            for personal_prefix in PERSONAL_PATTERN_PREFIXES:
                rows.extend(
                    _pattern_suggestion(pattern_row, suffix)
                    for pattern_row in search_pattern_rows(
                        session,
                        f"{personal_prefix}:{suffix}",
                        limit=limit,
                    )
                )
            rows.sort(key=_suggestion_sort_key)
        return [row[0] for row in rows[:limit]]

    if prefix:
        return [
            row[0]
            for row in [
                _pattern_suggestion(pattern_row, suffix)
                for pattern_row in search_pattern_rows(session, q, limit=limit)
            ]
        ]

    source_limit = min(max(limit * 3, limit), 100)
    rows: list[tuple[AutocompleteSuggestion, int, datetime | None, int, int]] = []
    rows.extend(
        _pattern_suggestion(pattern_row, q)
        for pattern_row in search_pattern_rows(session, q, limit=source_limit)
    )
    rows.extend(
        _product_suggestion(product, q)
        for product in _product_rows(session, q, limit=source_limit)
    )
    rows.sort(key=_suggestion_sort_key)
    return [row[0] for row in rows[:limit]]
