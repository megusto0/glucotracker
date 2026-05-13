"""Image serving headers for authenticated mobile clients."""

from fastapi.testclient import TestClient


def _meal_payload() -> dict:
    return {
        "eaten_at": "2026-04-28T08:00:00Z",
        "title": "Breakfast",
        "source": "manual",
        "items": [
            {
                "name": "Yogurt",
                "carbs_g": 8,
                "protein_g": 15,
                "fat_g": 4,
                "fiber_g": 0,
                "kcal": 128,
                "source_kind": "manual",
            }
        ],
    }


def test_photo_file_is_private_cacheable_inline(api_client: TestClient) -> None:
    meal = api_client.post("/meals", json=_meal_payload()).json()
    photo = api_client.post(
        f"/meals/{meal['id']}/photos",
        files={"file": ("meal.jpg", b"\xff\xd8fake-jpeg", "image/jpeg")},
    ).json()

    response = api_client.get(f"/photos/{photo['id']}/file")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=604800"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-type"].startswith("image/jpeg")


def test_photo_upload_accepts_content_type_parameters(api_client: TestClient) -> None:
    meal = api_client.post("/meals", json=_meal_payload()).json()

    response = api_client.post(
        f"/meals/{meal['id']}/photos",
        files={"file": ("meal.jpg", b"\xff\xd8fake-jpeg", "image/jpeg; charset=binary")},
    )

    assert response.status_code == 201
    assert response.json()["content_type"].startswith("image/jpeg")


def test_photo_upload_infers_supported_type_from_filename(api_client: TestClient) -> None:
    meal = api_client.post("/meals", json=_meal_payload()).json()

    response = api_client.post(
        f"/meals/{meal['id']}/photos",
        files={"file": ("meal.jpg", b"\xff\xd8fake-jpeg", "application/octet-stream")},
    )

    assert response.status_code == 201
    assert response.json()["content_type"].startswith("image/jpeg")


def test_product_image_file_is_private_cacheable_inline(api_client: TestClient) -> None:
    product = api_client.post(
        "/products",
        json={
            "name": "Crackers",
            "carbs_per_100g": 62,
            "protein_per_100g": 11,
            "fat_per_100g": 9,
            "kcal_per_100g": 410,
        },
    ).json()
    uploaded = api_client.post(
        f"/products/{product['id']}/image",
        files={"file": ("crackers.png", b"fake-png", "image/png")},
    )
    assert uploaded.status_code == 200

    response = api_client.get(f"/products/{product['id']}/image/file")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=604800"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-type"].startswith("image/png")
