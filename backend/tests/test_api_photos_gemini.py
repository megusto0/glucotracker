"""Photo upload and mocked Gemini estimation API tests."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import AIRun, DailyTotal, MealItem
from glucotracker.infra.gemini.client import (
    GeminiClientError,
    PhotoInput,
    get_gemini_client,
)
from glucotracker.infra.gemini.schemas import (
    EstimatedComponent,
    EstimatedItem,
    EstimationResult,
    ExtractedNutritionFacts,
    NutritionPer100g,
    VisibleLabelFact,
)
from glucotracker.infra.storage import photo_store
from glucotracker.infra.storage.photo_store import MAX_PHOTO_BYTES
from glucotracker.main import app


class FakeGeminiClient:
    """Deterministic Gemini client used by API tests."""

    model = "fake-gemini"

    def __init__(self, result: EstimationResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def estimate_photos(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None = None,
        products_context: list[dict[str, Any]] | None = None,
        scenario_hint: str | None = None,
        model_override: str | None = None,
        user_context: str | None = None,
    ) -> EstimationResult:
        """Return the configured estimation result."""
        self.calls.append(
            {
                "photos": photos,
                "patterns_context": patterns_context or [],
                "products_context": products_context or [],
                "scenario_hint": scenario_hint,
                "model_override": model_override,
                "user_context": user_context,
            }
        )
        return self.result


class FailingGeminiClient:
    """Gemini client that returns a controlled error."""

    model = "fake-gemini"
    last_model_attempts: list[str] = ["fake-gemini"]
    last_requested_model = "fake-gemini"
    last_used_model = None
    last_fallback_used = False
    last_attempts: list[dict[str, Any]] = []
    last_error_history: list[dict[str, Any]] = []
    last_latency_ms = None
    last_routing_reason = "test_failure"

    def __init__(self, error: GeminiClientError) -> None:
        self.error = error

    def estimate_photos(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None = None,
        products_context: list[dict[str, Any]] | None = None,
        scenario_hint: str | None = None,
        model_override: str | None = None,
        user_context: str | None = None,
    ) -> EstimationResult:
        """Raise the configured error."""
        raise self.error


class MetadataGeminiClient(FakeGeminiClient):
    """Fake Gemini client with routing metadata."""

    model = "gemini-3-flash-preview"

    def __init__(
        self,
        result: EstimationResult,
        *,
        requested: str = "gemini-3-flash-preview",
        used: str = "gemini-3-flash-preview",
        fallback_used: bool = False,
    ) -> None:
        super().__init__(result)
        self.last_requested_model = requested
        self.last_used_model = used
        self.last_fallback_used = fallback_used
        self.last_attempts = [
            {
                "model": requested,
                "attempt": 1,
                "fallback_used": False,
                "status": "error" if fallback_used else "success",
            }
        ]
        self.last_error_history = (
            [
                {
                    "model": requested,
                    "attempt": 1,
                    "code": 503,
                    "status": "UNAVAILABLE",
                    "category": "overload",
                    "message": "temporary overload",
                }
            ]
            if fallback_used
            else []
        )
        self.last_latency_ms = 25
        self.last_model_attempts = [requested, used] if fallback_used else [used]
        self.last_routing_reason = "explicit_model_override"


def _create_photo_meal(api_client: TestClient) -> dict[str, Any]:
    """Create a draft meal ready for photo uploads."""
    response = api_client.post(
        "/meals",
        json={
            "eaten_at": "2026-04-28T12:00:00Z",
            "title": "Photo meal",
            "source": "photo",
            "status": "draft",
            "items": [],
        },
    )
    assert response.status_code == 201
    return response.json()


def _upload_photo(
    api_client: TestClient,
    meal_id: str,
    filename: str = "meal.jpg",
) -> dict[str, Any]:
    """Upload a tiny JPEG payload and return the photo response."""
    response = api_client.post(
        f"/meals/{meal_id}/photos",
        files={"file": (filename, b"\xff\xd8fake-jpeg", "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def _accepted_photo_meal(api_client: TestClient) -> dict[str, Any]:
    """Create an accepted photo meal with one existing estimated item."""
    meal = _create_photo_meal(api_client)
    photo = _upload_photo(api_client, meal["id"])
    accepted = api_client.post(
        f"/meals/{meal['id']}/accept",
        json={
            "items": [
                {
                    "name": "Лаваш с курицей",
                    "grams": 150,
                    "carbs_g": 32,
                    "protein_g": 18,
                    "fat_g": 12,
                    "fiber_g": 0,
                    "kcal": 300,
                    "confidence": 0.75,
                    "source_kind": "photo_estimate",
                    "calculation_method": "visual_estimate_gemini_mid",
                    "assumptions": [],
                    "evidence": {"source_photo_ids": [photo["id"]]},
                    "warnings": [],
                    "photo_id": photo["id"],
                    "position": 0,
                }
            ]
        },
    )
    assert accepted.status_code == 200
    return accepted.json()


def _override_gemini(result: EstimationResult) -> FakeGeminiClient:
    """Install a fake Gemini client dependency."""
    fake = FakeGeminiClient(result)
    app.dependency_overrides[get_gemini_client] = lambda: fake
    return fake


def _create_tortilla_anchor(api_client: TestClient) -> dict[str, Any]:
    """Create a saved known component for tortilla/lavash."""
    response = api_client.post(
        "/products",
        json={
            "name": "Тортилья 40 г",
            "default_grams": 40,
            "default_serving_text": "1 шт",
            "carbs_per_serving": 24,
            "protein_per_serving": 4,
            "fat_per_serving": 4,
            "kcal_per_serving": 150,
            "source_kind": "personal_component",
            "nutrients_json": {"sodium_mg": {"amount": 120, "unit": "mg"}},
            "aliases": ["тортилья", "лаваш", "tortilla", "wrap base"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_tortilla_carbs_only_component(api_client: TestClient) -> dict[str, Any]:
    """Create a saved tortilla component that only knows carbs."""
    response = api_client.post(
        "/products",
        json={
            "name": "Тортилья 40 г",
            "default_grams": 40,
            "default_serving_text": "1 шт",
            "carbs_per_serving": 24,
            "source_kind": "personal_component",
            "aliases": ["тортилья", "лаваш", "tortilla", "wrap base"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _plated_result() -> EstimationResult:
    """Return a visual estimate for a plated meal."""
    return EstimationResult(
        items=[
            EstimatedItem(
                name="Chicken, potatoes, greens",
                scenario="PLATED",
                grams_low=250,
                grams_mid=320,
                grams_high=390,
                carbs_g_low=25,
                carbs_g_mid=34,
                carbs_g_high=43,
                protein_g_mid=38,
                fat_g_mid=14,
                fiber_g_mid=6,
                kcal_mid=414,
                confidence=0.74,
                confidence_reason="Clear plated meal with visible portions.",
                assumptions=["Potatoes are boiled, chicken is roasted."],
                evidence={"visible_components": ["chicken", "potatoes", "greens"]},
            )
        ],
        overall_notes="One plated meal detected.",
        reference_object_detected="plate",
    )


def _wrap_with_component_result() -> EstimationResult:
    """Return one coherent wrap estimate with a tortilla known component."""
    return EstimationResult(
        items=[
            EstimatedItem(
                name="Chicken wrap",
                display_name_ru="Лаваш с курицей",
                scenario="PLATED",
                item_type="plated_food",
                grams_low=130,
                grams_mid=160,
                grams_high=190,
                carbs_g_low=26,
                carbs_g_mid=32,
                carbs_g_high=40,
                protein_g_mid=18,
                fat_g_mid=12,
                kcal_mid=300,
                component_estimates=[
                    EstimatedComponent(
                        name_ru="Тортилья/лаваш",
                        component_type="carb_base",
                        estimated_grams_mid=40,
                        carbs_g_mid=32,
                        protein_g_mid=5,
                        fat_g_mid=3,
                        kcal_mid=190,
                        visual_count=1,
                        likely_database_match_query="тортилья лаваш 40 г",
                        should_use_database_if_available=True,
                        confidence=0.8,
                        evidence=["видна основа ролла"],
                    ),
                    EstimatedComponent(
                        name_ru="Курица",
                        component_type="protein",
                        estimated_grams_mid=70,
                        carbs_g_mid=0,
                        protein_g_mid=13,
                        fat_g_mid=9,
                        kcal_mid=110,
                        confidence=0.7,
                    ),
                ],
                confidence=0.74,
                confidence_reason="Clear wrap with visible tortilla.",
                assumptions=["Tortilla count is one."],
                evidence=["Visible wrap base", "Visible chicken"],
            )
        ],
        overall_notes="One wrap detected.",
    )


def test_upload_validation_rejects_mime_and_size(api_client: TestClient) -> None:
    """Upload validation rejects unsupported MIME types and oversized files."""
    meal = _create_photo_meal(api_client)

    bad_type = api_client.post(
        f"/meals/{meal['id']}/photos",
        files={"file": ("meal.txt", b"not an image", "text/plain")},
    )
    assert bad_type.status_code == 400

    too_large = api_client.post(
        f"/meals/{meal['id']}/photos",
        files={"file": ("huge.jpg", b"x" * (MAX_PHOTO_BYTES + 1), "image/jpeg")},
    )
    assert too_large.status_code == 400


def test_upload_estimate_accept_flow(api_client: TestClient) -> None:
    """Upload a photo, estimate draft items, then accept reviewed suggestions."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"])
    fake = _override_gemini(_plated_result())

    estimate = api_client.post(
        f"/meals/{meal['id']}/estimate",
        json={"scenario_hint": "PLATED"},
    )

    assert estimate.status_code == 200
    estimate_body = estimate.json()
    assert fake.calls
    assert fake.calls[0]["scenario_hint"] == "PLATED"
    assert estimate_body["suggested_totals"]["total_carbs_g"] == 34
    assert estimate_body["reference_detected"] == "plate"

    accepted = api_client.post(
        f"/meals/{meal['id']}/accept",
        json={"items": estimate_body["suggested_items"]},
    )

    assert accepted.status_code == 200
    accepted_body = accepted.json()
    assert accepted_body["status"] == "accepted"
    assert accepted_body["total_carbs_g"] == 34
    assert accepted_body["total_kcal"] == 414


