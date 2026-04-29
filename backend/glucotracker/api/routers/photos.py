"""Photo upload and Gemini estimation REST endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.routers.meals import (
    _build_item,
    _get_meal,
    _increment_usage_counters,
    _recalculate_meal,
)
from glucotracker.api.schemas import (
    AIRunResponse,
    ApplyEstimationRunRequest,
    ApplyEstimationRunResponse,
    DeleteResponse,
    EstimateCalculationBreakdown,
    EstimateCreatedDraftResponse,
    EstimateMacroBreakdown,
    EstimateMealRequest,
    EstimateMealResponse,
    EstimateSourcePhotoResponse,
    MealItemCreate,
    MealTotalsResponse,
    PhotoResponse,
    ReestimateMealRequest,
    ReestimateMealResponse,
)
from glucotracker.application.photo_estimation import (
    PhotoEstimationDependencies,
    PhotoEstimationService,
)
from glucotracker.domain.entities import (
    ItemSourceKind,
    MealSource,
    MealStatus,
    PhotoReferenceKind,
    PhotoScenario,
)
from glucotracker.domain.estimate_diff import compare_estimates
from glucotracker.domain.estimation import normalize_estimation_to_items
from glucotracker.domain.known_components import (
    KnownComponent,
)
from glucotracker.domain.nutrition import calculate_meal_totals
from glucotracker.infra.db.models import (
    AIRun,
    Meal,
    MealItem,
    Pattern,
    Photo,
    Product,
    utc_now,
)
from glucotracker.infra.gemini.client import (
    PHOTO_ESTIMATION_PROMPT_VERSION,
    GeminiClient,
    GeminiClientError,
    PhotoInput,
    get_gemini_client,
)
from glucotracker.infra.gemini.schemas import EstimationResult
from glucotracker.infra.storage import photo_store
from glucotracker.workers.daily_totals import schedule_and_recalculate

router = APIRouter(
    tags=["photos"],
    dependencies=[Depends(verify_token)],
)

GeminiClientDep = Annotated[GeminiClient, Depends(get_gemini_client)]
UploadFileDep = Annotated[UploadFile, File(description="JPEG, PNG, or WebP photo.")]


def _photo_estimation_service(
    session: SessionDep,
    gemini_client: GeminiClient,
) -> PhotoEstimationService:
    """Build the application service with router-local helper dependencies."""
    return PhotoEstimationService(
        session=session,
        gemini_client=gemini_client,
        dependencies=PhotoEstimationDependencies(
            get_meal=_get_meal,
            load_pattern_context=_load_pattern_context,
            load_product_context=_load_product_context,
            ordered_photos=_ordered_photos,
            photo_inputs=_photo_inputs,
            clean_context_note=_clean_context_note,
            ai_run_summary=_ai_run_summary,
            photo_reference_kind=_photo_reference_kind,
            photo_scenario=_photo_scenario,
            products_by_barcode=_products_by_barcode,
            load_known_components=_load_known_components,
            attach_user_context_to_items=_attach_user_context_to_items,
            set_photo_ids=_set_photo_ids,
            items_json=_items_json,
            save_suggested_items_as_drafts=_save_suggested_items_as_drafts,
            estimation_response=_estimation_response,
        ),
    )


def _get_photo(session: SessionDep, photo_id: UUID) -> Photo:
    """Fetch a photo or raise 404."""
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found.",
        )
    return photo


def _ordered_photos(photos: list[Photo]) -> list[Photo]:
    """Return photos in stable upload order."""
    return sorted(photos, key=lambda photo: (photo.created_at, str(photo.id)))


def _photo_inputs(photos: list[Photo]) -> list[PhotoInput]:
    """Build Gemini photo inputs from stored photo rows."""
    inputs: list[PhotoInput] = []
    for index, photo in enumerate(_ordered_photos(photos), start=1):
        if photo.content_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Photo is missing content type.",
            )
        full_path = photo_store.get_full_path(photo.path)
        if not full_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stored photo file is missing.",
            )
        inputs.append(
            PhotoInput(
                path=full_path,
                content_type=photo.content_type,
                photo_id=str(photo.id),
                filename=photo.original_filename,
                index=index,
            )
        )
    return inputs


def _serialize_pattern(pattern: Pattern) -> dict[str, Any]:
    """Serialize pattern context for Gemini."""
    return {
        "id": str(pattern.id),
        "prefix": pattern.prefix,
        "key": pattern.key,
        "display_name": pattern.display_name,
        "default_grams": pattern.default_grams,
        "default_carbs_g": pattern.default_carbs_g,
        "default_protein_g": pattern.default_protein_g,
        "default_fat_g": pattern.default_fat_g,
        "default_fiber_g": pattern.default_fiber_g,
        "default_kcal": pattern.default_kcal,
        "nutrients_json": pattern.nutrients_json,
    }


def _serialize_product(product: Product) -> dict[str, Any]:
    """Serialize product context for Gemini."""
    return {
        "id": str(product.id),
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
        "nutrients_json": product.nutrients_json,
    }


def _load_pattern_context(
    session: SessionDep,
    pattern_ids: list[UUID],
) -> list[dict[str, Any]]:
    """Load selected pattern context for Gemini."""
    if not pattern_ids:
        return []
    patterns = session.scalars(select(Pattern).where(Pattern.id.in_(pattern_ids))).all()
    return [_serialize_pattern(pattern) for pattern in patterns]


def _load_product_context(
    session: SessionDep,
    product_ids: list[UUID],
) -> list[dict[str, Any]]:
    """Load selected product context for Gemini."""
    if not product_ids:
        return []
    products = session.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    return [_serialize_product(product) for product in products]


def _products_by_barcode(
    session: SessionDep,
    result: EstimationResult,
) -> dict[str, Product]:
    """Load local products for barcodes identified by Gemini."""
    barcodes = {
        item.identified_barcode
        for item in result.items
        if item.identified_barcode is not None
    }
    if not barcodes:
        return {}
    products = session.scalars(
        select(Product).where(Product.barcode.in_(barcodes))
    ).all()
    return {product.barcode: product for product in products if product.barcode}


def _scale_optional_per_100g(
    value: float | None,
    grams: float | None,
) -> float | None:
    """Scale a per-100g value while preserving unknown as null."""
    if value is None or grams is None:
        return None
    return round(float(value) * (float(grams) / 100.0), 1)


def _product_component_macros(product: Product) -> dict[str, float | None] | None:
    """Return one-serving product values for a known component."""
    if product.default_grams is not None and any(
        value is not None
        for value in (
            product.carbs_per_100g,
            product.protein_per_100g,
            product.fat_per_100g,
            product.fiber_per_100g,
            product.kcal_per_100g,
        )
    ):
        return {
            "grams": product.default_grams,
            "carbs_g": _scale_optional_per_100g(
                product.carbs_per_100g,
                product.default_grams,
            ),
            "protein_g": _scale_optional_per_100g(
                product.protein_per_100g,
                product.default_grams,
            ),
            "fat_g": _scale_optional_per_100g(
                product.fat_per_100g,
                product.default_grams,
            ),
            "fiber_g": _scale_optional_per_100g(
                product.fiber_per_100g,
                product.default_grams,
            ),
            "kcal": _scale_optional_per_100g(
                product.kcal_per_100g,
                product.default_grams,
            ),
        }
    if not any(
        value is not None
        for value in (
            product.carbs_per_serving,
            product.protein_per_serving,
            product.fat_per_serving,
            product.fiber_per_serving,
            product.kcal_per_serving,
        )
    ):
        return None
    return {
        "grams": product.default_grams,
        "carbs_g": product.carbs_per_serving,
        "protein_g": product.protein_per_serving,
        "fat_g": product.fat_per_serving,
        "fiber_g": product.fiber_per_serving,
        "kcal": product.kcal_per_serving,
    }


def _is_component_record(
    *,
    name: str,
    aliases: list[str],
    source_kind: str | None = None,
    nutrients_json: dict[str, Any] | None = None,
) -> bool:
    """Return whether a database row should be offered as a known component."""
    nutrients_json = nutrients_json or {}
    marker = str(
        nutrients_json.get("component_type")
        or nutrients_json.get("kind")
        or source_kind
        or ""
    ).casefold()
    return marker in {
        "carb_anchor",
        "carb_base",
        "known_component",
        "macro_component",
        "personal_component",
        "component",
    }


def _load_known_components(session: SessionDep) -> list[KnownComponent]:
    """Load known local products and patterns for backend component adjustment."""
    components: list[KnownComponent] = []

    products = session.scalars(
        select(Product).options(selectinload(Product.aliases))
    ).all()
    for product in products:
        aliases = [alias.alias for alias in product.aliases]
        macros = _product_component_macros(product)
        if macros is None or not _is_component_record(
            name=product.name,
            aliases=aliases,
            source_kind=product.source_kind,
            nutrients_json=product.nutrients_json,
        ):
            continue
        components.append(
            KnownComponent(
                id=product.id,
                kind="product",
                display_name=product.name,
                aliases=aliases,
                grams=macros["grams"],
                carbs_g=macros["carbs_g"],
                protein_g=macros["protein_g"],
                fat_g=macros["fat_g"],
                fiber_g=macros["fiber_g"],
                kcal=macros["kcal"],
                nutrients_json=product.nutrients_json,
                token=f"product:{product.name}",
                source_kind="personal_component"
                if product.source_kind
                in {"carb_anchor", "carb_base", "known_component", "personal_component"}
                else "product_db",
            )
        )

    patterns = session.scalars(
        select(Pattern).options(selectinload(Pattern.aliases))
    ).all()
    for pattern in patterns:
        aliases = [alias.alias for alias in pattern.aliases]
        if pattern.is_archived or not _is_component_record(
            name=pattern.display_name,
            aliases=[pattern.key, *aliases],
            source_kind=pattern.source_confidence,
            nutrients_json=pattern.nutrients_json,
        ):
            continue
        components.append(
            KnownComponent(
                id=pattern.id,
                kind="pattern",
                display_name=pattern.display_name,
                aliases=[pattern.key, *aliases],
                grams=pattern.default_grams,
                carbs_g=pattern.default_carbs_g,
                protein_g=pattern.default_protein_g,
                fat_g=pattern.default_fat_g,
                fiber_g=pattern.default_fiber_g,
                kcal=pattern.default_kcal,
                nutrients_json=pattern.nutrients_json,
                token=f"{pattern.prefix}:{pattern.key}",
                source_kind="pattern",
            )
        )
    return components


def _photo_reference_kind(value: str) -> PhotoReferenceKind:
    """Map Gemini reference output to the stored photo enum."""
    try:
        return PhotoReferenceKind(value)
    except ValueError:
        return PhotoReferenceKind.none


def _photo_scenario(result: EstimationResult) -> PhotoScenario:
    """Map the first Gemini item scenario to the stored photo scenario."""
    if not result.items:
        return PhotoScenario.unknown
    scenario = result.items[0].scenario
    return {
        "LABEL_FULL": PhotoScenario.label_full,
        "SPLIT_LABEL_IDENTICAL_ITEMS": PhotoScenario.label_full,
        "LABEL_PARTIAL": PhotoScenario.label_partial,
        "PLATED": PhotoScenario.plated,
        "BARCODE": PhotoScenario.barcode,
        "UNKNOWN": PhotoScenario.unknown,
    }.get(scenario, PhotoScenario.unknown)


def _source_photo_ids(item: MealItemCreate) -> list[str]:
    """Return source photo ids stored in item evidence."""
    source_photo_ids = (item.evidence or {}).get("source_photo_ids")
    return (
        [str(value) for value in source_photo_ids]
        if isinstance(source_photo_ids, list)
        else []
    )


def _source_photo_indices(item: MealItemCreate) -> list[int]:
    """Return source photo indices stored in item evidence."""
    indices = (item.evidence or {}).get("source_photo_indices")
    if not isinstance(indices, list):
        return []
    parsed: list[int] = []
    for value in indices:
        try:
            parsed.append(int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _referenced_photo_ids(item: MealItemCreate, photos: list[Photo]) -> list[UUID]:
    """Resolve all source photos referenced by one suggested item."""
    ordered = _ordered_photos(photos)
    by_id = {str(photo.id): photo.id for photo in ordered}
    by_index = {index: photo.id for index, photo in enumerate(ordered, start=1)}
    resolved: list[UUID] = []
    primary_photo_id = (item.evidence or {}).get("primary_photo_id")
    if primary_photo_id is not None and str(primary_photo_id) in by_id:
        resolved.append(by_id[str(primary_photo_id)])
    for source_photo_id in _source_photo_ids(item):
        photo_id = by_id.get(source_photo_id)
        if photo_id is not None and photo_id not in resolved:
            resolved.append(photo_id)
    for source_photo_index in _source_photo_indices(item):
        photo_id = by_index.get(source_photo_index)
        if photo_id is not None and photo_id not in resolved:
            resolved.append(photo_id)
    if item.photo_id is not None and item.photo_id not in resolved:
        resolved.append(item.photo_id)
    return resolved


def _set_photo_ids(items: list[MealItemCreate], photos: list[Photo]) -> None:
    """Associate suggested items with their Gemini-referenced source photos."""
    if not photos:
        return
    ordered = _ordered_photos(photos)
    by_id = {str(photo.id): photo.id for photo in ordered}
    by_index = {index: photo.id for index, photo in enumerate(ordered, start=1)}
    for item in items:
        evidence = item.evidence or {}
        primary_photo_id = evidence.get("primary_photo_id")
        resolved = None
        if primary_photo_id is not None:
            resolved = by_id.get(str(primary_photo_id))
        if resolved is None:
            for source_photo_id in _source_photo_ids(item):
                resolved = by_id.get(source_photo_id)
                if resolved is not None:
                    break
        if resolved is None:
            for source_photo_index in _source_photo_indices(item):
                resolved = by_index.get(source_photo_index)
                if resolved is not None:
                    break
        if resolved is not None:
            item.photo_id = resolved
            continue
        item.warnings.append(
            {
                "code": "missing_source_photo",
                "message": "Позиция не связана с конкретным фото.",
                "field": "photo_id",
            }
        )


def _round_macro(value: object) -> float | None:
    """Round a macro value for display while preserving unknown as null."""
    if value is None:
        return None
    return round(float(value), 1)


def _round_kcal(value: object) -> float | None:
    """Round kcal to the nearest integer for display."""
    if value is None:
        return None
    return float(round(float(value)))


def _clean_context_note(value: str | None) -> str | None:
    """Normalize optional user context for Gemini and audit storage."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _attach_user_context_to_items(
    items: list[MealItemCreate],
    context_note: str | None,
) -> None:
    """Record user-provided context as item evidence for review UI."""
    if context_note is None:
        return
    label = f"Контекст пользователя: {context_note}"
    for item in items:
        evidence = dict(item.evidence or {})
        evidence_text = evidence.get("evidence_text")
        rows = list(evidence_text) if isinstance(evidence_text, list) else []
        if label not in rows:
            rows.insert(0, label)
        evidence["evidence_text"] = rows
        evidence["user_context_note"] = context_note
        item.evidence = evidence


