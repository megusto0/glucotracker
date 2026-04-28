"""Meal and meal item REST endpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import (
    DeleteResponse,
    MealAcceptRequest,
    MealCreate,
    MealItemCreate,
    MealItemPatch,
    MealItemResponse,
    MealPageResponse,
    MealPatch,
    MealResponse,
    ProductResponse,
    RememberProductRequest,
)
from glucotracker.domain.drafts import accept_meal_draft, discard_meal_draft
from glucotracker.domain.entities import ItemSourceKind, MealSource, MealStatus
from glucotracker.domain.nutrients import (
    DEFAULT_NUTRIENT_DEFINITIONS,
    merge_nutrient_maps,
    normalize_nutrients_object,
    nutrient_unit,
    source_priority,
)
from glucotracker.domain.nutrition import (
    calculate_item_from_per_100g,
    calculate_meal_totals,
    compute_meal_confidence,
    validate_macros_consistency,
)
from glucotracker.infra.db.models import (
    Meal,
    MealItem,
    MealItemNutrient,
    NutrientDefinition,
    Pattern,
    Photo,
    Product,
    ProductAlias,
    utc_now,
)
from glucotracker.infra.db.product_merge import merge_duplicate_source_photo_products
from glucotracker.workers.daily_totals import schedule_and_recalculate

router = APIRouter(
    tags=["meals"],
    dependencies=[Depends(verify_token)],
)


def _meal_options() -> tuple:
    """Return eager-load options used by meal responses."""
    return (
        selectinload(Meal.items).selectinload(MealItem.nutrients),
        selectinload(Meal.items).selectinload(MealItem.pattern),
        selectinload(Meal.items).selectinload(MealItem.product),
        selectinload(Meal.photos),
    )


def _get_meal(session: SessionDep, meal_id: UUID) -> Meal:
    """Fetch a meal or raise 404."""
    meal = session.scalar(
        select(Meal).where(Meal.id == meal_id).options(*_meal_options())
    )
    if meal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found.",
        )
    return meal


def _get_item(session: SessionDep, item_id: UUID) -> MealItem:
    """Fetch a meal item or raise 404."""
    item = session.scalar(
        select(MealItem)
        .where(MealItem.id == item_id)
        .options(
            selectinload(MealItem.nutrients),
            selectinload(MealItem.pattern),
            selectinload(MealItem.product),
        )
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal item not found.",
        )
    return item


def _meal_response(session: SessionDep, meal_id: UUID) -> Meal:
    """Reload a meal with response relationships."""
    meal = _get_meal(session, meal_id)
    return meal


def _warning_payload(item: MealItem) -> list[dict[str, str | None]]:
    """Return generated nutrition warnings for an item."""
    return [asdict(warning) for warning in validate_macros_consistency(item)]


def _ensure_nutrient_definition(
    session: SessionDep,
    code: str,
    unit: str,
) -> None:
    """Ensure a nutrient code exists before creating item nutrient rows."""
    if session.get(NutrientDefinition, code) is not None:
        return
    if any(
        isinstance(obj, NutrientDefinition) and obj.code == code for obj in session.new
    ):
        return
    built_in = {
        definition["code"]: definition for definition in DEFAULT_NUTRIENT_DEFINITIONS
    }.get(code)
    session.add(
        NutrientDefinition(
            code=code,
            display_name=(
                built_in["display_name"]
                if built_in is not None
                else code.replace("_", " ").title()
            ),
            unit=built_in["unit"] if built_in is not None else unit,
            category=built_in["category"] if built_in is not None else "custom",
        )
    )


def _source_nutrients_for_item(
    session: SessionDep,
    item: MealItem,
) -> dict[str, dict]:
    """Return default nutrients supplied by pattern or product records."""
    nutrient_maps: list[dict[str, dict]] = []
    if item.pattern_id is not None:
        pattern = session.get(Pattern, item.pattern_id)
        if pattern is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pattern not found.",
            )
        nutrient_maps.append(
            normalize_nutrients_object(
                pattern.nutrients_json,
                default_source_kind="pattern",
            )
        )
    if item.product_id is not None:
        product = session.get(Product, item.product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )
        nutrient_maps.append(
            normalize_nutrients_object(
                product.nutrients_json,
                default_source_kind="product_db",
            )
        )
    return merge_nutrient_maps(*nutrient_maps)


def _apply_nutrients(
    session: SessionDep,
    item: MealItem,
    nutrients: dict[str, dict],
    *,
    replace: bool,
) -> None:
    """Apply normalized nutrient rows to an item with source priority rules."""
    existing = {nutrient.nutrient_code: nutrient for nutrient in item.nutrients}
    if replace:
        item.nutrients = []
        existing = {}

    for code, entry in nutrients.items():
        unit = str(entry.get("unit") or nutrient_unit(code))
        _ensure_nutrient_definition(session, code, unit)
        current = existing.get(code)
        if current is not None and source_priority(current.source_kind) > (
            source_priority(entry.get("source_kind"))
        ):
            continue
        if current is None:
            current = MealItemNutrient(
                nutrient_code=code,
                unit=unit,
                source_kind=str(entry["source_kind"]),
            )
            item.nutrients.append(current)
        current.amount = entry.get("amount")
        current.unit = unit
        current.source_kind = str(entry["source_kind"])
        current.confidence = entry.get("confidence")
        current.evidence_json = dict(entry.get("evidence_json") or {})
        current.assumptions_json = list(entry.get("assumptions_json") or [])
        current.updated_at = utc_now()


def _increment_usage_counters(session: SessionDep, item: MealItem) -> None:
    """Increment product or pattern usage counters referenced by an item."""
    used_at = utc_now()
    if item.product_id is not None:
        product = session.get(Product, item.product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )
        product.usage_count += 1
        product.last_used_at = used_at

    if item.pattern_id is not None:
        pattern = session.get(Pattern, item.pattern_id)
        if pattern is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pattern not found.",
            )
        pattern.usage_count += 1
        pattern.last_used_at = used_at


def _quantity_from_evidence(evidence: object) -> float:
    """Return a positive product serving quantity from item evidence."""
    if not isinstance(evidence, dict):
        return 1
    value = _as_float(evidence.get("quantity"))
    return value if value is not None and value > 0 else 1


def _product_default_values(product: Product) -> dict[str, float | None]:
    """Return one-serving product macro values from the saved product row."""
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
            "fiber_g": float(scaled["fiber_g"]),
            "kcal": float(scaled["kcal"]),
        }
    return {
        "carbs_g": product.carbs_per_serving,
        "protein_g": product.protein_per_serving,
        "fat_g": product.fat_per_serving,
        "fiber_g": product.fiber_per_serving,
        "kcal": product.kcal_per_serving,
    }


def _photo_file_url(photo_id: UUID | None) -> str | None:
    """Return the authenticated photo endpoint for stored meal photos."""
    return f"/photos/{photo_id}/file" if photo_id is not None else None


def _first_meal_photo_url(session: SessionDep, meal_id: UUID) -> str | None:
    """Return the first stored photo URL for a meal, if any."""
    photo_id = session.scalar(
        select(Photo.id)
        .where(Photo.meal_id == meal_id)
        .order_by(Photo.created_at.asc(), Photo.id.asc())
        .limit(1)
    )
    return _photo_file_url(photo_id)


def _product_image_url_from_history(
    session: SessionDep,
    product_id: UUID,
) -> str | None:
    """Return a previous source photo URL for a product missing an image."""
    photo_id = session.scalar(
        select(MealItem.photo_id)
        .where(
            MealItem.product_id == product_id,
            MealItem.photo_id.is_not(None),
        )
        .order_by(MealItem.created_at.desc(), MealItem.id.desc())
        .limit(1)
    )
    return _photo_file_url(photo_id)


def _apply_product_database_values(session: SessionDep, item: MealItem) -> None:
    """Populate product_db item macros from the backend product database."""
    if item.product_id is None or item.source_kind != ItemSourceKind.product_db:
        return
    product = session.get(Product, item.product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    quantity = _quantity_from_evidence(item.evidence)
    values = _product_default_values(product)
    for field, value in values.items():
        if value is not None:
            setattr(item, field, round(value * quantity, 1))
    if product.default_grams is not None:
        item.grams = round(product.default_grams * quantity, 1)
    if item.serving_text is None:
        item.serving_text = f"{quantity:g} шт"
    if item.brand is None:
        item.brand = product.brand
    if not product.image_url:
        product.image_url = _product_image_url_from_history(session, product.id)


def _build_item(
    payload: MealItemCreate,
    meal_id: UUID,
    session: SessionDep,
) -> MealItem:
    """Build a meal item ORM object from an API payload."""
    item = MealItem(meal_id=meal_id, **payload.model_dump(exclude={"nutrients"}))
    _apply_product_database_values(session, item)
    item.warnings = list(payload.warnings) + _warning_payload(item)
    source_nutrients = _source_nutrients_for_item(session, item)
    payload_nutrients = normalize_nutrients_object(
        payload.model_dump()["nutrients"],
        default_source_kind="manual",
    )
    _apply_nutrients(
        session,
        item,
        merge_nutrient_maps(source_nutrients, payload_nutrients),
        replace=True,
    )
    return item


def _apply_item_patch(
    session: SessionDep, item: MealItem, payload: MealItemPatch
) -> None:
    """Apply an item patch payload to an ORM object."""
    data = payload.model_dump(exclude_unset=True)
    nutrient_payload = data.pop("nutrients", None)
    for field, value in data.items():
        setattr(item, field, value)
    if "warnings" not in data:
        item.warnings = _warning_payload(item)
    if nutrient_payload is not None:
        _apply_nutrients(
            session,
            item,
            normalize_nutrients_object(nutrient_payload, default_source_kind="manual"),
            replace=False,
        )
    if "pattern_id" in data or "product_id" in data:
        _apply_nutrients(
            session,
            item,
            _source_nutrients_for_item(session, item),
            replace=False,
        )
    item.updated_at = utc_now()


def _recalculate_meal(meal: Meal) -> None:
    """Recalculate backend-owned meal totals."""
    totals = calculate_meal_totals(meal.items)
    meal.total_carbs_g = totals["total_carbs_g"]
    meal.total_protein_g = totals["total_protein_g"]
    meal.total_fat_g = totals["total_fat_g"]
    meal.total_fiber_g = totals["total_fiber_g"]
    meal.total_kcal = totals["total_kcal"]
    meal.confidence = compute_meal_confidence(meal.items)
    meal.updated_at = utc_now()


def _default_status(source: MealSource, requested: MealStatus | None) -> MealStatus:
    """Return default meal status for create requests."""
    if requested is not None:
        return requested
    if source in {MealSource.manual, MealSource.pattern}:
        return MealStatus.accepted
    return MealStatus.draft


def _as_float(value: object) -> float | None:
    """Normalize a JSON value into a float while preserving unknown as null."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _item_evidence(item: MealItem) -> dict:
    """Return an item's evidence as a mapping."""
    return item.evidence if isinstance(item.evidence, dict) else {}


