"""Database product deduplication tests."""

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import Product


def test_database_items_collapses_duplicate_photo_label_products(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """The database page does not show stale duplicate label products."""
    image_url = "/photos/photo-label-brownie/file"
    with Session(db_engine) as session:
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
        current = Product(
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
        session.add_all([old_duplicate, current])
        session.commit()

    response = api_client.get("/database/items", params={"q": "brownie"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["display_name"] == "Protein brownie Shagi"

    autocomplete = api_client.get("/autocomplete", params={"q": "brownie"})
    assert autocomplete.status_code == 200
    assert len(autocomplete.json()) == 1
    assert autocomplete.json()[0]["display_name"] == "Protein brownie Shagi"