def test_estimate_failure_keeps_uploaded_photos_and_draft_retryable(
    api_client: TestClient,
) -> None:
    """Controlled Gemini failures do not delete photos or accept the draft."""
    meal = _create_photo_meal(api_client)
    photo = _upload_photo(api_client, meal["id"])
    app.dependency_overrides[get_gemini_client] = lambda: FailingGeminiClient(
        GeminiClientError(
            "Gemini временно перегружен. Фото сохранены, попробуйте повторить позже.",
            http_status_code=503,
        )
    )

    response = api_client.post(
        f"/meals/{meal['id']}/estimate_and_save_draft",
        json={},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Gemini временно перегружен. Фото сохранены, попробуйте повторить позже."
    )

    retryable_meal = api_client.get(f"/meals/{meal['id']}").json()
    assert retryable_meal["status"] == "draft"
    assert retryable_meal["items"] == []
    assert retryable_meal["photos"][0]["id"] == photo["id"]


def test_reestimate_creates_comparison_without_changing_meal(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Re-estimation stores a proposal and leaves accepted items unchanged."""
    meal = _accepted_photo_meal(api_client)
    app.dependency_overrides[get_gemini_client] = lambda: MetadataGeminiClient(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Chicken lavash",
                    display_name_ru="Лаваш с курицей",
                    scenario="PLATED",
                    grams_mid=150,
                    carbs_g_mid=24,
                    protein_g_mid=20,
                    fat_g_mid=10,
                    fiber_g_mid=2,
                    kcal_mid=270,
                    confidence=0.8,
                    confidence_reason="Re-estimated with another model.",
                )
            ],
            overall_notes="One item.",
        ),
        requested="gemini-3-flash-preview",
        used="gemini-3-flash-preview",
    )

    response = api_client.post(
        f"/meals/{meal['id']}/reestimate",
        json={"model": "gemini-3-flash-preview", "mode": "compare"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_totals"]["total_carbs_g"] == pytest.approx(32)
    assert body["proposed_totals"]["total_carbs_g"] == pytest.approx(24)
    assert body["diff"]["totals"]["carbs_delta"] == pytest.approx(-8)
    assert body["model_used"] == "gemini-3-flash-preview"

    unchanged = api_client.get(f"/meals/{meal['id']}").json()
    assert unchanged["total_carbs_g"] == pytest.approx(32)

    with Session(db_engine) as session:
        ai_run = session.get(AIRun, UUID(body["ai_run_id"]))
        assert ai_run is not None
        assert ai_run.request_type == "reestimate"
        assert ai_run.normalized_items_json[0]["carbs_g"] == pytest.approx(24)
        assert ai_run.promoted_at is None


def test_apply_reestimate_replace_current_preserves_photos(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Applying replace_current swaps items and keeps meal photos."""
    meal = _accepted_photo_meal(api_client)
    app.dependency_overrides[get_gemini_client] = lambda: MetadataGeminiClient(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Chicken lavash",
                    display_name_ru="Лаваш с курицей",
                    scenario="PLATED",
                    grams_mid=150,
                    carbs_g_mid=24,
                    protein_g_mid=20,
                    fat_g_mid=10,
                    kcal_mid=270,
                    confidence=0.8,
                    confidence_reason="Re-estimated.",
                )
            ]
        )
    )
    proposal = api_client.post(
        f"/meals/{meal['id']}/reestimate",
        json={"model": "default", "mode": "compare"},
    ).json()

    response = api_client.post(
        f"/meals/{meal['id']}/apply_estimation_run/{proposal['ai_run_id']}",
        json={"apply_mode": "replace_current"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meal"]["id"] == meal["id"]
    assert body["meal"]["total_carbs_g"] == pytest.approx(24)
    assert body["meal"]["photos"][0]["id"] == meal["photos"][0]["id"]

    with Session(db_engine) as session:
        ai_run = session.get(AIRun, UUID(proposal["ai_run_id"]))
        assert ai_run is not None
        assert ai_run.promoted_at is not None
        assert ai_run.promoted_by_action == "replace_current"


def test_apply_reestimate_save_as_draft_keeps_original(
    api_client: TestClient,
) -> None:
    """Applying save_as_draft creates a draft and leaves original unchanged."""
    meal = _accepted_photo_meal(api_client)
    app.dependency_overrides[get_gemini_client] = lambda: MetadataGeminiClient(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Chicken lavash",
                    display_name_ru="Лаваш с курицей",
                    scenario="PLATED",
                    grams_mid=150,
                    carbs_g_mid=24,
                    protein_g_mid=20,
                    fat_g_mid=10,
                    kcal_mid=270,
                    confidence=0.8,
                    confidence_reason="Re-estimated.",
                )
            ]
        )
    )
    proposal = api_client.post(
        f"/meals/{meal['id']}/reestimate",
        json={"model": "default", "mode": "compare"},
    ).json()

    response = api_client.post(
        f"/meals/{meal['id']}/apply_estimation_run/{proposal['ai_run_id']}",
        json={"apply_mode": "save_as_draft"},
    )

    assert response.status_code == 200
    draft = response.json()["meal"]
    assert draft["id"] != meal["id"]
    assert draft["status"] == "draft"
    assert draft["total_carbs_g"] == pytest.approx(24)
    original = api_client.get(f"/meals/{meal['id']}").json()
    assert original["total_carbs_g"] == pytest.approx(32)