def _nutrition_per_100g_from_evidence(item: MealItem) -> dict[str, float | None]:
    """Extract per-100g label facts from a label-calculated item."""
    evidence = _item_evidence(item)
    nutrition_per_100g = evidence.get("nutrition_per_100g")
    if isinstance(nutrition_per_100g, dict):
        return {
            "carbs_per_100g": _as_float(nutrition_per_100g.get("carbs_g")),
            "protein_per_100g": _as_float(nutrition_per_100g.get("protein_g")),
            "fat_per_100g": _as_float(nutrition_per_100g.get("fat_g")),
            "fiber_per_100g": _as_float(nutrition_per_100g.get("fiber_g")),
            "kcal_per_100g": _as_float(nutrition_per_100g.get("kcal")),
        }

    extracted_facts = evidence.get("extracted_facts")
    if isinstance(extracted_facts, dict):
        return {
            "carbs_per_100g": _as_float(extracted_facts.get("carbs_per_100g")),
            "protein_per_100g": _as_float(extracted_facts.get("protein_per_100g")),
            "fat_per_100g": _as_float(extracted_facts.get("fat_per_100g")),
            "fiber_per_100g": _as_float(extracted_facts.get("fiber_per_100g")),
            "kcal_per_100g": _as_float(extracted_facts.get("kcal_per_100g")),
        }
    return {}


