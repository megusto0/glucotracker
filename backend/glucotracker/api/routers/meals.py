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
    MealItemWeightReuseRequest,
    MealPageResponse,
    MealPatch,
    MealResponse,
    ProductResponse,
    RememberProductRequest,
)
from glucotracker.application.daily_totals import DailyTotalsService
from glucotracker.application.meal_drafts import MealDraftService
from glucotracker.application.product_memory import ProductMemoryService
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
    calculate_label_item_totals,
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
    utc_now,
)

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


def _label_item_weight_or_volume(
    facts: dict[str, object],
    *,
    use_assumed_size: bool,
) -> tuple[float | None, float | None]:
    """Return label weight/volume evidence for backend recalculation."""
    weight_key = "assumed_weight_g" if use_assumed_size else "visible_weight_g"
    volume_key = "assumed_volume_ml" if use_assumed_size else "visible_volume_ml"
    weight_g = _as_float(facts.get(weight_key)) or _as_float(
        facts.get("visible_weight_g")
    )
    volume_ml = _as_float(facts.get(volume_key)) or _as_float(
        facts.get("visible_volume_ml")
    )
    return weight_g, volume_ml


def _scale_item_from_per_100ml(
    facts: dict[str, object],
    volume_ml: float,
) -> dict[str, float]:
    """Scale per-100ml label facts to a concrete drink volume."""
    scale = volume_ml / 100.0
    carbs_g = (_as_float(facts.get("carbs_per_100ml")) or 0.0) * scale
    protein_g = (_as_float(facts.get("protein_per_100ml")) or 0.0) * scale
    fat_g = (_as_float(facts.get("fat_per_100ml")) or 0.0) * scale
    fiber_g = (_as_float(facts.get("fiber_per_100ml")) or 0.0) * scale
    kcal_per_100ml = _as_float(facts.get("kcal_per_100ml"))
    kcal = (
        kcal_per_100ml * scale
        if kcal_per_100ml is not None
        else carbs_g * 4 + protein_g * 4 + fat_g * 9
    )
    return {
        "grams": volume_ml,
        "carbs_g": carbs_g,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "fiber_g": fiber_g,
        "kcal": kcal,
    }


def _label_totals_from_evidence(item: MealItem) -> dict[str, float | None] | None:
    """Recalculate label item totals from evidence instead of trusting clients."""
    source_kind = getattr(item.source_kind, "value", item.source_kind)
    if source_kind != ItemSourceKind.label_calc.value and not (
        item.calculation_method or ""
    ).startswith("label_"):
        return None
    if not isinstance(item.evidence, dict):
        return None

    facts = item.evidence.get("extracted_facts")
    use_assumed_size = "assumed" in (item.calculation_method or "")
    if isinstance(facts, dict):
        weight_g, volume_ml = _label_item_weight_or_volume(
            facts,
            use_assumed_size=use_assumed_size,
        )
        if weight_g is not None and _as_float(facts.get("carbs_per_100g")) is not None:
            scaled = calculate_item_from_per_100g(
                _as_float(facts.get("carbs_per_100g")),
                _as_float(facts.get("protein_per_100g")),
                _as_float(facts.get("fat_per_100g")),
                _as_float(facts.get("fiber_per_100g")),
                _as_float(facts.get("kcal_per_100g")),
                weight_g,
            )
            return {
                "grams": float(scaled["grams"]),
                "carbs_g": float(scaled["carbs_g"]),
                "protein_g": float(scaled["protein_g"]),
                "fat_g": float(scaled["fat_g"]),
                "fiber_g": float(scaled["fiber_g"]),
                "kcal": float(scaled["kcal"]),
            }
        if (
            volume_ml is not None
            and _as_float(facts.get("carbs_per_100ml")) is not None
        ):
            return _scale_item_from_per_100ml(facts, volume_ml)

    nutrition_per_100g = item.evidence.get("nutrition_per_100g")
    if not isinstance(nutrition_per_100g, dict):
        return None

    total_weight_g = _as_float(item.evidence.get("total_weight_g"))
    net_weight_per_unit_g = _as_float(item.evidence.get("net_weight_per_unit_g"))
    count_detected = _as_float(item.evidence.get("count_detected"))
    if total_weight_g is not None:
        net_weight_per_unit_g = total_weight_g
        count_detected = 1
    if net_weight_per_unit_g is None or count_detected is None:
        return None

    totals = calculate_label_item_totals(
        nutrition_per_100g,
        net_weight_per_unit_g,
        int(count_detected),
    )
    return {
        "grams": totals["total_weight_g"],
        "carbs_g": totals["carbs_g"],
        "protein_g": totals["protein_g"],
        "fat_g": totals["fat_g"],
        "fiber_g": totals["fiber_g"],
        "kcal": totals["kcal"],
    }