def test_reestimate_without_photos_returns_clear_400(api_client: TestClient) -> None:
    """Re-estimation requires source photos."""
    response = api_client.post(
        "/meals",
        json={
            "eaten_at": "2026-04-28T12:00:00Z",
            "title": "Manual",
            "source": "manual",
            "status": "accepted",
            "items": [],
        },
    )
    meal = response.json()

    reestimate = api_client.post(
        f"/meals/{meal['id']}/reestimate",
        json={"model": "default", "mode": "compare"},
    )

    assert reestimate.status_code == 400
    assert reestimate.json()["detail"] == "У этой записи нет фото для переоценки"


def test_reestimate_response_shows_fallback_model(api_client: TestClient) -> None:
    """Re-estimation response reports fallback metadata."""
    meal = _accepted_photo_meal(api_client)
    app.dependency_overrides[get_gemini_client] = lambda: MetadataGeminiClient(
        _plated_result(),
        requested="gemini-3-flash-preview",
        used="gemini-2.5-flash",
        fallback_used=True,
    )

    response = api_client.post(
        f"/meals/{meal['id']}/reestimate",
        json={"model": "gemini-3-flash-preview", "mode": "compare"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model_used"] == "gemini-2.5-flash"
    assert body["fallback_used"] is True


def test_reestimate_manual_override_warning(api_client: TestClient) -> None:
    """Manual current items produce a replacement warning."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"])
    accepted = api_client.post(
        f"/meals/{meal['id']}/accept",
        json={
            "items": [
                {
                    "name": "Manual correction",
                    "carbs_g": 20,
                    "protein_g": 10,
                    "fat_g": 5,
                    "fiber_g": 0,
                    "kcal": 165,
                    "source_kind": "manual",
                    "calculation_method": "manual_override",
                    "assumptions": [],
                    "evidence": {"manual_override": True},
                    "warnings": [],
                    "position": 0,
                }
            ]
        },
    )
    assert accepted.status_code == 200
    app.dependency_overrides[get_gemini_client] = lambda: MetadataGeminiClient(
        _plated_result()
    )

    response = api_client.post(
        f"/meals/{meal['id']}/reestimate",
        json={"model": "default", "mode": "compare"},
    )

    assert response.status_code == 200
    assert (
        "Есть ручные исправления. Новая оценка может их заменить."
        in response.json()["diff"]["warnings"]
    )


def test_multi_photo_estimate_keeps_per_item_photo_identity(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Drink and wrap photos produce separate draft meals with their own photos."""
    meal = _create_photo_meal(api_client)
    drink_photo = _upload_photo(api_client, meal["id"], "drink.jpg")
    wrap_photo = _upload_photo(api_client, meal["id"], "wrap.jpg")
    fake = _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Energy drink",
                    display_name_ru="Напиток энергетический",
                    source_photo_ids=[drink_photo["id"]],
                    primary_photo_id=drink_photo["id"],
                    source_photo_indices=[1],
                    item_type="drink",
                    scenario="LABEL_PARTIAL",
                    extracted_facts=ExtractedNutritionFacts(
                        carbs_per_100ml=0,
                        protein_per_100ml=0,
                        fat_per_100ml=0,
                        fiber_per_100ml=0,
                        kcal_per_100ml=0,
                        assumed_volume_ml=449,
                        assumption_reason="Объём принят по видимой банке.",
                    ),
                    confidence=0.82,
                    confidence_reason="Drink label is readable.",
                    confidence_reason_ru="Этикетка напитка читается.",
                    evidence=["Углеводы видны на этикетке напитка."],
                    assumptions=["Объём принят как 449 мл."],
                ),
                EstimatedItem(
                    name="Chicken wrap",
                    display_name_ru="Лаваш с курицей",
                    source_photo_ids=[wrap_photo["id"]],
                    primary_photo_id=wrap_photo["id"],
                    source_photo_indices=[2],
                    item_type="plated_food",
                    scenario="PLATED",
                    grams_low=200,
                    grams_mid=240,
                    grams_high=280,
                    carbs_g_low=29,
                    carbs_g_mid=34,
                    carbs_g_high=40,
                    protein_g_mid=24,
                    fat_g_mid=15,
                    fiber_g_mid=2.5,
                    kcal_mid=375,
                    confidence=0.64,
                    confidence_reason="Wrap is visible but portion is uncertain.",
                    confidence_reason_ru="Лаваш виден, но вес оценён визуально.",
                    evidence=["Видны курица, овощи и лаваш."],
                    assumptions=["Вес оценён визуально."],
                ),
            ],
            overall_notes="Two unrelated items detected.",
        )
    )

    response = api_client.post(
        f"/meals/{meal['id']}/estimate_and_save_draft",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(fake.calls[0]["photos"]) == 2
    assert fake.calls[0]["photos"][0].photo_id == drink_photo["id"]
    assert fake.calls[0]["photos"][0].filename == "drink.jpg"
    assert fake.calls[0]["photos"][1].photo_id == wrap_photo["id"]
    assert fake.calls[0]["photos"][1].filename == "wrap.jpg"
    assert len(body["source_photos"]) == 2
    assert body["source_photos"][0]["index"] == 1
    assert body["source_photos"][0]["original_filename"] == "drink.jpg"
    assert body["source_photos"][1]["index"] == 2
    assert len(body["suggested_items"]) == 2
    drink, wrap = body["suggested_items"]
    assert drink["name"] == "Напиток энергетический"
    assert wrap["name"] == "Лаваш с курицей"
    assert drink["photo_id"] == drink_photo["id"]
    assert wrap["photo_id"] == wrap_photo["id"]
    assert drink["evidence"]["source_photo_ids"] == [drink_photo["id"]]
    assert wrap["evidence"]["source_photo_ids"] == [wrap_photo["id"]]
    assert body["suggested_totals"]["total_carbs_g"] == pytest.approx(34)
    assert body["suggested_totals"]["total_kcal"] == pytest.approx(375)
    assert len(body["created_drafts"]) == 2
    drink_draft, wrap_draft = body["created_drafts"]
    assert drink_draft["title"] == "Напиток энергетический"
    assert wrap_draft["title"] == "Лаваш с курицей"
    assert drink_draft["source_photo_id"] == drink_photo["id"]
    assert wrap_draft["source_photo_id"] == wrap_photo["id"]
    assert drink_draft["totals"]["total_kcal"] == pytest.approx(0)
    assert wrap_draft["totals"]["total_kcal"] == pytest.approx(375)

    meals = api_client.get("/meals").json()["items"]
    draft_rows = [row for row in meals if row["status"] == "draft"]
    assert len(draft_rows) == 2
    assert {row["title"] for row in draft_rows} == {
        "Напиток энергетический",
        "Лаваш с курицей",
    }
    assert {row["thumbnail_url"] for row in draft_rows} == {
        f"/photos/{drink_photo['id']}/file",
        f"/photos/{wrap_photo['id']}/file",
    }

    with Session(db_engine) as session:
        daily = session.get(DailyTotal, date(2026, 4, 28))
        assert daily is not None
        assert daily.meal_count == 0

    accepted = api_client.post(
        f"/meals/{wrap_draft['meal_id']}/accept",
        json={"items": [wrap_draft["item"]]},
    )
    assert accepted.status_code == 200

    with Session(db_engine) as session:
        daily = session.get(DailyTotal, date(2026, 4, 28))
        assert daily is not None
        assert daily.meal_count == 1
        assert daily.carbs_g == pytest.approx(34)


def test_multi_photo_single_unrelated_item_returns_warning(
    api_client: TestClient,
) -> None:
    """Multiple unrelated photos with one returned item produce a review warning."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "drink.jpg")
    _upload_photo(api_client, meal["id"], "wrap.jpg")
    _override_gemini(_plated_result())

    response = api_client.post(f"/meals/{meal['id']}/estimate", json={})

    assert response.status_code == 200
    body = response.json()
    assert (
        "Загружено несколько фото, найден один объект. Проверьте результат."
        in body["image_quality_warnings"]
    )
    assert "Позиция не связана с конкретным фото." in body["image_quality_warnings"]


def test_label_full_uses_backend_calculation(api_client: TestClient) -> None:
    """LABEL_FULL uses visible per-100g facts and visible weight."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"])
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Chocolate bar",
                    brand="Example",
                    scenario="LABEL_FULL",
                    extracted_facts=ExtractedNutritionFacts(
                        carbs_per_100g=56,
                        protein_per_100g=6,
                        fat_per_100g=24,
                        fiber_per_100g=4,
                        kcal_per_100g=460,
                        visible_weight_g=50,
                    ),
                    confidence=0.93,
                    confidence_reason="Full nutrition label and weight are visible.",
                    assumptions=[],
                    evidence={"label": "readable"},
                )
            ],
            overall_notes="Label readable.",
        )
    )

    response = api_client.post(f"/meals/{meal['id']}/estimate", json={})

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["source_kind"] == "label_calc"
    assert item["calculation_method"] == "label_visible_weight_backend_calc"
    assert item["grams"] == 50
    assert item["carbs_g"] == pytest.approx(28)
    assert item["protein_g"] == pytest.approx(3)
    assert item["fat_g"] == pytest.approx(12)
    assert item["fiber_g"] == pytest.approx(2)
    assert item["kcal"] == pytest.approx(230)


