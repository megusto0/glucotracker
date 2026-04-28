"""Tests for pure nutrition calculations."""

from types import SimpleNamespace

import pytest

from glucotracker.domain.nutrition import (
    calculate_item_from_per_100g,
    calculate_kcal_from_macros,
    calculate_label_item_totals,
    calculate_meal_totals,
    compute_meal_confidence,
    validate_macros_consistency,
)


def test_calculate_kcal_from_macros_uses_atwater_factors() -> None:
    """Carbs and protein use 4 kcal/g, fat uses 9 kcal/g."""
    assert calculate_kcal_from_macros(10, 5, 2) == 78


def test_calculate_item_from_per_100g_scales_label_values() -> None:
    """Per-100g nutrition values are scaled by actual grams."""
    item = calculate_item_from_per_100g(
        carbs_per_100g=20,
        protein_per_100g=10,
        fat_per_100g=5,
        fiber_per_100g=2,
        kcal_per_100g=165,
        grams=50,
    )

    assert item["carbs_g"] == pytest.approx(10)
    assert item["protein_g"] == pytest.approx(5)
    assert item["fat_g"] == pytest.approx(2.5)
    assert item["fiber_g"] == pytest.approx(1)
    assert item["kcal"] == pytest.approx(82.5)
    assert item["calculation_method"] == "per_100g_label"


def test_calculate_label_item_totals_handles_split_two_candies() -> None:
    """Split label facts are calculated from per-100g values, weight and count."""
    totals = calculate_label_item_totals(
        {
            "carbs_g": 62,
            "protein_g": 4.5,
            "fat_g": 16,
            "kcal": 410,
        },
        net_weight_per_unit_g=30,
        count_detected=2,
    )

    assert totals["total_weight_g"] == pytest.approx(60)
    assert totals["carbs_g"] == pytest.approx(37.2)
    assert totals["protein_g"] == pytest.approx(2.7)
    assert totals["fat_g"] == pytest.approx(9.6)
    assert totals["kcal"] == pytest.approx(246)


def test_calculate_meal_totals_sums_item_macros() -> None:
    """Meal totals are backend-owned sums of item macros."""
    totals = calculate_meal_totals(
        [
            {"carbs_g": 10, "protein_g": 5, "fat_g": 2, "fiber_g": 1, "kcal": 80},
            {"carbs_g": 4, "protein_g": 3, "fat_g": 1, "fiber_g": 0, "kcal": 37},
        ]
    )

    assert totals == {
        "total_carbs_g": 14,
        "total_protein_g": 8,
        "total_fat_g": 3,
        "total_fiber_g": 1,
        "total_kcal": 117,
    }


def test_validate_macros_consistency_warns_when_kcal_differs_over_20_percent() -> None:
    """Inconsistent non-label kcal values produce a warning."""
    item = SimpleNamespace(
        carbs_g=10,
        protein_g=0,
        fat_g=0,
        kcal=80,
        calculation_method="manual",
    )

    warnings = validate_macros_consistency(item)

    assert len(warnings) == 1
    assert warnings[0].code == "kcal_macro_mismatch"


def test_validate_macros_consistency_allows_direct_label_kcal() -> None:
    """Label-provided kcal can differ from 4/4/9 without a warning."""
    item = SimpleNamespace(
        carbs_g=10,
        protein_g=0,
        fat_g=0,
        kcal=80,
        calculation_method="per_100g_label",
    )

    assert validate_macros_consistency(item) == []


def test_compute_meal_confidence_weights_by_carbs_then_kcal() -> None:
    """Confidence uses carb weighting when carbs are present."""
    confidence = compute_meal_confidence(
        [
            SimpleNamespace(carbs_g=10, kcal=100, confidence=1),
            SimpleNamespace(carbs_g=30, kcal=100, confidence=0.5),
        ]
    )

    assert confidence == pytest.approx(0.625)