def _nutrition_value(nutrition: dict[str, Any], key: str) -> float | None:
    """Read a numeric nutrition value from an evidence mapping."""
    value = nutrition.get(key)
    return None if value is None else float(value)


def _macro_breakdown_from_item(item: MealItemCreate) -> EstimateMacroBreakdown:
    """Return total item macro values for calculation display."""
    return EstimateMacroBreakdown(
        carbs_g=_round_macro(item.carbs_g),
        protein_g=_round_macro(item.protein_g),
        fat_g=_round_macro(item.fat_g),
        fiber_g=_round_macro(item.fiber_g),
        kcal=_round_kcal(item.kcal),
    )


def _macro_breakdown_from_per_100g(
    nutrition: dict[str, Any],
) -> EstimateMacroBreakdown | None:
    """Return visible per-100g label facts when available."""
    if not nutrition:
        return None
    return EstimateMacroBreakdown(
        carbs_g=_round_macro(_nutrition_value(nutrition, "carbs_g")),
        protein_g=_round_macro(_nutrition_value(nutrition, "protein_g")),
        fat_g=_round_macro(_nutrition_value(nutrition, "fat_g")),
        fiber_g=_round_macro(_nutrition_value(nutrition, "fiber_g")),
        kcal=_round_kcal(_nutrition_value(nutrition, "kcal")),
    )


