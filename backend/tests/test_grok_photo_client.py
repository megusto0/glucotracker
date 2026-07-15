"""Tests for xAI Grok photo-estimate client and Gemini final fallback."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from glucotracker.infra.gemini.client import (
    GeminiClient,
    GeminiClientError,
    GeminiRequestError,
    PhotoInput,
)
from glucotracker.infra.gemini.quota_cooldown import GeminiQuotaCooldownStore
from glucotracker.infra.gemini.schemas import EstimationResult
from glucotracker.infra.grok.client import (
    GrokClientError,
    GrokPhotoClient,
    _strip_code_fence,
)


def _minimal_result() -> dict[str, Any]:
    return {
        "items": [
            {
                "name": "Лаваш с курицей",
                "display_name_ru": "Лаваш с курицей",
                "item_type": "plated_food",
                "scenario": "PLATED",
                "grams_mid": 250,
                "values_basis": "total_visible",
                "carbs_g_mid": 40,
                "protein_g_mid": 25,
                "fat_g_mid": 12,
                "kcal_mid": 370,
                "confidence": 0.7,
                "confidence_reason": "clear plated wrap",
                "assumptions": [],
                "evidence": ["видно лаваш и курицу"],
            }
        ],
        "overall_notes": "test",
        "reference_object_detected": "none",
        "image_quality_warnings": [],
    }


def test_strip_code_fence() -> None:
    raw = "```json\n{\"a\": 1}\n```"
    assert _strip_code_fence(raw) == '{"a": 1}'


def test_grok_client_requires_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"fake")
    monkeypatch.delenv("GROK_AUTH_JSON", raising=False)
    monkeypatch.delenv("GLUCOTRACKER_GROK_AUTH_JSON", raising=False)
    monkeypatch.setattr(
        "glucotracker.infra.grok.client.resolve_grok_credentials",
        lambda **_kwargs: None,
    )
    client = GrokPhotoClient(api_key="")
    with pytest.raises(GrokClientError, match="not signed in"):
        client.estimate_photos(
            [PhotoInput(path=photo, content_type="image/jpeg", photo_id="1")]
        )


def test_resolve_prefers_session_over_api_key(tmp_path: Path) -> None:
    from glucotracker.infra.grok.auth import resolve_grok_credentials

    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::client": {
                    "key": "session-jwt-token",
                    "email": "user@example.com",
                    "expires_at": "2099-01-01T00:00:00Z",
                    "auth_mode": "oidc",
                }
            }
        ),
        encoding="utf-8",
    )
    creds = resolve_grok_credentials(
        api_key="xai-console-key",
        auth_json_path=auth_path,
        prefer_session=True,
    )
    assert creds is not None
    assert creds.source == "session"
    assert creds.token == "session-jwt-token"
    assert creds.email == "user@example.com"


def test_grok_client_parses_json_response(tmp_path: Path) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"\xff\xd8\xff")  # tiny fake jpeg header
    payload = _minimal_result()
    mock_response = httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
            ]
        },
        request=httpx.Request("POST", "https://api.x.ai/v1/chat/completions"),
    )

    client = GrokPhotoClient(api_key="test-key", model="grok-4.5")
    with patch("httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.post.return_value = mock_response
        result = client.estimate_photos(
            [PhotoInput(path=photo, content_type="image/jpeg", photo_id="p1")]
        )

    assert isinstance(result, EstimationResult)
    assert result.items[0].display_name_ru == "Лаваш с курицей"
    assert client.last_used_model == "grok-4.5"
    call_kwargs = instance.post.call_args
    body = call_kwargs.kwargs["json"]
    assert body["model"] == "grok-4.5"
    assert body["response_format"] == {"type": "json_object"}
    content = body["messages"][1]["content"]
    assert any(part.get("type") == "image_url" for part in content)
    image_url = next(part for part in content if part.get("type") == "image_url")
    assert image_url["image_url"]["url"].startswith("data:image/jpeg;base64,")
    encoded_image = image_url["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(encoded_image) == b"\xff\xd8\xff"


def test_gemini_client_calls_grok_as_final_fallback(tmp_path: Path) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"\xff\xd8\xff")
    photos = [PhotoInput(path=photo, content_type="image/jpeg", photo_id="p1")]
    expected = EstimationResult.model_validate(_minimal_result())

    gemini = GeminiClient(
        api_key="gemini-key",
        model="gemini-primary",
        quota_cooldowns=GeminiQuotaCooldownStore(None),
    )
    gemini.fallback_models = ["gemini-fallback"]
    gemini.fallback_model = ""
    gemini.max_retries_per_model = 1
    gemini._sleep = lambda _s: None  # type: ignore[method-assign]

    def fail_model(*_args: object, **_kwargs: object) -> EstimationResult:
        raise GeminiRequestError(
            "quota", category="quota", code=429, status="RESOURCE_EXHAUSTED"
        )

    gemini._estimate_with_model = fail_model  # type: ignore[method-assign]
    gemini.fallback_api_key = None
    gemini.settings = MagicMock(
        grok_photo_fallback_enabled=True,
        xai_api_key=None,
        gemini_proxy_url=None,
    )

    with patch("glucotracker.infra.grok.client.GrokPhotoClient") as grok_cls:
        grok = grok_cls.return_value
        grok.configured = True
        grok.model = "grok-4.5"
        grok.last_used_model = "grok-4.5"
        grok.last_auth_source = "session"
        grok.estimate_photos.return_value = expected
        result = gemini.estimate_photos(photos)

    assert result.items[0].name == expected.items[0].name
    assert gemini.last_provider == "grok"
    assert gemini.last_fallback_used is True
    assert gemini.last_used_model == "grok-4.5"
    assert gemini.last_routing_reason == "grok_final_fallback"
    assert any(
        "SuperGrok session" in warning
        for warning in result.image_quality_warnings
    )
    grok.estimate_photos.assert_called_once()


def test_gemini_client_skips_grok_when_disabled(tmp_path: Path) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")
    photos = [PhotoInput(path=photo, content_type="image/jpeg")]

    gemini = GeminiClient(
        api_key="gemini-key",
        model="gemini-primary",
        quota_cooldowns=GeminiQuotaCooldownStore(None),
    )
    gemini.fallback_models = []
    gemini.fallback_model = ""
    gemini.fallback_api_key = None
    gemini.max_retries_per_model = 1
    gemini._estimate_with_model = (  # type: ignore[method-assign]
        lambda *_a, **_k: (_ for _ in ()).throw(
            GeminiRequestError("quota", category="quota", code=429)
        )
    )
    gemini.settings = MagicMock(
        grok_photo_fallback_enabled=False,
        xai_api_key="xai-test",
        gemini_proxy_url=None,
    )

    with pytest.raises(GeminiClientError):
        gemini.estimate_photos(photos)
