"""Pattern REST endpoints and prefix-aware pattern search."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import (
    DeleteResponse,
    PatternCreate,
    PatternPageResponse,
    PatternPatch,
    PatternResponse,
)
from glucotracker.domain.nutrients import normalize_nutrients_object
from glucotracker.infra.db.models import Pattern, PatternAlias, utc_now

router = APIRouter(
    tags=["patterns"],
    dependencies=[Depends(verify_token)],
)


def _normalize_token(value: str) -> str:
    """Normalize a prefix/key token for case-insensitive lookup."""
    return value.strip().casefold()


def _pattern_options() -> tuple:
    """Return eager-load options used by pattern responses."""
    return (selectinload(Pattern.aliases),)


def _get_pattern(session: SessionDep, pattern_id: UUID) -> Pattern:
    """Fetch a pattern or raise 404."""
    pattern = session.scalar(
        select(Pattern).where(Pattern.id == pattern_id).options(*_pattern_options())
    )
    if pattern is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pattern not found.",
        )
    return pattern


def _pattern_response(
    pattern: Pattern,
    *,
    matched_alias: str | None = None,
) -> PatternResponse:
    """Convert a pattern ORM object into an API response."""
    return PatternResponse.model_validate(
        {
            "id": pattern.id,
            "prefix": pattern.prefix,
            "key": pattern.key,
            "display_name": pattern.display_name,
            "default_grams": pattern.default_grams,
            "default_carbs_g": pattern.default_carbs_g,
            "default_protein_g": pattern.default_protein_g,
            "default_fat_g": pattern.default_fat_g,
            "default_fiber_g": pattern.default_fiber_g,
            "default_kcal": pattern.default_kcal,
            "per_100g_kcal": pattern.per_100g_kcal,
            "per_100g_carbs_g": pattern.per_100g_carbs_g,
            "per_100g_protein_g": pattern.per_100g_protein_g,
            "per_100g_fat_g": pattern.per_100g_fat_g,
            "source_url": pattern.source_url,
            "source_name": pattern.source_name,
            "source_file": pattern.source_file,
            "source_page": pattern.source_page,
            "source_confidence": pattern.source_confidence,
            "is_verified": pattern.is_verified,
            "image_url": pattern.image_url,
            "nutrients_json": pattern.nutrients_json,
            "usage_count": pattern.usage_count,
            "last_used_at": pattern.last_used_at,
            "is_archived": pattern.is_archived,
            "created_at": pattern.created_at,
            "updated_at": pattern.updated_at,
            "aliases": [alias.alias for alias in pattern.aliases],
            "matched_alias": matched_alias,
        }
    )


def _replace_aliases(pattern: Pattern, aliases: list[str]) -> None:
    """Replace pattern aliases with normalized non-empty unique values."""
    seen = set()
    pattern.aliases = []
    for alias in aliases:
        normalized = alias.strip()
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        pattern.aliases.append(PatternAlias(alias=normalized))


def _parse_pattern_query(q: str) -> tuple[str | None, str]:
    """Parse optional prefix namespace from a pattern query."""
    if ":" not in q:
        return None, q.strip()
    prefix, query = q.split(":", 1)
    normalized_prefix = _normalize_token(prefix)
    return (normalized_prefix or None), query.strip()


def _matched_alias(pattern: Pattern, query: str) -> str | None:
    """Return the alias matched by a query, if any."""
    query_value = query.casefold()
    if not query_value:
        return None

    exact = [
        alias.alias
        for alias in pattern.aliases
        if alias.alias.casefold() == query_value
    ]
    if exact:
        return exact[0]

    prefix = [
        alias.alias
        for alias in pattern.aliases
        if alias.alias.casefold().startswith(query_value)
    ]
    return prefix[0] if prefix else None


def _pattern_matches(pattern: Pattern, query: str) -> bool:
    """Return whether a pattern matches the after-colon query."""
    query_value = query.casefold()
    if not query_value:
        return True

    key_value = pattern.key.casefold()
    display_value = pattern.display_name.casefold()
    aliases = [alias.alias.casefold() for alias in pattern.aliases]
    return (
        key_value.startswith(query_value)
        or query_value in display_value
        or any(alias.startswith(query_value) for alias in aliases)
    )


def _sort_key(pattern: Pattern, query: str) -> tuple:
    """Return the configured pattern search ranking key."""
    query_value = query.casefold()
    aliases = [alias.alias.casefold() for alias in pattern.aliases]
    exact_key = bool(query_value and pattern.key.casefold() == query_value)
    alias_exact = bool(query_value and query_value in aliases)
    key_prefix = bool(query_value and pattern.key.casefold().startswith(query_value))
    alias_prefix = bool(
        query_value and any(alias.startswith(query_value) for alias in aliases)
    )

    last_used = pattern.last_used_at
    null_rank = 1 if last_used is None else 0
    timestamp_rank = -last_used.timestamp() if isinstance(last_used, datetime) else 0
    return (
        0 if exact_key else 1,
        0 if alias_exact else 1,
        0 if key_prefix else 1,
        0 if alias_prefix else 1,
        -(pattern.usage_count or 0),
        null_rank,
        timestamp_rank,
        pattern.display_name.casefold(),
    )


def search_pattern_rows(
    session: SessionDep,
    q: str,
    *,
    limit: int = 20,
) -> list[tuple[Pattern, str | None]]:
    """Search active patterns and return rows with matched aliases."""
    prefix, query = _parse_pattern_query(q)
    statement = (
        select(Pattern)
        .where(Pattern.is_archived.is_(False))
        .options(*_pattern_options())
    )
    if prefix is not None:
        statement = statement.where(Pattern.prefix == prefix)

    patterns = session.scalars(statement).all()
    matches = [
        (pattern, _matched_alias(pattern, query))
        for pattern in patterns
        if _pattern_matches(pattern, query)
    ]
    matches.sort(key=lambda match: _sort_key(match[0], query))
    return matches[:limit]


@router.get(
    "/patterns",
    response_model=PatternPageResponse,
    operation_id="listPatterns",
)
def list_patterns(
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PatternPageResponse:
    """List active patterns."""
    filters = [Pattern.is_archived.is_(False)]
    total = session.scalar(select(func.count(Pattern.id)).where(*filters)) or 0
    patterns = session.scalars(
        select(Pattern)
        .where(*filters)
        .options(*_pattern_options())
        .order_by(Pattern.prefix.asc(), Pattern.key.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PatternPageResponse(
        items=[_pattern_response(pattern) for pattern in patterns],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/patterns",
    response_model=PatternResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPattern",
)
def create_pattern(payload: PatternCreate, session: SessionDep) -> PatternResponse:
    """Create a reusable meal pattern."""
    data = payload.model_dump(exclude={"aliases"})
    data["prefix"] = _normalize_token(data["prefix"])
    data["key"] = _normalize_token(data["key"])
    data["nutrients_json"] = normalize_nutrients_object(
        data.get("nutrients_json"),
        default_source_kind="pattern",
    )
    pattern = Pattern(**data)
    _replace_aliases(pattern, payload.aliases)
    session.add(pattern)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pattern prefix/key already exists.",
        ) from exc
    return _pattern_response(_get_pattern(session, pattern.id))


@router.get(
    "/patterns/search",
    response_model=list[PatternResponse],
    operation_id="searchPatterns",
)
def search_patterns(
    session: SessionDep,
    q: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[PatternResponse]:
    """Search active patterns by prefix, key, display name, and aliases."""
    return [
        _pattern_response(pattern, matched_alias=matched_alias)
        for pattern, matched_alias in search_pattern_rows(session, q, limit=limit)
    ]


@router.get(
    "/patterns/{pattern_id}",
    response_model=PatternResponse,
    operation_id="getPattern",
)
def get_pattern(pattern_id: UUID, session: SessionDep) -> PatternResponse:
    """Return a pattern by id."""
    return _pattern_response(_get_pattern(session, pattern_id))


@router.patch(
    "/patterns/{pattern_id}",
    response_model=PatternResponse,
    operation_id="patchPattern",
)
def patch_pattern(
    pattern_id: UUID,
    payload: PatternPatch,
    session: SessionDep,
) -> PatternResponse:
    """Patch a reusable meal pattern."""
    pattern = _get_pattern(session, pattern_id)
    data = payload.model_dump(exclude_unset=True)
    aliases = data.pop("aliases", None)
    if "prefix" in data and data["prefix"] is not None:
        data["prefix"] = _normalize_token(data["prefix"])
    if "key" in data and data["key"] is not None:
        data["key"] = _normalize_token(data["key"])
    for field, value in data.items():
        if field == "nutrients_json" and value is not None:
            value = normalize_nutrients_object(value, default_source_kind="pattern")
        setattr(pattern, field, value)
    if aliases is not None:
        _replace_aliases(pattern, aliases)
    pattern.updated_at = utc_now()

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pattern prefix/key already exists.",
        ) from exc
    return _pattern_response(_get_pattern(session, pattern.id))


@router.delete(
    "/patterns/{pattern_id}",
    response_model=DeleteResponse,
    operation_id="deletePattern",
)
def delete_pattern(pattern_id: UUID, session: SessionDep) -> DeleteResponse:
    """Soft-delete a pattern by archiving it."""
    pattern = _get_pattern(session, pattern_id)
    pattern.is_archived = True
    pattern.updated_at = utc_now()
    session.commit()
    return DeleteResponse(deleted=True)
