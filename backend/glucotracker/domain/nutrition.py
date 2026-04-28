"""Pure nutrition calculations owned by the backend domain layer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from glucotracker.domain.entities import ValidationWarning

ATWATER_CARBS_KCAL_PER_G = 4.0
ATWATER_PROTEIN_KCAL_PER_G = 4.0
ATWATER_FAT_KCAL_PER_G = 9.0
KCAL_WARNING_THRESHOLD = 0.20


def _value(source: Any, key: str, default: Any = 0.0) -> Any:
    """Read a value from a mapping or object."""
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _number(value: Any, default: float = 0.0) -> float:
    """Convert a numeric domain value to float, treating None as a default."""
    if value is None:
        return default
    return float(value)


def calculate_kcal_from_macros(
    carbs_g: float,
    protein_g: float,
    fat_g: float,
) -> float:
    """Calculate kcal using 4/4/9 Atwater factors."""
    return (
        _number(carbs_g) * ATWATER_CARBS_KCAL_PER_G
        + _number(protein_g) * ATWATER_PROTEIN_KCAL_PER_G
        + _number(fat_g) * ATWATER_FAT_KCAL_PER_G
    )


def calculate_item_from_per_100g(
    carbs_per_100g: float | None,
    protein_per_100g: float | None,
    fat_per_100g: float | None,
    fiber_per_100g: float | None,
    kcal_per_100g: float | None,
    grams: float,
) -> dict[str, float | str]:
    """Scale nutrition label values from per-100g values to an item weight."""
    if grams is None:
        msg = "grams is required for per-100g label calculation"
        raise ValueError(msg)
    if grams < 0:
        msg = "grams cannot be negative"
        raise ValueError(msg)

    scale = grams / 100.0
    carbs_g = _number(carbs_per_100g) * scale
    protein_g = _number(protein_per_100g) * scale
    fat_g = _number(fat_per_100g) * scale
    fiber_g = _number(fiber_per_100g) * scale

    if kcal_per_100g is None:
        kcal = calculate_kcal_from_macros(carbs_g, protein_g, fat_g)
        calculation_method = "per_100g_macro_estimate"
    else:
        kcal = _number(kcal_per_100g) * scale
        calculation_method = "per_100g_label"

    return {
        "grams": float(grams),
        "carbs_g": carbs_g,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "fiber_g": fiber_g,
        "kcal": kcal,
        "calculation_method": calculation_method,
    }


def _rounded_macro(value: float | None) -> float | None:
    """Round a label-derived gram amount for storage/display."""
    return None if value is None else round(float(value), 1)


def _rounded_kcal(value: float | None) -> float | None:
    """Round label-derived kcal to the nearest whole kcal."""
    return None if value is None else float(round(float(value)))


def calculate_label_item_totals(
    nutrition_per_100g: Any,
    net_weight_per_unit_g: float,
    count_detected: int,
) -> dict[str, float | None]:
    """Calculate totals for visible per-100g label facts and package count.

    Unknown nutrient facts remain ``None`` in the returned payload. The caller is
    responsible for deciding whether a partially known result is acceptable for
    a concrete storage model.
    """
    if net_weight_per_unit_g is None:
        msg = "net_weight_per_unit_g is required"
        raise ValueError(msg)
    if count_detected is None:
        msg = "count_detected is required"
        raise ValueError(msg)
    if net_weight_per_unit_g < 0:
        msg = "net_weight_per_unit_g cannot be negative"
        raise ValueError(msg)
    if count_detected < 1:
        msg = "count_detected must be at least 1"
        raise ValueError(msg)

    total_weight_g = float(net_weight_per_unit_g) * int(count_detected)
    scale = total_weight_g / 100.0

    carbs_per_100g = _value(nutrition_per_100g, "carbs_g", None)
    protein_per_100g = _value(nutrition_per_100g, "protein_g", None)
    fat_per_100g = _value(nutrition_per_100g, "fat_g", None)
    fiber_per_100g = _value(nutrition_per_100g, "fiber_g", None)
    kcal_per_100g = _value(nutrition_per_100g, "kcal", None)

    return {
        "total_weight_g": _rounded_macro(total_weight_g),
        "carbs_g": _rounded_macro(
            None if carbs_per_100g is None else float(carbs_per_100g) * scale
        ),
        "protein_g": _rounded_macro(
            None if protein_per_100g is None else float(protein_per_100g) * scale
        ),
        "fat_g": _rounded_macro(
            None if fat_per_100g is None else float(fat_per_100g) * scale
        ),
        "fiber_g": _rounded_macro(
            None if fiber_per_100g is None else float(fiber_per_100g) * scale
        ),
        "kcal": _rounded_kcal(
            None if kcal_per_100g is None else float(kcal_per_100g) * scale
        ),
    }


def calculate_meal_totals(items: Iterable[Any]) -> dict[str, float]:
    """Sum item-level macros into backend-owned meal totals."""
    totals = {
        "total_carbs_g": 0.0,
        "total_protein_g": 0.0,
        "total_fat_g": 0.0,
        "total_fiber_g": 0.0,
        "total_kcal": 0.0,
    }

    for item in items:
        totals["total_carbs_g"] += _number(_value(item, "carbs_g"))
        totals["total_protein_g"] += _number(_value(item, "protein_g"))
        totals["total_fat_g"] += _number(_value(item, "fat_g"))
        totals["total_fiber_g"] += _number(_value(item, "fiber_g"))
        totals["total_kcal"] += _number(_value(item, "kcal"))

    return totals


def validate_macros_consistency(item: Any) -> list[ValidationWarning]:
    """Warn when kcal is materially inconsistent with 4/4/9 macro kcal."""
    calculation_method = str(_value(item, "calculation_method", "") or "").lower()
    if "label" in calculation_method:
        return []

    kcal = _number(_value(item, "kcal"))
    estimated_kcal = calculate_kcal_from_macros(
        _number(_value(item, "carbs_g")),
        _number(_value(item, "protein_g")),
        _number(_value(item, "fat_g")),
    )

    if estimated_kcal == 0:
        differs = kcal > 0
    else:
        differs = abs(kcal - estimated_kcal) / estimated_kcal > KCAL_WARNING_THRESHOLD

    if not differs:
        return []

    return [
        ValidationWarning(
            code="kcal_macro_mismatch",
            field="kcal",
            message=(
                "Item kcal differs from the 4/4/9 macro estimate by more than 20%."
            ),
        )
    ]


def compute_meal_confidence(items: Iterable[Any]) -> float | None:
    """Compute meal confidence as a weighted average across item confidences."""
    item_list = list(items)
    confident_items = [
        item for item in item_list if _value(item, "confidence", None) is not None
    ]
    if not confident_items:
        return None

    total_carbs = sum(max(_number(_value(item, "carbs_g")), 0.0) for item in item_list)
    weight_key = "carbs_g" if total_carbs > 0 else "kcal"

    weighted_total = 0.0
    total_weight = 0.0
    for item in confident_items:
        weight = max(_number(_value(item, weight_key)), 0.0)
        if weight == 0:
            weight = 1.0
        confidence = min(max(_number(_value(item, "confidence")), 0.0), 1.0)
        weighted_total += confidence * weight
        total_weight += weight

    if total_weight == 0:
        return None
    return weighted_total / total_weight
