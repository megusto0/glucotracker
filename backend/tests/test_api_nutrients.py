"""Optional nutrient tracking tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from glucotracker.domain.estimation import normalize_estimation_to_items
from glucotracker.infra.gemini.schemas import (
    EstimatedComponent,
    EstimatedItem,
    EstimationResult,
    ExtractedNutritionFacts,
    OptionalNutrientFact,
)


def _today_iso() -> str:
    """Return a current UTC datetime string for dashboard-today tests."""
    return datetime.now(UTC).isoformat()


def _manual_meal_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return an accepted manual meal payload."""
    return {
        "eaten_at": _today_iso(),
        "title": "Nutrient test meal",
        "source": "manual",
        "status": "accepted",
        "items": items,
    }


def _item(**overrides: Any) -> dict[str, Any]:
    """Return a valid item payload."""
    payload: dict[str, Any] = {
        "name": "Soup",
        "carbs_g": 10,
        "protein_g": 4,
        "fat_g": 2,
        "fiber_g": 1,
        "kcal": 74,
        "source_kind": "manual",
    }
    payload.update(overrides)
    return payload


def _nutrient(body: dict[str, Any], code: str) -> dict[str, Any]:
    """Return one nutrient row from an item or dashboard response."""
    return next(row for row in body["nutrients"] if row["nutrient_code"] == code)


def test_nutrient_definitions_are_seeded(api_client: TestClient) -> None:
    """GET /nutrients/definitions returns built-in nutrient definitions."""
    response = api_client.get("/nutrients/definitions")

    assert response.status_code == 200
    codes = {row["code"] for row in response.json()}
    assert {
        "sodium_mg",
        "caffeine_mg",
        "sugar_g",
        "potassium_mg",
        "iron_mg",
        "calcium_mg",
        "magnesium_mg",
    }.issubset(codes)


def test_unknown_nutrient_remains_null_and_not_counted_as_zero(
    api_client: TestClient,
) -> None:
    """Null nutrient values are unknown, not zero totals."""
    created = api_client.post(
        "/meals",
        json=_manual_meal_payload(
            [
                _item(
                    nutrients={
                        "sodium_mg": {
                            "amount": None,
                            "unit": "mg",
                            "source_kind": "manual",
                        }
                    }
                )
            ]
        ),
    )
    assert created.status_code == 201
    item = created.json()["items"][0]
    assert _nutrient(item, "sodium_mg")["amount"] is None

    dashboard = api_client.get("/dashboard/today")

    assert dashboard.status_code == 200
    sodium = _nutrient(dashboard.json(), "sodium_mg")
    assert sodium["amount"] is None
    assert sodium["known_item_count"] == 0
    assert sodium["total_item_count"] == 1
    assert sodium["coverage"] == 0


def test_manual_override_beats_restaurant_db(api_client: TestClient) -> None:
    """Manual nutrient override has higher priority than database values."""
    created = api_client.post(
        "/meals",
        json=_manual_meal_payload(
            [
                _item(
                    source_kind="restaurant_db",
                    nutrients={
                        "sodium_mg": {
                            "amount": 980,
                            "unit": "mg",
                            "source_kind": "restaurant_db",
                        }
                    },
                )
            ]
        ),
    ).json()
    item_id = created["items"][0]["id"]

    patched = api_client.patch(
        f"/meal_items/{item_id}",
        json={
            "nutrients": {
                "sodium_mg": {
                    "amount": 720,
                    "unit": "mg",
                    "source_kind": "manual",
                }
            }
        },
    )

    assert patched.status_code == 200
    sodium = _nutrient(patched.json(), "sodium_mg")
    assert sodium["amount"] == 720
    assert sodium["source_kind"] == "manual"


def test_label_per_100ml_caffeine_converts_to_package_total() -> None:
    """Backend scales visible per-100ml caffeine to the item volume."""
    items = normalize_estimation_to_items(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Energy drink",
                    scenario="LABEL_FULL",
                    extracted_facts=ExtractedNutritionFacts(
                        carbs_per_100ml=0,
                        protein_per_100ml=0,
                        fat_per_100ml=0,
                        fiber_per_100ml=0,
                        kcal_per_100ml=1,
                        visible_volume_ml=500,
                    ),
                    optional_nutrients={
                        "caffeine_mg": OptionalNutrientFact(
                            amount_per_100ml=32,
                            unit="mg",
                            confidence=0.95,
                        )
                    },
                    confidence=0.94,
                    confidence_reason="Label and can volume are visible.",
                )
            ]
        )
    )

    caffeine = items[0].nutrients["caffeine_mg"]
    amount = caffeine.amount if hasattr(caffeine, "amount") else caffeine["amount"]
    source_kind = (
        caffeine.source_kind
        if hasattr(caffeine, "source_kind")
        else caffeine["source_kind"]
    )
    assert amount == pytest.approx(160)
    assert source_kind == "label_calc"