def _per_unit_breakdown(
    item: MealItemCreate,
    *,
    nutrition_per_100g: dict[str, Any],
    count_detected: int | None,
    net_weight_per_unit_g: float | None,
) -> EstimateMacroBreakdown | None:
    """Return values for one countable package/unit when known."""
    if net_weight_per_unit_g is not None and nutrition_per_100g:
        scale = net_weight_per_unit_g / 100
        return EstimateMacroBreakdown(
            carbs_g=_round_macro(
                _nutrition_value(nutrition_per_100g, "carbs_g") * scale
                if _nutrition_value(nutrition_per_100g, "carbs_g") is not None
                else None
            ),
            protein_g=_round_macro(
                _nutrition_value(nutrition_per_100g, "protein_g") * scale
                if _nutrition_value(nutrition_per_100g, "protein_g") is not None
                else None
            ),
            fat_g=_round_macro(
                _nutrition_value(nutrition_per_100g, "fat_g") * scale
                if _nutrition_value(nutrition_per_100g, "fat_g") is not None
                else None
            ),
            fiber_g=_round_macro(
                _nutrition_value(nutrition_per_100g, "fiber_g") * scale
                if _nutrition_value(nutrition_per_100g, "fiber_g") is not None
                else None
            ),
            kcal=_round_kcal(
                _nutrition_value(nutrition_per_100g, "kcal") * scale
                if _nutrition_value(nutrition_per_100g, "kcal") is not None
                else None
            ),
        )
    if count_detected and count_detected > 1:
        return EstimateMacroBreakdown(
            carbs_g=_round_macro(item.carbs_g / count_detected),
            protein_g=_round_macro(item.protein_g / count_detected),
            fat_g=_round_macro(item.fat_g / count_detected),
            fiber_g=_round_macro(item.fiber_g / count_detected),
            kcal=_round_kcal(item.kcal / count_detected),
        )
    return None