def test_label_full_split_identical_packages_uses_backend_calculation(
    api_client: TestClient,
) -> None:
    """Split Russian label facts across identical packages use backend totals."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"])
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Biscuit sandwich",
                    display_name_ru="Бисквит-сэндвич",
                    scenario="LABEL_FULL",
                    nutrition_per_100g=NutritionPer100g(
                        carbs_g=62,
                        protein_g=4.5,
                        fat_g=16,
                        kcal=410,
                    ),
                    visible_label_facts=[
                        VisibleLabelFact(
                            label_ru="углеводы",
                            value=62,
                            unit="г",
                            basis="per_100g",
                            confidence=0.96,
                        ),
                        VisibleLabelFact(
                            label_ru="белки",
                            value=4.5,
                            unit="г",
                            basis="per_100g",
                            confidence=0.95,
                        ),
                        VisibleLabelFact(
                            label_ru="жиры",
                            value=16,
                            unit="г",
                            basis="per_100g",
                            confidence=0.96,
                        ),
                        VisibleLabelFact(
                            label_ru="энергетическая ценность",
                            value=410,
                            unit="ккал",
                            basis="per_100g",
                            confidence=0.95,
                        ),
                        VisibleLabelFact(
                            label_ru="масса нетто",
                            value=30,
                            unit="г",
                            basis="net_weight",
                            confidence=0.94,
                        ),
                    ],
                    count_detected=2,
                    count_confidence=0.92,
                    net_weight_per_unit_g=30,
                    total_weight_g=60,
                    evidence_is_split_across_identical_items=True,
                    confidence=0.9,
                    confidence_reason=(
                        "Nutrition facts and net weight are visible on "
                        "matching wrappers."
                    ),
                    evidence=[
                        "Углеводы/белки/жиры/ккал видны на одной упаковке",
                        "Масса нетто 30 г видна на другой упаковке",
                        "На фото видно 2 одинаковые упаковки",
                    ],
                )
            ],
            overall_notes="Two identical candies detected.",
        )
    )

    response = api_client.post(f"/meals/{meal['id']}/estimate", json={})

    assert response.status_code == 200
    body = response.json()
    item = body["suggested_items"][0]
    assert item["source_kind"] == "label_calc"
    assert item["calculation_method"] == "label_split_visible_weight_backend_calc"
    assert item["name"] == "Бисквит-сэндвич"
    assert item["grams"] == pytest.approx(60)
    assert item["serving_text"] == "×2 упаковки · 30 г каждая"
    assert item["carbs_g"] == pytest.approx(37.2)
    assert item["protein_g"] == pytest.approx(2.7)
    assert item["fat_g"] == pytest.approx(9.6)
    assert item["kcal"] == pytest.approx(246)
    assert body["suggested_totals"]["total_carbs_g"] == pytest.approx(37.2)
    assert body["source_photos"][0]["url"].endswith("/file")
    breakdown = body["calculation_breakdowns"][0]
    assert breakdown["name"] == item["name"]
    assert breakdown["count_detected"] == 2
    assert breakdown["net_weight_per_unit_g"] == pytest.approx(30)
    assert breakdown["total_weight_g"] == pytest.approx(60)
    assert breakdown["nutrition_per_100g"]["carbs_g"] == pytest.approx(62)
    assert breakdown["calculated_per_unit"]["carbs_g"] == pytest.approx(18.6)
    assert breakdown["calculated_per_unit"]["kcal"] == pytest.approx(123)
    assert breakdown["calculated_total"]["carbs_g"] == pytest.approx(37.2)
    assert breakdown["calculated_total"]["kcal"] == pytest.approx(246)
    assert any(
        "62 × 60 / 100 = 37.2" in step for step in breakdown["calculation_steps"]
    )
    assert "Обе упаковки считаются одинаковым продуктом" in item["assumptions"]
    assert (
        "Масса нетто 30 г видна на другой упаковке" in item["evidence"]["evidence_text"]
    )


def test_split_identical_packages_save_as_one_draft_row(api_client: TestClient) -> None:
    """Two identical packages stay one draft row with count in the title."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "candies.jpg")
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Biscuit sandwich",
                    display_name_ru="Бисквит-сэндвич",
                    scenario="SPLIT_LABEL_IDENTICAL_ITEMS",
                    nutrition_per_100g=NutritionPer100g(
                        carbs_g=62,
                        protein_g=4.5,
                        fat_g=16,
                        kcal=410,
                    ),
                    count_detected=2,
                    count_confidence=0.92,
                    net_weight_per_unit_g=30,
                    total_weight_g=60,
                    evidence_is_split_across_identical_items=True,
                    confidence=0.9,
                    confidence_reason="Split label facts are visible.",
                    evidence=["На фото видно 2 одинаковые упаковки"],
                )
            ],
            overall_notes="Two identical candies detected.",
        )
    )

    response = api_client.post(
        f"/meals/{meal['id']}/estimate_and_save_draft",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["created_drafts"]) == 1
    draft = body["created_drafts"][0]
    assert draft["title"] == "Бисквит-сэндвич ×2"
    assert draft["item"]["carbs_g"] == pytest.approx(37.2)

    rows = api_client.get("/meals").json()["items"]
    assert len(rows) == 1
    assert rows[0]["title"] == "Бисквит-сэндвич ×2"
    assert rows[0]["status"] == "draft"


