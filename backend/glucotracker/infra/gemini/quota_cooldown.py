"""Persistent per-model cooldowns after Gemini provider errors."""

from __future__ import annotations

import fcntl
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GeminiQuotaCooldownStore:
    """Share quota cooldowns across processes using a locked JSON file."""

    def __init__(
        self,
        path: Path | None,
        *,
        cooldown_hours: float = 30,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = path
        self.cooldown = timedelta(hours=cooldown_hours)
        self._now = now or (lambda: datetime.now(UTC))
        self._memory: dict[str, datetime] = {}

    def active_until(self, model: str) -> datetime | None:
        """Return the active cooldown deadline for a model, if any."""
        now = self._utc_now()
        if self.path is None:
            expires_at = self._memory.get(model)
        else:
            expires_at = self._read_models().get(model)
        if expires_at is None or expires_at <= now:
            return None
        return expires_at

    def block(self, model: str, *, duration: timedelta | None = None) -> datetime:
        """Block a model without shortening an existing longer cooldown."""
        expires_at = self._utc_now() + (duration or self.cooldown)
        if self.path is None:
            current = self._memory.get(model)
            if current is not None:
                expires_at = max(expires_at, current)
            self._memory[model] = expires_at
            return expires_at

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            try:
                self.path.chmod(0o600)
            except OSError as exc:
                logger.warning("Could not restrict Gemini cooldown file: %s", exc)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            models = self._load_models(handle)
            current = models.get(model)
            if current is not None:
                expires_at = max(expires_at, current)
            models[model] = expires_at
            self._write_models(handle, models)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return expires_at

    def _read_models(self) -> dict[str, datetime]:
        assert self.path is not None
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
                models = self._load_models(handle)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return models
        except OSError as exc:
            logger.warning("Could not read Gemini quota cooldowns: %s", exc)
            return {}

    def _load_models(self, handle: Any) -> dict[str, datetime]:
        handle.seek(0)
        try:
            raw = json.load(handle)
        except (json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        raw_models = raw.get("models")
        if not isinstance(raw_models, dict):
            return {}
        models: dict[str, datetime] = {}
        for model, value in raw_models.items():
            if not isinstance(model, str) or not isinstance(value, str):
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            models[model] = parsed.astimezone(UTC)
        return models

    def _write_models(self, handle: Any, models: dict[str, datetime]) -> None:
        active = {
            model: expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
            for model, expires_at in models.items()
            if expires_at > self._utc_now()
        }
        handle.seek(0)
        handle.truncate()
        json.dump({"models": active}, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