def _formula_step(
    label: str,
    per_100g: float | None,
    total_weight_g: float | None,
    total: float | None,
    unit: str,
) -> str | None:
    """Build one readable calculation formula line."""
    if per_100g is None or total_weight_g is None or total is None:
        return None
    displayed_total = round(total) if unit == "ккал" else round(total, 1)
    return (
        f"{label}: {per_100g:g} × {total_weight_g:g} / 100 = {displayed_total:g} {unit}"
    )


def _package_word(count: int) -> str:
    """Return the Russian package word for a count."""
    if count % 10 == 1 and count % 100 != 11:
        return "упаковка"
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return "упаковки"
    return "упаковок"


def _calculation_steps(
    item: MealItemCreate,
    *,
    count_detected: int | None,
    net_weight_per_unit_g: float | None,
    total_weight_g: float | None,
    nutrition_per_100g: dict[str, Any],
) -> list[str]:
    """Build Russian calculation history lines for a suggested item."""
    steps: list[str] = []
    if net_weight_per_unit_g is not None:
        steps.append(f"1 упаковка = {net_weight_per_unit_g:g} г")
    if count_detected is not None and total_weight_g is not None:
        steps.append(
            f"{count_detected:g} {_package_word(count_detected)} = {total_weight_g:g} г"
        )
    if nutrition_per_100g and total_weight_g is not None:
        candidates = [
            _formula_step(
                "углеводы",
                _nutrition_value(nutrition_per_100g, "carbs_g"),
                total_weight_g,
                item.carbs_g,
                "г",
            ),
            _formula_step(
                "белки",
                _nutrition_value(nutrition_per_100g, "protein_g"),
                total_weight_g,
                item.protein_g,
                "г",
            ),
            _formula_step(
                "жиры",
                _nutrition_value(nutrition_per_100g, "fat_g"),
                total_weight_g,
                item.fat_g,
                "г",
            ),
            _formula_step(
                "клетчатка",
                _nutrition_value(nutrition_per_100g, "fiber_g"),
                total_weight_g,
                item.fiber_g,
                "г",
            ),
            _formula_step(
                "ккал",
                _nutrition_value(nutrition_per_100g, "kcal"),
                total_weight_g,
                item.kcal,
                "ккал",
            ),
        ]
        steps.extend(step for step in candidates if step is not None)
    return steps