def _apply_label_database_values(item: MealItem) -> None:
    """Keep accepted label items aligned with backend-owned label math."""
    values = _label_totals_from_evidence(item)
    if values is None:
        return
    for field, value in values.items():
        if value is not None:
            setattr(item, field, float(value))


def _build_item(
    payload: MealItemCreate,
    meal_id: UUID,
    session: SessionDep,
) -> MealItem:
    """Build a meal item ORM object from an API payload."""
    item = MealItem(meal_id=meal_id, **payload.model_dump(exclude={"nutrients"}))
    _apply_product_database_values(session, item)
    _apply_label_database_values(item)
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
    old_grams = item.grams
    new_grams = _as_float(data.get("grams")) if "grams" in data else None
    macro_fields = {"carbs_g", "protein_g", "fat_g", "fiber_g", "kcal"}
    should_rescale_weight = (
        "grams" in data
        and not macro_fields.intersection(data)
        and old_grams is not None
        and old_grams > 0
        and new_grams is not None
        and new_grams > 0
    )
    for field, value in data.items():
        setattr(item, field, value)
    if should_rescale_weight:
        _rescale_item_to_grams(item, old_grams, new_grams)
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


def _scale_macro(value: float | None, scale: float) -> float:
    """Scale an item macro for a new weight."""
    return round((value or 0) * scale, 1)


def _scaled_weight_evidence(
    source_item: MealItem,
    *,
    grams: float,
    scale: float,
) -> dict:
    """Build traceable evidence for a weight-based repeat."""
    source_evidence = (
        dict(source_item.evidence)
        if isinstance(source_item.evidence, dict)
        else {}
    )
    source_grams = float(source_item.grams or 0)
    per_100g = {
        "carbs_g": round(source_item.carbs_g / source_grams * 100, 3),
        "protein_g": round(source_item.protein_g / source_grams * 100, 3),
        "fat_g": round(source_item.fat_g / source_grams * 100, 3),
        "fiber_g": round(source_item.fiber_g / source_grams * 100, 3),
        "kcal": round(source_item.kcal / source_grams * 100, 3),
    }
    return {
        **source_evidence,
        "scaled_from_history": {
            "source_item_id": str(source_item.id),
            "source_meal_id": str(source_item.meal_id),
            "source_grams": source_grams,
            "target_grams": float(grams),
            "scale": round(scale, 6),
            "nutrition_per_100g": per_100g,
        },
    }


def _copy_scaled_nutrients(
    source_item: MealItem,
    new_item: MealItem,
    scale: float,
) -> None:
    """Copy optional nutrient rows from a source item with weight scaling."""
    for source in source_item.nutrients:
        amount = source.amount * scale if source.amount is not None else None
        new_item.nutrients.append(
            MealItemNutrient(
                nutrient_code=source.nutrient_code,
                amount=round(amount, 3) if amount is not None else None,
                unit=source.unit,
                source_kind=source.source_kind,
                confidence=source.confidence,
                evidence_json=dict(source.evidence_json or {}),
                assumptions_json=list(source.assumptions_json or []),
            )
        )


def _rescale_item_to_grams(item: MealItem, old_grams: float, new_grams: float) -> None:
    """Recalculate item macros after a backend-owned weight edit."""
    if old_grams <= 0 or new_grams <= 0:
        return

    evidence = dict(item.evidence) if isinstance(item.evidence, dict) else {}
    scaled_from_history = evidence.get("scaled_from_history")
    per_100g = (
        scaled_from_history.get("nutrition_per_100g")
        if isinstance(scaled_from_history, dict)
        else None
    )
    if isinstance(per_100g, dict):
        scale = new_grams / 100
        for source, target in [
            ("carbs_g", "carbs_g"),
            ("protein_g", "protein_g"),
            ("fat_g", "fat_g"),
            ("fiber_g", "fiber_g"),
            ("kcal", "kcal"),
        ]:
            value = _as_float(per_100g.get(source))
            if value is not None:
                setattr(item, target, round(value * scale, 1))
        source_grams = _as_float(scaled_from_history.get("source_grams"))
        scaled_from_history = {
            **scaled_from_history,
            "target_grams": float(new_grams),
            "scale": round(new_grams / source_grams, 6) if source_grams else None,
        }
        evidence["scaled_from_history"] = scaled_from_history
    else:
        scale = new_grams / old_grams
        item.carbs_g = _scale_macro(item.carbs_g, scale)
        item.protein_g = _scale_macro(item.protein_g, scale)
        item.fat_g = _scale_macro(item.fat_g, scale)
        item.fiber_g = _scale_macro(item.fiber_g, scale)
        item.kcal = _scale_macro(item.kcal, scale)
        evidence["rescaled_from_weight_edit"] = {
            "previous_grams": float(old_grams),
            "target_grams": float(new_grams),
            "scale": round(scale, 6),
        }

    nutrient_scale = new_grams / old_grams
    for nutrient in item.nutrients:
        if nutrient.amount is not None:
            nutrient.amount = round(nutrient.amount * nutrient_scale, 3)
            nutrient.updated_at = utc_now()

    item.serving_text = f"{new_grams:g} г"
    item.evidence = evidence
    if item.calculation_method != "scaled_from_history_per_100g":
        item.calculation_method = "weight_edit_backend_scale"
    assumption = f"Вес изменён вручную; backend пересчитал значения на {new_grams:g} г."
    assumptions = list(item.assumptions or [])
    if assumption not in assumptions:
        assumptions.append(assumption)
    item.assumptions = assumptions


