"""Idempotent seed loader for pattern shortcut data."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.domain.nutrients import normalize_nutrients_object
from glucotracker.infra.db.models import Pattern, PatternAlias, utc_now
from glucotracker.infra.db.session import get_session_factory


def _default_seed_dir() -> Path:
    """Return the repository seed directory."""
    return Path(__file__).resolve().parents[3] / "pattern_seeds"


def _normalize_token(value: str) -> str:
    """Normalize a prefix/key token for case-insensitive lookup."""
    return value.strip().casefold()


def _replace_aliases(pattern: Pattern, aliases: list[str]) -> None:
    """Replace aliases with normalized non-empty unique values."""
    seen = set()
    pattern.aliases = []
    for alias in aliases:
        normalized = str(alias).strip()
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        pattern.aliases.append(PatternAlias(alias=normalized))


def _seed_files(seed_dir: Path, seed_file: Path | None = None) -> list[Path]:
    """Return YAML seed files in deterministic order."""
    if seed_file is not None:
        return [seed_file]
    files = [*seed_dir.glob("*.yaml"), *seed_dir.glob("*.yml")]
    return sorted(files, key=lambda path: (".generated" in path.stem, path.name))


def _load_seed_file(path: Path) -> dict[str, Any]:
    """Load one YAML seed file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"Seed file {path} must contain a mapping."
        raise ValueError(msg)
    return data


def _upsert_pattern(
    session: Session,
    *,
    prefix: str,
    source_url: str | None,
    source_name: str | None,
    source_file: str | None,
    item: dict[str, Any],
) -> None:
    """Upsert one pattern by (prefix, key)."""
    key = _normalize_token(str(item["key"]))
    pattern = session.scalar(
        select(Pattern)
        .where(Pattern.prefix == prefix, Pattern.key == key)
        .options(selectinload(Pattern.aliases))
    )
    if pattern is None:
        pattern = Pattern(
            prefix=prefix,
            key=key,
            display_name=str(item["display_name"]),
        )
        session.add(pattern)

    pattern.display_name = str(item["display_name"])
    pattern.default_grams = item.get("default_grams")
    pattern.default_carbs_g = float(item.get("default_carbs_g", 0))
    pattern.default_protein_g = float(item.get("default_protein_g", 0))
    pattern.default_fat_g = float(item.get("default_fat_g", 0))
    pattern.default_fiber_g = float(item.get("default_fiber_g", 0))
    pattern.default_kcal = float(item.get("default_kcal", 0))
    pattern.per_100g_kcal = item.get("per_100g_kcal")
    pattern.per_100g_carbs_g = item.get("per_100g_carbs_g")
    pattern.per_100g_protein_g = item.get("per_100g_protein_g")
    pattern.per_100g_fat_g = item.get("per_100g_fat_g")
    pattern.source_url = item.get("source_url") or source_url
    pattern.source_name = item.get("source_name") or source_name
    pattern.source_file = item.get("source_file") or source_file
    pattern.source_page = item.get("source_page")
    pattern.source_confidence = item.get("source_confidence")
    pattern.is_verified = bool(item.get("is_verified", False))
    pattern.image_url = item.get("image_url")
    pattern.nutrients_json = normalize_nutrients_object(
        item.get("nutrients_json"),
        default_source_kind="pattern",
    )
    pattern.is_archived = bool(item.get("is_archived", False))
    pattern.updated_at = utc_now()
    if pattern.id is not None:
        pattern.aliases.clear()
        session.flush()
    _replace_aliases(pattern, [str(alias) for alias in item.get("aliases", [])])


def load_pattern_seeds(
    *,
    seed_dir: Path | None = None,
    seed_file: Path | None = None,
    prune_missing: bool = False,
    session: Session | None = None,
) -> int:
    """Load pattern seed YAML files with idempotent upserts."""
    seed_dir = seed_dir or _default_seed_dir()
    seed_file = seed_file.resolve() if seed_file is not None else None
    own_session = session is None
    active_session = session or get_session_factory()()
    loaded = 0
    seen_keys: set[tuple[str, str]] = set()
    loaded_prefixes: set[str] = set()
    try:
        for path in _seed_files(seed_dir, seed_file):
            data = _load_seed_file(path)
            prefix = _normalize_token(str(data["prefix"]))
            loaded_prefixes.add(prefix)
            source_url = data.get("source_url")
            source_name = data.get("source_name")
            source_file = data.get("source_file")
            for raw_item in data.get("items", []):
                if not isinstance(raw_item, dict):
                    msg = f"Seed item in {path} must be a mapping."
                    raise ValueError(msg)
                _upsert_pattern(
                    active_session,
                    prefix=prefix,
                    source_url=source_url,
                    source_name=source_name,
                    source_file=source_file,
                    item=raw_item,
                )
                seen_key = (prefix, _normalize_token(str(raw_item["key"])))
                if seen_key not in seen_keys:
                    seen_keys.add(seen_key)
                    loaded += 1
        if prune_missing:
            for prefix in loaded_prefixes:
                present = {
                    key for item_prefix, key in seen_keys if item_prefix == prefix
                }
                patterns = active_session.scalars(
                    select(Pattern).where(Pattern.prefix == prefix)
                ).all()
                for pattern in patterns:
                    if pattern.key not in present:
                        pattern.is_archived = True
                        pattern.updated_at = utc_now()
        active_session.commit()
    except Exception:
        active_session.rollback()
        raise
    finally:
        if own_session:
            active_session.close()
    return loaded


def main() -> None:
    """CLI entry point for `python -m glucotracker.infra.db.seed`."""
    parser = argparse.ArgumentParser(description="Load pattern seed YAML files.")
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Load one YAML seed file instead of the whole pattern_seeds directory.",
    )
    parser.add_argument(
        "--prune-missing",
        action="store_true",
        help=(
            "Archive rows for loaded prefixes when their keys are absent from "
            "the seed file."
        ),
    )
    args = parser.parse_args()
    loaded = load_pattern_seeds(seed_file=args.file, prune_missing=args.prune_missing)
    print(f"Loaded {loaded} pattern seed items.")


if __name__ == "__main__":
    main()
