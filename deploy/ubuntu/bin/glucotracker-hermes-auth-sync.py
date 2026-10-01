#!/usr/bin/env python3
"""Renew Hermes Codex credentials and atomically publish the access token."""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def sync_credentials(
    destination: Path,
    resolve_credentials: Callable[..., dict[str, Any]],
) -> bool:
    """Use Hermes's locked refresh; keep refresh tokens in its canonical store."""
    credentials = resolve_credentials(
        refresh_if_expiring=True, refresh_skew_seconds=300
    )
    token = credentials.get("api_key")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Hermes returned no OpenAI Codex access token")
    token = token.strip()
    try:
        payload = token.split(".")[1]
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        expires_at = float(claims["exp"])
    except (IndexError, KeyError, ValueError, TypeError) as exc:
        raise ValueError("Hermes returned a token without a valid expiry") from exc
    if not expires_at > time.time():
        raise ValueError("Hermes returned an expired OpenAI Codex access token")

    # The backend needs only the bearer, never the renewable session or other
    # providers' credentials from Hermes's auth.json.
    content = (
        json.dumps({"providers": {"openai-codex": {"tokens": {"access_token": token}}}})
        + "\n"
    )
    try:
        stat = destination.stat()
        if (
            destination.read_text(encoding="utf-8") == content
            and stat.st_mode & 0o777 == 0o640
            and stat.st_uid == os.geteuid()
            and stat.st_gid == os.getegid()
        ):
            return False
    except (FileNotFoundError, PermissionError):
        pass

    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchown(handle.fileno(), -1, os.getegid())
            os.fchmod(handle.fileno(), 0o640)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        from hermes_cli.auth import resolve_codex_runtime_credentials

        changed = sync_credentials(args.destination, resolve_codex_runtime_credentials)
    except Exception as exc:
        # Upstream exceptions may contain provider responses. Never print tokens.
        code = getattr(exc, "code", None) or type(exc).__name__
        print(f"Hermes Codex auth sync failed ({code}); previous copy retained")
        return 1
    if changed:
        print("Hermes Codex access token synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
