"""Pure helpers for comparing current and proposed meal estimates."""

from __future__ import annotations

from typing import Any

from glucotracker.api.schemas import (
    EstimateComparisonDiff,
    EstimateDiffTotals,
    EstimateItemChange,
    MealItemCreate,
)
from glucotracker.domain.nutrition import calculate_meal_totals


def _evidence(item: MealItemCreate) -> dict[str, Any]:
    """Return evidence as a mapping."""
    return item.evidence if isinstance(item.evidence, dict) else {}


def _source_photo_ids(item: MealItemCreate) -> tuple[str, ...]:
    """Return source photo ids used for matching estimates."""
    evidence = _evidence(item)
    source_ids = evidence.get("source_photo_ids")
    if isinstance(source_ids, list):
        return tuple(sorted(str(value) for value in source_ids))
    if item.photo_id is not None:
        return (str(item.photo_id),)
    return ()


def _item_key(item: MealItemCreate) -> str:
    """Return a stable fuzzy key for item-level comparison."""
    photo_key = ",".join(_source_photo_ids(item))
    return f"{item.name.casefold().strip()}|{photo_key}"


def _changed(current: MealItemCreate, proposed: MealItemCreate) -> bool:
    """Return whether visible macro fields changed meaningfully."""
    fields = ("carbs_g", "protein_g", "fat_g", "fiber_g", "kcal")
    return any(
        abs(getattr(current, field) - getattr(proposed, field)) > 0.05
        for field in fields
    )


def compare_estimates(
    current_items: list[MealItemCreate],
    proposed_items: list[MealItemCreate],
    *,
    current_model: str | None = None,
    proposed_model: str | None = None,
    warnings: list[str] | None = None,
) -> EstimateComparisonDiff:
    """Compare current and proposed item lists by totals and fuzzy item keys."""
    current_totals = calculate_meal_totals(current_items)
    proposed_totals = calculate_meal_totals(proposed_items)

    current_by_key = {_item_key(item): item for item in current_items}
    proposed_by_key = {_item_key(item): item for item in proposed_items}
    current_keys = set(current_by_key)
    proposed_keys = set(proposed_by_key)

    added = [
        EstimateItemChange(
            name=proposed_by_key[key].name,
            proposed=proposed_by_key[key],
        )
        for key in sorted(proposed_keys - current_keys)
    ]
    removed = [
        EstimateItemChange(name=current_by_key[key].name, current=current_by_key[key])
        for key in sorted(current_keys - proposed_keys)
    ]
    changed = [
        EstimateItemChange(
            name=proposed_by_key[key].name,
            current=current_by_key[key],
            proposed=proposed_by_key[key],
        )
        for key in sorted(current_keys & proposed_keys)
        if _changed(current_by_key[key], proposed_by_key[key])
    ]

    comparison_warnings = list(warnings or [])
    if len(current_items) != len(proposed_items):
        comparison_warnings.append(
            
                f"Новая оценка нашла {len(proposed_items)} позиций вместо "
                f"{len(current_items)}."
            
        )

    current_confidences = [
        item.confidence for item in current_items if item.confidence is not None
    ]
    proposed_confidences = [
        item.confidence for item in proposed_items if item.confidence is not None
    ]
    confidence_delta = None
    if current_confidences and proposed_confidences:
        confidence_delta = round(
            sum(proposed_confidences) / len(proposed_confidences)
            - sum(current_confidences) / len(current_confidences),
            3,
        )

    return EstimateComparisonDiff(
        totals=EstimateDiffTotals(
            carbs_delta=round(
                proposed_totals["total_carbs_g"] - current_totals["total_carbs_g"], 1
            ),
            protein_delta=round(
                proposed_totals["total_protein_g"]
                - current_totals["total_protein_g"],
                1,
            ),
            fat_delta=round(
                proposed_totals["total_fat_g"] - current_totals["total_fat_g"], 1
            ),
            fiber_delta=round(
                proposed_totals["total_fiber_g"] - current_totals["total_fiber_g"], 1
            ),
            kcal_delta=round(
                proposed_totals["total_kcal"] - current_totals["total_kcal"], 1
            ),
        ),
        added_items=added,
        removed_items=removed,
        changed_items=changed,
        current_model=current_model,
        proposed_model=proposed_model,
        confidence_delta=confidence_delta,
        warnings=list(dict.fromkeys(comparison_warnings)),
    )
