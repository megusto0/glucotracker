"""Resolve OpenAI Codex OAuth credentials from the Hermes auth store.

Hermes authenticates to OpenAI Codex via OAuth and persists the session in
``$HERMES_HOME/auth.json`` under ``providers["openai-codex"]["tokens"]``. The
glucotracker service runs as the ``glucotracker`` user with ``ProtectHome=true``,
so it cannot read ``/home/megusto/.hermes/auth.json`` directly. A service-readable
drop-in copy is kept under the runtime directory instead.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from glucotracker.config import get_settings

logger = logging.getLogger(__name__)

CODEX_ACCOUNT_CLAIM = "https://api.openai.com/auth"
DEFAULT_AUTH_PATHS: tuple[Path, ...] = (
    Path("/media/megusto/storage/glucotracker/runtime/hermes-auth.json"),
    Path("/home/megusto/.hermes/auth.json"),
    Path.home() / ".hermes" / "auth.json",
)


@dataclass(frozen=True)
class CodexCredentials:
    """OpenAI Codex OAuth session resolved from the Hermes auth store."""

    access_token: str
    account_id: str | None = None
    source: str = "hermes-auth"


def account_id_from_token(token: str) -> str | None:
    """Return the ChatGPT account id embedded in a Codex access token JWT."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    auth_claim = claims.get(CODEX_ACCOUNT_CLAIM)
    if isinstance(auth_claim, dict):
        value = auth_claim.get("chatgpt_account_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _token_from_store(store: dict) -> str | None:
    providers = store.get("providers") or {}
    state = providers.get("openai-codex") or {}
    tokens = state.get("tokens") or {}
    token = tokens.get("access_token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    pool = store.get("credential_pool") or {}
    entries = pool.get("openai-codex")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            token = entry.get("access_token")
            if isinstance(token, str) and token.strip():
                return token.strip()
    return None


def resolve_hermes_codex_credentials(
    *,
    access_token: str | None = None,
    auth_json_path: str | Path | None = None,
) -> CodexCredentials | None:
    """Return Codex credentials from an explicit token or the Hermes auth store."""
    if isinstance(access_token, str) and access_token.strip():
        token = access_token.strip()
        return CodexCredentials(token, account_id_from_token(token), "explicit")

    settings = get_settings()
    candidates: list[Path] = []
    if auth_json_path:
        candidates.append(Path(auth_json_path))
    if settings.openai_hermes_auth_json:
        candidates.append(Path(settings.openai_hermes_auth_json))
    candidates.extend(DEFAULT_AUTH_PATHS)

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            path = candidate.expanduser()
        except (RuntimeError, OSError):
            continue
        if path in seen:
            continue
        seen.add(path)
        try:
            if not path.is_file():
                continue
            store = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.debug("Could not read Hermes auth store at %s", path, exc_info=True)
            continue
        token = _token_from_store(store)
        if token:
            return CodexCredentials(token, account_id_from_token(token), str(path))
    return None
