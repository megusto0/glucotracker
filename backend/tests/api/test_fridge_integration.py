"""Tests for Fridge & MealPrep integration in GlucoTracker."""

import pytest
from fastapi.testclient import TestClient

from glucotracker.application.fridge_sync import (
    FridgeIntegrationService,
    FridgeItem,
    MealPrepItem,
)


def test_autocomplete_includes_available_fridge_and_mealprep_items(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify that available fridge items and mealpreps appear in autocomplete suggestions."""
    mock_fridge_items = [
        FridgeItem(
            id="lot-111",
            lot_id="lot-111",
            name="Йогурт Epica с ананасом",
            brand="Epica",
            unit="г",
            remaining_quantity=260.0,
            weight_grams=260.0,
            kcal_per_100g=120.0,
            protein_per_100g=5.7,
            fat_per_100g=4.8,
            carbs_per_100g=13.6,
            image_url="https://example.com/epica.jpg",
            days_to_expiry=5,
        ),
        FridgeItem(
            id="lot-222",
            lot_id="lot-222",
            name="Сыр Гауда",
            brand=None,
            unit="г",
            remaining_quantity=0.0,  # DEPLETED! Should be filtered out!
            weight_grams=0.0,
            kcal_per_100g=350.0,
            protein_per_100g=25.0,
            fat_per_100g=27.0,
            carbs_per_100g=0.0,
            image_url=None,
        ),
    ]

    mock_mealpreps = [
        MealPrepItem(
            container_id="cont-333",
            batch_id="batch-333",
            dish_name="Гречка с индейкой",
            public_code="MP01",
            net_weight_g=320.0,
            remaining_weight_g=320.0,
            kcal=480.0,
            protein=35.0,
            fat=12.0,
            carbs=55.0,
            image_url="https://example.com/mealprep.jpg",
        )
    ]

    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_inventory",
        lambda self, owner_id=None: [x for x in mock_fridge_items if x.remaining_quantity > 0],
    )
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_mealpreps",
        lambda self, owner_id=None: [x for x in mock_mealpreps if x.remaining_weight_g > 0],
    )

    # 1. Search for "Epica" -> should find available Fridge yogurt
    res = api_client.get("/autocomplete?q=epica")
    assert res.status_code == 200
    data = res.json()
    assert any(item["token"] == "fridge:lot-111" for item in data)
    epica_item = next(item for item in data if item["token"] == "fridge:lot-111")
    assert "Холодильник" in epica_item["subtitle"]
    assert "260 г" in epica_item["subtitle"]

    # 2. Search for depleted "Гауда" -> should NOT be found because remaining_quantity == 0
    res_gauda = api_client.get("/autocomplete?q=гауда")
    assert res_gauda.status_code == 200
    assert not any(item.get("token") == "fridge:lot-222" for item in res_gauda.json())

    # 3. Search for MealPrep "гречка" -> should find container MP01
    res_mp = api_client.get("/autocomplete?q=гречка")
    assert res_mp.status_code == 200
    assert any(item["token"] == "mp:cont-333" for item in res_mp.json())
    mp_item = next(item for item in res_mp.json() if item["token"] == "mp:cont-333")
    assert "Милпреп" in mp_item["subtitle"]
    assert "MP01" in mp_item["subtitle"]

    # 4. Search with prefix "fridge:" and "mp:"
    res_prefix_fridge = api_client.get("/autocomplete?q=fridge:йогурт")
    assert res_prefix_fridge.status_code == 200
    assert any(item["token"] == "fridge:lot-111" for item in res_prefix_fridge.json())

    res_prefix_mp = api_client.get("/autocomplete?q=mp:MP01")
    assert res_prefix_mp.status_code == 200
    assert any(item["token"] == "mp:cont-333" for item in res_prefix_mp.json())


def test_creating_meal_with_fridge_item_triggers_consumption(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify that creating/accepting a meal with fridge product consumes it in Fridge service."""
    consumed_events = []
    monkeypatch.setattr(
        FridgeIntegrationService,
        "consume_item",
        lambda self, lot_id=None, container_id=None, quantity=None, unit=None, meal_id=None, owner_id=None: (
            consumed_events.append({"lot_id": lot_id, "container_id": container_id, "quantity": quantity, "unit": unit}) or True
        ),
    )

    payload = {
        "title": "Полдник",
        "source": "manual",
        "status": "accepted",
        "eaten_at": "2026-08-18T16:00:00",
        "items": [
            {
                "name": "Йогурт Epica",
                "grams": 130.0,
                "carbs_g": 17.6,
                "protein_g": 7.4,
                "fat_g": 6.2,
                "kcal": 156.0,
                "source_kind": "fridge",
                "evidence": {
                    "fridge_lot_id": "lot-111",
                },
            },
            {
                "name": "Гречка с индейкой",
                "grams": 320.0,
                "carbs_g": 55.0,
                "protein_g": 35.0,
                "fat_g": 12.0,
                "kcal": 480.0,
                "source_kind": "meal_prep",
                "evidence": {
                    "mealprep_container_id": "cont-333",
                },
            },
        ],
    }

    res = api_client.post("/meals", json=payload)
    assert res.status_code == 201

    # Verify both consumption events were triggered
    assert len(consumed_events) == 2
    lot_consume = next(e for e in consumed_events if e["lot_id"] == "lot-111")
    assert lot_consume["quantity"] == 130.0
    assert lot_consume["unit"] == "g"

    cont_consume = next(e for e in consumed_events if e["container_id"] == "cont-333")
    assert cont_consume["quantity"] == 320.0
