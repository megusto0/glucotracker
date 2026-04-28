"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings for the backend service."""

    app_version: str = "0.1.0"
    token: str | None = None
    database_url: str = "sqlite:///./data/glucotracker.sqlite3"
    photo_storage_dir: Path = Field(
        default=Path("./data/photos"),
        validation_alias=AliasChoices(
            "PHOTO_STORAGE_DIR",
            "GLUCOTRACKER_PHOTO_STORAGE_DIR",
        ),
    )
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GLUCOTRACKER_GEMINI_API_KEY"),
    )
    gemini_model: str = Field(
        default="gemini-3-flash-preview",
        validation_alias=AliasChoices("GEMINI_MODEL", "GLUCOTRACKER_GEMINI_MODEL"),
    )
    gemini_cheap_model: str = Field(
        default="gemini-3.1-flash-lite-preview",
        validation_alias=AliasChoices(
            "GEMINI_CHEAP_MODEL",
            "GLUCOTRACKER_GEMINI_CHEAP_MODEL",
        ),
    )
    gemini_free_test_model: str | None = Field(
        default="gemini-3.1-flash-lite-preview",
        validation_alias=AliasChoices(
            "GEMINI_FREE_TEST_MODEL",
            "GLUCOTRACKER_GEMINI_FREE_TEST_MODEL",
        ),
    )
    gemini_fallback_model: str = Field(
        default="gemini-3-flash-preview",
        validation_alias=AliasChoices(
            "GEMINI_FALLBACK_MODEL",
            "GLUCOTRACKER_GEMINI_FALLBACK_MODEL",
        ),
    )
    gemini_fallback_models: str = Field(
        default="gemini-2.5-flash,gemini-3.1-flash-lite-preview",
        validation_alias=AliasChoices(
            "GEMINI_FALLBACK_MODELS",
            "GLUCOTRACKER_GEMINI_FALLBACK_MODELS",
        ),
    )
    gemini_max_retries_per_model: int = Field(
        default=2,
        ge=1,
        le=5,
        validation_alias=AliasChoices(
            "GEMINI_MAX_RETRIES_PER_MODEL",
            "GLUCOTRACKER_GEMINI_MAX_RETRIES_PER_MODEL",
        ),
    )
    gemini_low_confidence_retry_threshold: float = Field(
        default=0.60,
        ge=0,
        le=1,
        validation_alias=AliasChoices(
            "GEMINI_LOW_CONFIDENCE_RETRY_THRESHOLD",
            "GLUCOTRACKER_GEMINI_LOW_CONFIDENCE_RETRY_THRESHOLD",
        ),
    )
    nightscout_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NIGHTSCOUT_URL", "GLUCOTRACKER_NIGHTSCOUT_URL"),
    )
    nightscout_api_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NIGHTSCOUT_API_SECRET",
            "GLUCOTRACKER_NIGHTSCOUT_API_SECRET",
            "GLUCOTRACKER_NIGHTSCOUT_TOKEN",
        ),
    )

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", ".env"),
        env_prefix="GLUCOTRACKER_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached backend settings."""
    return Settings()