def test_label_partial_uses_assumed_volume_backend_calculation(
    api_client: TestClient,
) -> None:
    """LABEL_PARTIAL uses visible per-100ml facts and assumed volume."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"])
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Fruit drink",
                    scenario="LABEL_PARTIAL",
                    extracted_facts=ExtractedNutritionFacts(
                        carbs_per_100ml=10,
                        protein_per_100ml=0,
                        fat_per_100ml=0,
                        fiber_per_100ml=0,
                        kcal_per_100ml=42,
                        assumed_volume_ml=500,
                        assumption_reason="Bottle appears to be a 500 ml size.",
                    ),
                    confidence=0.7,
                    confidence_reason="Nutrition facts are visible, volume is assumed.",
                    assumptions=[],
                    evidence={"label": "partial"},
                )
            ],
            overall_notes="Volume not visible.",
        )
    )

    response = api_client.post(f"/meals/{meal['id']}/estimate", json={})

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["source_kind"] == "label_calc"
    assert item["calculation_method"] == "label_assumed_weight_backend_calc"
    assert item["grams"] == 500
    assert item["carbs_g"] == pytest.approx(50)
    assert item["kcal"] == pytest.approx(210)
    assert "Bottle appears to be a 500 ml size." in item["assumptions"]


def test_plated_uses_gemini_mid_values(api_client: TestClient) -> None:
    """PLATED suggestions use Gemini mid estimates."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"])
    _override_gemini(_plated_result())

    response = api_client.post(f"/meals/{meal['id']}/estimate", json={})

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["source_kind"] == "photo_estimate"
    assert item["calculation_method"] == "visual_estimate_gemini_mid"
    assert item["grams"] == 320
    assert item["carbs_g"] == 34
    assert item["protein_g"] == 38
    assert item["fat_g"] == 14
    assert item["fiber_g"] == 6
    assert item["kcal"] == 414