def _calculation_breakdowns(
    suggested_items: list[MealItemCreate],
) -> list[EstimateCalculationBreakdown]:
    """Build backend-prepared calculation evidence for suggested items."""
    breakdowns: list[EstimateCalculationBreakdown] = []
    for position, item in enumerate(suggested_items):
        evidence = item.evidence or {}
        nutrition_per_100g = evidence.get("nutrition_per_100g") or {}
        count_detected = evidence.get("count_detected")
        net_weight_per_unit_g = evidence.get("net_weight_per_unit_g")
        total_weight_g = evidence.get("total_weight_g") or item.grams
        count_value = int(count_detected) if count_detected is not None else None
        net_weight_value = (
            float(net_weight_per_unit_g) if net_weight_per_unit_g is not None else None
        )
        total_weight_value = (
            float(total_weight_g) if total_weight_g is not None else None
        )
        nutrition_map = (
            dict(nutrition_per_100g) if isinstance(nutrition_per_100g, dict) else {}
        )
        breakdowns.append(
            EstimateCalculationBreakdown(
                position=position,
                name=item.name,
                count_detected=count_value,
                net_weight_per_unit_g=net_weight_value,
                total_weight_g=total_weight_value,
                nutrition_per_100g=_macro_breakdown_from_per_100g(nutrition_map),
                calculated_per_unit=_per_unit_breakdown(
                    item,
                    nutrition_per_100g=nutrition_map,
                    count_detected=count_value,
                    net_weight_per_unit_g=net_weight_value,
                ),
                calculated_total=_macro_breakdown_from_item(item),
                calculation_steps=_calculation_steps(
                    item,
                    count_detected=count_value,
                    net_weight_per_unit_g=net_weight_value,
                    total_weight_g=total_weight_value,
                    nutrition_per_100g=nutrition_map,
                ),
                evidence=[str(entry) for entry in evidence.get("evidence_text", [])],
                assumptions=[str(entry) for entry in item.assumptions],
            )
        )
    return breakdowns


def _draft_title(item: MealItemCreate) -> str:
    """Return a journal title for one estimated draft item."""
    evidence = item.evidence or {}
    count_detected = evidence.get("count_detected")
    try:
        count_value = int(count_detected) if count_detected is not None else None
    except (TypeError, ValueError):
        count_value = None
    if count_value is not None and count_value > 1:
        return f"{item.name} ×{count_value}"
    return item.name or "Еда по фото"


def _item_with_original_estimate(
    item: MealItemCreate,
    original_item: object | None,
) -> MealItemCreate:
    """Attach raw per-item Gemini output to evidence for persisted review."""
    evidence = dict(item.evidence or {})
    if original_item is not None and hasattr(original_item, "model_dump"):
        evidence.setdefault(
            "original_estimate_json",
            original_item.model_dump(mode="json"),
        )
    return item.model_copy(update={"evidence": evidence})


def _created_draft_response(
    meal: Meal,
    item: MealItemCreate,
) -> EstimateCreatedDraftResponse:
    """Return the compact batch review row for one created draft."""
    source_photo_id = item.photo_id
    return EstimateCreatedDraftResponse(
        meal_id=meal.id,
        title=meal.title or item.name,
        source_photo_id=source_photo_id,
        thumbnail_url=f"/photos/{source_photo_id}/file" if source_photo_id else None,
        item=item,
        totals=MealTotalsResponse(**calculate_meal_totals([item])),
    )


def _move_source_photos_to_draft(
    *,
    item: MealItemCreate,
    meal: Meal,
    photos: list[Photo],
    moved_photo_ids: set[UUID],
) -> None:
    """Move unclaimed source photo rows to the draft meal for their item."""
    for photo_id in _referenced_photo_ids(item, photos):
        if photo_id in moved_photo_ids:
            continue
        photo = next(
            (candidate for candidate in photos if candidate.id == photo_id), None
        )
        if photo is None:
            continue
        photo.meal_id = meal.id
        moved_photo_ids.add(photo_id)


def _save_suggested_items_as_drafts(
    *,
    source_meal: Meal,
    suggested_items: list[MealItemCreate],
    result: EstimationResult,
    photos: list[Photo],
    session: SessionDep,
) -> list[EstimateCreatedDraftResponse]:
    """Persist estimated items as one editable draft journal row per item."""
    created: list[EstimateCreatedDraftResponse] = []
    moved_photo_ids: set[UUID] = set()
    original_items = list(result.items)

    for position, suggested_item in enumerate(suggested_items):
        item = _item_with_original_estimate(
            suggested_item,
            original_items[position] if position < len(original_items) else None,
        )
        draft_meal = source_meal
        if position > 0:
            draft_meal = Meal(
                eaten_at=source_meal.eaten_at,
                title=_draft_title(item),
                note=source_meal.note,
                status=MealStatus.draft,
                source=MealSource.photo,
            )
            session.add(draft_meal)
            session.flush()
        else:
            draft_meal.title = _draft_title(item)
            draft_meal.status = MealStatus.draft
            draft_meal.source = MealSource.photo

        item.position = 0
        draft_meal.items = [_build_item(item, draft_meal.id, session)]
        _move_source_photos_to_draft(
            item=item,
            meal=draft_meal,
            photos=photos,
            moved_photo_ids=moved_photo_ids,
        )
        for draft_item in draft_meal.items:
            _increment_usage_counters(session, draft_item)
        _recalculate_meal(draft_meal)
        created.append(_created_draft_response(draft_meal, item))

    if created and photos:
        fallback_meal_id = created[0].meal_id
        for photo in photos:
            if photo.id not in moved_photo_ids:
                photo.meal_id = fallback_meal_id

    return created


