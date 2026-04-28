"""Product REST endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import (
    ProductCreate,
    ProductFromLabelRequest,
    ProductPageResponse,
    ProductPatch,
    ProductResponse,
)
from glucotracker.domain.nutrients import normalize_nutrients_object
from glucotracker.infra.db.models import Product, ProductAlias, utc_now
from glucotracker.infra.db.product_merge import (
    collapse_duplicate_source_photo_products,
    merge_duplicate_source_photo_products,
)
from glucotracker.infra.storage import product_image_store

router = APIRouter(
    tags=["products"],
    dependencies=[Depends(verify_token)],
)


def _product_options() -> tuple:
    """Return eager-load options used by product responses."""
    return (selectinload(Product.aliases),)


def _get_product(session: SessionDep, product_id: UUID) -> Product:
    """Fetch a product or raise 404."""
    product = session.scalar(
        select(Product).where(Product.id == product_id).options(*_product_options())
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )
    return product


def _product_response(product: Product) -> ProductResponse:
    """Convert a product ORM object into an API response."""
    return ProductResponse.model_validate(
        {
            "id": product.id,
            "barcode": product.barcode,
            "brand": product.brand,
            "name": product.name,
            "default_grams": product.default_grams,
            "default_serving_text": product.default_serving_text,
            "carbs_per_100g": product.carbs_per_100g,
            "protein_per_100g": product.protein_per_100g,
            "fat_per_100g": product.fat_per_100g,
            "fiber_per_100g": product.fiber_per_100g,
            "kcal_per_100g": product.kcal_per_100g,
            "carbs_per_serving": product.carbs_per_serving,
            "protein_per_serving": product.protein_per_serving,
            "fat_per_serving": product.fat_per_serving,
            "fiber_per_serving": product.fiber_per_serving,
            "kcal_per_serving": product.kcal_per_serving,
            "source_kind": product.source_kind,
            "source_url": product.source_url,
            "image_url": product.image_url,
            "nutrients_json": product.nutrients_json,
            "usage_count": product.usage_count,
            "last_used_at": product.last_used_at,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
            "aliases": [alias.alias for alias in product.aliases],
        }
    )


def _replace_aliases(product: Product, aliases: list[str]) -> None:
    """Replace product aliases with normalized non-empty values."""
    seen = set()
    product.aliases = []
    for alias in aliases:
        normalized = alias.strip()
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        product.aliases.append(ProductAlias(alias=normalized))


def _find_product_for_label(
    session: SessionDep,
    payload: ProductFromLabelRequest,
) -> Product | None:
    """Find an existing product suitable for label-fact update."""
    if payload.barcode:
        product = session.scalar(
            select(Product)
            .where(Product.barcode == payload.barcode)
            .options(*_product_options())
        )
        if product is not None:
            return product

    brand = (payload.brand or "").casefold()
    name = payload.name.casefold()
    products = session.scalars(select(Product).options(*_product_options())).all()
    for product in products:
        brand_matches = (product.brand or "").casefold() == brand
        name_matches = product.name.casefold() == name
        if brand_matches and name_matches:
            return product
    return None


@router.get(
    "/products",
    response_model=ProductPageResponse,
    operation_id="listProducts",
)
def list_products(
    session: SessionDep,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProductPageResponse:
    """List products, optionally searching brand, name, or barcode."""
    filters = []
    if q:
        term = f"%{q}%"
        filters.append(
            or_(
                Product.name.ilike(term),
                Product.brand.ilike(term),
                Product.barcode.ilike(term),
            )
        )

    products = session.scalars(
        select(Product)
        .where(*filters)
        .options(*_product_options())
        .order_by(Product.name.asc())
    ).all()

    products = collapse_duplicate_source_photo_products(products)
    total = len(products)
    products = products[offset : offset + limit]
    return ProductPageResponse(
        items=[_product_response(product) for product in products],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProduct",
)
def create_product(payload: ProductCreate, session: SessionDep) -> ProductResponse:
    """Create a manually saved packaged food."""
    data = payload.model_dump(exclude={"aliases"})
    data["nutrients_json"] = normalize_nutrients_object(
        data.get("nutrients_json"),
        default_source_kind="product_db",
    )
    product = Product(**data)
    _replace_aliases(product, payload.aliases)
    session.add(product)
    session.commit()
    return _product_response(_get_product(session, product.id))


@router.post(
    "/products/from_label",
    response_model=ProductResponse,
    operation_id="createOrUpdateProductFromLabel",
)
def create_or_update_product_from_label(
    payload: ProductFromLabelRequest,
    session: SessionDep,
) -> ProductResponse:
    """Create or update a product from manually confirmed label facts."""
    data = payload.model_dump(exclude={"aliases"})
    data["nutrients_json"] = normalize_nutrients_object(
        data.get("nutrients_json"),
        default_source_kind="label_calc",
    )
    product = _find_product_for_label(session, payload)
    if product is None:
        product = Product(**data)
        session.add(product)
    else:
        for field, value in data.items():
            setattr(product, field, value)
        product.updated_at = utc_now()

    _replace_aliases(product, payload.aliases)
    session.commit()
    return _product_response(_get_product(session, product.id))


@router.get(
    "/products/search",
    response_model=list[ProductResponse],
    operation_id="searchProducts",
)
def search_products(
    session: SessionDep,
    q: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ProductResponse]:
    """Search products by name, brand, barcode, and aliases."""
    term = f"%{q}%"
    products = session.scalars(
        select(Product)
        .where(
            or_(
                Product.name.ilike(term),
                Product.brand.ilike(term),
                Product.barcode.ilike(term),
                Product.aliases.any(ProductAlias.alias.ilike(term)),
            )
        )
        .options(*_product_options())
        .limit(limit)
    ).all()

    products = sorted(
        products,
        key=lambda product: (
            -(product.usage_count or 0),
            1 if product.last_used_at is None else 0,
            -product.last_used_at.timestamp() if product.last_used_at else 0,
            product.name.casefold(),
        ),
    )
    return [_product_response(product) for product in products]


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    operation_id="getProduct",
)
def get_product(product_id: UUID, session: SessionDep) -> ProductResponse:
    """Return a saved product."""
    return _product_response(_get_product(session, product_id))


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    operation_id="patchProduct",
)
def patch_product(
    product_id: UUID,
    payload: ProductPatch,
    session: SessionDep,
) -> ProductResponse:
    """Patch a saved product."""
    product = _get_product(session, product_id)
    data = payload.model_dump(exclude_unset=True)
    aliases = data.pop("aliases", None)
    for field, value in data.items():
        if field == "nutrients_json" and value is not None:
            value = normalize_nutrients_object(value, default_source_kind="product_db")
        setattr(product, field, value)
    if aliases is not None:
        _replace_aliases(product, aliases)
    product.updated_at = utc_now()
    merge_duplicate_source_photo_products(session, product)

    session.commit()
    return _product_response(_get_product(session, product.id))


@router.post(
    "/products/{product_id}/image",
    response_model=ProductResponse,
    operation_id="uploadProductImage",
)
def upload_product_image(
    product_id: UUID,
    session: SessionDep,
    file: Annotated[UploadFile, File(...)],
) -> ProductResponse:
    """Upload and replace a local product image."""
    product = _get_product(session, product_id)
    try:
        product_image_store.save_upload(product.id, file)
    except product_image_store.ProductImageStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    product.image_url = f"/products/{product.id}/image/file"
    product.updated_at = utc_now()
    session.commit()
    return _product_response(_get_product(session, product.id))


@router.get(
    "/products/{product_id}/image/file",
    operation_id="getProductImageFile",
)
def get_product_image_file(product_id: UUID, session: SessionDep) -> FileResponse:
    """Stream a locally stored product image."""
    product = _get_product(session, product_id)
    try:
        full_path = product_image_store.get_full_path(product.id)
    except product_image_store.ProductImageStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return FileResponse(
        full_path,
        media_type=product_image_store.content_type_for_path(full_path),
        filename=f"{product.name}{full_path.suffix}",
    )