def test_unpeeled_orange_scale_weight_uses_edible_yield(
    api_client: TestClient,
) -> None:
    """Whole citrus on scales is adjusted from gross weight to edible part."""
    meal = _create_photo_meal(api_client)
    photo = _upload_photo(api_client, meal["id"], "orange.jpg")
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Orange",
                    display_name_ru="Апельсин",
                    scenario="PLATED",
                    item_type="plated_food",
                    source_photo_ids=[photo["id"]],
                    primary_photo_id=photo["id"],
                    source_photo_indices=[1],
                    grams_low=210,
                    grams_mid=210,
                    grams_high=210,
                    carbs_g_low=21,
                    carbs_g_mid=24.7,
                    carbs_g_high=27.3,
                    protein_g_mid=2,
                    fat_g_mid=0.3,
                    fiber_g_mid=5,
                    kcal_mid=98.7,
                    count_detected=1,
                    count_confidence=1,
                    net_weight_per_unit_g=210,
                    total_weight_g=210,
                    confidence=0.95,
                    confidence_reason="Exact scale weight is visible.",
                    confidence_reason_ru=(
                        "Продукт четко определен, и его точный вес виден на весах."
                    ),
                    assumptions=[
                        "Типичные макронутриенты для апельсина использованы "
                        "на основе его веса."
                    ],
                    evidence=[
                        "Вес 210 г виден на электронных весах",
                        "Апельсин четко виден в миске",
                    ],
                )
            ]
        )
    )

    response = api_client.post(f"/meals/{meal['id']}/estimate", json={})

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["calculation_method"] == "visual_estimate_gross_weight_edible_yield"
    assert item["carbs_g"] == pytest.approx(18.3)
    assert item["kcal"] == pytest.approx(73.0)
    assert item["evidence"]["gross_weight_edible_yield"]["gross_weight_g"] == 210
    assert item["evidence"]["gross_weight_edible_yield"]["edible_weight_g"] == 155.4
    assert item["evidence"]["raw_model_estimate"]["carbs_g"] == 24.7
    assert any(
        warning["code"] == "gross_weight_includes_peel"
        for warning in item["warnings"]
    )


def test_known_component_replaces_full_component_macros(
    api_client: TestClient,
) -> None:
    """Known tortilla component replaces all known component macro fields."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "wrap.jpg")
    _create_tortilla_anchor(api_client)
    _override_gemini(_wrap_with_component_result())

    response = api_client.post(
        f"/meals/{meal['id']}/estimate",
        json={"scenario_hint": "PLATED"},
    )

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["name"] == "Лаваш с курицей"
    assert item["calculation_method"] == "visual_estimate_with_known_component"
    assert item["carbs_g"] == pytest.approx(24)
    assert item["protein_g"] == pytest.approx(17)
    assert item["fat_g"] == pytest.approx(13)
    assert item["kcal"] == pytest.approx(260)
    assert item["evidence"]["raw_model_estimate"]["carbs_g"] == pytest.approx(32)
    component = item["evidence"]["known_component"]
    assert component["final_backend_adjusted_values"]["carbs_g"] == pytest.approx(24)
    assert component["final_backend_adjusted_values"]["protein_g"] == pytest.approx(17)
    assert component["final_backend_adjusted_values"]["fat_g"] == pytest.approx(13)
    assert component["final_backend_adjusted_values"]["kcal"] == pytest.approx(260)
    assert component["matches"][0]["known_component_display_name"] == "Тортилья 40 г"
    assert component["matches"][0]["known_component_carbs_g"] == pytest.approx(24)
    assert component["matches"][0]["known_component_protein_g"] == pytest.approx(4)
    assert component["matches"][0]["known_component_fat_g"] == pytest.approx(4)
    assert component["matches"][0]["known_component_kcal"] == pytest.approx(150)
    assert (
        component["components"][0]["field_sources"]["carbs_g"]
        == "personal_component"
    )
    assert component["components"][1]["field_sources"]["protein_g"] == (
        "gemini_visual_estimate"
    )
    assert item["nutrients"]["sodium_mg"]["amount"] == pytest.approx(120)
    assert item["nutrients"]["sodium_mg"]["source_kind"] in {
        "personal_component",
        "product_db",
    }


def test_known_component_missing_database_keeps_visual_estimate_with_warning(
    api_client: TestClient,
) -> None:
    """Missing tortilla component keeps Gemini estimate and warns the user."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "wrap.jpg")
    _override_gemini(_wrap_with_component_result())

    response = api_client.post(
        f"/meals/{meal['id']}/estimate",
        json={"scenario_hint": "PLATED"},
    )

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["calculation_method"] == "visual_estimate_gemini_mid"
    assert item["carbs_g"] == pytest.approx(32)
    assert any(
        warning["code"] == "known_component_review" for warning in item["warnings"]
    )


