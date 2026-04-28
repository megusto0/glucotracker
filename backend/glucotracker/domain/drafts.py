"""Pure domain operations for meal draft lifecycle changes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from glucotracker.domain.entities import MealStatus
from glucotracker.domain.nutrition import calculate_meal_totals, compute_meal_confidence


def _status_value(meal: Any) -> str:
    """Return a comparable meal status value."""
    status = meal.status
    return getattr(status, "value", status)


def ensure_editable(meal: Any) -> None:
    """Ensure a meal can be edited."""
    if _status_value(meal) == MealStatus.discarded.value:
        msg = "discarded meals are not editable"
        raise ValueError(msg)


def accept_meal_draft(meal: Any, final_items: list[Any]) -> Any:
    """Replace draft items, recalculate totals, and mark the meal accepted."""
    ensure_editable(meal)

    items = list(final_items)
    for position, item in enumerate(items):
        if hasattr(item, "position"):
            item.position = position

    meal.items = items
    totals = calculate_meal_totals(items)
    meal.total_carbs_g = totals["total_carbs_g"]
    meal.total_protein_g = totals["total_protein_g"]
    meal.total_fat_g = totals["total_fat_g"]
    meal.total_fiber_g = totals["total_fiber_g"]
    meal.total_kcal = totals["total_kcal"]
    meal.confidence = compute_meal_confidence(items)
    meal.status = MealStatus.accepted
    if hasattr(meal, "updated_at"):
        meal.updated_at = datetime.now(UTC)
    return meal


def discard_meal_draft(meal: Any) -> Any:
    """Mark a meal draft discarded."""
    ensure_editable(meal)
    meal.status = MealStatus.discarded
    if hasattr(meal, "updated_at"):
        meal.updated_at = datetime.now(UTC)
    return meal
