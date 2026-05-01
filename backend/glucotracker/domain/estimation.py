"""Normalize Gemini extraction results into backend draft meal items."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from glucotracker.api.schemas import MealItemCreate
from glucotracker.domain.entities import ItemSourceKind
from glucotracker.domain.known_components import (
    KnownComponent,
    adjust_item_with_known_components,
    collapse_plated_items,
    known_component_evidence_payload,
    known_component_warning,
)
from glucotracker.domain.nutrients import (
    VISUAL_GUESS_BLOCKLIST,
    normalize_nutrients_object,
    nutrient_unit,
)
from glucotracker.domain.nutrition import (
    calculate_item_from_per_100g,
    calculate_label_item_totals,
    validate_macros_consistency,
)
from glucotracker.infra.gemini.schemas import (
    EstimatedItem,
    EstimationResult,
    ExtractedNutritionFacts,
    NutritionPer100g,
    OptionalNutrientFact,
    VisibleLabelFact,
)


def _warning_payload(item: MealItemCreate) -> list[dict[str, str | None]]:
    """Return macro consistency warnings for a normalized item."""
    return [
        warning.__dict__
        for warning in validate_macros_consistency(SimpleNamespace(**item.model_dump()))
    ]


def _facts_dict(facts: ExtractedNutritionFacts | None) -> dict[str, Any] | None:
    """Serialize extracted facts for evidence payloads."""
    return facts.model_dump() if facts is not None else None


def _visible_label_facts_payload(facts: list[VisibleLabelFact]) -> list[dict[str, Any]]:
    """Serialize visible label fact rows for evidence payloads."""
    return [fact.model_dump(exclude_none=True) for fact in facts]


def _nutrition_per_100g_payload(
    nutrition: NutritionPer100g | None,
) -> dict[str, Any] | None:
    """Serialize normalized per-100g nutrition facts."""
    return nutrition.model_dump() if nutrition is not None else None


def _evidence_text(item: EstimatedItem) -> list[str]:
    """Return human-readable evidence strings from legacy or new schemas."""
    return [str(entry) for entry in item.evidence]


def _item_name(item: EstimatedItem) -> str:
    """Return the user-facing item name, preferring Russian labels."""
    return item.display_name_ru or item.name


def _confidence_reason(item: EstimatedItem) -> str:
    """Return confidence reason, preferring Russian text."""
    return item.confidence_reason_ru or item.confidence_reason


UNPEELED_FRUIT_RULES: dict[str, dict[str, Any]] = {
    "orange": {
        "aliases": ("апельсин", "orange"),
        "edible_yield": 0.74,
        "carbs_per_100g": 11.8,
        "protein_per_100g": 0.9,
        "fat_per_100g": 0.1,
        "fiber_per_100g": 2.4,
        "kcal_per_100g": 47,
        "ru_name": "апельсина",
    },
    "mandarin": {
        "aliases": ("мандарин", "mandarin", "tangerine", "clementine"),
        "edible_yield": 0.75,
        "carbs_per_100g": 13.3,
        "protein_per_100g": 0.8,
        "fat_per_100g": 0.3,
        "fiber_per_100g": 1.8,
        "kcal_per_100g": 53,
        "ru_name": "мандарина",
    },
}


def _text_haystack(item: EstimatedItem) -> str:
    """Return searchable text from Gemini item fields."""
    parts = [
        item.name,
        item.display_name_ru or "",
        item.confidence_reason,
        item.confidence_reason_ru or "",
        *item.assumptions,
        *item.evidence,
    ]
    return " ".join(parts).casefold()


def _matched_unpeeled_fruit_rule(item: EstimatedItem) -> dict[str, Any] | None:
    """Return a fruit rule when visible scale weight likely includes peel."""
    if item.scenario != "PLATED":
        return None
    haystack = _text_haystack(item)
    if any(marker in haystack for marker in ("очищ", "peeled", "без кожур")):
        return None
    has_scale_or_gross_weight = any(
        marker in haystack
        for marker in ("вес", "scale", "весах", "кожур", "unpeeled", "whole")
    )
    if not has_scale_or_gross_weight:
        return None
    for rule in UNPEELED_FRUIT_RULES.values():
        if any(alias in haystack for alias in rule["aliases"]):
            return rule
    return None


def _unpeeled_fruit_adjustment(
    item: EstimatedItem,
) -> tuple[dict[str, float], dict[str, Any], list[dict[str, str | None]]] | None:
    """Adjust unpeeled fruit gross scale weight to edible-weight macros."""
    rule = _matched_unpeeled_fruit_rule(item)
    gross_weight_g = item.total_weight_g or item.net_weight_per_unit_g or item.grams_mid
    if rule is None or gross_weight_g is None:
        return None

    gross_weight_g = float(gross_weight_g)
    edible_weight_g = round(gross_weight_g * float(rule["edible_yield"]), 1)
    scale = edible_weight_g / 100.0
    final_values = {
        "carbs_g": round(float(rule["carbs_per_100g"]) * scale, 1),
        "protein_g": round(float(rule["protein_per_100g"]) * scale, 1),
        "fat_g": round(float(rule["fat_per_100g"]) * scale, 1),
        "fiber_g": round(float(rule["fiber_per_100g"]) * scale, 1),
        "kcal": round(float(rule["kcal_per_100g"]) * scale, 1),
    }
    evidence = {
        "gross_weight_g": gross_weight_g,
        "edible_yield": rule["edible_yield"],
        "edible_weight_g": edible_weight_g,
        "raw_model_estimate": {
            "carbs_g": item.carbs_g_mid,
            "protein_g": item.protein_g_mid,
            "fat_g": item.fat_g_mid,
            "fiber_g": item.fiber_g_mid,
            "kcal": item.kcal_mid,
        },
        "final_backend_adjusted_values": final_values,
        "evidence_text": [
            f"Вес {gross_weight_g:g} г принят как вес с кожурой.",
            (
                f"Съедобная часть {rule['ru_name']} оценена как "
                f"{edible_weight_g:g} г."
            ),
        ],
    }
    warnings = [
        {
            "code": "gross_weight_includes_peel",
            "message": (
                "Вес фрукта на фото, вероятно, включает кожуру. "
                "Макросы пересчитаны на съедобную часть."
            ),
            "field": "grams",
        }
    ]
    return final_values, evidence, warnings


def _optional_nutrient_entries(
    item: EstimatedItem,
) -> list[tuple[str, OptionalNutrientFact]]:
    """Return optional nutrient facts keyed by their nutrient code."""
    return [(fact.code, fact) for fact in item.optional_nutrients]


def _component_estimates_payload(item: EstimatedItem) -> list[dict[str, Any]]:
    """Serialize component-level visual analysis."""
    return [
        component.model_dump(exclude_none=True)
        for component in item.component_estimates
    ]


def _base_evidence(item: EstimatedItem) -> dict[str, Any]:
    """Build shared evidence fields from a Gemini item."""
    evidence = {"evidence_text": _evidence_text(item)}
    evidence["scenario"] = item.scenario
    evidence["item_type"] = item.item_type
    evidence["source_photo_ids"] = list(item.source_photo_ids)
    evidence["primary_photo_id"] = item.primary_photo_id
    evidence["source_photo_indices"] = list(item.source_photo_indices)
    evidence["extracted_facts"] = _facts_dict(item.extracted_facts)
    evidence["visible_label_facts"] = _visible_label_facts_payload(
        item.visible_label_facts
    )
    evidence["nutrition_per_100g"] = _nutrition_per_100g_payload(
        item.nutrition_per_100g
    )
    evidence["count_detected"] = item.count_detected
    evidence["count_confidence"] = item.count_confidence
    evidence["net_weight_per_unit_g"] = item.net_weight_per_unit_g
    evidence["total_weight_g"] = item.total_weight_g
    evidence["evidence_is_split_across_identical_items"] = (
        item.evidence_is_split_across_identical_items
    )
    evidence["component_estimates"] = _component_estimates_payload(item)
    evidence["display_labels_ru"] = {
        "carbs": "Углеводы",
        "protein": "Белки",
        "fat": "Жиры",
        "fiber": "Клетчатка",
        "kcal": "Ккал",
        "mass": "Масса",
        "count": "Количество",
        "source": "Источник",
        "confidence": "Уверенность",
        "evidence": "Данные",
        "assumptions": "Допущения",
        "label": "Этикетка",
        "label_calc": "Рассчитано по этикетке",
        "identical_packages": "Одинаковые упаковки",
        "unknown": "Значение неизвестно",
    }
    if item.identified_barcode is not None:
        evidence["identified_barcode"] = item.identified_barcode
    if item.grams_low is not None or item.grams_high is not None:
        evidence["grams_range"] = {
            "low": item.grams_low,
            "mid": item.grams_mid,
            "high": item.grams_high,
        }
    if item.carbs_g_low is not None or item.carbs_g_high is not None:
        evidence["carbs_g_range"] = {
            "low": item.carbs_g_low,
            "mid": item.carbs_g_mid,
            "high": item.carbs_g_high,
        }
    return evidence


def _split_label_evidence(item: EstimatedItem) -> list[str]:
    """Return evidence strings for a split-label identical-package case."""
    evidence = _evidence_text(item)
    if item.evidence_is_split_across_identical_items:
        evidence.extend(
            [
                "Углеводы/белки/жиры/ккал видны на одной упаковке",
                (
                    f"Масса нетто {item.net_weight_per_unit_g:g} г видна "
                    "на другой упаковке"
                    if item.net_weight_per_unit_g is not None
                    else "Масса нетто видна на другой упаковке"
                ),
                (
                    f"На фото видно {item.count_detected} одинаковые упаковки"
                    if item.count_detected is not None
                    else "На фото видно одинаковые упаковки"
                ),
            ]
        )
    return list(dict.fromkeys(evidence))


def _with_split_assumption(item: EstimatedItem) -> list[str]:
    """Return assumptions including the identical-package split assumption."""
    assumptions = list(item.assumptions)
    if item.evidence_is_split_across_identical_items:
        assumptions.append("Обе упаковки считаются одинаковым продуктом")
    return list(dict.fromkeys(assumptions))


def _optional_nutrients_from_label(
    item: EstimatedItem,
    *,
    weight_g: float | None,
    volume_ml: float | None,
) -> dict[str, Any]:
    """Scale visible optional label nutrients into item totals."""
    nutrients: dict[str, Any] = {}
    for code, fact in _optional_nutrient_entries(item):
        amount = _scaled_optional_nutrient_amount(
            fact,
            weight_g=weight_g,
            volume_ml=volume_ml,
        )
        nutrients[code] = {
            "amount": amount,
            "unit": fact.unit or nutrient_unit(code),
            "source_kind": fact.source_kind or "label_calc",
            "confidence": fact.confidence
            if fact.confidence is not None
            else item.confidence,
            "evidence_json": {
                "evidence_text": fact.evidence,
                "visible_label_fact": fact.model_dump(exclude_none=True),
            },
            "assumptions_json": fact.assumptions,
        }
    return nutrients


def _optional_nutrients_from_per_100g(
    item: EstimatedItem,
    *,
    total_weight_g: float,
) -> dict[str, Any]:
    """Scale visible optional per-100g nutrients into item totals."""
    if item.nutrition_per_100g is None:
        return {}

    scale = total_weight_g / 100.0
    nutrient_fields = {
        "sugar_g": "g",
        "sodium_mg": "mg",
        "caffeine_mg": "mg",
    }
    nutrients: dict[str, Any] = {}
    for code, unit in nutrient_fields.items():
        value = getattr(item.nutrition_per_100g, code)
        if value is None:
            continue
        nutrients[code] = {
            "amount": round(float(value) * scale, 1),
            "unit": unit,
            "source_kind": "label_calc",
            "confidence": item.confidence,
            "evidence_json": {
                "nutrition_per_100g": item.nutrition_per_100g.model_dump(),
                "visible_label_facts": _visible_label_facts_payload(
                    item.visible_label_facts
                ),
            },
            "assumptions_json": _with_split_assumption(item),
        }
    return nutrients


def _scaled_optional_nutrient_amount(
    fact: OptionalNutrientFact,
    *,
    weight_g: float | None,
    volume_ml: float | None,
) -> float | None:
    """Scale one optional nutrient fact using backend arithmetic."""
    if fact.amount is not None:
        return fact.amount
    if fact.amount_per_100g is not None and weight_g is not None:
        return fact.amount_per_100g * (weight_g / 100.0)
    if fact.amount_per_100ml is not None and volume_ml is not None:
        return fact.amount_per_100ml * (volume_ml / 100.0)
    if fact.amount_per_serving is not None:
        return fact.amount_per_serving
    return None


def _scale_per_100ml(
    facts: ExtractedNutritionFacts,
    volume_ml: float,
) -> dict[str, float | str]:
    """Scale per-100ml label values to a visible or assumed volume."""
    scale = volume_ml / 100.0
    carbs_g = (facts.carbs_per_100ml or 0) * scale
    protein_g = (facts.protein_per_100ml or 0) * scale
    fat_g = (facts.fat_per_100ml or 0) * scale
    fiber_g = (facts.fiber_per_100ml or 0) * scale
    kcal = (
        (facts.kcal_per_100ml * scale)
        if facts.kcal_per_100ml is not None
        else carbs_g * 4 + protein_g * 4 + fat_g * 9
    )
    return {
        "grams": volume_ml,
        "carbs_g": carbs_g,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "fiber_g": fiber_g,
        "kcal": kcal,
        "calculation_method": "per_100ml_label",
    }


def _label_split_item(item: EstimatedItem) -> MealItemCreate | None:
    """Normalize split visible label facts from identical packages."""
    if (
        item.nutrition_per_100g is None
        or item.net_weight_per_unit_g is None
        or item.count_detected is None
    ):
        return None

    totals = calculate_label_item_totals(
        item.nutrition_per_100g,
        item.net_weight_per_unit_g,
        item.count_detected,
    )
    if any(totals[key] is None for key in ("carbs_g", "protein_g", "fat_g", "kcal")):
        return None

    total_weight_g = float(totals["total_weight_g"] or 0)
    evidence = _base_evidence(item)
    evidence["evidence_text"] = _split_label_evidence(item)

    nutrients = _optional_nutrients_from_per_100g(
        item,
        total_weight_g=total_weight_g,
    )
    nutrients.update(
        _optional_nutrients_from_label(
            item,
            weight_g=total_weight_g,
            volume_ml=None,
        )
    )

    normalized = MealItemCreate(
        name=_item_name(item) or "Бисквит-сэндвич",
        brand=item.brand,
        grams=total_weight_g,
        serving_text=(
            f"×{item.count_detected} упаковки · {item.net_weight_per_unit_g:g} г каждая"
        ),
        carbs_g=float(totals["carbs_g"] or 0),
        protein_g=float(totals["protein_g"] or 0),
        fat_g=float(totals["fat_g"] or 0),
        fiber_g=float(totals["fiber_g"] or 0),
        kcal=float(totals["kcal"] or 0),
        confidence=item.confidence,
        confidence_reason=_confidence_reason(item),
        source_kind=ItemSourceKind.label_calc,
        calculation_method="label_split_visible_weight_backend_calc",
        assumptions=_with_split_assumption(item),
        evidence=evidence,
        nutrients=nutrients,
    )
    normalized.warnings = _warning_payload(normalized)
    return normalized


def _label_item(
    item: EstimatedItem,
    *,
    use_assumed_size: bool,
) -> MealItemCreate | None:
    """Normalize a label extraction using backend arithmetic."""
    facts = item.extracted_facts
    if facts is None:
        return None

    weight_g = facts.assumed_weight_g if use_assumed_size else facts.visible_weight_g
    volume_ml = facts.assumed_volume_ml if use_assumed_size else facts.visible_volume_ml
    assumptions = list(item.assumptions)
    if use_assumed_size and facts.assumption_reason:
        assumptions.append(facts.assumption_reason)

    if weight_g is not None and facts.carbs_per_100g is not None:
        scaled = calculate_item_from_per_100g(
            facts.carbs_per_100g,
            facts.protein_per_100g,
            facts.fat_per_100g,
            facts.fiber_per_100g,
            facts.kcal_per_100g,
            weight_g,
        )
        serving_text = f"{weight_g:g} g"
    elif volume_ml is not None and facts.carbs_per_100ml is not None:
        scaled = _scale_per_100ml(facts, volume_ml)
        serving_text = f"{volume_ml:g} ml"
    elif volume_ml is not None and facts.carbs_per_100g is not None:
        assumptions.append(
            f"плотность ~1 г/мл, объём {volume_ml:g} мл ≈ {volume_ml:g} г"
        )
        scaled = calculate_item_from_per_100g(
            facts.carbs_per_100g,
            facts.protein_per_100g,
            facts.fat_per_100g,
            facts.fiber_per_100g,
            facts.kcal_per_100g,
            volume_ml,
        )
        serving_text = f"{volume_ml:g} мл (~{volume_ml:g} г)"
    else:
        return None

    calculation_method = (
        "label_assumed_weight_backend_calc"
        if use_assumed_size
        else "label_visible_weight_backend_calc"
    )
    normalized = MealItemCreate(
        name=_item_name(item),
        brand=item.brand,
        grams=float(scaled["grams"]),
        serving_text=serving_text,
        carbs_g=float(scaled["carbs_g"]),
        protein_g=float(scaled["protein_g"]),
        fat_g=float(scaled["fat_g"]),
        fiber_g=float(scaled["fiber_g"]),
        kcal=float(scaled["kcal"]),
        confidence=item.confidence,
        confidence_reason=_confidence_reason(item),
        source_kind=ItemSourceKind.label_calc,
        calculation_method=calculation_method,
        assumptions=assumptions,
        evidence=_base_evidence(item),
        nutrients=_optional_nutrients_from_label(
            item,
            weight_g=weight_g,
            volume_ml=volume_ml,
        ),
    )
    normalized.warnings = _warning_payload(normalized)
    return normalized


def _plated_item(
    item: EstimatedItem,
    *,
    known_components: list[KnownComponent],
) -> MealItemCreate:
    """Normalize a plated-food visual estimate."""
    optional_nutrients = {
        code: fact.model_dump(exclude_none=True)
        for code, fact in _optional_nutrient_entries(item)
        if code not in VISUAL_GUESS_BLOCKLIST
        and fact.source_kind in {"generic_food_db", "product_db", "restaurant_db"}
    }
    evidence = _base_evidence(item)
    adjustment = adjust_item_with_known_components(item, known_components)
    component_payload = known_component_evidence_payload(adjustment)
    warnings: list[dict[str, str | None]] = []
    assumptions = list(item.assumptions)
    calculation_method = "visual_estimate_gemini_mid"
    final_values = adjustment.adjusted_totals or {
        "carbs_g": item.carbs_g_mid,
        "protein_g": item.protein_g_mid,
        "fat_g": item.fat_g_mid,
        "fiber_g": item.fiber_g_mid,
        "kcal": item.kcal_mid,
    }
    fruit_adjustment = (
        None if component_payload is not None else _unpeeled_fruit_adjustment(item)
    )
    if fruit_adjustment is not None:
        final_values, fruit_evidence, fruit_warnings = fruit_adjustment
        evidence["gross_weight_edible_yield"] = fruit_evidence
        evidence["raw_model_estimate"] = fruit_evidence["raw_model_estimate"]
        evidence["final_backend_adjusted_values"] = final_values
        evidence["evidence_text"] = [
            *evidence.get("evidence_text", []),
            *fruit_evidence["evidence_text"],
        ]
        assumptions.append(
            "Вес фрукта на весах включает кожуру; значения пересчитаны "
            "на съедобную часть."
        )
        warnings.extend(fruit_warnings)
        calculation_method = "visual_estimate_gross_weight_edible_yield"
    if component_payload is not None:
        evidence["known_component"] = component_payload
        evidence["carb_anchor"] = component_payload
        evidence["raw_model_estimate"] = adjustment.raw_model_totals
        evidence["final_backend_adjusted_values"] = final_values
        evidence["field_sources"] = adjustment.field_sources
        assumptions.append(
            "Значения видимых компонентов частично взяты из сохранённой базы "
            "компонентов."
        )
        calculation_method = "visual_estimate_with_known_component"
    if warning := known_component_warning(adjustment):
        warnings.append(
            {
                "code": "known_component_review",
                "message": warning,
                "field": "evidence.component_estimates",
            }
        )
    optional_nutrients.update(_known_component_nutrients(adjustment))

    count = item.count_detected or 1
    if count > 1:
        final_values = {
            k: (v * count if isinstance(v, (int, float)) else v)
            for k, v in final_values.items()
        }
        evidence["raw_model_estimate"] = {
            k: (v * count if isinstance(v, (int, float)) else v)
            for k, v in evidence.get("raw_model_estimate", {}).items()
        }
        evidence["final_backend_adjusted_values"] = final_values
        assumptions.append(
            f"Модель определила {count} порций; значения умножены на {count}."
        )
        calculation_method = f"{calculation_method}_count_{count}"

    normalized = MealItemCreate(
        name=_item_name(item),
        brand=item.brand,
        grams=(item.grams_mid or 0) * count if count > 1 else item.grams_mid,
        carbs_g=final_values.get("carbs_g") or 0,
        protein_g=final_values.get("protein_g") or 0,
        fat_g=final_values.get("fat_g") or 0,
        fiber_g=final_values.get("fiber_g") or 0,
        kcal=final_values.get("kcal") or 0,
        confidence=item.confidence,
        confidence_reason=_confidence_reason(item),
        source_kind=ItemSourceKind.photo_estimate,
        calculation_method=calculation_method,
        assumptions=list(dict.fromkeys(assumptions)),
        evidence=evidence,
        nutrients=normalize_nutrients_object(
            optional_nutrients,
            default_source_kind="generic_food_db",
        ),
    )
    normalized.warnings = [*warnings, *_warning_payload(normalized)]
    return normalized


def _known_component_nutrients(adjustment: Any) -> dict[str, Any]:
    """Return optional nutrients copied from matched known components."""
    nutrients: dict[str, Any] = {}
    for match in adjustment.matches:
        for code, value in (match.known_component.nutrients_json or {}).items():
            if code in {"component_type", "kind"}:
                continue
            if isinstance(value, dict):
                nutrients[code] = {
                    "source_kind": match.known_component.source_kind,
                    **value,
                }
            else:
                nutrients[code] = {
                    "amount": value,
                    "source_kind": match.known_component.source_kind,
                }
    return nutrients


def _product_value(product: Any, key: str) -> Any:
    """Read a value from a product mapping or object."""
    if isinstance(product, Mapping):
        return product.get(key)
    return getattr(product, key, None)


def _barcode_item(
    item: EstimatedItem,
    products_by_barcode: Mapping[str, Any],
) -> MealItemCreate:
    """Normalize a barcode result using a local product when available."""
    barcode = item.identified_barcode
    product = products_by_barcode.get(barcode or "")
    evidence = _base_evidence(item)

    if product is None:
        normalized = MealItemCreate(
            name=_item_name(item) or "Unknown barcode item",
            brand=item.brand,
            carbs_g=0,
            protein_g=0,
            fat_g=0,
            fiber_g=0,
            kcal=0,
            confidence=item.confidence,
            confidence_reason=_confidence_reason(item),
            source_kind=ItemSourceKind.photo_estimate,
            calculation_method="barcode_unmatched",
            assumptions=list(item.assumptions),
            evidence=evidence,
        )
        normalized.warnings = _warning_payload(normalized)
        return normalized

    default_grams = _product_value(product, "default_grams")
    if (
        default_grams is not None
        and _product_value(product, "carbs_per_100g") is not None
    ):
        scaled = calculate_item_from_per_100g(
            _product_value(product, "carbs_per_100g"),
            _product_value(product, "protein_per_100g"),
            _product_value(product, "fat_per_100g"),
            _product_value(product, "fiber_per_100g"),
            _product_value(product, "kcal_per_100g"),
            default_grams,
        )
        grams = float(scaled["grams"])
        carbs_g = float(scaled["carbs_g"])
        protein_g = float(scaled["protein_g"])
        fat_g = float(scaled["fat_g"])
        fiber_g = float(scaled["fiber_g"])
        kcal = float(scaled["kcal"])
        calculation_method = "product_per_100g_backend_calc"
    else:
        grams = default_grams
        carbs_g = _product_value(product, "carbs_per_serving") or 0
        protein_g = _product_value(product, "protein_per_serving") or 0
        fat_g = _product_value(product, "fat_per_serving") or 0
        fiber_g = _product_value(product, "fiber_per_serving") or 0
        kcal = _product_value(product, "kcal_per_serving") or 0
        calculation_method = "product_serving_values"

    normalized = MealItemCreate(
        name=_product_value(product, "name") or _item_name(item),
        brand=_product_value(product, "brand") or item.brand,
        grams=grams,
        serving_text=_product_value(product, "default_serving_text"),
        carbs_g=carbs_g,
        protein_g=protein_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        kcal=kcal,
        confidence=item.confidence,
        confidence_reason=_confidence_reason(item),
        source_kind=ItemSourceKind.product_db,
        calculation_method=calculation_method,
        assumptions=list(item.assumptions),
        evidence=evidence,
        product_id=_product_value(product, "id"),
        nutrients=normalize_nutrients_object(
            _product_value(product, "nutrients_json"),
            default_source_kind="product_db",
        ),
    )
    normalized.warnings = _warning_payload(normalized)
    return normalized


def normalize_estimation_to_items(
    result: EstimationResult,
    products_by_barcode: Mapping[str, Any] | None = None,
    known_components: list[KnownComponent] | None = None,
) -> list[MealItemCreate]:
    """Convert a Gemini result into draft meal item create payloads."""
    products_by_barcode = products_by_barcode or {}
    known_components = known_components or []
    normalized_items: list[MealItemCreate] = []

    for item in collapse_plated_items(result.items):
        normalized: MealItemCreate | None
        if item.scenario in {"LABEL_FULL", "SPLIT_LABEL_IDENTICAL_ITEMS"}:
            normalized = _label_split_item(item) or _label_item(
                item,
                use_assumed_size=False,
            )
        elif item.scenario == "LABEL_PARTIAL":
            normalized = _label_item(item, use_assumed_size=True)
        elif item.scenario == "BARCODE":
            normalized = _barcode_item(item, products_by_barcode)
        else:
            normalized = _plated_item(item, known_components=known_components)

        if normalized is not None:
            normalized_items.append(normalized)

    return normalized_items