def _meal_from_item_weight(
    source_item: MealItem,
    payload: MealItemWeightReuseRequest,
    session: SessionDep,
) -> Meal:
    """Create an accepted one-item meal by scaling a historical item by weight."""
    if source_item.grams is None or source_item.grams <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Source item has no positive grams to scale from.",
        )

    scale = payload.grams / source_item.grams
    source_meal = _get_meal(session, source_item.meal_id)
    item_name = source_item.name or source_meal.title or "Еда"
    meal = Meal(
        eaten_at=payload.eaten_at or utc_now(),
        title=item_name,
        note=f"Повтор по весу из записи {source_meal.id}",
        source=MealSource.manual,
        status=MealStatus.accepted,
    )
    session.add(meal)
    session.flush()
    source_photo_id = source_item.photo_id
    if source_photo_id is None and source_meal.photos:
        source_photo_id = source_meal.photos[0].id
    item = MealItem(
        meal_id=meal.id,
        name=item_name,
        brand=source_item.brand,
        grams=round(payload.grams, 1),
        serving_text=f"{payload.grams:g} г",
        carbs_g=_scale_macro(source_item.carbs_g, scale),
        protein_g=_scale_macro(source_item.protein_g, scale),
        fat_g=_scale_macro(source_item.fat_g, scale),
        fiber_g=_scale_macro(source_item.fiber_g, scale),
        kcal=_scale_macro(source_item.kcal, scale),
        confidence=source_item.confidence,
        confidence_reason=source_item.confidence_reason,
        source_kind=source_item.source_kind,
        calculation_method="scaled_from_history_per_100g",
        assumptions=[
            *list(source_item.assumptions or []),
            (
                f"Создано из прошлой позиции {source_item.grams:g} г; "
                f"пересчитано backend на {payload.grams:g} г."
            ),
        ],
        evidence=_scaled_weight_evidence(source_item, grams=payload.grams, scale=scale),
        warnings=[],
        pattern_id=source_item.pattern_id,
        product_id=source_item.product_id,
        photo_id=source_photo_id,
        position=0,
    )
    item.warnings = _warning_payload(item)
    _copy_scaled_nutrients(source_item, item, scale)
    meal.items = [item]
    _increment_usage_counters(session, item)
    _recalculate_meal(meal)
    DailyTotalsService(session).schedule_for_meal_times([meal.eaten_at])
    session.commit()
    return _meal_response(session, meal.id)


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
    DailyTotalsService(session).schedule_for_meal_times([meal.eaten_at])

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
    DailyTotalsService(session).schedule_for_meal_times([old_eaten_at, meal.eaten_at])

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
    DailyTotalsService(session).schedule_for_meal_times([eaten_at])
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
    DailyTotalsService(session).schedule_for_meal_times([meal.eaten_at])

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
    DailyTotalsService(session).schedule_for_meal_times([meal.eaten_at])

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
    product_memory = ProductMemoryService(session)
    product = product_memory.remember_item(item, payload.aliases)
    session.commit()
    return product_memory.response(product)


@router.post(
    "/meal_items/{item_id}/copy_by_weight",
    response_model=MealResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createMealFromMealItemWeight",
)
def create_meal_from_item_weight(
    item_id: UUID,
    payload: MealItemWeightReuseRequest,
    session: SessionDep,
) -> Meal:
    """Create a new meal from an existing item scaled to a target weight."""
    item = _get_item(session, item_id)
    return _meal_from_item_weight(item, payload, session)


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
    DailyTotalsService(session).schedule_for_meal_times([meal.eaten_at])

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
    DailyTotalsService(session).schedule_for_meal_times([meal.eaten_at])

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
    ProductMemoryService(session).remember_items(final_items)
    for item in final_items:
        _increment_usage_counters(session, item)
    MealDraftService(session).accept(meal, final_items)

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
    MealDraftService(session).discard(meal)

    session.commit()
    return _meal_response(session, meal.id)