def _default_label_serving_size(item: MealItem) -> float | None:
    """Return the best default package or serving size for a label item."""
    evidence = _item_evidence(item)
    for key in ("net_weight_per_unit_g", "total_weight_g"):
        value = _as_float(evidence.get(key))
        if value is not None:
            return value

    extracted_facts = evidence.get("extracted_facts")
    if isinstance(extracted_facts, dict):
        for key in (
            "visible_weight_g",
            "assumed_weight_g",
            "visible_volume_ml",
            "assumed_volume_ml",
        ):
            value = _as_float(extracted_facts.get(key))
            if value is not None:
                return value
    return item.grams


def _per_serving_label_values(
    item: MealItem,
    nutrition_per_100g: dict[str, float | None],
    default_grams: float | None,
) -> dict[str, float | None]:
    """Calculate per-serving product values from accepted label facts."""
    if default_grams is None or not any(
        value is not None for value in nutrition_per_100g.values()
    ):
        return {
            "carbs_per_serving": item.carbs_g,
            "protein_per_serving": item.protein_g,
            "fat_per_serving": item.fat_g,
            "fiber_per_serving": item.fiber_g,
            "kcal_per_serving": item.kcal,
        }

    scale = default_grams / 100
    return {
        "carbs_per_serving": (
            round(nutrition_per_100g["carbs_per_100g"] * scale, 1)
            if nutrition_per_100g.get("carbs_per_100g") is not None
            else None
        ),
        "protein_per_serving": (
            round(nutrition_per_100g["protein_per_100g"] * scale, 1)
            if nutrition_per_100g.get("protein_per_100g") is not None
            else None
        ),
        "fat_per_serving": (
            round(nutrition_per_100g["fat_per_100g"] * scale, 1)
            if nutrition_per_100g.get("fat_per_100g") is not None
            else None
        ),
        "fiber_per_serving": (
            round(nutrition_per_100g["fiber_per_100g"] * scale, 1)
            if nutrition_per_100g.get("fiber_per_100g") is not None
            else None
        ),
        "kcal_per_serving": (
            round(nutrition_per_100g["kcal_per_100g"] * scale)
            if nutrition_per_100g.get("kcal_per_100g") is not None
            else None
        ),
    }


