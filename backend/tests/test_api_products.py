"""Product REST API tests."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import Product, ProductAlias


def product_payload(**overrides: object) -> dict:
    """Return a valid product create payload."""
    payload = {
        "barcode": "4601234567890",
        "brand": "Example Foods",
        "name": "Whole grain crackers",
        "default_grams": 30,
        "default_serving_text": "6 crackers",
        "carbs_per_100g": 62,
        "protein_per_100g": 11,
        "fat_per_100g": 9,
        "fiber_per_100g": 7,
        "kcal_per_100g": 410,
        "source_kind": "manual",
        "aliases": ["crackers"],
    }
    payload.update(overrides)
    return payload


def test_product_crud_and_search(api_client: TestClient) -> None:
    """Products can be created, listed, patched, fetched, and searched."""
    created_response = api_client.post("/products", json=product_payload())
    assert created_response.status_code == 201
    product = created_response.json()
    product_id = product["id"]
    assert product["aliases"] == ["crackers"]

    list_response = api_client.get("/products", params={"q": "Example"})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    patch_response = api_client.patch(
        f"/products/{product_id}",
        json={"name": "Seed crackers", "aliases": ["seed crackers"]},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Seed crackers"
    assert patch_response.json()["aliases"] == ["seed crackers"]

    get_response = api_client.get(f"/products/{product_id}")
    assert get_response.status_code == 200
    assert get_response.json()["barcode"] == "4601234567890"

    search_by_alias = api_client.get(
        "/products/search",
        params={"q": "seed", "limit": 20},
    )
    assert search_by_alias.status_code == 200
    assert search_by_alias.json()[0]["id"] == product_id

    search_by_barcode = api_client.get(
        "/products/search",
        params={"q": "4601234567890", "limit": 20},
    )
    assert search_by_barcode.status_code == 200
    assert search_by_barcode.json()[0]["id"] == product_id


def test_product_image_upload_updates_product_and_linked_meal_thumbnail(
    api_client: TestClient,
) -> None:
    """Product image uploads are served locally and inherited by meal rows."""
    created_response = api_client.post("/products", json=product_payload())
    assert created_response.status_code == 201
    product_id = created_response.json()["id"]

    upload_response = api_client.post(
        f"/products/{product_id}/image",
        files={"file": ("crackers.png", b"fake-image-bytes", "image/png")},
    )

    assert upload_response.status_code == 200
    image_url = upload_response.json()["image_url"]
    assert image_url == f"/products/{product_id}/image/file"

    file_response = api_client.get(image_url)
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("image/png")
    assert file_response.content == b"fake-image-bytes"

    meal_response = api_client.post(
        "/meals",
        json={
            "title": "Seed crackers",
            "source": "manual",
            "items": [
                {
                    "name": "Seed crackers",
                    "carbs_g": 0,
                    "protein_g": 0,
                    "fat_g": 0,
                    "fiber_g": 0,
                    "kcal": 0,
                    "source_kind": "product_db",
                    "product_id": product_id,
                }
            ],
        },
    )

    assert meal_response.status_code == 201
    meal = meal_response.json()
    assert meal["thumbnail_url"] == image_url
    assert meal["items"][0]["source_image_url"] == image_url


def test_product_patch_merges_duplicate_photo_label_products(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Renaming a photo-label product removes older duplicate DB rows."""
    image_url = "/photos/photo-label-brownie/file"
    with Session(db_engine) as session:
        target = Product(
            brand="Royal Cake",
            name="Protein brownie Shagi",
            default_grams=35,
            carbs_per_serving=8,
            protein_per_serving=4,
            fat_per_serving=11,
            fiber_per_serving=7,
            kcal_per_serving=144,
            source_kind="label_calc",
            image_url=image_url,
        )
        old_duplicate = Product(
            brand="Royal Cake",
            name="Biscuit sandwich Royal Cake",
            default_grams=35,
            carbs_per_serving=8,
            protein_per_serving=4,
            fat_per_serving=11,
            fiber_per_serving=7,
            kcal_per_serving=144,
            source_kind="label_calc",
            image_url=image_url,
            usage_count=1,
        )
        old_duplicate.aliases.append(ProductAlias(alias="biscuit sandwich"))
        session.add_all([target, old_duplicate])
        session.commit()
        target_id = str(target.id)

    response = api_client.patch(
        f"/products/{target_id}",
        json={"name": "Протеиновое брауни Shagi"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Протеиновое брауни Shagi"
    with Session(db_engine) as session:
        assert (
            session.scalar(
                select(func.count(Product.id)).where(Product.image_url == image_url)
            )
            == 1
        )
        product = session.scalar(select(Product).where(Product.image_url == image_url))
        assert product is not None
        assert product.name == "Протеиновое брауни Shagi"
        assert product.usage_count == 1
        assert [alias.alias for alias in product.aliases] == ["biscuit sandwich"]
