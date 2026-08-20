"""Product REST endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.routers.autocomplete import (
    _product_search_values,
    _search_tokens,
    _text_match_rank,
)
from glucotracker.api.schemas import (
    DeleteResponse,
    ProductCreate,
    ProductFromLabelRequest,
    ProductPageResponse,
    ProductPatch,
    ProductResponse,
    ServingUnitUpdate,
)
from glucotracker.domain.nutrients import normalize_nutrients_object
from glucotracker.infra.db.models import Meal, MealItem, Product, ProductAlias, utc_now
from glucotracker.infra.db.product_merge import (
    collapse_duplicate_source_photo_products,
    merge_duplicate_source_photo_products,
)
from glucotracker.infra.storage import product_image_store

router = APIRouter(tags=["products"])
IMAGE_RESPONSE_HEADERS = {"Cache-Control": "private, max-age=604800"}


def _product_options() -> tuple:
    """Return eager-load options used by product responses."""
    return (selectinload(Product.aliases),)


def _visible_product_filter(user_id: UUID):
    return (Product.owner_id.is_(None)) | (Product.owner_id == user_id)


def _get_product(session: SessionDep, user_id: UUID, product_id: UUID) -> Product:
    """Fetch a product or raise 404."""
    product = session.scalar(
        select(Product).where(Product.id == product_id).options(*_product_options())
        .where(_visible_product_filter(user_id))
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
        product.aliases.append(
            ProductAlias(owner_id=product.owner_id, alias=normalized)
        )


def _find_product_for_label(
    session: SessionDep,
    user_id: UUID,
    payload: ProductFromLabelRequest,
) -> Product | None:
    """Find an existing product suitable for label-fact update."""
    if payload.barcode:
        product = session.scalar(
            select(Product)
            .where(Product.barcode == payload.barcode)
            .where(_visible_product_filter(user_id))
            .options(*_product_options())
        )
        if product is not None:
            return product

    brand = (payload.brand or "").casefold()
    name = payload.name.casefold()
    products = session.scalars(
        select(Product)
        .where(_visible_product_filter(user_id))
        .options(*_product_options())
    ).all()
    for product in products:
        brand_matches = (product.brand or "").casefold() == brand
        name_matches = product.name.casefold() == name
        if brand_matches and name_matches:
            return product
    return None


from glucotracker.application.fridge_sync import FridgeIntegrationService, FridgeItem, MealPrepItem


def _fridge_item_to_product_response(item: FridgeItem) -> ProductResponse:
    """Convert an available fridge item into a ProductResponse for mobile client sync."""
    try:
        item_uuid = UUID(hex=item.lot_id.replace("-", ""))
    except Exception:
        item_uuid = UUID("00000000-0000-0000-0000-000000000000")

    unit_norm = (item.unit or "").lower().strip()
    is_pcs = unit_norm in ("pcs", "шт", "pack", "уп")

    # Normalised to the unit the client actually computes in. A lot held in
    # kilograms reported `0.9 kg`, and the client reads stock_remaining as the
    # ceiling for its gram slider — which pinned an entire kilogram of apples
    # at nought point nine grams.
    remaining = item.remaining_quantity
    if is_pcs:
        unit_display = "шт"
    elif unit_norm in ("kg", "кг"):
        remaining *= 1000.0
        unit_display = "г"
    elif unit_norm in ("l", "л"):
        remaining *= 1000.0
        unit_display = "мл"
    elif unit_norm in ("g", "г"):
        unit_display = "г"
    elif unit_norm in ("ml", "мл"):
        unit_display = "мл"
    else:
        unit_display = item.unit

    # Grams once the count stops being whole. «0.0 шт в наличии» over a fifth
    # of a bag of halva reported the rounding, not the stock — and a fifth of a
    # bag is a real amount you can still eat. Whole counts stay counts: ten
    # eggs are ten eggs, not six hundred grams.
    show_grams = (
        is_pcs
        and not float(remaining).is_integer()
        and item.weight_grams
        and item.weight_grams > 0
    )
    if show_grams:
        qty_str = f"{round(item.weight_grams)} г"
    else:
        qty_str = (
            f"{int(remaining)} {unit_display}"
            if float(remaining).is_integer()
            else f"{remaining:.1f} {unit_display}"
        )
    # Plain text. The origin travels in `source_kind` and the amount in
    # `stock_remaining`, so the client can draw its own mark rather than
    # inherit a snowflake from the middle of a sentence.
    serving_text = f"{qty_str} в наличии"

    # What is left, in grams, however the lot is counted. Sent outright because
    # the client cannot work it out: multiplying a remainder by a piece weight
    # only works when the piece weight is real, and «0,2 шт» of halva came out
    # as the weight of a full bag.
    remaining_grams: float | None = item.weight_grams if is_pcs else remaining

    # Independent of how the lot is measured. Apples bought by weight still
    # come one apple at a time, and the fridge's estimate of one is the only
    # thing that lets the portion sheet offer «1 шт» for a 0,9 kg bag.
    single_piece_grams: float | None = item.piece_weight_g
    if is_pcs:
        # Only a weight the fridge actually measured is a piece. What is left
        # divided by how many packages are left is the size of a package, and
        # a 500 g bag of halva is not a piece of anything — offering it as one
        # put «Целиком · 500 г за штуку» over a fifth of a bag.
        pack_grams = (
            round(item.weight_grams / item.remaining_quantity, 1)
            if item.weight_grams and item.remaining_quantity > 0
            else None
        )
        default_grams = single_piece_grams or pack_grams or 100.0
    else:
        default_grams = min(100.0, item.weight_grams or 100.0)

    kcal_100 = item.kcal_per_100g or 0.0
    carbs_100 = item.carbs_per_100g or 0.0
    protein_100 = item.protein_per_100g or 0.0
    fat_100 = item.fat_per_100g or 0.0

    return ProductResponse.model_validate(
        {
            "id": item_uuid,
            "barcode": None,
            "brand": item.brand,
            "name": item.name,
            "default_grams": default_grams,
            "default_serving_text": serving_text,
            "carbs_per_100g": carbs_100,
            "protein_per_100g": protein_100,
            "fat_per_100g": fat_100,
            "fiber_per_100g": 0.0,
            "kcal_per_100g": kcal_100,
            "carbs_per_serving": round(carbs_100 * default_grams / 100.0, 1),
            "protein_per_serving": round(protein_100 * default_grams / 100.0, 1),
            "fat_per_serving": round(fat_100 * default_grams / 100.0, 1),
            "fiber_per_serving": 0.0,
            "kcal_per_serving": round(kcal_100 * default_grams / 100.0, 1),
            "source_kind": "fridge",
            "serving_unit": item.serving_unit,
            "stock_remaining_g": remaining_grams,
            "source_url": f"fridge:{item.lot_id}",
            "image_url": item.image_url,
            "nutrients_json": {},
            "stock_remaining": remaining,
            "stock_unit": unit_display,
            "piece_weight_g": single_piece_grams,
            "stock_expires_in_days": item.days_to_expiry,
            # Not 100. Stock is already put at the head of the list by the
            # endpoint, and a fabricated count rendered as «× 100 раз» — a
            # claim about the user's history that never happened.
            "usage_count": 0,
            "last_used_at": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "aliases": ["холодильник", "fridge"],
        }
    )


def _collapse_mealpreps(items: list[MealPrepItem]) -> list[tuple[MealPrepItem, int]]:
    """Group a batch's containers into one entry carrying how many are left.

    Six containers of one cook are one dish, not six products. Each was
    arriving as its own row whose name differed only by a code the list then
    truncated, so the search offered «Сметанник» three times and gave no way to
    tell which was which. The oldest remaining container stands for the batch —
    recording one still consumes a real container, and first in, first out is
    what you want from a fridge anyway.
    """
    by_batch: dict[str, list[MealPrepItem]] = {}
    for item in items:
        by_batch.setdefault(item.batch_id, []).append(item)
    collapsed: list[tuple[MealPrepItem, int]] = []
    for containers in by_batch.values():
        oldest = min(containers, key=lambda c: c.public_code)
        collapsed.append((oldest, len(containers)))
    return collapsed


def _mealprep_item_to_product_response(
    item: MealPrepItem,
    containers_left: int = 1,
) -> ProductResponse:
    """Convert an available meal prep container into a ProductResponse for mobile client sync."""
    try:
        cont_uuid = UUID(hex=item.container_id.replace("-", ""))
    except Exception:
        cont_uuid = UUID("00000000-0000-0000-0000-000000000000")

    remaining_g = float(item.remaining_weight_g or item.net_weight_g or 0)
    net_w = item.net_weight_g or item.remaining_weight_g or 100.0
    # The only number in this sentence must be grams. The installed client
    # takes the last figure as the slider ceiling, so «ещё 3» locked every
    # portion at 3 g even after stock_remaining was already the weight.
    #
    # Rounded the way the client rounds, not truncated: int() on 113,75 g put
    # «113 г в контейнере» directly above a chip offering «Вся (114 г)», two
    # figures on one screen for the one container in front of you.
    serving_text = f"{round(remaining_g or net_w)} г в контейнере"

    return ProductResponse.model_validate(
        {
            "id": cont_uuid,
            "barcode": None,
            "brand": item.public_code,
            # The code left the name. «Сметанник (GT:C:1793F419F0)» three times
            # over is one dish in three containers, and the only part that told
            # them apart was truncated by every list that drew it.
            "name": item.dish_name,
            "default_grams": remaining_g or net_w,
            "default_serving_text": serving_text,
            "carbs_per_100g": round((item.carbs / net_w) * 100.0, 1) if net_w > 0 else item.carbs,
            "protein_per_100g": round((item.protein / net_w) * 100.0, 1) if net_w > 0 else item.protein,
            "fat_per_100g": round((item.fat / net_w) * 100.0, 1) if net_w > 0 else item.fat,
            "fiber_per_100g": 0.0,
            "kcal_per_100g": round((item.kcal / net_w) * 100.0, 1) if net_w > 0 else item.kcal,
            "carbs_per_serving": item.carbs,
            "protein_per_serving": item.protein,
            "fat_per_serving": item.fat,
            "fiber_per_serving": 0.0,
            "kcal_per_serving": item.kcal,
            "source_kind": "meal_prep",
            "source_url": f"mp:{item.container_id}",
            "image_url": item.image_url,
            "nutrients_json": {},
            # Grams left in THIS container. The slider reads stock_remaining as
            # its max; sending the container count (3) pinned every portion at 3 g.
            "stock_remaining": remaining_g,
            "stock_unit": "г",
            "stock_code": item.public_code,
            # What the picker counts in. The alias below says the same thing in
            # words for clients that predate this field.
            "stock_containers_left": containers_left,
            "usage_count": 0,
            "last_used_at": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "aliases": ["милпреп", "mp", item.public_code]
            + ([f"ещё {containers_left}"] if containers_left > 1 else []),
        }
    )


@router.get(
    "/products",
    response_model=ProductPageResponse,
    operation_id="listProducts",
)
def list_products(
    session: SessionDep,
    current_user: CurrentUserDep,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ProductPageResponse:
    """List products including live available fridge items and meal preps."""
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
        .where(_visible_product_filter(current_user.id))
        .options(*_product_options())
        .order_by(Product.name.asc())
    ).all()

    products = collapse_duplicate_source_photo_products(products)
    product_responses = [_product_response(product) for product in products]

    # Fetch live available items from Fridge
    fridge_service = FridgeIntegrationService()
    try:
        fridge_items = fridge_service.fetch_available_inventory(current_user.id)
        mealprep_items = fridge_service.fetch_available_mealpreps(current_user.id)

        fridge_responses = [_fridge_item_to_product_response(item) for item in fridge_items]
        mealprep_responses = [
            _mealprep_item_to_product_response(item, containers_left)
            for item, containers_left in _collapse_mealpreps(mealprep_items)
        ]

        if q:
            q_norm = q.casefold().strip()
            fridge_responses = [
                r for r in fridge_responses
                if q_norm in r.name.casefold() or (r.brand and q_norm in r.brand.casefold())
            ]
            mealprep_responses = [
                r for r in mealprep_responses
                if q_norm in r.name.casefold() or (r.brand and q_norm in r.brand.casefold())
            ]

        # Prioritize ready mealpreps and fridge stock at the top of the list
        all_items = mealprep_responses + fridge_responses + product_responses
    except Exception:
        all_items = product_responses

    total = len(all_items)
    paged = all_items[offset : offset + limit]
    return ProductPageResponse(
        items=paged,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/products/{product_id}/serving-unit",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="setProductServingUnit",
)
def set_product_serving_unit(
    product_id: UUID,
    payload: ServingUnitUpdate,
    current_user: CurrentUserDep,
) -> Response:
    """Record whether this fridge product is eaten by pieces or by grams.

    Kept in the fridge rather than here, because the answer belongs to the food
    and not to whichever client was open when it was given: a tub of ice cream
    is eaten by the spoonful on every phone, and in the fridge's own screens.
    """
    outcome = FridgeIntegrationService().set_serving_unit(
        str(product_id),
        payload.serving_unit,
        owner_id=current_user.id,
    )
    if outcome == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Такого продукта нет в холодильнике.",
        )
    if outcome != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Холодильник не принял ответ ({outcome}).",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProduct",
)
def create_product(
    payload: ProductCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ProductResponse:
    """Create a manually saved packaged food."""
    data = payload.model_dump(exclude={"aliases"})
    data["nutrients_json"] = normalize_nutrients_object(
        data.get("nutrients_json"),
        default_source_kind="product_db",
    )
    product = Product(owner_id=current_user.id, **data)
    _replace_aliases(product, payload.aliases)
    session.add(product)
    session.commit()
    return _product_response(_get_product(session, current_user.id, product.id))


@router.post(
    "/products/from_label",
    response_model=ProductResponse,
    operation_id="createOrUpdateProductFromLabel",
)
def create_or_update_product_from_label(
    payload: ProductFromLabelRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ProductResponse:
    """Create or update a product from manually confirmed label facts."""
    data = payload.model_dump(exclude={"aliases"})
    data["nutrients_json"] = normalize_nutrients_object(
        data.get("nutrients_json"),
        default_source_kind="label_calc",
    )
    product = _find_product_for_label(session, current_user.id, payload)
    if product is None:
        product = Product(owner_id=current_user.id, **data)
        session.add(product)
    else:
        for field, value in data.items():
            setattr(product, field, value)
        product.updated_at = utc_now()

    _replace_aliases(product, payload.aliases)
    session.commit()
    return _product_response(_get_product(session, current_user.id, product.id))


@router.get(
    "/products/search",
    response_model=list[ProductResponse],
    operation_id="searchProducts",
)
def search_products(
    session: SessionDep,
    current_user: CurrentUserDep,
    q: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ProductResponse]:
    """Search products by name, brand, barcode, and aliases."""
    tokens = _search_tokens(q)
    if not tokens:
        return []
    token_conditions = []
    for token in tokens:
        term = f"%{token}%"
        token_conditions.append(
            or_(
                Product.name.ilike(term),
                Product.brand.ilike(term),
                Product.barcode.ilike(term),
                Product.aliases.any(ProductAlias.alias.ilike(term)),
            )
        )
    products = session.scalars(
        select(Product)
        .where(or_(*token_conditions))
        .where(_visible_product_filter(current_user.id))
        .options(*_product_options())
    ).all()
    products = [
        product
        for product in products
        if _text_match_rank(_product_search_values(product), q) < 9
    ]

    products = sorted(
        products,
        key=lambda product: (
            _text_match_rank(_product_search_values(product), q),
            -(product.usage_count or 0),
            1 if product.last_used_at is None else 0,
            -product.last_used_at.timestamp() if product.last_used_at else 0,
            product.name.casefold(),
        ),
    )[:limit]
    return [_product_response(product) for product in products]


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    operation_id="getProduct",
)
def get_product(
    product_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ProductResponse:
    """Return a saved product."""
    return _product_response(_get_product(session, current_user.id, product_id))


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    operation_id="patchProduct",
)
def patch_product(
    product_id: UUID,
    payload: ProductPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ProductResponse:
    """Patch a saved product."""
    product = _get_product(session, current_user.id, product_id)
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
    return _product_response(_get_product(session, current_user.id, product.id))


@router.delete(
    "/products/{product_id}",
    response_model=DeleteResponse,
    operation_id="deleteProduct",
)
def delete_product(
    product_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> DeleteResponse:
    """Delete a personal saved product and unlink it from the user's meal items."""
    product = _get_product(session, current_user.id, product_id)
    if product.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only personal products can be deleted.",
        )

    linked_items = session.scalars(
        select(MealItem)
        .join(Meal, Meal.id == MealItem.meal_id)
        .where(MealItem.product_id == product.id, Meal.owner_id == current_user.id)
    ).all()
    for item in linked_items:
        item.product_id = None

    session.delete(product)
    session.commit()
    return DeleteResponse(deleted=True)