def test_pattern_with_sodium_caffeine_creates_item_nutrients(
    api_client: TestClient,
) -> None:
    """Pattern nutrient defaults are copied into meal item nutrient rows."""
    pattern = api_client.post(
        "/patterns",
        json={
            "prefix": "bk",
            "key": "whopper",
            "display_name": "Whopper",
            "default_carbs_g": 51,
            "default_protein_g": 28,
            "default_fat_g": 35,
            "default_fiber_g": 3,
            "default_kcal": 635,
            "nutrients_json": {
                "sodium_mg": {"amount": 980, "unit": "mg"},
                "caffeine_mg": {"amount": 0, "unit": "mg"},
            },
            "aliases": ["whopper"],
        },
    ).json()

    meal = api_client.post(
        "/meals",
        json=_manual_meal_payload(
            [
                _item(
                    name="Whopper",
                    carbs_g=51,
                    protein_g=28,
                    fat_g=35,
                    fiber_g=3,
                    kcal=635,
                    source_kind="pattern",
                    pattern_id=pattern["id"],
                )
            ]
        ),
    )

    assert meal.status_code == 201
    nutrients = {
        row["nutrient_code"]: row for row in meal.json()["items"][0]["nutrients"]
    }
    assert nutrients["sodium_mg"]["amount"] == 980
    assert nutrients["sodium_mg"]["source_kind"] == "pattern"
    assert nutrients["caffeine_mg"]["amount"] == 0


def test_dashboard_nutrient_totals_include_coverage(
    api_client: TestClient,
) -> None:
    """Dashboard nutrient totals sum known values and expose coverage."""
    api_client.post(
        "/meals",
        json=_manual_meal_payload(
            [
                _item(
                    name="Known sodium",
                    nutrients={"sodium_mg": {"amount": 100, "unit": "mg"}},
                ),
                _item(
                    name="Unknown sodium",
                    nutrients={"sodium_mg": {"amount": None, "unit": "mg"}},
                ),
            ]
        ),
    )

    response = api_client.get("/dashboard/today")

    assert response.status_code == 200
    sodium = _nutrient(response.json(), "sodium_mg")
    assert sodium["amount"] == 100
    assert sodium["known_item_count"] == 1
    assert sodium["total_item_count"] == 2
    assert sodium["coverage"] == 0.5


def test_gemini_visual_plated_food_does_not_invent_sodium_or_caffeine() -> None:
    """PLATED Gemini visual estimates do not keep sodium/caffeine guesses."""
    items = normalize_estimation_to_items(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Chicken and potatoes",
                    scenario="PLATED",
                    grams_mid=300,
                    carbs_g_mid=34,
                    protein_g_mid=28,
                    fat_g_mid=12,
                    fiber_g_mid=5,
                    kcal_mid=360,
                    optional_nutrients={
                        "sodium_mg": OptionalNutrientFact(
                            amount=800,
                            unit="mg",
                            source_kind="photo_estimate",
                        ),
                        "caffeine_mg": OptionalNutrientFact(
                            amount=20,
                            unit="mg",
                            source_kind="photo_estimate",
                        ),
                    },
                    confidence=0.6,
                    confidence_reason="Visual estimate only.",
                )
            ]
        )
    )

    assert "sodium_mg" not in items[0].nutrients
    assert "caffeine_mg" not in items[0].nutrients


def test_plated_item_uses_component_totals_when_top_level_macros_missing() -> None:
    """PLATED items must fall back to component estimates when item totals are null."""
    items = normalize_estimation_to_items(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Cottage cheese with toppings",
                    display_name_ru="Творог со сметаной и маракуйей",
                    scenario="PLATED",
                    component_estimates=[
                        EstimatedComponent(
                            name_ru="Творог",
                            component_type="protein",
                            estimated_grams_mid=120,
                            carbs_g_mid=4.2,
                            protein_g_mid=21.6,
                            fat_g_mid=6,
                            kcal_mid=144,
                        ),
                        EstimatedComponent(
                            name_ru="Сметана",
                            component_type="sauce",
                            estimated_grams_mid=30,
                            carbs_g_mid=1,
                            protein_g_mid=0.8,
                            fat_g_mid=4.5,
                            kcal_mid=48,
                        ),
                        EstimatedComponent(
                            name_ru="Маракуйя",
                            component_type="vegetable",
                            estimated_grams_mid=30,
                            carbs_g_mid=4,
                            protein_g_mid=0.5,
                            fat_g_mid=0.1,
                            fiber_g_mid=3,
                            kcal_mid=20,
                        ),
                    ],
                    confidence=0.9,
                    confidence_reason="Visual estimate with user context.",
                )
            ]
        )
    )

    item = items[0]
    assert item.grams == pytest.approx(180)
    assert item.carbs_g == pytest.approx(9.2)
    assert item.protein_g == pytest.approx(22.9)
    assert item.fat_g == pytest.approx(10.6)
    assert item.fiber_g == pytest.approx(3)
    assert item.kcal == pytest.approx(212)