def _source_photo_response(photo: Photo, index: int) -> EstimateSourcePhotoResponse:
    """Return photo URLs that generated frontends can resolve through the API."""
    url = f"/photos/{photo.id}/file"
    return EstimateSourcePhotoResponse(
        id=photo.id,
        index=index,
        url=url,
        thumbnail_url=url,
        original_filename=photo.original_filename,
    )


def _estimation_warnings(
    photos: list[Photo],
    suggested_items: list[MealItemCreate],
    result: EstimationResult,
) -> list[str]:
    """Return user-visible warnings about suspicious multi-photo estimates."""
    warnings = list(result.image_quality_warnings)
    if len(photos) > 1 and len(suggested_items) == 1:
        evidence = suggested_items[0].evidence or {}
        if not evidence.get("evidence_is_split_across_identical_items"):
            warnings.append(
                "Загружено несколько фото, найден один объект. Проверьте результат."
            )
    for item in suggested_items:
        if not _source_photo_ids(item) and not _source_photo_indices(item):
            warnings.append("Позиция не связана с конкретным фото.")
            break
    return list(dict.fromkeys(warnings))


def _estimation_response(
    meal: Meal,
    suggested_items: list[MealItemCreate],
    result: EstimationResult,
    ai_run_id: UUID,
    *,
    source_photos: list[Photo] | None = None,
    created_drafts: list[EstimateCreatedDraftResponse] | None = None,
) -> EstimateMealResponse:
    """Build a stable estimation response."""
    totals = MealTotalsResponse(**calculate_meal_totals(suggested_items))
    response_photos = _ordered_photos(source_photos or meal.photos)
    return EstimateMealResponse(
        meal_id=meal.id,
        source_photos=[
            _source_photo_response(photo, index)
            for index, photo in enumerate(response_photos, start=1)
        ],
        suggested_items=suggested_items,
        suggested_totals=totals,
        calculation_breakdowns=_calculation_breakdowns(suggested_items),
        gemini_notes=result.overall_notes,
        image_quality_warnings=_estimation_warnings(
            _ordered_photos(meal.photos),
            suggested_items,
            result,
        ),
        reference_detected=_photo_reference_kind(result.reference_object_detected),
        ai_run_id=ai_run_id,
        raw_gemini_response=result.model_dump(mode="json"),
        created_drafts=created_drafts or [],
    )


def _item_create_from_orm(item: MealItem) -> MealItemCreate:
    """Convert a stored meal item into an API item payload."""
    return MealItemCreate(
        name=item.name,
        brand=item.brand,
        grams=item.grams,
        serving_text=item.serving_text,
        carbs_g=item.carbs_g,
        protein_g=item.protein_g,
        fat_g=item.fat_g,
        fiber_g=item.fiber_g,
        kcal=item.kcal,
        confidence=item.confidence,
        confidence_reason=item.confidence_reason,
        source_kind=item.source_kind,
        calculation_method=item.calculation_method,
        assumptions=list(item.assumptions or []),
        evidence=dict(item.evidence or {}),
        warnings=list(item.warnings or []),
        pattern_id=item.pattern_id,
        product_id=item.product_id,
        photo_id=item.photo_id,
        position=item.position,
    )


def _items_json(items: list[MealItemCreate]) -> list[dict[str, Any]]:
    """Serialize item payloads for AI run history."""
    return [item.model_dump(mode="json") for item in items]


def _totals_response(items: list[MealItemCreate]) -> MealTotalsResponse:
    """Return backend total response for item payloads."""
    return MealTotalsResponse(**calculate_meal_totals(items))


