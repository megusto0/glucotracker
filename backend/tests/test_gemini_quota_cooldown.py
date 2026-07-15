"""Tests for persistent Gemini model quota cooldowns."""

from datetime import UTC, datetime, timedelta

from glucotracker.infra.gemini.quota_cooldown import GeminiQuotaCooldownStore


def test_quota_cooldown_persists_across_store_instances(tmp_path) -> None:
    """A cooldown file is shared by separate web worker instances."""
    now = datetime(2026, 7, 15, 16, 0, tzinfo=UTC)
    path = tmp_path / "gemini-quota.json"
    first = GeminiQuotaCooldownStore(path, cooldown_hours=30, now=lambda: now)

    expires_at = first.block("gemini-3.5-flash")
    second = GeminiQuotaCooldownStore(path, cooldown_hours=30, now=lambda: now)

    assert expires_at == now + timedelta(hours=30)
    assert second.active_until("gemini-3.5-flash") == expires_at


def test_quota_cooldown_expires_after_thirty_hours(tmp_path) -> None:
    """A model becomes eligible again after the cooldown deadline."""
    clock = [datetime(2026, 7, 15, 16, 0, tzinfo=UTC)]
    store = GeminiQuotaCooldownStore(
        tmp_path / "gemini-quota.json",
        cooldown_hours=30,
        now=lambda: clock[0],
    )
    store.block("gemini-3.5-flash")

    clock[0] += timedelta(hours=30, seconds=1)

    assert store.active_until("gemini-3.5-flash") is None


def test_shorter_cooldown_does_not_replace_longer_block(tmp_path) -> None:
    """A later overload block cannot shorten an existing quota block."""
    now = datetime(2026, 7, 15, 16, 0, tzinfo=UTC)
    store = GeminiQuotaCooldownStore(
        tmp_path / "gemini-quota.json",
        cooldown_hours=30,
        now=lambda: now,
    )
    quota_deadline = store.block("gemini-3.5-flash")

    overload_deadline = store.block(
        "gemini-3.5-flash",
        duration=timedelta(hours=4),
    )

    assert overload_deadline == quota_deadline
