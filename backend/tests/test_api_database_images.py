"""Database page API and meal thumbnail image tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _pattern_payload(**overrides: object) -> dict:
    payload = {
        "prefix": "bk",
        "key": "whopper",
        "display_name": "Whopper",
        "default_grams": 270,
        "default_carbs_g": 51,
        "default_protein_g": 28,
        "default_fat_g": 35,
        "default_fiber_g": 3,
        "default_kcal": 635,
        "source_url": "https://origin.bk.com/pdfs/nutrition.pdf",
        "image_url": "https://example.test/whopper.png",
        "aliases": ["воппер", "вопер", "whopper"],
    }
    payload.update(overrides)
    return payload


def _product_payload(**overrides: object) -> dict:
    payload = {
        "barcode": "4601234567890",
        "brand": "Example",
        "name": "Protein Drink",
        "default_grams": 330,
        "default_serving_text": "330 ml",
        "carbs_per_serving": 12,
        "protein_per_serving": 25,
        "fat_per_serving": 2,
        "fiber_per_serving": 1,
        "kcal_per_serving": 166,
        "source_kind": "manual",
        "image_url": "https://example.test/drink.png",
        "aliases": ["drink"],
    }
    payload.update(overrides)
    return payload


def test_meal_created_from_pattern_returns_thumbnail(api_client: TestClient) -> None:
    """Pattern-created meals expose thumbnail and item source image fields."""
    pattern = api_client.post("/patterns", json=_pattern_payload()).json()

    response = api_client.post(
        "/meals",
        json={
            "title": "Whopper",
            "source": "pattern",
            "items": [
                {
                    "name": "Whopper",
                    "carbs_g": 51,
                    "protein_g": 28,
                    "fat_g": 35,
                    "fiber_g": 3,
                    "kcal": 635,
                    "source_kind": "pattern",
                    "pattern_id": pattern["id"],
                }
            ],
        },
    )

    assert response.status_code == 201
    meal = response.json()
    assert meal["thumbnail_url"] == "https://example.test/whopper.png"
    assert meal["items"][0]["source_image_url"] == "https://example.test/whopper.png"
    assert meal["items"][0]["image_url"] == "https://example.test/whopper.png"


def test_meal_created_from_product_returns_thumbnail(api_client: TestClient) -> None:
    """Product-created meals expose product source images."""
    product = api_client.post("/products", json=_product_payload()).json()

    response = api_client.post(
        "/meals",
        json={
            "title": "Protein Drink",
            "source": "manual",
            "items": [
                {
                    "name": "Protein Drink",
                    "carbs_g": 12,
                    "protein_g": 25,
                    "fat_g": 2,
                    "fiber_g": 1,
                    "kcal": 166,
                    "source_kind": "product_db",
                    "product_id": product["id"],
                }
            ],
        },
    )

    assert response.status_code == 201
    meal = response.json()
    assert meal["thumbnail_url"] == "https://example.test/drink.png"
    assert meal["items"][0]["source_image_url"] == "https://example.test/drink.png"


def test_database_items_searches_aliases(api_client: TestClient) -> None:
    """The database page endpoint searches pattern aliases and returns images."""
    api_client.post("/patterns", json=_pattern_payload())
    api_client.post("/products", json=_product_payload())

    response = api_client.get("/database/items", params={"q": "воппер"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["kind"] == "restaurant"
    assert body["items"][0]["token"] == "bk:whopper"
    assert body["items"][0]["image_url"] == "https://example.test/whopper.png"


def test_database_items_can_filter_needs_review(api_client: TestClient) -> None:
    """Rows with incomplete quality data can be listed for review."""
    api_client.post("/patterns", json=_pattern_payload(image_url=None))

    response = api_client.get("/database/items", params={"needs_review": True})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert "нет картинки" in body["items"][0]["quality_warnings"]
