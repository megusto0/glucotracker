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
    # The origin travels in `kind`, not in the prose: the client draws its own
    # mark from it, and a snowflake in the middle of a sentence is something a
    # client can print but cannot act on.
    assert epica_item["kind"] == "fridge_product"
    assert "260 г" in epica_item["subtitle"]
    assert "Холодильник" not in epica_item["subtitle"]

    # 2. Search for depleted "Гауда" -> should NOT be found because remaining_quantity == 0
    res_gauda = api_client.get("/autocomplete?q=гауда")
    assert res_gauda.status_code == 200
    assert not any(item.get("token") == "fridge:lot-222" for item in res_gauda.json())

    # 3. Search for MealPrep "гречка" -> should find container MP01
    res_mp = api_client.get("/autocomplete?q=гречка")
    assert res_mp.status_code == 200
    assert any(item["token"] == "mp:cont-333" for item in res_mp.json())
    mp_item = next(item for item in res_mp.json() if item["token"] == "mp:cont-333")
    assert mp_item["kind"] == "meal_prep"
    # The code is not part of the dish's name. A diary entry copies the name at
    # the moment it is written, so a code in it outlives every later fix — see
    # «Азу с чечевицей (GT:C:16EC03A46F)», which is what this guards against.
    assert "MP01" not in mp_item["display_name"]
    assert "GT:C" not in mp_item["display_name"]

    # 4. Search with prefix "fridge:" and "mp:"
    res_prefix_fridge = api_client.get("/autocomplete?q=fridge:йогурт")
    assert res_prefix_fridge.status_code == 200
    assert any(item["token"] == "fridge:lot-111" for item in res_prefix_fridge.json())

    res_prefix_mp = api_client.get("/autocomplete?q=mp:MP01")
    assert res_prefix_mp.status_code == 200
    assert any(item["token"] == "mp:cont-333" for item in res_prefix_mp.json())


def test_products_list_mealprep_slider_uses_grams_not_container_count(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """The gram slider reads stock_remaining as its ceiling.

    Three leftover containers used to be sent as stock_remaining=3, which
    pinned «Вся» at 3 g. The count belongs nowhere near that field.
    """
    mock_mealpreps = [
        MealPrepItem(
            container_id=f"cont-{idx}",
            batch_id="batch-smetannik",
            dish_name="Сметанник",
            public_code=f"GT:C:00{idx}",
            net_weight_g=116.75,
            remaining_weight_g=113.75 if idx == 1 else 116.75,
            kcal=300.45,
            protein=4.46,
            fat=22.2,
            carbs=20.84,
            image_url=None,
        )
        for idx in range(1, 4)
    ]
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_inventory",
        lambda self, owner_id=None: [],
    )
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_mealpreps",
        lambda self, owner_id=None: mock_mealpreps,
    )

    res = api_client.get("/products")
    assert res.status_code == 200
    item = next(p for p in res.json()["items"] if p["name"] == "Сметанник")
    assert item["source_kind"] == "meal_prep"
    assert item["stock_unit"] == "г"
    assert item["stock_remaining"] == 113.75
    assert item["default_grams"] == 113.75
    # Rounded, not truncated. The client rounds default_grams to draw its
    # chips, so int() here put «113 г в контейнере» above a chip offering
    # «Вся (114 г)» — one container wearing two weights.
    assert item["default_serving_text"] == "114 г в контейнере"
    assert item["stock_remaining"] != 3
    # Three containers of one batch, as a number the picker can count in.
    assert item["stock_containers_left"] == 3


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


def test_two_containers_write_off_two_containers(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """A portion of two boxes empties two boxes.

    A container cannot be half-consumed — the fridge zeroes whichever one it is
    told about — so an entry that ate two while only one was written off left
    stock on the shelf that nobody had.
    """
    consumed: list[dict] = []
    monkeypatch.setattr(
        FridgeIntegrationService,
        "consume_item",
        lambda self, lot_id=None, container_id=None, quantity=None, unit=None, meal_id=None, owner_id=None: (
            consumed.append({"container_id": container_id, "quantity": quantity}) or True
        ),
    )
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_mealpreps",
        lambda self, owner_id=None: [
            MealPrepItem(
                container_id=f"cont-{idx}",
                batch_id="batch-smetannik",
                dish_name="Сметанник",
                public_code=f"GT:C:00{idx}",
                net_weight_g=114.0,
                remaining_weight_g=114.0,
                kcal=300.0,
                protein=4.5,
                fat=22.2,
                carbs=20.8,
                image_url=None,
            )
            for idx in range(1, 4)
        ],
    )

    res = api_client.post(
        "/meals",
        json={
            "title": "Сметанник",
            "source": "manual",
            "status": "accepted",
            "eaten_at": "2026-08-18T21:30:00",
            "items": [
                {
                    "name": "Сметанник",
                    "grams": 228.0,
                    "carbs_g": 41.6,
                    "protein_g": 9.0,
                    "fat_g": 44.4,
                    "kcal": 600.0,
                    "source_kind": "meal_prep",
                    "evidence": {
                        "mealprep_container_id": "cont-1",
                        "mealprep_containers": 2,
                    },
                }
            ],
        },
    )

    assert res.status_code == 201, res.text
    assert [e["container_id"] for e in consumed] == ["cont-1", "cont-2"]
    # The weight is split over the boxes it came out of.
    assert [e["quantity"] for e in consumed] == [114.0, 114.0]


