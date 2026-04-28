"""Gemini model routing tests."""

from pathlib import Path
from typing import Any

import pytest

from glucotracker.infra.gemini.client import (
    GeminiClient,
    GeminiClientError,
    GeminiRequestError,
    PhotoInput,
)
from glucotracker.infra.gemini.schemas import EstimatedItem, EstimationResult

FakeGeminiResult = EstimationResult | Exception


def _result(confidence: float, name: str = "Food") -> EstimationResult:
    """Build a minimal structured estimation result."""
    return EstimationResult(
        items=[
            EstimatedItem(
                name=name,
                scenario="PLATED",
                grams_mid=100,
                carbs_g_mid=10,
                protein_g_mid=5,
                fat_g_mid=3,
                fiber_g_mid=1,
                kcal_mid=87,
                confidence=confidence,
                confidence_reason="test",
            )
        ]
    )


class RoutingGeminiClient(GeminiClient):
    """Gemini client that records selected models without calling the SDK."""

    def __init__(
        self,
        results_by_model: dict[str, FakeGeminiResult | list[FakeGeminiResult]],
    ) -> None:
        super().__init__(api_key="test-key", model="gemini-2.5-flash")
        self.cheap_model = "gemini-2.5-flash-lite"
        self.free_test_model = "gemini-3.1-flash-lite-preview"
        self.fallback_model = "gemini-3-flash-preview"
        self.fallback_models = [self.fallback_model]
        self.max_retries_per_model = 2
        self.results_by_model = results_by_model
        self.calls: list[str] = []

    def _sleep(self, seconds: float) -> None:
        """Avoid slowing retry tests."""
        return None

    def _estimate_with_model(
        self,
        model: str,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None = None,
        products_context: list[dict[str, Any]] | None = None,
        user_context: str | None = None,
    ) -> EstimationResult:
        """Record the routed model and return a fake result."""
        self._ensure_not_pro_model(model)
        self.calls.append(model)
        configured = self.results_by_model[model]
        if isinstance(configured, list):
            next_value = configured.pop(0)
        else:
            next_value = configured
        if isinstance(next_value, Exception):
            raise next_value
        return next_value


def _photo_inputs() -> list[PhotoInput]:
    """Return a placeholder photo input for routing tests."""
    return [PhotoInput(path=Path("photo.jpg"), content_type="image/jpeg")]


def test_label_full_routes_to_free_test_model() -> None:
    """LABEL_FULL uses the configured free-test lite model first."""
    client = RoutingGeminiClient({"gemini-3.1-flash-lite-preview": _result(0.9)})

    client.estimate_photos(_photo_inputs(), scenario_hint="LABEL_FULL")

    assert client.calls == ["gemini-3.1-flash-lite-preview"]
    assert client.last_used_model == "gemini-3.1-flash-lite-preview"
    assert client.last_routing_reason == "label_full_lite"


def test_label_full_falls_back_to_cheap_model_when_free_test_empty() -> None:
    """LABEL_FULL uses 2.5 Flash-Lite when the free-test model is disabled."""
    client = RoutingGeminiClient({"gemini-2.5-flash-lite": _result(0.9)})
    client.free_test_model = None

    client.estimate_photos(_photo_inputs(), scenario_hint="LABEL_FULL")

    assert client.calls == ["gemini-2.5-flash-lite"]
    assert client.last_used_model == "gemini-2.5-flash-lite"


@pytest.mark.parametrize("scenario_hint", ["LABEL_PARTIAL", "PLATED"])
def test_label_partial_and_plated_route_to_default_flash(
    scenario_hint: str,
) -> None:
    """LABEL_PARTIAL and PLATED use the default 2.5 Flash model."""
    client = RoutingGeminiClient({"gemini-2.5-flash": _result(0.8)})

    client.estimate_photos(_photo_inputs(), scenario_hint=scenario_hint)

    assert client.calls == ["gemini-2.5-flash"]
    assert client.last_used_model == "gemini-2.5-flash"


