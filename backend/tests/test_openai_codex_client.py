"""Tests for the OpenAI Codex (Hermes OAuth) photo-estimate fallback."""

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
from glucotracker.infra.openai_codex.auth import (
    CodexCredentials,
    account_id_from_token,
    resolve_hermes_codex_credentials,
)
from glucotracker.infra.openai_codex.client import (
    OpenAICodexClientError,
    OpenAICodexPhotoClient,
    _extract_json,
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


def _jwt(account_id: str | None) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    claims: dict[str, Any] = {"sub": "u"}
    if account_id is not None:
        claims["https://api.openai.com/auth"] = {"chatgpt_account_id": account_id}
    payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    )
    return f"{header}.{payload}.sig"


def test_account_id_from_token() -> None:
    assert account_id_from_token(_jwt("acct-123")) == "acct-123"
    assert account_id_from_token(_jwt(None)) is None
    assert account_id_from_token("not-a-jwt") is None


def test_resolve_credentials_from_store_file(tmp_path: Path) -> None:
    token = _jwt("acct-abc")
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps(
            {"providers": {"openai-codex": {"tokens": {"access_token": token}}}}
        ),
        encoding="utf-8",
    )
    creds = resolve_hermes_codex_credentials(auth_json_path=auth_path)
    assert creds is not None
    assert creds.access_token == token
    assert creds.account_id == "acct-abc"
    assert creds.source == str(auth_path)


def test_resolve_credentials_falls_back_to_pool(tmp_path: Path) -> None:
    token = _jwt("acct-pool")
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps({"credential_pool": {"openai-codex": [{"access_token": token}]}}),
        encoding="utf-8",
    )
    creds = resolve_hermes_codex_credentials(auth_json_path=auth_path)
    assert creds is not None
    assert creds.account_id == "acct-pool"


def test_resolve_prefers_explicit_token(tmp_path: Path) -> None:
    creds = resolve_hermes_codex_credentials(
        access_token="explicit-token",
        auth_json_path=tmp_path / "missing.json",
    )
    assert creds is not None
    assert creds.access_token == "explicit-token"
    assert creds.source == "explicit"


def _sse(*events: dict[str, Any]) -> bytes:
    chunks = [
        f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
        for event in events
    ]
    return b"".join(chunks)


def _client_with_transport(handler: Any) -> OpenAICodexPhotoClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return OpenAICodexPhotoClient(
        credentials=CodexCredentials("tok", "acct", "explicit"),
        base_url="https://codex.example/backend-api/codex",
        model="gpt-5.6-luna",
        http_client=http_client,
    )


def test_client_parses_sse_stream(tmp_path: Path) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"\xff\xd8\xff")
    payload = json.dumps(_minimal_result(), ensure_ascii=False)
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                {"type": "response.output_text.delta", "delta": payload[:20]},
                {"type": "response.output_text.delta", "delta": payload[20:]},
                {"type": "response.completed"},
            ),
        )

    client = _client_with_transport(handler)
    result = client.estimate_photos(
        [PhotoInput(path=photo, content_type="image/jpeg", photo_id="p1")]
    )

    assert isinstance(result, EstimationResult)
    assert result.items[0].display_name_ru == "Лаваш с курицей"
    assert client.last_used_model == "gpt-5.6-luna"
    assert client.last_response_latency_ms is not None
    assert client.last_response_latency_ms >= 0
    assert seen["url"].endswith("/responses")
    assert seen["headers"]["originator"] == "codex_cli_rs"
    assert seen["headers"]["chatgpt-account-id"] == "acct"
    assert seen["headers"]["authorization"] == "Bearer tok"
    content = seen["body"]["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")


def test_client_raises_on_auth_error(tmp_path: Path) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized"})

    client = _client_with_transport(handler)
    with pytest.raises(OpenAICodexClientError, match="отклонил сессию"):
        client.estimate_photos([PhotoInput(path=photo, content_type="image/jpeg")])


def test_client_requires_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")
    monkeypatch.setattr(
        "glucotracker.infra.openai_codex.client.resolve_hermes_codex_credentials",
        lambda **_kwargs: None,
    )
    client = OpenAICodexPhotoClient(
        access_token="",
        auth_json_path=tmp_path / "missing.json",
    )
    with pytest.raises(OpenAICodexClientError, match="не авторизован"):
        client.estimate_photos([PhotoInput(path=photo, content_type="image/jpeg")])


def test_extract_json_ignores_fences_and_prose() -> None:
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('Вот результат: {"a": 1} готово') == '{"a": 1}'


def test_gemini_client_calls_openai_codex_as_last_fallback(tmp_path: Path) -> None:
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"\xff\xd8\xff")
    photos = [PhotoInput(path=photo, content_type="image/jpeg", photo_id="p1")]
    expected = EstimationResult.model_validate(_minimal_result())

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
        openai_photo_fallback_enabled=True,
        xai_api_key=None,
        gemini_proxy_url=None,
        openai_hermes_access_token="tok",
        openai_hermes_auth_json=None,
        openai_codex_base_url="https://codex.example/backend-api/codex",
        openai_photo_model="gpt-5.6-luna",
    )

    with patch(
        "glucotracker.infra.openai_codex.client.OpenAICodexPhotoClient"
    ) as client_cls:
        client = client_cls.return_value
        client.configured = True
        client.model = "gpt-5.6-luna"
        client.last_used_model = "gpt-5.6-luna"
        client.last_auth_source = "explicit"
        client.estimate_photos.return_value = expected
        result = gemini.estimate_photos(photos)

    assert result.items[0].name == expected.items[0].name
    assert gemini.last_provider == "openai-codex"
    assert gemini.last_fallback_used is True
    assert gemini.last_used_model == "gpt-5.6-luna"
    assert gemini.last_routing_reason == "openai_codex_final_fallback"
    assert any("OpenAI Codex" in warning for warning in result.image_quality_warnings)
    client.estimate_photos.assert_called_once()


def test_gemini_client_reports_openai_codex_failure(tmp_path: Path) -> None:
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
        openai_photo_fallback_enabled=True,
        xai_api_key=None,
        gemini_proxy_url=None,
        openai_hermes_access_token="tok",
        openai_hermes_auth_json=None,
        openai_codex_base_url="https://codex.example/backend-api/codex",
        openai_photo_model="gpt-5.6-luna",
    )

    with patch(
        "glucotracker.infra.openai_codex.client.OpenAICodexPhotoClient"
    ) as client_cls:
        client = client_cls.return_value
        client.configured = True
        client.model = "gpt-5.6-luna"
        client.last_auth_source = "explicit"
        client.estimate_photos.side_effect = OpenAICodexClientError(
            "OpenAI Codex отклонил сессию Hermes."
        )
        with pytest.raises(GeminiClientError, match="отклонил сессию"):
            gemini.estimate_photos(photos)
