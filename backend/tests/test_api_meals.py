"""Meal REST API tests."""

from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import MealItem, Product


def meal_payload(**overrides: object) -> dict:
    """Return a valid meal create payload."""
    payload = {
        "eaten_at": "2026-04-28T08:00:00Z",
        "title": "Breakfast",
        "note": "manual note",
        "source": "manual",
        "items": [
            {
                "name": "Yogurt",
                "brand": "Plain",
                "grams": 150,
                "carbs_g": 8,
                "protein_g": 15,
                "fat_g": 4,
                "fiber_g": 0,
                "kcal": 128,
                "source_kind": "manual",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_full_crud_lifecycle_for_meals(api_client: TestClient) -> None:
    """Create, read, update, mutate items, and delete a meal."""
    create_response = api_client.post("/meals", json=meal_payload())
    assert create_response.status_code == 201
    meal = create_response.json()
    meal_id = meal["id"]
    assert meal["status"] == "accepted"
    assert meal["total_carbs_g"] == 8

    get_response = api_client.get(f"/meals/{meal_id}")
    assert get_response.status_code == 200
    assert get_response.json()["items"][0]["name"] == "Yogurt"

    patch_response = api_client.patch(
        f"/meals/{meal_id}",
        json={"title": "Updated breakfast", "note": "corrected"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Updated breakfast"

    item_response = api_client.post(
        f"/meals/{meal_id}/items",
        json={
            "name": "Toast",
            "carbs_g": 20,
            "protein_g": 4,
            "fat_g": 2,
            "fiber_g": 3,
            "kcal": 114,
            "source_kind": "manual",
        },
    )
    assert item_response.status_code == 201
    item_id = item_response.json()["id"]

    patched_item = api_client.patch(
        f"/meal_items/{item_id}",
        json={"carbs_g": 22, "kcal": 122},
    )
    assert patched_item.status_code == 200
    assert patched_item.json()["carbs_g"] == 22

    delete_item = api_client.delete(f"/meal_items/{item_id}")
    assert delete_item.status_code == 200
    assert delete_item.json() == {"deleted": True}

    meal_after_item_delete = api_client.get(f"/meals/{meal_id}").json()
    assert len(meal_after_item_delete["items"]) == 1
    assert meal_after_item_delete["total_carbs_g"] == 8

    delete_response = api_client.delete(f"/meals/{meal_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert api_client.get(f"/meals/{meal_id}").status_code == 404


def test_cascade_delete_removes_items(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Deleting a meal cascades to meal_items."""
    created = api_client.post("/meals", json=meal_payload()).json()

    assert api_client.delete(f"/meals/{created['id']}").status_code == 200

    with Session(db_engine) as session:
        item_count = session.scalar(select(func.count(MealItem.id)))
    assert item_count == 0


def test_patch_updates_updated_at(api_client: TestClient) -> None:
    """Patching a meal advances updated_at."""
    created = api_client.post("/meals", json=meal_payload()).json()
    before = datetime.fromisoformat(created["updated_at"])

    patched = api_client.patch(
        f"/meals/{created['id']}",
        json={"note": "patched note"},
    ).json()
    after = datetime.fromisoformat(patched["updated_at"])

    assert after > before


def test_q_search_finds_note_and_item_name(api_client: TestClient) -> None:
    """Meal search checks meal notes and item names."""
    api_client.post("/meals", json=meal_payload(note="contains kiwi"))
    api_client.post(
        "/meals",
        json=meal_payload(
            title="Lunch",
            note="other",
            items=[
                {
                    "name": "Buckwheat",
                    "carbs_g": 30,
                    "protein_g": 6,
                    "fat_g": 2,
                    "fiber_g": 4,
                    "kcal": 162,
                    "source_kind": "manual",
                }
            ],
        ),
    )

    note_results = api_client.get("/meals", params={"q": "kiwi"}).json()
    item_results = api_client.get("/meals", params={"q": "Buckwheat"}).json()

    assert note_results["total"] == 1
    assert note_results["items"][0]["note"] == "contains kiwi"
    assert item_results["total"] == 1
    assert item_results["items"][0]["items"][0]["name"] == "Buckwheat"


def test_replace_meal_items_recalculates_totals(api_client: TestClient) -> None:
    """PUT /meals/{id}/items replaces all items atomically."""
    created = api_client.post("/meals", json=meal_payload()).json()

    replaced = api_client.put(
        f"/meals/{created['id']}/items",
        json=[
            {
                "name": "Rice",
                "carbs_g": 45,
                "protein_g": 4,
                "fat_g": 1,
                "fiber_g": 1,
                "kcal": 205,
                "source_kind": "manual",
            }
        ],
    )

    assert replaced.status_code == 200
    body = replaced.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Rice"
    assert body["total_carbs_g"] == 45
    assert body["total_kcal"] == 205


def test_create_meal_from_item_weight_scales_source_item(
    api_client: TestClient,
) -> None:
    """A historical item can be repeated at a new gram weight."""
    created = api_client.post(
        "/meals",
        json=meal_payload(
            title="Кусочек торта",
            items=[
                {
                    "name": "Кусочек торта",
                    "grams": 117,
                    "carbs_g": 35.1,
                    "protein_g": 5.9,
                    "fat_g": 14,
                    "fiber_g": 1.2,
                    "kcal": 280,
                    "source_kind": "manual",
                }
            ],
        ),
    ).json()
    item_id = created["items"][0]["id"]
    photo = api_client.post(
        f"/meals/{created['id']}/photos",
        files={"file": ("cake.jpg", b"\xff\xd8fake-jpeg", "image/jpeg")},
    ).json()

    response = api_client.post(
        f"/meal_items/{item_id}/copy_by_weight",
        json={"grams": 127, "eaten_at": "2026-04-30T21:45:00"},
    )

    assert response.status_code == 201
    body = response.json()
    item = body["items"][0]
    assert body["status"] == "accepted"
    assert body["title"] == "Кусочек торта"
    assert item["grams"] == 127
    assert item["serving_text"] == "127 г"
    assert item["photo_id"] == photo["id"]
    assert body["thumbnail_url"] == f"/photos/{photo['id']}/file"
    assert item["carbs_g"] == pytest.approx(38.1)
    assert item["protein_g"] == pytest.approx(6.4)
    assert item["fat_g"] == pytest.approx(15.2)
    assert item["kcal"] == pytest.approx(303.9)
    assert body["total_carbs_g"] == pytest.approx(38.1)
    assert item["evidence"]["scaled_from_history"]["source_grams"] == 117
    assert item["evidence"]["scaled_from_history"]["target_grams"] == 127


def test_patch_item_grams_rescales_macros_on_backend(
    api_client: TestClient,
) -> None:
    """Changing only grams keeps macro math on the backend."""
    created = api_client.post(
        "/meals",
        json=meal_payload(
            title="Кусочек торта",
            items=[
                {
                    "name": "Кусочек торта",
                    "grams": 117,
                    "carbs_g": 35.1,
                    "protein_g": 5.9,
                    "fat_g": 14,
                    "fiber_g": 1.2,
                    "kcal": 280,
                    "source_kind": "manual",
                }
            ],
        ),
    ).json()
    item_id = created["items"][0]["id"]

    response = api_client.patch(f"/meal_items/{item_id}", json={"grams": 127})

    assert response.status_code == 200
    item = response.json()
    assert item["grams"] == 127
    assert item["serving_text"] == "127 г"
    assert item["carbs_g"] == pytest.approx(38.1)
    assert item["protein_g"] == pytest.approx(6.4)
    assert item["fat_g"] == pytest.approx(15.2)
    assert item["kcal"] == pytest.approx(303.9)

    meal = api_client.get(f"/meals/{created['id']}").json()
    assert meal["total_carbs_g"] == pytest.approx(38.1)
    assert meal["total_kcal"] == pytest.approx(303.9)


def test_accept_meal_draft_replaces_items_and_accepts(api_client: TestClient) -> None:
    """POST /meals/{id}/accept is the canonical draft acceptance endpoint."""
    created = api_client.post(
        "/meals",
        json=meal_payload(source="photo", status="draft", items=[]),
    ).json()
    assert created["status"] == "draft"

    accepted = api_client.post(
        f"/meals/{created['id']}/accept",
        json={
            "items": [
                {
                    "name": "Pasta",
                    "carbs_g": 68,
                    "protein_g": 12,
                    "fat_g": 5,
                    "fiber_g": 4,
                    "kcal": 365,
                    "source_kind": "photo_estimate",
                    "confidence": 0.72,
                }
            ]
        },
    )

    assert accepted.status_code == 200
    body = accepted.json()
    assert body["status"] == "accepted"
    assert body["total_carbs_g"] == 68
    assert body["total_kcal"] == 365


def test_accept_label_calc_item_remembers_product(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Accepted label calculations are saved to the local product database."""
    created = api_client.post(
        "/meals",
        json=meal_payload(source="photo", status="draft", items=[]),
    ).json()
    photo = api_client.post(
        f"/meals/{created['id']}/photos",
        files={"file": ("label.jpg", b"\xff\xd8fake-jpeg", "image/jpeg")},
    ).json()

    accepted = api_client.post(
        f"/meals/{created['id']}/accept",
        json={
            "items": [
                {
                    "name": "Бисквит-сэндвич",
                    "brand": "Крокотыш",
                    "grams": 60,
                    "serving_text": "×2 упаковки · 30 г каждая",
                    "carbs_g": 37.2,
                    "protein_g": 2.7,
                    "fat_g": 9.6,
                    "fiber_g": 0,
                    "kcal": 246,
                    "source_kind": "label_calc",
                    "calculation_method": "label_split_visible_weight_backend_calc",
                    "assumptions": ["Обе упаковки считаются одинаковым продуктом"],
                    "evidence": {
                        "nutrition_per_100g": {
                            "carbs_g": 62,
                            "protein_g": 4.5,
                            "fat_g": 16,
                            "fiber_g": None,
                            "kcal": 410,
                        },
                        "count_detected": 2,
                        "net_weight_per_unit_g": 30,
                        "total_weight_g": 60,
                    },
                    "photo_id": photo["id"],
                }
            ]
        },
    )

    assert accepted.status_code == 200
    accepted_body = accepted.json()
    product_id = accepted_body["items"][0]["product_id"]
    assert product_id is not None

    with Session(db_engine) as session:
        product = session.get(Product, UUID(product_id))
        assert product is not None
        assert product.name == "Бисквит-сэндвич"
        assert product.brand == "Крокотыш"
        assert product.default_grams == 30
        assert product.default_serving_text == "1 упаковка"
        assert product.carbs_per_100g == 62
        assert product.protein_per_100g == 4.5
        assert product.fat_per_100g == 16
        assert product.kcal_per_100g == 410
        assert product.carbs_per_serving == 18.6
        assert product.protein_per_serving == 1.3
        assert product.fat_per_serving == 4.8
        assert product.kcal_per_serving == 123
        assert product.image_url == f"/photos/{photo['id']}/file"
        assert product.usage_count == 1

    database = api_client.get("/database/items", params={"q": "Бисквит"})
    assert database.status_code == 200
    rows = database.json()["items"]
    row = next(row for row in rows if row["display_name"] == "Бисквит-сэндвич")
    assert row["image_url"] == f"/photos/{photo['id']}/file"


def test_accept_label_calc_recalculates_per_100ml_payload_from_evidence(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Accepted label items use backend evidence math, not client totals."""
    created = api_client.post(
        "/meals",
        json=meal_payload(source="photo", status="draft", items=[]),
    ).json()
    photo = api_client.post(
        f"/meals/{created['id']}/photos",
        files={"file": ("cola.jpg", b"\xff\xd8fake-jpeg", "image/jpeg")},
    ).json()

    accepted = api_client.post(
        f"/meals/{created['id']}/accept",
        json={
            "items": [
                {
                    "name": "Кола Ориджинал",
                    "brand": "Черноголовка",
                    "grams": 330,
                    "serving_text": "330 ml",
                    "carbs_g": 15515.51,
                    "protein_g": 999,
                    "fat_g": 999,
                    "fiber_g": 999,
                    "kcal": 999,
                    "source_kind": "label_calc",
                    "calculation_method": "label_assumed_weight_backend_calc",
                    "evidence": {
                        "identified_barcode": "4602441024742",
                        "extracted_facts": {
                            "carbs_per_100ml": 4.7,
                            "protein_per_100ml": 0,
                            "fat_per_100ml": 0,
                            "fiber_per_100ml": 0,
                            "kcal_per_100ml": 19,
                            "assumed_volume_ml": 330,
                        },
                        "nutrition_per_100g": {
                            "carbs_g": 4.7,
                            "protein_g": 0,
                            "fat_g": 0,
                            "fiber_g": None,
                            "kcal": 19,
                        },
                    },
                    "photo_id": photo["id"],
                }
            ]
        },
    )

    assert accepted.status_code == 200
    body = accepted.json()
    item = body["items"][0]
    assert item["carbs_g"] == pytest.approx(15.51)
    assert item["protein_g"] == pytest.approx(0)
    assert item["fat_g"] == pytest.approx(0)
    assert item["fiber_g"] == pytest.approx(0)
    assert item["kcal"] == pytest.approx(62.7)
    assert body["total_carbs_g"] == pytest.approx(15.51)
    assert body["total_kcal"] == pytest.approx(62.7)

    with Session(db_engine) as session:
        product = session.get(Product, UUID(item["product_id"]))
        assert product is not None
        assert product.carbs_per_100g == pytest.approx(4.7)
        assert product.carbs_per_serving == pytest.approx(15.5)
        stored_item = session.get(MealItem, UUID(item["id"]))
        assert stored_item is not None
        assert stored_item.carbs_g == pytest.approx(15.51)


def test_product_db_meal_backfills_missing_product_image_from_history(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """A saved product with an old missing image reuses previous photo evidence."""
    source_meal = api_client.post(
        "/meals",
        json=meal_payload(
            title="Photo snack",
            source="photo",
            status="draft",
            items=[],
        ),
    ).json()
    photo = api_client.post(
        f"/meals/{source_meal['id']}/photos",
        files={"file": ("snack.jpg", b"\xff\xd8fake-jpeg", "image/jpeg")},
    ).json()
    accepted = api_client.post(
        f"/meals/{source_meal['id']}/accept",
        json={
            "items": [
                {
                    "name": "Cheese snack",
                    "brand": "Example",
                    "grams": 40,
                    "serving_text": "1 pc",
                    "carbs_g": 27,
                    "protein_g": 7,
                    "fat_g": 17,
                    "fiber_g": 0,
                    "kcal": 293,
                    "source_kind": "label_calc",
                    "calculation_method": "label_visible_weight_backend_calc",
                    "evidence": {
                        "nutrition_per_100g": {
                            "carbs_g": 67.5,
                            "protein_g": 17.5,
                            "fat_g": 42.5,
                            "fiber_g": None,
                            "kcal": 732.5,
                        },
                        "net_weight_per_unit_g": 40,
                    },
                    "photo_id": photo["id"],
                }
            ]
        },
    ).json()
    product_id = accepted["items"][0]["product_id"]

    with Session(db_engine) as session:
        product = session.get(Product, UUID(product_id))
        assert product is not None
        product.image_url = None
        session.commit()

    created = api_client.post(
        "/meals",
        json=meal_payload(
            title="From product",
            source="manual",
            status="accepted",
            items=[
                {
                    "name": "Cheese snack",
                    "carbs_g": 0,
                    "protein_g": 0,
                    "fat_g": 0,
                    "fiber_g": 0,
                    "kcal": 0,
                    "source_kind": "product_db",
                    "product_id": product_id,
                }
            ],
        ),
    )

    assert created.status_code == 201
    body = created.json()
    expected_url = f"/photos/{photo['id']}/file"
    assert body["thumbnail_url"] == expected_url
    assert body["items"][0]["source_image_url"] == expected_url
    with Session(db_engine) as session:
        product = session.get(Product, UUID(product_id))
        assert product is not None
        assert product.image_url == expected_url


def test_remember_product_relinks_old_label_item_by_photo_image(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Old label items without product_id still update the saved product by photo."""
    meal = api_client.post(
        "/meals",
        json=meal_payload(
            title="Photo label",
            source="photo",
            status="draft",
            items=[],
        ),
    ).json()
    photo = api_client.post(
        f"/meals/{meal['id']}/photos",
        files={"file": ("brownie.jpg", b"\xff\xd8fake-jpeg", "image/jpeg")},
    ).json()
    accepted = api_client.post(
        f"/meals/{meal['id']}/accept",
        json={
            "items": [
                {
                    "name": "Wrong label name",
                    "brand": "Shagi",
                    "grams": 40,
                    "serving_text": "1 pc",
                    "carbs_g": 22.1,
                    "protein_g": 3,
                    "fat_g": 2.45,
                    "fiber_g": 1.1,
                    "kcal": 124,
                    "source_kind": "label_calc",
                    "calculation_method": "label_visible_weight_backend_calc",
                    "evidence": {
                        "nutrition_per_100g": {
                            "carbs_g": 55.25,
                            "protein_g": 7.5,
                            "fat_g": 6.125,
                            "fiber_g": 2.75,
                            "kcal": 310,
                        },
                        "net_weight_per_unit_g": 40,
                    },
                    "photo_id": photo["id"],
                }
            ]
        },
    ).json()
    item_id = accepted["items"][0]["id"]
    product_id = accepted["items"][0]["product_id"]

    with Session(db_engine) as session:
        item = session.get(MealItem, UUID(item_id))
        assert item is not None
        item.product_id = None
        item.name = "Protein brownie Shagi"
        session.commit()

    response = api_client.post(
        f"/meal_items/{item_id}/remember_product",
        json={"aliases": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == product_id
    assert body["name"] == "Protein brownie Shagi"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count(Product.id))) == 1
        item = session.get(MealItem, UUID(item_id))
        assert item is not None
        assert item.product_id == UUID(product_id)
        product = session.get(Product, UUID(product_id))
        assert product is not None
        assert product.image_url == f"/photos/{photo['id']}/file"


def test_remember_product_endpoint_adds_user_aliases(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """A confirmed label item can be explicitly saved with aliases."""
    created = api_client.post(
        "/meals",
        json=meal_payload(
            title="Сырок",
            source="manual",
            status="accepted",
            items=[
                {
                    "name": "Сырок глазированный",
                    "brand": "Example",
                    "grams": 40,
                    "serving_text": "1 шт",
                    "carbs_g": 27,
                    "protein_g": 7,
                    "fat_g": 17,
                    "fiber_g": 0,
                    "kcal": 293,
                    "source_kind": "label_calc",
                    "calculation_method": "label_visible_weight_backend_calc",
                    "evidence": {
                        "nutrition_per_100g": {
                            "carbs_g": 67.5,
                            "protein_g": 17.5,
                            "fat_g": 42.5,
                            "fiber_g": None,
                            "kcal": 732.5,
                        },
                        "net_weight_per_unit_g": 40,
                    },
                }
            ],
        ),
    ).json()
    item_id = created["items"][0]["id"]

    response = api_client.post(
        f"/meal_items/{item_id}/remember_product",
        json={"aliases": ["творожный сырок"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Сырок глазированный"
    assert "сырок" in body["aliases"]
    assert "глазированный сырок" in body["aliases"]
    assert "творожный сырок" in body["aliases"]
    with Session(db_engine) as session:
        product_count = session.scalar(select(func.count(Product.id)))
    assert product_count == 1

    autocomplete = api_client.get("/autocomplete", params={"q": "сырок"})
    assert autocomplete.status_code == 200
    assert any(
        item["kind"] == "product" and item["id"] == body["id"]
        for item in autocomplete.json()
    )


def test_discard_meal_sets_discarded(api_client: TestClient) -> None:
    """POST /meals/{id}/discard marks the meal discarded."""
    created = api_client.post(
        "/meals",
        json=meal_payload(source="photo", status="draft", items=[]),
    ).json()

    discarded = api_client.post(f"/meals/{created['id']}/discard")

    assert discarded.status_code == 200
    assert discarded.json()["status"] == "discarded"


def test_meal_filters_status_and_date_range(api_client: TestClient) -> None:
    """List filters include status and from/to ranges."""
    api_client.post("/meals", json=meal_payload())
    api_client.post(
        "/meals",
        json=meal_payload(
            eaten_at="2026-04-29T08:00:00Z",
            source="photo",
            status="draft",
            items=[],
        ),
    )

    results = api_client.get(
        "/meals",
        params={
            "status": "accepted",
            "from": "2026-04-28T00:00:00Z",
            "to": "2026-04-28T23:59:59Z",
        },
    )

    assert results.status_code == 200
    assert results.json()["total"] == 1
    assert UUID(results.json()["items"][0]["id"])
