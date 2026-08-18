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


def test_delete_survives_a_mirror_that_will_not_answer(api_client, monkeypatch):
    """Deleting your own entry cannot depend on Nightscout being reachable.

    It used to raise out of the endpoint, so the phone's outbox saw a failed
    request, retried it, and the entry stayed on screen in the queue.
    """
    from glucotracker.api.routers import meals as meals_router

    created = api_client.post(
        "/meals",
        json={
            "eaten_at": "2026-08-18T12:00:00",
            "source": "manual",
            "title": "Азу с чечевицей",
            "items": [{"name": "Азу с чечевицей", "grams": 300, "carbs_g": 40}],
        },
    )
    assert created.status_code == 201, created.text
    meal_id = created.json()["id"]

    async def exploding_mirror(service, meal, *, commit=False):
        raise RuntimeError("Nightscout unreachable")

    monkeypatch.setattr(
        meals_router.NightscoutSyncService,
        "mirror_meal_delete",
        exploding_mirror,
        raising=False,
    )

    response = api_client.delete(f"/meals/{meal_id}")

    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True
    assert api_client.get(f"/meals/{meal_id}").status_code == 404


def test_deleting_a_fridge_entry_asks_the_fridge_for_its_stock_back(
    api_client, monkeypatch
):
    """An entry added by mistake must not take its stock with it."""
    from glucotracker.application import fridge_sync

    asked: list[str] = []

    def fake_revert(self, meal_id, owner_id=None):
        asked.append(str(meal_id))
        return ""

    monkeypatch.setattr(
        fridge_sync.FridgeIntegrationService, "revert_consumption", fake_revert
    )

    created = api_client.post(
        "/meals",
        json={
            "eaten_at": "2026-08-18T21:09:00",
            "source": "manual",
            "title": "Яблоки свежие",
            "items": [
                {
                    "name": "Яблоки свежие",
                    "grams": 180,
                    "carbs_g": 18,
                    "evidence": {"fridge_lot_id": "lot-111"},
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    meal_id = created.json()["id"]

    response = api_client.delete(f"/meals/{meal_id}")

    assert response.status_code == 200, response.text
    assert response.json()["fridge_error"] is None
    assert asked == [meal_id]


def test_an_ordinary_meal_does_not_touch_the_fridge(api_client, monkeypatch):
    from glucotracker.application import fridge_sync

    asked: list[str] = []
    monkeypatch.setattr(
        fridge_sync.FridgeIntegrationService,
        "revert_consumption",
        lambda self, meal_id, owner_id=None: asked.append(str(meal_id)) or "",
    )

    created = api_client.post(
        "/meals",
        json={
            "eaten_at": "2026-08-18T20:02:00",
            "source": "manual",
            "title": "Карамель",
            "items": [{"name": "Карамель", "grams": 12, "carbs_g": 11}],
        },
    )
    meal_id = created.json()["id"]

    api_client.delete(f"/meals/{meal_id}")

    assert asked == []