def _label_product_aliases(item: MealItem) -> list[str]:
    """Return aliases that make a remembered label item searchable."""
    aliases = [item.name, item.name.casefold()]
    if item.brand:
        aliases.append(f"{item.brand} {item.name}")
        aliases.append(f"{item.brand} {item.name}".casefold())
    lowered = item.name.casefold()
    if "сырок" in lowered:
        aliases.extend(["сырок", "глазированный сырок", "творожный сырок"])
    if "бисквит" in lowered and ("сэндвич" in lowered or "сандвич" in lowered):
        aliases.extend(["бисквит", "бисквит-сэндвич", "сэндвич"])
    return aliases


def _merge_product_aliases(product: Product, aliases: list[str]) -> None:
    """Append new aliases without removing existing user-entered aliases."""
    existing = {alias.alias.casefold() for alias in product.aliases}
    for alias in aliases:
        normalized = alias.strip()
        if not normalized or normalized.casefold() in existing:
            continue
        product.aliases.append(ProductAlias(alias=normalized))
        existing.add(normalized.casefold())


def _product_response(product: Product) -> ProductResponse:
    """Convert a product row into an API response."""
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


def _nutrients_json_from_item(item: MealItem) -> dict:
    """Copy confirmed item nutrients into a remembered product record."""
    return {
        nutrient.nutrient_code: {
            "amount": nutrient.amount,
            "unit": nutrient.unit,
            "source_kind": nutrient.source_kind,
            "confidence": nutrient.confidence,
            "evidence_json": nutrient.evidence_json,
            "assumptions_json": nutrient.assumptions_json,
        }
        for nutrient in item.nutrients
    }


