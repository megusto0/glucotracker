"""Public, credential-free photo model management contract."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AIModelChoice(BaseModel):
    provider: Literal["gemini", "grok", "openai-codex"]
    model: str = Field(
        min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    enabled: bool = True


class AIModelRoutingUpdate(BaseModel):
    revision: int = Field(ge=0)
    models: list[AIModelChoice] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_models(self):
        if any(
            m.provider == "gemini" and "pro" in m.model.lower() for m in self.models
        ):
            raise ValueError("Автоматическое использование Gemini Pro отключено")
        keys = [(m.provider, m.model) for m in self.models]
        if len(set(keys)) != len(keys):
            raise ValueError("Модель уже есть в списке")
        if not any(m.enabled for m in self.models):
            raise ValueError("Оставьте хотя бы одну включённую модель")
        return self


class AIModelErrorCount(BaseModel):
    category: str
    count: int
    last_at: datetime


class AIModelOverview(AIModelChoice):
    in_routing: bool = True
    available: bool
    cooldown_until: datetime | None = None
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    skipped: int = 0
    timed_attempts: int = 0
    timed_responses: int = 0
    success_rate: float | None = None
    average_latency_ms: float | None = None
    average_response_latency_ms: float | None = None
    timed_requests: int = 0
    average_request_latency_ms: float | None = None
    average_confidence: float | None = None
    confidence_samples: int = 0
    last_called_at: datetime | None = None
    errors: list[AIModelErrorCount] = Field(default_factory=list)


class AIModelAttemptHistory(BaseModel):
    provider: Literal["gemini", "grok", "openai-codex"]
    model: str
    status: Literal["success", "error", "skipped"]
    latency_ms: float | None = None
    response_latency_ms: float | None = None
    confidence: float | None = None
    error_category: str | None = None


class AIRequestHistory(BaseModel):
    id: UUID
    created_at: datetime
    request_type: str
    status: str
    model_requested: str | None = None
    model_used: str | None = None
    provider: str
    fallback_used: bool
    latency_ms: float | None = None
    attempts: list[AIModelAttemptHistory]


class AIModelsResponse(BaseModel):
    revision: int
    custom_routing: bool
    since: datetime
    generated_at: datetime
    history_truncated: bool
    models: list[AIModelOverview]
    history_total: int
    history_offset: int
    history: list[AIRequestHistory]
