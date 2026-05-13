"""Pure functions for computing derived_categories from meal data.

All functions are deterministic and testable without external dependencies.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from glucotracker.domain.entities import (
    MealRole,
    MealWindow,
    Provenance,
    TasteProfile,
    WeekdayType,
)
from glucotracker.infra.db.models import Meal

WINDOW_ABSOLUTE_FALLBACK: dict[MealWindow, tuple[time, time]] = {
    MealWindow.start: (time(5, 0), time(11, 0)),
    MealWindow.mid: (time(11, 0), time(16, 0)),
    MealWindow.late: (time(16, 0), time(22, 0)),
    MealWindow.night_cap: (time(22, 0), time(5, 0)),
}


def compute_meal_window(
    eaten_at: datetime,
    anchor_minutes: int | None,
) -> MealWindow:
    """Determine which meal window a meal falls into relative to the user's anchor.

    When anchor_minutes is None, falls back to absolute windows.
    """
    if anchor_minutes is None:
        t = eaten_at.time()
        for window, (start, end) in WINDOW_ABSOLUTE_FALLBACK.items():
            if end > start:
                if start <= t < end:
                    return window
            else:
                if t >= start or t < end:
                    return window
        return MealWindow.night_cap

    minutes_of_day = eaten_at.hour * 60 + eaten_at.minute
    offset = (minutes_of_day - anchor_minutes) % (24 * 60)

    if offset < 3 * 60:
        return MealWindow.start
    if offset < 8 * 60:
        return MealWindow.mid
    if offset < 13 * 60:
        return MealWindow.late
    return MealWindow.night_cap


def compute_weekday_type(eaten_at: datetime) -> WeekdayType:
    """Return whether a meal falls on a weekday or weekend."""
    return WeekdayType.weekend if eaten_at.weekday() >= 5 else WeekdayType.weekday


def compute_provenance(
    meal_name: str | None,
    brand_slug: str | None = None,
    kcal_per_100g: float | None = None,
    protein_per_100g: float | None = None,
) -> Provenance:
    """Determine food provenance from brand slug, name patterns, and macros."""
    from glucotracker.application.categorization.brands import (
        KNOWN_PACKAGED_BRANDS,
        KNOWN_RESTAURANT_BRANDS,
    )
    from glucotracker.application.categorization.patterns import (
        FASTFOOD_NAME_PATTERNS,
    )

    if brand_slug:
        slug_lower = brand_slug.lower().strip().replace(" ", "_")
        if slug_lower in KNOWN_RESTAURANT_BRANDS:
            return Provenance.restaurant_fastfood
        if slug_lower in KNOWN_PACKAGED_BRANDS:
            return Provenance.packaged

    if meal_name:
        name_lower = meal_name.casefold()
        for pattern in FASTFOOD_NAME_PATTERNS:
            if pattern in name_lower:
                return Provenance.restaurant_fastfood

    if kcal_per_100g is not None and protein_per_100g is not None:
        if kcal_per_100g > 450 and protein_per_100g < 8:
            return Provenance.packaged

    return Provenance.unknown


def compute_meal_role(
    meal: Meal,
    taste: TasteProfile | None,
    *,
    has_main_meal_in_window: bool = False,
    meal_item_count: int = 0,
    provenance: Provenance | None = None,
) -> MealRole:
    """Determine the structural meal role from kcal, protein, taste, and context."""
    if taste in (TasteProfile.drink_sweet, TasteProfile.drink_other):
        return MealRole.drink

    if meal.total_kcal >= 350 and meal.total_protein_g >= 20:
        if (
            provenance == Provenance.restaurant_fastfood
            and meal_item_count >= 3
            and taste == TasteProfile.sweet
        ):
            return MealRole.composite
        return MealRole.main_meal

    if meal.total_kcal < 350:
        if has_main_meal_in_window:
            return MealRole.dessert
        return MealRole.snack

    return MealRole.snack


def compute_derived_categories(
    meal: Meal,
    *,
    anchor_minutes: int | None = None,
    brand_slug: str | None = None,
    has_main_meal_in_window: bool = False,
    taste: TasteProfile | None = None,
) -> dict[str, Any]:
    """Compute all derived categories for a meal and return as a JSON-serializable dict.

    Args:
        meal: The meal ORM object.
        anchor_minutes: User's day_anchor in minutes from midnight
            (None = absolute fallback).
        brand_slug: Brand slug from the first meal item's linked product.
        has_main_meal_in_window: Whether another accepted meal in the
            same window is a main_meal.
        taste: Taste profile from LLM classification, or None if not
            yet classified.
    """
    from datetime import UTC, datetime

    meal_window = compute_meal_window(meal.eaten_at, anchor_minutes)
    weekday_type = compute_weekday_type(meal.eaten_at)

    meal_name = meal.title or (
        meal.items[0].name if meal.items else None
    )

    provenance = compute_provenance(
        meal_name=meal_name,
        brand_slug=brand_slug,
    )

    meal_role = compute_meal_role(
        meal,
        taste,
        has_main_meal_in_window=has_main_meal_in_window,
        meal_item_count=len(meal.items),
        provenance=provenance,
    )

    return {
        "meal_window": meal_window.value,
        "meal_role": meal_role.value,
        "provenance": provenance.value,
        "weekday_type": weekday_type.value,
        "computed_at": datetime.now(UTC).isoformat(),
    }