def _find_existing_label_product(session: SessionDep, item: MealItem) -> Product | None:
    """Find a product row that should be updated by an accepted label item."""
    if item.product_id is not None:
        product = session.scalar(
            select(Product)
            .where(Product.id == item.product_id)
            .options(selectinload(Product.aliases))
        )
        if product is not None:
            return product

    evidence = _item_evidence(item)
    barcode = evidence.get("identified_barcode")
    if barcode:
        product = session.scalar(
            select(Product)
            .where(Product.barcode == str(barcode))
            .options(selectinload(Product.aliases))
        )
        if product is not None:
            return product

    image_url = _photo_file_url(item.photo_id) or _first_meal_photo_url(
        session,
        item.meal_id,
    )
    if image_url:
        product = session.scalar(
            select(Product)
            .where(Product.image_url == image_url)
            .options(selectinload(Product.aliases))
        )
        if product is not None:
            return product

    if not item.name.strip():
        return None
    filters = [Product.name == item.name]
    if item.brand is None:
        filters.append(Product.brand.is_(None))
    else:
        filters.append(Product.brand == item.brand)
    return session.scalar(
        select(Product).where(*filters).options(selectinload(Product.aliases))
    )


def _remember_label_item_as_product(session: SessionDep, item: MealItem) -> None:
    """Persist an accepted label-calculated meal item into the product database."""
    is_label_item = item.source_kind == ItemSourceKind.label_calc or (
        item.calculation_method or ""
    ).startswith("label_")
    if not is_label_item or not item.name.strip():
        return

    nutrition_per_100g = _nutrition_per_100g_from_evidence(item)
    default_grams = _default_label_serving_size(item)
    serving_values = _per_serving_label_values(
        item,
        nutrition_per_100g,
        default_grams,
    )
    evidence = _item_evidence(item)
    barcode = evidence.get("identified_barcode")
    nutrients_json = _nutrients_json_from_item(item)
    image_url = _photo_file_url(item.photo_id) or _first_meal_photo_url(
        session,
        item.meal_id,
    )
    product = _find_existing_label_product(session, item)

    product_values = {
        "barcode": str(barcode) if barcode else None,
        "brand": item.brand,
        "name": item.name,
        "default_grams": default_grams,
        "default_serving_text": (
            "1 упаковка"
            if evidence.get("net_weight_per_unit_g") is not None
            else item.serving_text
        ),
        **nutrition_per_100g,
        **serving_values,
        "source_kind": "label_calc",
        "image_url": image_url,
        "nutrients_json": nutrients_json,
    }

    if product is None:
        product = Product(
            **{
                key: value
                for key, value in product_values.items()
                if value is not None or key in {"name", "source_kind", "nutrients_json"}
            }
        )
        session.add(product)
    else:
        for key, value in product_values.items():
            if value is not None or key in {"name", "source_kind"}:
                setattr(product, key, value)
        if image_url and not product.image_url:
            product.image_url = image_url
        if nutrients_json:
            product.nutrients_json = nutrients_json
        product.updated_at = utc_now()

    _merge_product_aliases(product, _label_product_aliases(item))
    session.flush()
    item.product_id = product.id
    merge_duplicate_source_photo_products(session, product)


def _remember_label_items_as_products(
    session: SessionDep,
    items: list[MealItem],
) -> None:
    """Persist accepted label-calculated items into the local product database."""
    for item in items:
        _remember_label_item_as_product(session, item)


