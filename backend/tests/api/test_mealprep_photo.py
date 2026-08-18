"""A photograph of a cooked batch, taken on the phone."""

from __future__ import annotations

import io
import sqlite3
import uuid

import pytest

from glucotracker.application.fridge_sync import FridgeIntegrationService


@pytest.fixture
def fridge_db(tmp_path, monkeypatch):
    """A fridge database with one batch of two containers."""
    path = tmp_path / "fridge.db"
    batch_id = str(uuid.uuid4())
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE meal_prep_batches (id TEXT PRIMARY KEY, image_url TEXT)")
    conn.execute(
        "CREATE TABLE meal_prep_containers (id TEXT PRIMARY KEY, batch_id TEXT, image_url TEXT)"
    )
    conn.execute("INSERT INTO meal_prep_batches VALUES (?, NULL)", (batch_id,))
    container_ids = [str(uuid.uuid4()) for _ in range(2)]
    for container_id in container_ids:
        conn.execute(
            "INSERT INTO meal_prep_containers VALUES (?, ?, NULL)",
            (container_id, batch_id),
        )
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        FridgeIntegrationService,
        "__init__",
        lambda self, settings=None: (
            setattr(self, "settings", None),
            setattr(self, "api_url", "http://127.0.0.1:8011"),
            setattr(self, "db_path", str(path)),
        )
        and None,
    )
    return batch_id, container_ids


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_photo_reaches_the_batch_and_every_container(api_client, fridge_db):
    batch_id, container_ids = fridge_db

    response = api_client.post(
        f"/fridge/mealpreps/{batch_id}/photo",
        files={"file": ("dish.png", io.BytesIO(PNG), "image/png")},
    )

    assert response.status_code == 201, response.text
    url = response.json()["url"]
    assert url == f"/fridge/mealpreps/{batch_id}/photo"

    service = FridgeIntegrationService()
    conn = sqlite3.connect(service.db_path)
    stored = conn.execute(
        "SELECT image_url FROM meal_prep_batches WHERE id = ?", (batch_id,)
    ).fetchone()[0]
    containers = [
        row[0]
        for row in conn.execute(
            "SELECT image_url FROM meal_prep_containers WHERE batch_id = ?", (batch_id,)
        )
    ]
    conn.close()

    assert stored == url
    # The dish is what was photographed, so every box of it gets the picture.
    assert containers == [url, url]


def test_a_container_id_resolves_to_its_batch(api_client, fridge_db):
    """The phone holds container ids, because that is what a lid code means."""
    batch_id, container_ids = fridge_db

    response = api_client.post(
        f"/fridge/mealpreps/{container_ids[0]}/photo",
        files={"file": ("dish.png", io.BytesIO(PNG), "image/png")},
    )

    assert response.status_code == 201, response.text
    assert response.json()["url"] == f"/fridge/mealpreps/{batch_id}/photo"


def test_unknown_batch_is_a_404(api_client, fridge_db):
    response = api_client.post(
        f"/fridge/mealpreps/{uuid.uuid4()}/photo",
        files={"file": ("dish.png", io.BytesIO(PNG), "image/png")},
    )

    assert response.status_code == 404
