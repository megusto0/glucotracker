"""Regression coverage for stale service copies and atomic token publishing."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "deploy/ubuntu/bin/glucotracker-hermes-auth-sync.py"
)
spec = importlib.util.spec_from_file_location("hermes_auth_sync", SCRIPT)
assert spec is not None and spec.loader is not None
sync_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_module)


def token(expires_at: float) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"exp": expires_at}).encode())
    return f"header.{claims.decode().rstrip('=')}.signature"


def test_sync_replaces_stale_copy_and_publishes_only_access_token(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "auth.json"
    destination.write_text('{"old": "expired"}')
    bearer = token(time.time() + 3600)
    resolver = Mock(return_value={"api_key": bearer, "refresh_token": "private"})

    assert sync_module.sync_credentials(destination, resolver)
    resolver.assert_called_once_with(refresh_if_expiring=True, refresh_skew_seconds=300)
    assert json.loads(destination.read_text()) == {
        "providers": {"openai-codex": {"tokens": {"access_token": bearer}}}
    }
    assert destination.stat().st_mode & 0o777 == 0o640
    assert destination.stat().st_gid == os.getegid()
    assert list(tmp_path.iterdir()) == [destination]


def test_sync_picks_up_rotated_token_without_backend_restart(tmp_path: Path) -> None:
    destination = tmp_path / "auth.json"
    old = token(time.time() + 3600)
    fresh = token(time.time() + 7200)
    resolver = Mock(side_effect=[{"api_key": old}, {"api_key": fresh}])
    sync_module.sync_credentials(destination, resolver)
    assert sync_module.sync_credentials(destination, resolver)
    assert fresh in destination.read_text()
    assert old not in destination.read_text()


def test_sync_avoids_rewriting_unchanged_token(tmp_path: Path) -> None:
    destination = tmp_path / "auth.json"
    resolver = Mock(return_value={"api_key": token(time.time() + 3600)})
    sync_module.sync_credentials(destination, resolver)
    before = destination.stat()
    assert not sync_module.sync_credentials(destination, resolver)
    assert destination.stat().st_ino == before.st_ino
    assert destination.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("bearer", [None, "malformed", token(1)])
def test_invalid_credentials_keep_previous_copy(
    tmp_path: Path, bearer: str | None
) -> None:
    destination = tmp_path / "auth.json"
    destination.write_text("previous copy")
    with pytest.raises(ValueError):
        sync_module.sync_credentials(
            destination, Mock(return_value={"api_key": bearer})
        )
    assert destination.read_text() == "previous copy"


def test_refresh_failure_keeps_previous_copy(tmp_path: Path) -> None:
    destination = tmp_path / "auth.json"
    destination.write_text("previous copy")
    with pytest.raises(RuntimeError):
        sync_module.sync_credentials(
            destination, Mock(side_effect=RuntimeError("offline"))
        )
    assert destination.read_text() == "previous copy"


def test_failed_atomic_replace_keeps_previous_copy(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "auth.json"
    destination.write_text("previous copy")
    monkeypatch.setattr(sync_module.os, "replace", Mock(side_effect=OSError("failed")))
    with pytest.raises(OSError):
        sync_module.sync_credentials(
            destination, Mock(return_value={"api_key": token(time.time() + 3600)})
        )
    assert destination.read_text() == "previous copy"
    assert list(tmp_path.iterdir()) == [destination]