@router.post(
    "/meals",
    response_model=MealResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createMeal",
)
def create_meal(payload: MealCreate, session: SessionDep) -> Meal:
    """Create a meal with optional inline items."""
    meal = Meal(
        eaten_at=payload.eaten_at,
        title=payload.title,
        note=payload.note,
        source=payload.source,
        status=_default_status(payload.source, payload.status),
    )
    session.add(meal)
    session.flush()

    meal.items = [_build_item(item, meal.id, session) for item in payload.items]
    for item in meal.items:
        _increment_usage_counters(session, item)
    _recalculate_meal(meal)
    schedule_and_recalculate(session, [meal.eaten_at])

    session.commit()
    return _meal_response(session, meal.id)


@router.get(
    "/meals",
    response_model=MealPageResponse,
    operation_id="listMeals",
)
def list_meals(
    session: SessionDep,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: str | None = None,
    status: MealStatus | None = None,
) -> MealPageResponse:
    """List meals with pagination and simple text search."""
    filters = []
    if from_ is not None:
        filters.append(Meal.eaten_at >= from_)
    if to is not None:
        filters.append(Meal.eaten_at <= to)
    if status is not None:
        filters.append(Meal.status == status)
    if q:
        term = f"%{q}%"
        filters.append(
            or_(
                Meal.title.ilike(term),
                Meal.note.ilike(term),
                Meal.items.any(
                    or_(
                        MealItem.name.ilike(term),
                        MealItem.brand.ilike(term),
                    )
                ),
            )
        )

    total = session.scalar(select(func.count(Meal.id)).where(*filters)) or 0
    meals = session.scalars(
        select(Meal)
        .where(*filters)
        .options(*_meal_options())
        .order_by(Meal.eaten_at.desc(), Meal.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return MealPageResponse(items=list(meals), total=total, limit=limit, offset=offset)


@router.get(
    "/meals/{meal_id}",
    response_model=MealResponse,
    operation_id="getMeal",
)
def get_meal(meal_id: UUID, session: SessionDep) -> Meal:
    """Return a meal with items and photos."""
    return _get_meal(session, meal_id)


@router.patch(
    "/meals/{meal_id}",
    response_model=MealResponse,
    operation_id="patchMeal",
)
def patch_meal(meal_id: UUID, payload: MealPatch, session: SessionDep) -> Meal:
    """Patch editable meal fields."""
    meal = _get_meal(session, meal_id)
    old_eaten_at = meal.eaten_at
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(meal, field, value)
    _recalculate_meal(meal)
    schedule_and_recalculate(session, [old_eaten_at, meal.eaten_at])

    session.commit()
    return _meal_response(session, meal.id)


@router.delete(
    "/meals/{meal_id}",
    response_model=DeleteResponse,
    operation_id="deleteMeal",
)
def delete_meal(meal_id: UUID, session: SessionDep) -> DeleteResponse:
    """Delete a meal and cascade its items and photos."""
    meal = _get_meal(session, meal_id)
    eaten_at = meal.eaten_at
    session.delete(meal)
    session.flush()
    schedule_and_recalculate(session, [eaten_at])
    session.commit()
    return DeleteResponse(deleted=True)


@router.post(
    "/meals/{meal_id}/items",
    response_model=MealItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="addMealItem",
)
def add_meal_item(
    meal_id: UUID,
    payload: MealItemCreate,
    session: SessionDep,
) -> MealItem:
    """Add an item to a meal and recalculate meal totals."""
    meal = _get_meal(session, meal_id)
    item = _build_item(payload, meal.id, session)
    meal.items.append(item)
    _increment_usage_counters(session, item)
    _recalculate_meal(meal)
    schedule_and_recalculate(session, [meal.eaten_at])

    session.commit()
    session.refresh(item)
    return item


@router.patch(
    "/meal_items/{item_id}",
    response_model=MealItemResponse,
    operation_id="patchMealItem",
)
def patch_meal_item(
    item_id: UUID,
    payload: MealItemPatch,
    session: SessionDep,
) -> MealItem:
    """Patch a meal item and recalculate its meal totals."""
    item = _get_item(session, item_id)
    meal = _get_meal(session, item.meal_id)
    changed_fields = payload.model_dump(exclude_unset=True)
    _apply_item_patch(session, item, payload)
    if "pattern_id" in changed_fields or "product_id" in changed_fields:
        _increment_usage_counters(session, item)
    _recalculate_meal(meal)
    schedule_and_recalculate(session, [meal.eaten_at])

    session.commit()
    session.refresh(item)
    return item


@router.post(
    "/meal_items/{item_id}/remember_product",
    response_model=ProductResponse,
    operation_id="rememberProductFromMealItem",
)
def remember_product_from_meal_item(
    item_id: UUID,
    payload: RememberProductRequest,
    session: SessionDep,
) -> ProductResponse:
    """Persist a confirmed label item into the local product database."""
    item = _get_item(session, item_id)
    _remember_label_item_as_product(session, item)
    if item.product_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meal item does not contain enough label data to remember.",
        )

    product = session.scalar(
        select(Product)
        .where(Product.id == item.product_id)
        .options(selectinload(Product.aliases))
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )
    _merge_product_aliases(product, payload.aliases)
    product.updated_at = utc_now()
    session.commit()
    return _product_response(product)


@router.delete(
    "/meal_items/{item_id}",
    response_model=DeleteResponse,
    operation_id="deleteMealItem",
)
def delete_meal_item(item_id: UUID, session: SessionDep) -> DeleteResponse:
    """Delete a meal item and recalculate its meal totals."""
    item = _get_item(session, item_id)
    meal = _get_meal(session, item.meal_id)
    meal.items = [existing for existing in meal.items if existing.id != item.id]
    session.flush()
    _recalculate_meal(meal)
    schedule_and_recalculate(session, [meal.eaten_at])

    session.commit()
    return DeleteResponse(deleted=True)


@router.put(
    "/meals/{meal_id}/items",
    response_model=MealResponse,
    operation_id="replaceMealItems",
)
def replace_meal_items(
    meal_id: UUID,
    payload: list[MealItemCreate],
    session: SessionDep,
) -> Meal:
    """Atomically replace all meal items and recalculate totals."""
    meal = _get_meal(session, meal_id)
    meal.items = [_build_item(item, meal.id, session) for item in payload]
    for position, item in enumerate(meal.items):
        item.position = position
        _increment_usage_counters(session, item)
    _recalculate_meal(meal)
    schedule_and_recalculate(session, [meal.eaten_at])

    session.commit()
    return _meal_response(session, meal.id)


@router.post(
    "/meals/{meal_id}/accept",
    response_model=MealResponse,
    operation_id="acceptMealDraft",
)
def accept_meal(
    meal_id: UUID,
    payload: MealAcceptRequest,
    session: SessionDep,
) -> Meal:
    """Accept a draft by atomically replacing Gemini-suggested items."""
    meal = _get_meal(session, meal_id)
    final_items = [_build_item(item, meal.id, session) for item in payload.items]
    _remember_label_items_as_products(session, final_items)
    for item in final_items:
        _increment_usage_counters(session, item)
    accept_meal_draft(meal, final_items)
    session.flush()
    schedule_and_recalculate(session, [meal.eaten_at])

    session.commit()
    return _meal_response(session, meal.id)


@router.post(
    "/meals/{meal_id}/discard",
    response_model=MealResponse,
    operation_id="discardMealDraft",
)
def discard_meal(meal_id: UUID, session: SessionDep) -> Meal:
    """Discard a meal draft."""
    meal = _get_meal(session, meal_id)
    eaten_at = meal.eaten_at
    discard_meal_draft(meal)
    schedule_and_recalculate(session, [eaten_at])

    session.commit()
    return _meal_response(session, meal.id)