def _latest_ai_model(session: SessionDep, meal_id: UUID) -> str | None:
    """Return the latest successful model used for a meal when known."""
    run = session.scalar(
        select(AIRun)
        .where(AIRun.meal_id == meal_id, AIRun.status == "success")
        .order_by(AIRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    return run.model_used or run.model


def _manual_override_warnings(meal: Meal) -> list[str]:
    """Return warnings when current data may include user corrections."""
    for item in meal.items:
        evidence = item.evidence if isinstance(item.evidence, dict) else {}
        method = (item.calculation_method or "").casefold()
        if (
            item.source_kind == ItemSourceKind.manual
            or "manual" in method
            or "override" in method
            or bool(evidence.get("manual_override"))
            or bool(evidence.get("correction"))
        ):
            return ["Есть ручные исправления. Новая оценка может их заменить."]
    return []


def _ai_run_summary(gemini_client: GeminiClient) -> dict[str, Any]:
    """Return common model routing metadata for AI run request summaries."""
    return {
        "model_requested": getattr(gemini_client, "last_requested_model", None)
        or gemini_client.model,
        "model_used": getattr(gemini_client, "last_used_model", None)
        or gemini_client.model,
        "fallback_used": getattr(gemini_client, "last_fallback_used", False),
        "attempts": getattr(gemini_client, "last_attempts", []),
        "error_history": getattr(gemini_client, "last_error_history", []),
        "latency_ms": getattr(gemini_client, "last_latency_ms", None),
        "model_attempts": getattr(gemini_client, "last_model_attempts", []),
        "routing_reason": getattr(gemini_client, "last_routing_reason", None),
    }


@router.post(
    "/meals/{meal_id}/reestimate",
    response_model=ReestimateMealResponse,
    operation_id="reestimateMealPhotos",
)
def reestimate_meal_photos(
    meal_id: UUID,
    payload: ReestimateMealRequest,
    session: SessionDep,
    gemini_client: GeminiClientDep,
) -> ReestimateMealResponse:
    """Re-run photo estimation for an existing meal without overwriting it."""
    meal = _get_meal(session, meal_id)
    if not meal.photos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У этой записи нет фото для переоценки",
        )

    ordered_photos = _ordered_photos(meal.photos)
    photo_inputs = _photo_inputs(ordered_photos)
    model_override = None if payload.model == "default" else payload.model

    try:
        result = gemini_client.estimate_photos(
            photo_inputs,
            patterns_context=[],
            products_context=[],
            model_override=model_override,
        )
    except GeminiClientError as exc:
        ai_summary = _ai_run_summary(gemini_client)
        failed_run = AIRun(
            meal_id=meal.id,
            model=ai_summary["model_used"],
            prompt_version=PHOTO_ESTIMATION_PROMPT_VERSION,
            provider="gemini",
            model_requested=ai_summary["model_requested"],
            model_used=ai_summary["model_used"],
            fallback_used=ai_summary["fallback_used"],
            status="failed",
            request_type="reestimate",
            source_photo_ids=[str(photo.id) for photo in ordered_photos],
            error_history_json=ai_summary["error_history"],
            request_summary={
                "photo_ids": [str(photo.id) for photo in ordered_photos],
                "requested_model": payload.model,
                **ai_summary,
            },
            response_raw={"error": str(exc)},
        )
        session.add(failed_run)
        session.commit()
        raise HTTPException(
            status_code=getattr(
                exc,
                "http_status_code",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ),
            detail=str(exc),
        ) from exc

    suggested_items = normalize_estimation_to_items(
        result,
        products_by_barcode=_products_by_barcode(session, result),
        known_components=_load_known_components(session),
    )
    _set_photo_ids(suggested_items, ordered_photos)
    current_items = [_item_create_from_orm(item) for item in meal.items]
    warnings = _manual_override_warnings(meal)
    ai_summary = _ai_run_summary(gemini_client)
    comparison = compare_estimates(
        current_items,
        suggested_items,
        current_model=_latest_ai_model(session, meal.id),
        proposed_model=ai_summary["model_used"],
        warnings=warnings,
    )

    result_raw = result.model_dump(mode="json")
    ai_run = AIRun(
        meal_id=meal.id,
        model=ai_summary["model_used"],
        prompt_version=PHOTO_ESTIMATION_PROMPT_VERSION,
        provider="gemini",
        model_requested=ai_summary["model_requested"],
        model_used=ai_summary["model_used"],
        fallback_used=ai_summary["fallback_used"],
        status="success",
        request_type="reestimate",
        source_photo_ids=[str(photo.id) for photo in ordered_photos],
        normalized_items_json=_items_json(suggested_items),
        error_history_json=ai_summary["error_history"],
        request_summary={
            "photo_ids": [str(photo.id) for photo in ordered_photos],
            "requested_model": payload.model,
            **ai_summary,
        },
        response_raw=result_raw,
    )
    session.add(ai_run)
    session.flush()

    response = ReestimateMealResponse(
        meal_id=meal.id,
        current_items=current_items,
        proposed_items=suggested_items,
        current_totals=_totals_response(current_items),
        proposed_totals=_totals_response(suggested_items),
        diff=comparison,
        ai_run_id=ai_run.id,
        model_used=ai_summary["model_used"],
        fallback_used=ai_summary["fallback_used"],
        image_quality_warnings=result.image_quality_warnings,
    )
    session.commit()
    return response


@router.post(
    "/meals/{meal_id}/apply_estimation_run/{run_id}",
    response_model=ApplyEstimationRunResponse,
    operation_id="applyEstimationRun",
)
def apply_estimation_run(
    meal_id: UUID,
    run_id: UUID,
    payload: ApplyEstimationRunRequest,
    session: SessionDep,
) -> ApplyEstimationRunResponse:
    """Apply a stored re-estimation proposal to the current meal or a draft."""
    meal = _get_meal(session, meal_id)
    run = session.get(AIRun, run_id)
    if run is None or run.meal_id != meal.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI estimation run not found.",
        )
    if run.status != "success" or not run.normalized_items_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI estimation run has no proposal to apply.",
        )

    proposed_items = [
        MealItemCreate.model_validate(item) for item in run.normalized_items_json
    ]
    old_eaten_at = meal.eaten_at
    if payload.apply_mode == "replace_current":
        meal.items = [_build_item(item, meal.id, session) for item in proposed_items]
        for position, item in enumerate(meal.items):
            item.position = position
            _increment_usage_counters(session, item)
        _recalculate_meal(meal)
        schedule_and_recalculate(session, [old_eaten_at, meal.eaten_at])
        target_meal = meal
    else:
        title = (
            proposed_items[0].name
            if len(proposed_items) == 1
            else f"Переоценка · {len(proposed_items)} позиции"
        )
        draft = Meal(
            eaten_at=meal.eaten_at,
            title=title,
            note=meal.note,
            status=MealStatus.draft,
            source=MealSource.photo,
        )
        session.add(draft)
        session.flush()
        draft.items = [_build_item(item, draft.id, session) for item in proposed_items]
        for position, item in enumerate(draft.items):
            item.position = position
            _increment_usage_counters(session, item)
        for photo in _ordered_photos(meal.photos):
            session.add(
                Photo(
                    meal_id=draft.id,
                    path=photo.path,
                    original_filename=photo.original_filename,
                    content_type=photo.content_type,
                    taken_at=photo.taken_at,
                    scenario=photo.scenario,
                    has_reference_object=photo.has_reference_object,
                    reference_kind=photo.reference_kind,
                    gemini_response_raw=photo.gemini_response_raw,
                )
            )
        _recalculate_meal(draft)
        target_meal = draft

    run.promoted_at = utc_now()
    run.promoted_by_action = payload.apply_mode
    session.commit()
    return ApplyEstimationRunResponse(
        apply_mode=payload.apply_mode,
        meal=_get_meal(session, target_meal.id),
        ai_run_id=run.id,
    )