def test_one_container_stays_one_call(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Saying nothing about containers means one, as every older client did."""
    consumed: list[str] = []
    monkeypatch.setattr(
        FridgeIntegrationService,
        "consume_item",
        lambda self, lot_id=None, container_id=None, quantity=None, unit=None, meal_id=None, owner_id=None: (
            consumed.append(str(container_id)) or True
        ),
    )

    res = api_client.post(
        "/meals",
        json={
            "title": "Сметанник",
            "source": "manual",
            "status": "accepted",
            "eaten_at": "2026-08-18T21:40:00",
            "items": [
                {
                    "name": "Сметанник",
                    "grams": 114.0,
                    "carbs_g": 20.8,
                    "kcal": 300.0,
                    "source_kind": "meal_prep",
                    "evidence": {"mealprep_container_id": "cont-9"},
                }
            ],
        },
    )

    assert res.status_code == 201, res.text
    assert consumed == ["cont-9"]


def test_a_fridge_picture_survives_the_trip_to_a_phone():
    """127.0.0.1 is the server talking to itself, not an address a phone can use."""
    from glucotracker.application.fridge_sync import _shared_media_url

    fridge = "http://127.0.0.1:8011"

    # The case that showed an empty frame: the Fridge stamps its own loopback
    # base into the address, and the phone resolves that to itself.
    assert (
        _shared_media_url("http://127.0.0.1:8011/uploaded-media/abc.jpg", fridge)
        == "/uploaded-media/abc.jpg"
    )
    # Whatever host the Fridge is configured on, not just the loopback literal.
    elsewhere = "http://fridge.local:8011"
    assert (
        _shared_media_url(f"{elsewhere}/uploaded-media/abc.jpg", elsewhere)
        == "/uploaded-media/abc.jpg"
    )
    assert (
        _shared_media_url("http://localhost:8011/uploaded-media/a.jpg?v=2", fridge)
        == "/uploaded-media/a.jpg?v=2"
    )

    # Already a path, or genuinely somewhere else: left exactly as it was.
    already_a_path = "/uploaded-media/abc.jpg"
    assert _shared_media_url(already_a_path, fridge) == already_a_path
    external = "https://avatars.mds.yandex.net/get-eda/1/2/400x400nocrop"
    assert _shared_media_url(external, fridge) == external

    assert _shared_media_url(None, fridge) is None
    assert _shared_media_url("   ", fridge) is None


def test_products_hand_a_meal_prep_picture_the_phone_can_load(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_inventory",
        lambda self, owner_id=None: [],
    )
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_mealpreps",
        lambda self, owner_id=None: [
            MealPrepItem(
                container_id="cont-1",
                batch_id="batch-1",
                dish_name="Сметанник",
                public_code="GT:C:001",
                net_weight_g=116.0,
                remaining_weight_g=116.0,
                kcal=300.0,
                protein=4.5,
                fat=22.2,
                carbs=20.8,
                image_url=FridgeIntegrationService()._media_url(
                    "http://127.0.0.1:8011/uploaded-media/smetannik.jpg"
                ),
            )
        ],
    )

    res = api_client.get("/products")
    assert res.status_code == 200
    item = next(p for p in res.json()["items"] if p["name"] == "Сметанник")
    assert item["image_url"] == "/uploaded-media/smetannik.jpg"


def test_a_fridge_lot_carries_how_it_is_eaten(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Answered, unanswered, and answered the other way — all three travel."""
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_mealpreps",
        lambda self, owner_id=None: [],
    )
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_inventory",
        lambda self, owner_id=None: [
            FridgeItem(
                id="lot-ice",
                lot_id="lot-ice",
                name="Мороженое Экзо ведёрко",
                brand=None,
                unit="шт",
                remaining_quantity=0.366,
                weight_grams=520.0,
                kcal_per_100g=140.0,
                protein_per_100g=1.5,
                fat_per_100g=3.5,
                carbs_per_100g=25.0,
                image_url=None,
                piece_weight_g=520.0,
                serving_unit="g",
            ),
            FridgeItem(
                id="lot-apple",
                lot_id="lot-apple",
                name="Яблоки свежие",
                brand=None,
                unit="г",
                remaining_quantity=200.0,
                weight_grams=200.0,
                kcal_per_100g=47.0,
                protein_per_100g=0.4,
                fat_per_100g=0.4,
                carbs_per_100g=9.8,
                image_url=None,
                piece_weight_g=180.0,
                serving_unit="pcs",
            ),
            FridgeItem(
                id="lot-new",
                lot_id="lot-new",
                name="Коржи для торта",
                brand=None,
                unit="шт",
                remaining_quantity=0.75,
                weight_grams=400.0,
                kcal_per_100g=360.0,
                protein_per_100g=7.0,
                fat_per_100g=8.5,
                carbs_per_100g=64.0,
                image_url=None,
                piece_weight_g=400.0,
            ),
        ],
    )

    items = {p["name"]: p for p in api_client.get("/products").json()["items"]}

    assert items["Мороженое Экзо ведёрко"]["serving_unit"] == "g"
    assert items["Яблоки свежие"]["serving_unit"] == "pcs"
    # Nobody has said yet, and that is not the same as «by grams».
    assert items["Коржи для торта"]["serving_unit"] is None