def test_known_component_matching_rejects_generic_cake_base_alias(
    api_client: TestClient,
) -> None:
    """Generic component token overlap must not turn cake base into tortilla."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "cake.jpg")
    response = api_client.post(
        "/products",
        json={
            "name": "Тортилья 40 г",
            "default_grams": 40,
            "default_serving_text": "1 шт",
            "carbs_per_serving": 22.1,
            "protein_per_serving": 3,
            "fat_per_serving": 2.45,
            "fiber_per_serving": 1.1,
            "kcal_per_serving": 124,
            "source_kind": "personal_component",
            "aliases": ["тортилья", "лаваш", "tortilla", "основа ролла"],
        },
    )
    assert response.status_code == 201
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Cake slice",
                    display_name_ru="Кусочек торта",
                    scenario="PLATED",
                    item_type="plated_food",
                    grams_mid=117,
                    carbs_g_mid=52,
                    protein_g_mid=6,
                    fat_g_mid=28,
                    fiber_g_mid=1,
                    kcal_mid=480,
                    component_estimates=[
                        EstimatedComponent(
                            name_ru="Основа торта (бисквит/коржи)",
                            component_type="carb_base",
                            estimated_grams_mid=80,
                            carbs_g_mid=35,
                            protein_g_mid=4,
                            fat_g_mid=15,
                            fiber_g_mid=0.5,
                            kcal_mid=290,
                            should_use_database_if_available=True,
                        ),
                        EstimatedComponent(
                            name_ru="Крем и меренга",
                            component_type="fat_source",
                            estimated_grams_mid=37,
                            carbs_g_mid=17,
                            protein_g_mid=2,
                            fat_g_mid=13,
                            fiber_g_mid=0.5,
                            kcal_mid=190,
                            should_use_database_if_available=True,
                        ),
                    ],
                    confidence=0.92,
                    confidence_reason="Scale weight is visible.",
                    evidence=["Вес 117 г виден на дисплее весов"],
                )
            ],
            overall_notes="Cake slice on scales.",
        )
    )

    estimate = api_client.post(
        f"/meals/{meal['id']}/estimate",
        json={"scenario_hint": "PLATED"},
    )

    assert estimate.status_code == 200
    item = estimate.json()["suggested_items"][0]
    assert item["calculation_method"] == "visual_estimate_gemini_mid"
    assert item["carbs_g"] == pytest.approx(52)
    assert item["fat_g"] == pytest.approx(28)
    assert item["kcal"] == pytest.approx(480)
    assert "known_component" not in item["evidence"]
    assert "carb_anchor" not in item["evidence"]


def test_known_component_matching_ignores_unrelated_saved_components(
    api_client: TestClient,
) -> None:
    """Unrelated plated components must not be replaced by random DB rows."""
    meal = _create_photo_meal(api_client)
    photo = _upload_photo(api_client, meal["id"], "lunch.jpg")
    _create_tortilla_anchor(api_client)
    pattern_response = api_client.post(
        "/patterns",
        json={
            "prefix": "home",
            "key": "chicken_potato_greens",
            "display_name": "Chicken, Potatoes, Greens",
            "default_grams": 520,
            "default_carbs_g": 56,
            "default_protein_g": 61,
            "default_fat_g": 26,
            "default_fiber_g": 9,
            "default_kcal": 735,
            "aliases": ["курица картошка зелень", "plate chicken"],
        },
    )
    assert pattern_response.status_code == 201
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Lunch with cutlets and garnish",
                    display_name_ru="Обед с котлетами и гарниром",
                    scenario="PLATED",
                    item_type="plated_food",
                    grams_mid=615,
                    carbs_g_mid=122.5,
                    protein_g_mid=60.1,
                    fat_g_mid=29,
                    fiber_g_mid=9.9,
                    kcal_mid=980.5,
                    source_photo_ids=[photo["id"]],
                    primary_photo_id=photo["id"],
                    source_photo_indices=[1],
                    component_estimates=[
                        EstimatedComponent(
                            name_ru="Котлеты",
                            component_type="protein",
                            estimated_grams_mid=180,
                            carbs_g_mid=12.6,
                            protein_g_mid=39.6,
                            fat_g_mid=18,
                            fiber_g_mid=0,
                            kcal_mid=342,
                            likely_database_match_query="Куриные котлеты",
                            should_use_database_if_available=True,
                            confidence=0.75,
                            evidence=["Две жареные котлеты"],
                        ),
                        EstimatedComponent(
                            name_ru="Рис отварной",
                            component_type="carb_base",
                            estimated_grams_mid=220,
                            carbs_g_mid=61.6,
                            protein_g_mid=5.9,
                            fat_g_mid=0.7,
                            fiber_g_mid=0.9,
                            kcal_mid=286,
                            likely_database_match_query="Белый рис отварной",
                            should_use_database_if_available=True,
                            confidence=0.8,
                            evidence=["Порция отварного белого риса"],
                        ),
                        EstimatedComponent(
                            name_ru="Хлеб",
                            component_type="carb_base",
                            estimated_grams_mid=70,
                            carbs_g_mid=31.5,
                            protein_g_mid=7,
                            fat_g_mid=2.1,
                            fiber_g_mid=3.5,
                            kcal_mid=175,
                            likely_database_match_query="Цельнозерновой хлеб",
                            should_use_database_if_available=True,
                            confidence=0.7,
                            evidence=["Два кусочка хлеба"],
                        ),
                    ],
                    confidence=0.78,
                    confidence_reason="Clear plated lunch.",
                    assumptions=["Portions estimated visually."],
                    evidence=["Plate with cutlets, rice and bread."],
                )
            ],
            overall_notes="Plated lunch.",
        )
    )

    response = api_client.post(
        f"/meals/{meal['id']}/estimate",
        json={"scenario_hint": "PLATED"},
    )

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["calculation_method"] == "visual_estimate_gemini_mid"
    assert item["carbs_g"] == pytest.approx(122.5)
    assert item["protein_g"] == pytest.approx(60.1)
    assert item["fat_g"] == pytest.approx(29)
    assert item["kcal"] == pytest.approx(980.5)
    assert "known_component" not in item["evidence"]
    assert "carb_anchor" not in item["evidence"]


def test_initial_estimate_can_request_specific_model(
    api_client: TestClient,
) -> None:
    """Initial photo estimate passes a selected model to the Gemini adapter."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "meal.jpg")
    fake = _override_gemini(_plated_result())

    response = api_client.post(
        f"/meals/{meal['id']}/estimate",
        json={"model": "gemini-2.5-flash"},
    )

    assert response.status_code == 200
    assert fake.calls[-1]["model_override"] == "gemini-2.5-flash"