@router.get(
    "/meals/{meal_id}/ai_runs",
    response_model=list[AIRunResponse],
    operation_id="listMealAiRuns",
)
def list_meal_ai_runs(meal_id: UUID, session: SessionDep) -> list[AIRun]:
    """Return AI estimation history for one meal."""
    _get_meal(session, meal_id)
    return list(
        session.scalars(
            select(AIRun)
            .where(AIRun.meal_id == meal_id)
            .order_by(AIRun.created_at.desc())
        ).all()
    )


@router.post(
    "/meals/{meal_id}/photos",
    response_model=PhotoResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadMealPhoto",
)
def upload_meal_photo(
    meal_id: UUID,
    session: SessionDep,
    file: UploadFileDep,
) -> Photo:
    """Upload a JPEG, PNG, or WebP photo for a meal."""
    _get_meal(session, meal_id)
    try:
        rel_path = photo_store.save_upload(file)
    except photo_store.PhotoStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    photo = Photo(
        id=UUID(Path(rel_path).stem),
        meal_id=meal_id,
        path=rel_path,
        original_filename=file.filename,
        content_type=file.content_type,
    )
    session.add(photo)
    try:
        session.commit()
    except Exception:
        photo_store.delete(rel_path)
        raise
    return photo


@router.get(
    "/photos/{photo_id}/file",
    operation_id="getPhotoFile",
)
def get_photo_file(photo_id: UUID, session: SessionDep) -> FileResponse:
    """Stream the stored image bytes for a photo."""
    photo = _get_photo(session, photo_id)
    full_path = photo_store.get_full_path(photo.path)
    if not full_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo file not found.",
        )
    return FileResponse(
        full_path,
        media_type=photo.content_type,
        filename=photo.original_filename,
    )


@router.delete(
    "/photos/{photo_id}",
    response_model=DeleteResponse,
    operation_id="deletePhoto",
)
def delete_photo(photo_id: UUID, session: SessionDep) -> DeleteResponse:
    """Delete a photo row and its stored file."""
    photo = _get_photo(session, photo_id)
    path = photo.path
    for item in session.scalars(select(MealItem).where(MealItem.photo_id == photo.id)):
        item.photo_id = None
    session.delete(photo)
    session.commit()
    photo_store.delete(path)
    return DeleteResponse(deleted=True)


@router.post(
    "/meals/{meal_id}/estimate",
    response_model=EstimateMealResponse,
    operation_id="estimateMealPhotos",
)
def estimate_meal_photos(
    meal_id: UUID,
    payload: EstimateMealRequest,
    session: SessionDep,
    gemini_client: GeminiClientDep,
) -> EstimateMealResponse:
    """Estimate draft items from meal photos without saving them."""
    return _photo_estimation_service(session, gemini_client).estimate(
        meal_id=meal_id,
        payload=payload,
        save_draft=False,
    )


@router.post(
    "/meals/{meal_id}/estimate_and_save_draft",
    response_model=EstimateMealResponse,
    operation_id="estimateAndSaveMealDraft",
)
def estimate_and_save_meal_draft(
    meal_id: UUID,
    payload: EstimateMealRequest,
    session: SessionDep,
    gemini_client: GeminiClientDep,
) -> EstimateMealResponse:
    """Estimate draft items from meal photos and save them to the draft meal."""
    return _photo_estimation_service(session, gemini_client).estimate(
        meal_id=meal_id,
        payload=payload,
        save_draft=True,
    )