def test_answering_the_question_reaches_the_fridge(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        FridgeIntegrationService,
        "set_serving_unit",
        lambda self, lot_id, unit, owner_id=None: (
            asked.append((str(lot_id), unit)) or "ok"
        ),
    )

    lot = "11111111-1111-4111-8111-111111111111"
    response = api_client.patch(
        f"/products/{lot}/serving-unit",
        json={"serving_unit": "g"},
    )

    assert response.status_code == 204, response.text
    assert asked == [(lot, "g")]


def test_a_fridge_that_will_not_answer_is_reported_not_swallowed(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """The next open would ask again, so silence here is a lie."""
    monkeypatch.setattr(
        FridgeIntegrationService,
        "set_serving_unit",
        lambda self, lot_id, unit, owner_id=None: "timed out",
    )

    response = api_client.patch(
        f"/products/{'2' * 8}-2222-4222-8222-{'2' * 12}/serving-unit",
        json={"serving_unit": "pcs"},
    )

    assert response.status_code == 503


def test_only_the_two_units_are_accepted(api_client: TestClient):
    response = api_client.patch(
        f"/products/{'3' * 8}-3333-4333-8333-{'3' * 12}/serving-unit",
        json={"serving_unit": "штук"},
    )
    assert response.status_code == 422


def test_the_serving_unit_reads_the_same_either_way_round():
    """SQLite hands back the enum's name; HTTP hands back its value."""
    from glucotracker.application.fridge_sync import _serving_unit

    assert _serving_unit("PIECES") == "pcs"
    assert _serving_unit("GRAMS") == "g"
    assert _serving_unit("pcs") == "pcs"
    assert _serving_unit("g") == "g"
    assert _serving_unit(None) is None
    assert _serving_unit("  ") is None


def test_a_part_used_package_reports_grams_not_a_rounded_count(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """«0.0 шт» reported the rounding; 20 г is the stock."""
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_mealpreps",
        lambda self, owner_id=None: [],
    )
    monkeypatch.setattr(
        FridgeIntegrationService,
        "fetch_available_inventory",
        lambda self, owner_id=None: [
            FridgeItem(
                id="lot-halva",
                lot_id="lot-halva",
                name="Халва Восточный гость 500 г",
                brand=None,
                unit="шт",
                remaining_quantity=0.04,
                weight_grams=20.0,
                kcal_per_100g=560.0,
                protein_per_100g=13.0,
                fat_per_100g=37.0,
                carbs_per_100g=43.0,
                image_url=None,
            ),
            FridgeItem(
                id="lot-eggs",
                lot_id="lot-eggs",
                name="Яйцо куриное столовое С1",
                brand=None,
                unit="шт",
                remaining_quantity=10.0,
                weight_grams=600.0,
                kcal_per_100g=157.0,
                protein_per_100g=12.7,
                fat_per_100g=11.5,
                carbs_per_100g=0.7,
                image_url=None,
                piece_weight_g=60.0,
            ),
        ],
    )

    items = {p["name"]: p for p in api_client.get("/products").json()["items"]}

    assert items["Халва Восточный гость 500 г"]["default_serving_text"] == "20 г в наличии"
    # A whole count is still a count: ten eggs, not six hundred grams.
    assert items["Яйцо куриное столовое С1"]["default_serving_text"] == "10 шт в наличии"