def test_initial_estimate_passes_and_stores_user_context(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Photo estimate sends user context to Gemini and records it for audit."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "rice.jpg")
    fake = _override_gemini(_plated_result())
    context_note = "100 г варёного риса на тарелке"

    response = api_client.post(
        f"/meals/{meal['id']}/estimate_and_save_draft",
        json={"context_note": context_note, "scenario_hint": "PLATED"},
    )

    assert response.status_code == 200
    body = response.json()
    assert fake.calls[-1]["user_context"] == context_note
    item_evidence = body["suggested_items"][0]["evidence"]
    assert item_evidence["user_context_note"] == context_note
    assert f"Контекст пользователя: {context_note}" in item_evidence["evidence_text"]
    with Session(db_engine) as session:
        ai_run = session.scalar(select(AIRun).where(AIRun.meal_id == UUID(meal["id"])))
        assert ai_run is not None
        assert ai_run.request_summary["context_note"] == context_note


def test_known_component_with_only_carbs_preserves_model_values_for_unknown_fields(
    api_client: TestClient,
) -> None:
    """Known null fields do not become zero or erase model protein/fat/kcal."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"], "wrap.jpg")
    _create_tortilla_carbs_only_component(api_client)
    _override_gemini(_wrap_with_component_result())

    response = api_client.post(
        f"/meals/{meal['id']}/estimate",
        json={"scenario_hint": "PLATED"},
    )

    assert response.status_code == 200
    item = response.json()["suggested_items"][0]
    assert item["calculation_method"] == "visual_estimate_with_known_component"
    assert item["carbs_g"] == pytest.approx(24)
    assert item["protein_g"] == pytest.approx(18)
    assert item["fat_g"] == pytest.approx(12)
    assert item["kcal"] == pytest.approx(300)
    component = item["evidence"]["known_component"]
    match = component["matches"][0]
    assert match["known_component_protein_g"] is None
    assert match["known_component_fat_g"] is None
    assert match["known_component_kcal"] is None
    assert component["components"][0]["field_sources"]["protein_g"] == (
        "gemini_visual_estimate"
    )


def test_over_split_wrap_collapses_to_one_draft_with_known_component(
    api_client: TestClient,
) -> None:
    """Split tortilla/chicken/sauce items become one draft wrap item."""
    meal = _create_photo_meal(api_client)
    photo = _upload_photo(api_client, meal["id"], "wrap.jpg")
    _create_tortilla_anchor(api_client)
    _override_gemini(
        EstimationResult(
            items=[
                EstimatedItem(
                    name="Тортилья",
                    display_name_ru="Тортилья",
                    scenario="PLATED",
                    item_type="plated_food",
                    source_photo_ids=[photo["id"]],
                    primary_photo_id=photo["id"],
                    source_photo_indices=[1],
                    grams_mid=70,
                    carbs_g_mid=35,
                    protein_g_mid=5.6,
                    fat_g_mid=3.5,
                    kcal_mid=194,
                    confidence=0.75,
                    confidence_reason="Visual component estimate.",
                    evidence=["Видна одна тортилья"],
                ),
                EstimatedItem(
                    name="Жареная курица",
                    display_name_ru="Жареная курица",
                    scenario="PLATED",
                    item_type="plated_food",
                    source_photo_ids=[photo["id"]],
                    primary_photo_id=photo["id"],
                    source_photo_indices=[1],
                    grams_mid=120,
                    carbs_g_mid=18,
                    protein_g_mid=24,
                    fat_g_mid=18,
                    kcal_mid=330,
                    confidence=0.7,
                    confidence_reason="Visual component estimate.",
                    evidence=["Видны кусочки курицы"],
                ),
                EstimatedItem(
                    name="Белый соус",
                    display_name_ru="Белый соус",
                    scenario="PLATED",
                    item_type="plated_food",
                    source_photo_ids=[photo["id"]],
                    primary_photo_id=photo["id"],
                    source_photo_indices=[1],
                    grams_mid=40,
                    carbs_g_mid=2,
                    protein_g_mid=0.4,
                    fat_g_mid=28,
                    kcal_mid=262,
                    confidence=0.65,
                    confidence_reason="Visual component estimate.",
                    evidence=["Виден белый соус"],
                ),
            ],
            overall_notes="One wrap over-split into components.",
        )
    )

    response = api_client.post(
        f"/meals/{meal['id']}/estimate_and_save_draft",
        json={"scenario_hint": "PLATED"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["suggested_items"]) == 1
    assert len(body["created_drafts"]) == 1
    item = body["suggested_items"][0]
    assert item["name"] == "Лаваш с курицей"
    assert item["carbs_g"] == pytest.approx(44)
    assert item["protein_g"] == pytest.approx(28.4)
    assert item["fat_g"] == pytest.approx(50)
    assert item["kcal"] == pytest.approx(742)
    assert item["calculation_method"] == "visual_estimate_with_known_component"
    assert len(item["evidence"]["component_estimates"]) == 3
    rows = api_client.get("/meals").json()["items"]
    assert len(rows) == 1
    assert rows[0]["title"] == "Лаваш с курицей"


def test_estimate_and_save_draft_stores_raw_ai_run_and_items(
    api_client: TestClient,
    db_engine: Engine,
) -> None:
    """Saving an estimate stores raw AI output and draft items."""
    meal = _create_photo_meal(api_client)
    _upload_photo(api_client, meal["id"])
    _override_gemini(_plated_result())

    response = api_client.post(
        f"/meals/{meal['id']}/estimate_and_save_draft",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suggested_totals"]["total_kcal"] == 414

    meal_response = api_client.get(f"/meals/{meal['id']}").json()
    assert meal_response["status"] == "draft"
    assert len(meal_response["items"]) == 1
    assert meal_response["total_kcal"] == 414
    assert meal_response["photos"][0]["gemini_response_raw"]["overall_notes"]

    with Session(db_engine) as session:
        run_count = session.scalar(select(func.count(AIRun.id)))
        item_count = session.scalar(select(func.count(MealItem.id)))
        ai_run = session.scalar(select(AIRun))

    assert run_count == 1
    assert item_count == 1
    assert ai_run is not None
    assert ai_run.response_raw["overall_notes"] == "One plated meal detected."


def test_photo_delete_removes_disk_file(api_client: TestClient) -> None:
    """Deleting a photo removes its DB row and stored file."""
    meal = _create_photo_meal(api_client)
    photo = _upload_photo(api_client, meal["id"])
    full_path = photo_store.get_full_path(photo["path"])
    assert full_path.exists()

    response = api_client.delete(f"/photos/{photo['id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert not full_path.exists()
    assert api_client.get(f"/photos/{photo['id']}/file").status_code == 404
