"""Pattern, alias, seed, and autocomplete API tests."""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import Pattern, PatternAlias, Product
from glucotracker.infra.db.seed import load_pattern_seeds


def pattern_payload(**overrides: object) -> dict:
    """Return a valid pattern create payload."""
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
        "aliases": ["воппер", "вопер", "whopper", "vopper"],
    }
    payload.update(overrides)
    return payload


def product_payload(**overrides: object) -> dict:
    """Return a valid product create payload."""
    payload = {
        "barcode": "1234567890123",
        "brand": "Example",
        "name": "Whey Bar",
        "default_grams": 60,
        "default_serving_text": "1 bar",
        "carbs_per_100g": 40,
        "protein_per_100g": 30,
        "fat_per_100g": 12,
        "fiber_per_100g": 6,
        "kcal_per_100g": 390,
        "source_kind": "manual",
        "image_url": "https://example.test/whey-bar.png",
        "aliases": ["protein bar", "батончик"],
    }
    payload.update(overrides)
    return payload


def _create_pattern(api_client: TestClient, **overrides: object) -> dict:
    """Create a pattern through the API."""
    response = api_client.post("/patterns", json=pattern_payload(**overrides))
    assert response.status_code == 201
    return response.json()


def test_patterns_search_prefix_only(api_client: TestClient) -> None:
    """Searching `prefix:` returns active patterns in that namespace."""
    _create_pattern(api_client)
    _create_pattern(
        api_client,
        key="cheeseburger",
        display_name="Cheeseburger",
        aliases=["чизбургер"],
    )

    response = api_client.get("/patterns/search", params={"q": "bk:", "limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert {item["key"] for item in body} == {"whopper", "cheeseburger"}


def test_patterns_search_prefix_partial_query(api_client: TestClient) -> None:
    """Searching prefix plus partial key finds matching patterns."""
    _create_pattern(api_client)

    response = api_client.get("/patterns/search", params={"q": "bk:who"})

    assert response.status_code == 200
    assert response.json()[0]["key"] == "whopper"


def test_patterns_search_russian_alias_match(api_client: TestClient) -> None:
    """Russian aliases are matched case-insensitively by prefix."""
    _create_pattern(api_client)

    response = api_client.get("/patterns/search", params={"q": "bk:во"})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["key"] == "whopper"
    assert body[0]["matched_alias"] == "воппер"


def test_patterns_search_sorts_by_usage_count(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Equivalent prefix matches are sorted by usage count."""
    whopper = _create_pattern(api_client, aliases=["воппер"])
    jr = _create_pattern(
        api_client,
        key="whopper_jr",
        display_name="Whopper Jr",
        aliases=["воппер джр"],
    )
    with Session(db_engine) as session:
        session.get(Pattern, UUID(whopper["id"])).usage_count = 1
        session.get(Pattern, UUID(jr["id"])).usage_count = 5
        session.commit()

    response = api_client.get("/patterns/search", params={"q": "bk:who"})

    assert response.status_code == 200
    assert response.json()[0]["key"] == "whopper_jr"


def test_archived_patterns_hidden(api_client: TestClient) -> None:
    """Soft-deleted patterns do not appear in search."""
    pattern = _create_pattern(api_client)

    delete_response = api_client.delete(f"/patterns/{pattern['id']}")
    search_response = api_client.get("/patterns/search", params={"q": "bk:who"})

    assert delete_response.status_code == 200
    assert search_response.status_code == 200
    assert search_response.json() == []


def test_seed_loader_idempotent(db_engine: Engine) -> None:
    """Pattern seed loading can run repeatedly without duplicate rows."""
    with Session(db_engine) as session:
        loaded_first = load_pattern_seeds(session=session)
        loaded_second = load_pattern_seeds(session=session)
        pattern_count = session.scalar(select(func.count(Pattern.id)))
        alias_count = session.scalar(select(func.count(PatternAlias.id)))

    assert loaded_first >= 1
    assert loaded_second == loaded_first
    assert pattern_count == loaded_first
    assert alias_count is not None
    assert alias_count >= loaded_first


def test_autocomplete_returns_patterns_and_products(api_client: TestClient) -> None:
    """Unified autocomplete returns both pattern and product suggestions."""
    _create_pattern(api_client)
    product = api_client.post("/products", json=product_payload()).json()

    response = api_client.get("/autocomplete", params={"q": "w", "limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert any(
        item["kind"] == "pattern" and item["token"] == "bk:whopper" for item in body
    )
    assert any(
        item["kind"] == "product" and item["id"] == product["id"] for item in body
    )
    assert any(
        item["kind"] == "pattern"
        and item["token"] == "bk:whopper"
        and item["image_url"] == "https://example.test/whopper.png"
        for item in body
    )
    assert any(
        item["kind"] == "product"
        and item["id"] == product["id"]
        and item["image_url"] == "https://example.test/whey-bar.png"
        for item in body
    )


def test_autocomplete_prefix_prefers_pattern_namespace(api_client: TestClient) -> None:
    """Prefix autocomplete searches matching pattern namespace."""
    _create_pattern(api_client)

    response = api_client.get("/autocomplete", params={"q": "bk:во", "limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["kind"] == "pattern"
    assert body[0]["token"] == "bk:whopper"
    assert body[0]["matched_alias"] == "воппер"


def test_autocomplete_product_prefix_searches_saved_products(
    api_client: TestClient,
) -> None:
    """Product namespaces search saved products instead of pattern prefixes."""
    product = api_client.post(
        "/products",
        json=product_payload(
            name="Сырок глазированный",
            brand="Example",
            aliases=["сырок", "глазированный сырок"],
        ),
    ).json()

    product_response = api_client.get(
        "/autocomplete",
        params={"q": "product:сыр", "limit": 20},
    )
    my_response = api_client.get(
        "/autocomplete",
        params={"q": "my:сыр", "limit": 20},
    )

    assert product_response.status_code == 200
    assert my_response.status_code == 200
    assert product_response.json()[0]["kind"] == "product"
    assert product_response.json()[0]["id"] == product["id"]
    assert product_response.json()[0]["matched_alias"] == "сырок"
    assert my_response.json()[0]["id"] == product["id"]


def test_autocomplete_plain_query_finds_saved_product_without_prefix(
    api_client: TestClient,
) -> None:
    """Plain autocomplete searches saved products by Unicode names and aliases."""
    product = api_client.post(
        "/products",
        json=product_payload(
            name='Сырок глазированный "Эффер"',
            brand="Эффер",
            aliases=["Глазированный сырок", "Творожный сырок"],
        ),
    ).json()

    response = api_client.get("/autocomplete", params={"q": "сырок", "limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["kind"] == "product"
    assert body[0]["id"] == product["id"]


def test_autocomplete_plain_query_prioritizes_saved_product_over_restaurant(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Saved products rank above restaurant rows for the same plain query."""
    product = api_client.post(
        "/products",
        json=product_payload(
            name="Сырок глазированный",
            aliases=["сырок"],
        ),
    ).json()
    pattern = _create_pattern(
        api_client,
        key="cheese_snack",
        display_name="Ресторанный сырок",
        aliases=["сырок"],
    )
    with Session(db_engine) as session:
        session.get(Pattern, UUID(pattern["id"])).usage_count = 99
        session.commit()

    response = api_client.get("/autocomplete", params={"q": "сырок", "limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["kind"] == "product"
    assert body[0]["id"] == product["id"]


def test_autocomplete_my_prefix_searches_products_and_personal_patterns_only(
    api_client: TestClient,
) -> None:
    """The my: namespace excludes restaurant rows but includes saved items."""
    product = api_client.post(
        "/products",
        json=product_payload(name="Сырок глазированный", aliases=["сырок"]),
    ).json()
    personal = _create_pattern(
        api_client,
        prefix="my",
        key="syrok_home",
        display_name="Домашний сырок",
        aliases=["сырок"],
    )
    _create_pattern(
        api_client,
        key="cheese_snack",
        display_name="BK сырок",
        aliases=["сырок"],
    )

    response = api_client.get("/autocomplete", params={"q": "my:сырок", "limit": 20})

    assert response.status_code == 200
    tokens = {item["token"] for item in response.json()}
    ids = {item["id"] for item in response.json()}
    assert product["id"] in ids
    assert personal["id"] in ids
    assert "bk:cheese_snack" not in tokens


def test_autocomplete_plain_query_finds_restaurant_alias_without_prefix(
    api_client: TestClient,
) -> None:
    """Restaurant aliases are available without typing the namespace."""
    _create_pattern(api_client)

    response = api_client.get("/autocomplete", params={"q": "воппер", "limit": 20})

    assert response.status_code == 200
    assert response.json()[0]["token"] == "bk:whopper"


def test_usage_counters_increment_for_patterns_and_products(
    api_client: TestClient,
) -> None:
    """Creating meal items with pattern_id/product_id increments usage counters."""
    pattern = _create_pattern(api_client)
    product = api_client.post("/products", json=product_payload()).json()

    meal = api_client.post(
        "/meals",
        json={
            "title": "Shortcut meal",
            "source": "manual",
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
                },
                {
                    "name": "Whey Bar",
                    "carbs_g": 24,
                    "protein_g": 18,
                    "fat_g": 7.2,
                    "fiber_g": 3.6,
                    "kcal": 234,
                    "source_kind": "product_db",
                    "product_id": product["id"],
                },
            ],
        },
    )

    assert meal.status_code == 201
    assert api_client.get(f"/patterns/{pattern['id']}").json()["usage_count"] == 1
    assert api_client.get(f"/products/{product['id']}").json()["usage_count"] == 1


def test_product_quantity_is_calculated_from_product_database(
    api_client: TestClient,
) -> None:
    """Product quantity is backend-calculated from saved product values."""
    product = api_client.post("/products", json=product_payload()).json()

    response = api_client.post(
        "/meals",
        json={
            "title": "Two bars",
            "source": "manual",
            "items": [
                {
                    "name": "Whey Bar",
                    "carbs_g": 0,
                    "protein_g": 0,
                    "fat_g": 0,
                    "fiber_g": 0,
                    "kcal": 0,
                    "source_kind": "product_db",
                    "product_id": product["id"],
                    "evidence": {"quantity": 2},
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    item = body["items"][0]
    assert item["grams"] == 120
    assert item["serving_text"] == "2 шт"
    assert item["carbs_g"] == 48
    assert item["protein_g"] == 36
    assert item["fat_g"] == 14.4
    assert item["fiber_g"] == 7.2
    assert item["kcal"] == 468
    assert body["total_carbs_g"] == 48
    assert body["total_kcal"] == 468


def test_product_from_label_updates_existing_barcode(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """POST /products/from_label upserts by barcode."""
    first = api_client.post("/products/from_label", json=product_payload()).json()
    second = api_client.post(
        "/products/from_label",
        json=product_payload(name="Updated Whey Bar", aliases=["updated"]),
    ).json()

    with Session(db_engine) as session:
        product_count = session.scalar(select(func.count(Product.id)))

    assert first["id"] == second["id"]
    assert second["name"] == "Updated Whey Bar"
    assert second["aliases"] == ["updated"]
    assert product_count == 1
