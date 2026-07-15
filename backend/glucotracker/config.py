"""Application configuration loaded from environment variables."""

from datetime import datetime, tzinfo
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings for the backend service."""

    app_version: str = "0.1.0"
    token: str | None = None
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "GLUCOTRACKER_LOG_LEVEL"),
    )
    jwt_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("JWT_SECRET", "GLUCOTRACKER_JWT_SECRET"),
    )
    database_url: str = Field(
        default="sqlite:///./data/glucotracker.sqlite3",
        validation_alias=AliasChoices("DATABASE_URL", "GLUCOTRACKER_DATABASE_URL"),
    )
    storage_backend: str = Field(
        default="filesystem",
        validation_alias=AliasChoices(
            "STORAGE_BACKEND",
            "GLUCOTRACKER_STORAGE_BACKEND",
        ),
    )
    photo_storage_dir: Path = Field(
        default=Path("./data/photos"),
        validation_alias=AliasChoices(
            "PHOTO_STORAGE_DIR",
            "GLUCOTRACKER_PHOTO_STORAGE_DIR",
        ),
    )
    photo_max_size_bytes: int = Field(
        default=12 * 1024 * 1024,
        gt=0,
        validation_alias=AliasChoices(
            "PHOTO_MAX_SIZE_BYTES",
            "GLUCOTRACKER_PHOTO_MAX_SIZE_BYTES",
        ),
    )
    activity_log_dir: Path = Field(
        default=Path("./data/activity_logs"),
        validation_alias=AliasChoices(
            "ACTIVITY_LOG_DIR",
            "GLUCOTRACKER_ACTIVITY_LOG_DIR",
        ),
    )
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GLUCOTRACKER_GEMINI_API_KEY"),
    )
    # Second Google AI Studio / Gemini project key. Used when the primary key
    # hits quota/rate limits so photo estimate can continue on another project.
    gemini_fallback_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GEMINI_FALLBACK_API_KEY",
            "GLUCOTRACKER_GEMINI_FALLBACK_API_KEY",
            "GEMINI_API_KEY_FALLBACK",
            "GLUCOTRACKER_GEMINI_API_KEY_FALLBACK",
        ),
    )
    gemini_proxy_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GEMINI_PROXY_URL",
            "GLUCOTRACKER_GEMINI_PROXY_URL",
        ),
    )
    gemini_model: str = Field(
        default="gemini-3-flash-preview",
        validation_alias=AliasChoices(
            "GEMINI_MODEL_PHOTO",
            "GLUCOTRACKER_GEMINI_MODEL_PHOTO",
            "GEMINI_MODEL",
            "GLUCOTRACKER_GEMINI_MODEL",
        ),
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
    gemini_taste_profile_model: str = Field(
        default="gemini-3.1-flash-lite-preview",
        validation_alias=AliasChoices(
            "GEMINI_TASTE_PROFILE_MODEL",
            "GLUCOTRACKER_GEMINI_TASTE_PROFILE_MODEL",
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
        default=(
            "gemini-3.1-flash-lite,gemini-2.5-flash-lite,gemini-2.5-flash"
        ),
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
    gemini_quota_cooldown_hours: float = Field(
        default=30,
        gt=0,
        validation_alias=AliasChoices(
            "GEMINI_QUOTA_COOLDOWN_HOURS",
            "GLUCOTRACKER_GEMINI_QUOTA_COOLDOWN_HOURS",
        ),
    )
    gemini_overload_cooldown_hours: float = Field(
        default=4,
        gt=0,
        validation_alias=AliasChoices(
            "GEMINI_OVERLOAD_COOLDOWN_HOURS",
            "GLUCOTRACKER_GEMINI_OVERLOAD_COOLDOWN_HOURS",
        ),
    )
    gemini_quota_cooldown_path: Path = Field(
        default=Path(
            "/media/megusto/storage/glucotracker/runtime/"
            "gemini-quota-cooldowns.json"
        ),
        validation_alias=AliasChoices(
            "GEMINI_QUOTA_COOLDOWN_PATH",
            "GLUCOTRACKER_GEMINI_QUOTA_COOLDOWN_PATH",
        ),
    )
    # Final photo-estimate fallback after Gemini primary + Gemini fallbacks fail.
    # Auth: SuperGrok session (~/.grok/auth.json from `grok login`) preferred,
    # then optional console XAI_API_KEY. OpenAI-compatible https://api.x.ai/v1.
    xai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "XAI_API_KEY",
            "GLUCOTRACKER_XAI_API_KEY",
            "GROK_API_KEY",
            "GLUCOTRACKER_GROK_API_KEY",
        ),
    )
    xai_base_url: str = Field(
        default="https://api.x.ai/v1",
        validation_alias=AliasChoices(
            "XAI_BASE_URL",
            "GLUCOTRACKER_XAI_BASE_URL",
            "GROK_CLI_CHAT_PROXY_BASE_URL",
        ),
    )
    grok_auth_json: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GROK_AUTH_JSON",
            "GLUCOTRACKER_GROK_AUTH_JSON",
        ),
    )
    grok_photo_model: str = Field(
        default="grok-4.5",
        validation_alias=AliasChoices(
            "GROK_PHOTO_MODEL",
            "GLUCOTRACKER_GROK_PHOTO_MODEL",
            "XAI_PHOTO_MODEL",
            "GLUCOTRACKER_XAI_PHOTO_MODEL",
        ),
    )
    grok_photo_fallback_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "GROK_PHOTO_FALLBACK_ENABLED",
            "GLUCOTRACKER_GROK_PHOTO_FALLBACK_ENABLED",
        ),
    )
    nightscout_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NIGHTSCOUT_BASE_URL",
            "GLUCOTRACKER_NIGHTSCOUT_BASE_URL",
            "NIGHTSCOUT_URL",
            "GLUCOTRACKER_NIGHTSCOUT_URL",
        ),
    )
    nightscout_api_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NIGHTSCOUT_API_SECRET",
            "GLUCOTRACKER_NIGHTSCOUT_API_SECRET",
            "GLUCOTRACKER_NIGHTSCOUT_TOKEN",
        ),
    )
    nightscout_background_import_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "NIGHTSCOUT_BACKGROUND_IMPORT_ENABLED",
            "GLUCOTRACKER_NIGHTSCOUT_BACKGROUND_IMPORT_ENABLED",
        ),
    )
    run_background_tasks_in_web: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "RUN_BACKGROUND_TASKS_IN_WEB",
            "GLUCOTRACKER_RUN_BACKGROUND_TASKS_IN_WEB",
        ),
    )
    nightscout_background_import_interval_seconds: int = Field(
        default=300,
        ge=60,
        validation_alias=AliasChoices(
            "NIGHTSCOUT_IMPORT_INTERVAL_SECONDS",
            "GLUCOTRACKER_NIGHTSCOUT_IMPORT_INTERVAL_SECONDS",
            "NIGHTSCOUT_BACKGROUND_IMPORT_INTERVAL_SECONDS",
            "GLUCOTRACKER_NIGHTSCOUT_BACKGROUND_IMPORT_INTERVAL_SECONDS",
        ),
    )
    nightscout_background_import_lookback_hours: int = Field(
        default=24,
        ge=1,
        validation_alias=AliasChoices(
            "NIGHTSCOUT_BACKGROUND_IMPORT_LOOKBACK_HOURS",
            "GLUCOTRACKER_NIGHTSCOUT_BACKGROUND_IMPORT_LOOKBACK_HOURS",
        ),
    )
    nightscout_background_import_overlap_minutes: int = Field(
        default=15,
        ge=0,
        validation_alias=AliasChoices(
            "NIGHTSCOUT_BACKGROUND_IMPORT_OVERLAP_MINUTES",
            "GLUCOTRACKER_NIGHTSCOUT_BACKGROUND_IMPORT_OVERLAP_MINUTES",
        ),
    )
    app_timezone: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_TIMEZONE", "GLUCOTRACKER_APP_TIMEZONE"),
    )
    # Browser desktop (Vite) is a different origin than the API host; without
    # CORS, login and all authenticated fetch() calls fail with NetworkError.
    cors_origins: str = Field(
        default=(
            "http://127.0.0.1:4173,"
            "http://localhost:4173,"
            "http://127.0.0.1:1420,"
            "http://localhost:1420,"
            "http://127.0.0.1:5173,"
            "http://localhost:5173,"
            "https://megusto.duckdns.org,"
            "https://megusto.duckdns.org:1338"
        ),
        validation_alias=AliasChoices("CORS_ORIGINS", "GLUCOTRACKER_CORS_ORIGINS"),
    )

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", ".env"),
        env_prefix="GLUCOTRACKER_",
        extra="ignore",
    )

    @property
    def local_zoneinfo(self) -> tzinfo:
        """Return the configured app timezone or the host local timezone."""
        if self.app_timezone:
            try:
                return ZoneInfo(self.app_timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError(
                    f"Unknown APP_TIMEZONE value: {self.app_timezone}"
                ) from exc

        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is not None:
            return local_tz
        return ZoneInfo("UTC")

    def validated_jwt_secret(self) -> str:
        """Return the JWT signing secret or reject unsafe backend startup."""
        if self.jwt_secret is None or len(self.jwt_secret) < 32:
            msg = "JWT_SECRET must be set and contain at least 32 characters."
            raise RuntimeError(msg)
        return self.jwt_secret


@lru_cache
def get_settings() -> Settings:
    """Return cached backend settings."""
    return Settings()