def test_low_confidence_retries_with_fallback_model() -> None:
    """Low-confidence estimates retry through Gemini 3 Flash Preview."""
    client = RoutingGeminiClient(
        {
            "gemini-2.5-flash": _result(0.3, name="primary"),
            "gemini-3-flash-preview": _result(0.8, name="fallback"),
        }
    )

    result = client.estimate_photos(_photo_inputs(), scenario_hint="PLATED")

    assert client.calls == ["gemini-2.5-flash", "gemini-3-flash-preview"]
    assert client.last_model_attempts == [
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
    ]
    assert client.last_used_model == "gemini-3-flash-preview"
    assert client.last_routing_reason == "low_confidence_retry"
    assert result.items[0].name == "fallback"


def test_503_retries_primary_model_once_then_succeeds() -> None:
    """Temporary overload retries the same primary model before fallback."""
    client = RoutingGeminiClient(
        {
            "gemini-2.5-flash": [
                GeminiRequestError(
                    "temporary overload",
                    category="overload",
                    code=503,
                    status="UNAVAILABLE",
                ),
                _result(0.8, name="primary retry"),
            ],
        }
    )

    result = client.estimate_photos(_photo_inputs(), scenario_hint="PLATED")

    assert result.items[0].name == "primary retry"
    assert client.calls == ["gemini-2.5-flash", "gemini-2.5-flash"]
    assert client.last_used_model == "gemini-2.5-flash"
    assert client.last_fallback_used is False
    assert client.last_error_history[0]["code"] == 503


def test_503_falls_back_after_primary_retries_exhausted() -> None:
    """Temporary overload falls back to the next configured model."""
    client = RoutingGeminiClient(
        {
            "gemini-2.5-flash": [
                GeminiRequestError(
                    "temporary overload",
                    category="overload",
                    code=503,
                    status="UNAVAILABLE",
                ),
                GeminiRequestError(
                    "temporary overload",
                    category="overload",
                    code=503,
                    status="UNAVAILABLE",
                ),
            ],
            "gemini-3-flash-preview": _result(0.8, name="fallback"),
        }
    )

    result = client.estimate_photos(_photo_inputs(), scenario_hint="PLATED")

    assert result.items[0].name == "fallback"
    assert client.calls == [
        "gemini-2.5-flash",
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
    ]
    assert client.last_used_model == "gemini-3-flash-preview"
    assert client.last_fallback_used is True


def test_503_all_models_exhausted_returns_controlled_error() -> None:
    """Exhausted overload attempts return a user-facing retry message."""
    client = RoutingGeminiClient(
        {
            "gemini-2.5-flash": [
                GeminiRequestError(
                    "temporary overload",
                    category="overload",
                    code=503,
                    status="UNAVAILABLE",
                ),
                GeminiRequestError(
                    "temporary overload",
                    category="overload",
                    code=503,
                    status="UNAVAILABLE",
                ),
            ],
            "gemini-3-flash-preview": [
                GeminiRequestError(
                    "temporary overload",
                    category="overload",
                    code=503,
                    status="UNAVAILABLE",
                ),
                GeminiRequestError(
                    "temporary overload",
                    category="overload",
                    code=503,
                    status="UNAVAILABLE",
                ),
            ],
        }
    )

    with pytest.raises(GeminiClientError, match="Gemini временно перегружен"):
        client.estimate_photos(_photo_inputs(), scenario_hint="PLATED")

    assert client.last_used_model is None
    assert client.calls == [
        "gemini-2.5-flash",
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-3-flash-preview",
    ]


def test_429_quota_error_does_not_retry() -> None:
    """Quota errors do not spam retries or fallback models."""
    client = RoutingGeminiClient(
        {
            "gemini-2.5-flash": GeminiRequestError(
                "quota exhausted",
                category="quota",
                code=429,
                status="RESOURCE_EXHAUSTED",
                http_status_code=429,
            ),
        }
    )
    client.fallback_models = []
    client.fallback_model = ""

    with pytest.raises(GeminiClientError, match="Дневной лимит Gemini"):
        client.estimate_photos(_photo_inputs(), scenario_hint="PLATED")

    assert client.calls == ["gemini-2.5-flash"]


def test_automatic_routing_rejects_pro_models() -> None:
    """Pro models are not allowed through automatic estimation routing."""
    client = RoutingGeminiClient({"gemini-2.5-pro": _result(0.9)})
    client.model = "gemini-2.5-pro"

    with pytest.raises(GeminiClientError, match="refuses Pro models"):
        client.estimate_photos(_photo_inputs(), scenario_hint="PLATED")
