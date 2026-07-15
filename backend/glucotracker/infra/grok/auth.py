"""Resolve Grok/xAI credentials the same way the Grok CLI does.

Order:
1. Explicit API key (`XAI_API_KEY` / settings)
2. Signed-in SuperGrok session from `auth.json` (browser/`grok login` OIDC)

Session file format matches `~/.grok/auth.json` from the Grok CLI.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GrokCredentials:
    """Bearer token plus metadata for logging."""

    token: str
    source: str  # "api_key" | "session"
    email: str | None = None
    expires_at: datetime | None = None


def resolve_grok_credentials(
    *,
    api_key: str | None = None,
    auth_json_path: str | Path | None = None,
    prefer_session: bool = True,
) -> GrokCredentials | None:
    """Return the best available Grok credential or None."""
    session = load_session_credentials(auth_json_path)
    key = (api_key or "").strip() or None

    # Match Grok CLI: signed-in session takes precedence over API key.
    if prefer_session and session is not None:
        return session
    if key:
        return GrokCredentials(token=key, source="api_key")
    return session


def load_session_credentials(
    auth_json_path: str | Path | None = None,
) -> GrokCredentials | None:
    """Load and optionally refresh a SuperGrok OIDC session token."""
    path = _resolve_auth_json_path(auth_json_path)
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Grok auth file %s: %s", path, exc)
        return None
    if not isinstance(raw, dict) or not raw:
        return None

    # Prefer the newest non-expired entry; fall back to newest overall.
    entries: list[tuple[datetime | None, dict[str, Any]]] = []
    for value in raw.values():
        if not isinstance(value, dict):
            continue
        token = value.get("key") or value.get("access_token")
        if not isinstance(token, str) or not token.strip():
            continue
        entries.append((_parse_expires(value.get("expires_at")), value))
    if not entries:
        return None

    now = datetime.now(UTC)
    valid = [
        (expires, entry)
        for expires, entry in entries
        if expires is None or expires > now + timedelta(seconds=30)
    ]
    pool = valid or entries
    pool.sort(
        key=lambda item: item[0] or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    expires, entry = pool[0]
    token = str(entry.get("key") or entry.get("access_token") or "").strip()

    # Try silent refresh when close to expiry and we have a refresh token.
    if expires is not None and expires <= now + timedelta(minutes=5):
        refreshed = _try_refresh_session(path, entry)
        if refreshed is not None:
            return refreshed

    if not token:
        return None
    return GrokCredentials(
        token=token,
        source="session",
        email=str(entry.get("email")) if entry.get("email") else None,
        expires_at=expires,
    )


def _try_refresh_session(
    path: Path,
    entry: dict[str, Any],
) -> GrokCredentials | None:
    """Refresh an OIDC session using the stored refresh_token."""
    refresh_token = entry.get("refresh_token")
    client_id = entry.get("oidc_client_id")
    issuer = entry.get("oidc_issuer") or "https://auth.x.ai"
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        return None
    if not isinstance(client_id, str) or not client_id.strip():
        return None

    token_url = f"{str(issuer).rstrip('/')}/oauth/token"
    # Common OIDC paths; auth.x.ai uses standard token endpoint discovery.
    candidates = [
        f"{str(issuer).rstrip('/')}/oauth/token",
        f"{str(issuer).rstrip('/')}/oauth2/token",
        token_url,
    ]
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    for url in candidates:
        try:
            with httpx.Client(timeout=20.0, trust_env=False) as client:
                response = client.post(url, data=data)
        except httpx.HTTPError as exc:
            logger.info("Grok session refresh transport error url=%s err=%s", url, exc)
            continue
        if response.status_code >= 400:
            logger.info(
                "Grok session refresh failed url=%s status=%s body=%s",
                url,
                response.status_code,
                (response.text or "")[:200],
            )
            continue
        try:
            body = response.json()
        except Exception:
            continue
        access = body.get("access_token")
        if not isinstance(access, str) or not access.strip():
            continue
        new_refresh = body.get("refresh_token") or refresh_token
        expires_in = body.get("expires_in")
        expires_at: datetime | None = None
        if isinstance(expires_in, (int, float)):
            expires_at = datetime.now(UTC) + timedelta(seconds=float(expires_in))
        # Persist updated tokens back into auth.json best-effort.
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if value is entry or (
                        isinstance(value, dict)
                        and value.get("refresh_token") == refresh_token
                    ):
                        value["key"] = access
                        value["refresh_token"] = new_refresh
                        if expires_at is not None:
                            value["expires_at"] = expires_at.isoformat().replace(
                                "+00:00",
                                "Z",
                            )
                        raw[key] = value
                        break
                path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not persist refreshed Grok session: %s", exc)
        logger.info("Refreshed SuperGrok session token from %s", path)
        return GrokCredentials(
            token=access,
            source="session",
            email=str(entry.get("email")) if entry.get("email") else None,
            expires_at=expires_at,
        )
    return None


def _resolve_auth_json_path(explicit: str | Path | None) -> Path | None:
    """Pick the first readable Grok auth.json path."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env_path = os.environ.get("GROK_AUTH_JSON") or os.environ.get(
        "GLUCOTRACKER_GROK_AUTH_JSON"
    )
    if env_path:
        candidates.append(Path(env_path).expanduser())
    # Runtime drop-in (service-readable; ProtectHome blocks ~/.grok for systemd).
    candidates.append(
        Path("/media/megusto/storage/glucotracker/runtime/grok-auth.json")
    )
    candidates.append(Path.home() / ".grok" / "auth.json")
    # Interactive SuperGrok login on this host.
    candidates.append(Path("/home/megusto/.grok/auth.json"))

    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file() and os.access(resolved, os.R_OK):
            return resolved
    return None


def _parse_expires(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
