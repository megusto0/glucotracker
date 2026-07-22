"""xAI Grok photo nutrition estimate client (final Gemini fallback).

Auth matches the Grok CLI / SuperGrok account:
1. Signed-in session from ``~/.grok/auth.json`` (or GROK_AUTH_JSON)
2. Explicit ``XAI_API_KEY`` console key as fallback

Uses the OpenAI-compatible Chat Completions API with vision input and JSON
output parsed into the shared EstimationResult schema.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from glucotracker.config import get_settings
from glucotracker.infra.gemini.client import PHOTO_ESTIMATION_PROMPT_V2, PhotoInput
from glucotracker.infra.gemini.schemas import EstimationResult
from glucotracker.infra.grok.auth import GrokCredentials, resolve_grok_credentials

logger = logging.getLogger(__name__)


class GrokClientError(RuntimeError):
    """Raised when Grok photo estimation cannot be completed."""

    def __init__(self, message: str, *, http_status_code: int | None = None) -> None:
        super().__init__(message)
        self.http_status_code = http_status_code


class GrokPhotoClient:
    """Estimate meal macros from photos via xAI Grok (vision)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 90.0,
        auth_json_path: str | Path | None = None,
        credentials: GrokCredentials | None = None,
    ) -> None:
        settings = get_settings()
        self._explicit_api_key = api_key
        self._auth_json_path = auth_json_path or settings.grok_auth_json
        self.base_url = (base_url or settings.xai_base_url).rstrip("/")
        self.model = model or settings.grok_photo_model
        self.timeout = timeout
        self._credentials = credentials
        self.last_used_model: str | None = None
        self.last_auth_source: str | None = None
        self.last_raw_response: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        """Return whether SuperGrok session or API key credentials are available."""
        return self._resolve_credentials() is not None

    def _resolve_credentials(self) -> GrokCredentials | None:
        if self._credentials is not None:
            return self._credentials
        settings = get_settings()
        return resolve_grok_credentials(
            api_key=self._explicit_api_key
            if self._explicit_api_key is not None
            else settings.xai_api_key,
            auth_json_path=self._auth_json_path,
            prefer_session=True,
        )

    def estimate_photos(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None = None,
        products_context: list[dict[str, Any]] | None = None,
        user_context: str | None = None,
    ) -> EstimationResult:
        """Estimate visible meal items from photos using Grok vision."""
        creds = self._resolve_credentials()
        if creds is None:
            raise GrokClientError(
                "Grok is not signed in. Run `grok login` (SuperGrok session) "
                "or set XAI_API_KEY."
            )
        if not photos:
            raise GrokClientError("at least one photo is required for estimation")

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._build_prompt(
                    photos,
                    patterns_context=patterns_context,
                    products_context=products_context,
                    user_context=user_context,
                ),
            }
        ]
        for photo in photos:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _data_url(photo.path, photo.content_type),
                        "detail": "high",
                    },
                }
            )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You return only valid JSON matching the requested schema. "
                        "No markdown fences, no commentary outside JSON."
                    ),
                },
                {"role": "user", "content": content},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "Grok photo estimate attempt model=%s auth=%s email=%s",
            self.model,
            creds.source,
            creds.email or "-",
        )
        try:
            # Prefer explicit proxy (same as Gemini) — direct routes to api.x.ai
            # are often unreachable on this host. Avoid broken shell SOCKS proxies.
            with httpx.Client(**self._http_client_kwargs()) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise GrokClientError(
                "Grok request timed out while estimating the photo.",
                http_status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise GrokClientError(
                f"Grok request failed: {exc}",
                http_status_code=503,
            ) from exc

        if response.status_code in {401, 403}:
            detail = _safe_error_body(response)
            if (
                "spending-limit" in detail
                or "credits" in detail.lower()
                or "subscription" in detail.lower()
            ):
                raise GrokClientError(
                    "Grok API: нет кредитов / лимит команды. "
                    "Нужен xAI API credit или подписка с API, "
                    "не только SuperGrok chat. "
                    f"({detail[:200]})",
                    http_status_code=403,
                )
            raise GrokClientError(
                "Grok session rejected. Re-run `grok login` or refresh XAI_API_KEY. "
                f"({detail[:200]})",
                http_status_code=response.status_code,
            )
        if response.status_code == 429:
            raise GrokClientError(
                "Grok quota or rate limit exceeded. Try again later.",
                http_status_code=429,
            )
        if response.status_code >= 400:
            detail = _safe_error_body(response)
            raise GrokClientError(
                f"Grok request failed ({response.status_code}): {detail}",
                http_status_code=response.status_code
                if response.status_code in {400, 401, 403, 404, 429, 503}
                else 503,
            )

        try:
            body = response.json()
            self.last_raw_response = body
            text = body["choices"][0]["message"]["content"]
            if isinstance(text, list):
                text = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in text
                )
            result = EstimationResult.model_validate_json(_strip_code_fence(str(text)))
        except Exception as exc:
            raise GrokClientError(
                f"Grok response could not be parsed: {exc}",
                http_status_code=502,
            ) from exc

        self.last_used_model = self.model
        self.last_auth_source = creds.source
        logger.info(
            "Grok photo estimate succeeded model=%s auth=%s",
            self.model,
            creds.source,
        )
        return result

    def _http_client_kwargs(self) -> dict[str, Any]:
        """HTTP client options: Gemini proxy when set, else no env proxies."""
        settings = get_settings()
        proxy = (settings.gemini_proxy_url or "").strip() or None
        kwargs: dict[str, Any] = {
            "timeout": self.timeout,
            "trust_env": False,
        }
        if proxy:
            kwargs["proxy"] = proxy
        return kwargs

    def _build_prompt(
        self,
        photos: list[PhotoInput],
        *,
        patterns_context: list[dict[str, Any]] | None,
        products_context: list[dict[str, Any]] | None,
        user_context: str | None,
    ) -> str:
        """Build the text portion of the multimodal user message."""
        manifest = [
            {
                "index": photo.index or position,
                "id": photo.photo_id,
                "filename": photo.filename or photo.path.name,
            }
            for position, photo in enumerate(photos, start=1)
        ]
        context = {
            "patterns": patterns_context or [],
            "products": products_context or [],
        }
        schema = EstimationResult.model_json_schema()
        parts = [
            PHOTO_ESTIMATION_PROMPT_V2,
            "PHOTO MANIFEST JSON:",
            json.dumps(manifest, ensure_ascii=False),
            "Known context JSON:",
            json.dumps(context, ensure_ascii=False),
            "Return a single JSON object matching this schema:",
            json.dumps(schema, ensure_ascii=False),
        ]
        if user_context and user_context.strip():
            parts.extend(["USER CONTEXT:", user_context.strip()])
        return "\n\n".join(parts)


def _data_url(path: Path, content_type: str | None) -> str:
    """Encode a local photo as a data URL for vision chat completions."""
    mime = content_type or mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _strip_code_fence(text: str) -> str:
    """Remove optional markdown fences from a model JSON reply."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _safe_error_body(response: httpx.Response) -> str:
    """Return a short error body for logs/exceptions."""
    try:
        data = response.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:400]
            if data.get("message"):
                return str(data["message"])[:400]
        return str(data)[:400]
    except Exception:
        return (response.text or response.reason_phrase or "unknown error")[:400]