@router.post(
    "/products/{product_id}/image",
    response_model=ProductResponse,
    operation_id="uploadProductImage",
)
def upload_product_image(
    product_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    file: Annotated[UploadFile, File(...)],
) -> ProductResponse:
    """Upload and replace a local product image."""
    product = _get_product(session, current_user.id, product_id)
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
    return _product_response(_get_product(session, current_user.id, product.id))


@router.get(
    "/products/{product_id}/image/file",
    operation_id="getProductImageFile",
)
def get_product_image_file(
    product_id: UUID,
    session: SessionDep,
) -> Response:
    """Stream a locally stored product image or redirect to external/fridge image URL."""
    product = session.scalar(
        select(Product).where(Product.id == product_id).options(*_product_options())
    )
    if product is not None:
        try:
            full_path = product_image_store.get_full_path(product.id)
            return FileResponse(
                full_path,
                media_type=product_image_store.content_type_for_path(full_path),
                filename=f"{product.name}{full_path.suffix}",
                headers=IMAGE_RESPONSE_HEADERS,
                content_disposition_type="inline",
            )
        except product_image_store.ProductImageStorageError:
            if product.image_url:
                from fastapi.responses import RedirectResponse
                return RedirectResponse(product.image_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Check if product is from Fridge or MealPrep
    fridge_service = FridgeIntegrationService()
    img_url = fridge_service.get_image_for_item_id(str(product_id), None)
    if img_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(img_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product image not found.",
    )
