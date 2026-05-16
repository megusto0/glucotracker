"""Flash Lite Gemini client for low-cost text-only classification tasks.

Thin wrapper around google-genai SDK, separate from the photo-estimation
GeminiClient. No retry logic — the worker handles retries.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from glucotracker.config import get_settings

logger = logging.getLogger(__name__)


class FlashLiteClient:
    """Minimal Gemini Flash Lite client for text classification."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = (
            model if model is not None else settings.gemini_taste_profile_model
        )

    def classify(
        self,
        system_prompt: str,
        user_json: dict[str, Any],
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a system+user prompt pair and return parsed JSON response.

        Args:
            system_prompt: System instructions for the model.
            user_json: User-facing JSON payload (converted to string).
            response_schema: Optional JSON Schema for structured output.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            FlashLiteError: On SDK errors, parse failures, or missing API key.
        """
        if not self.api_key:
            raise FlashLiteError("GEMINI_API_KEY is not configured")

        try:
            from google import genai
        except ImportError as exc:
            raise FlashLiteError("google-genai is not installed") from exc

        contents: list[Any] = [
            system_prompt,
            json.dumps(user_json, ensure_ascii=False),
        ]

        config: dict[str, Any] = {
            "response_mime_type": "application/json",
        }
        if response_schema is not None:
            config["response_schema"] = response_schema

        client = genai.Client(api_key=self.api_key)
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise FlashLiteError(f"Flash Lite request failed: {exc}") from exc

        try:
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, dict):
                return parsed
            result = json.loads(response.text)
            if not isinstance(result, dict):
                raise FlashLiteError("Flash Lite response is not a JSON object")
            return result
        except (json.JSONDecodeError, TypeError) as exc:
            raise FlashLiteError(
                f"Flash Lite response could not be parsed: {exc}"
            ) from exc


class FlashLiteError(Exception):
    """Raised when a Flash Lite request cannot be completed."""


def get_flash_lite_client() -> FlashLiteClient:
    """Dependency factory for the Flash Lite client."""
    return FlashLiteClient()
