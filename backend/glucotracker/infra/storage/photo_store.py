"""Filesystem storage for uploaded meal photos."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from glucotracker.config import get_settings

MAX_PHOTO_BYTES = 10 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class PhotoStorageError(ValueError):
    """Raised when an uploaded photo cannot be stored."""


def _storage_root() -> Path:
    """Return the configured photo storage root."""
    return get_settings().photo_storage_dir


def _safe_relative_path(path: str) -> Path:
    """Return a normalized relative path or raise for unsafe values."""
    rel_path = Path(path)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        msg = "unsafe photo path"
        raise PhotoStorageError(msg)
    return rel_path


def _read_limited(file_obj: BinaryIO) -> bytes:
    """Read an upload while enforcing the maximum file size."""
    data = file_obj.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        msg = "photo exceeds 10MB limit"
        raise PhotoStorageError(msg)
    return data


def save_upload(file: UploadFile) -> str:
    """Persist an uploaded image and return its storage-relative path."""
    extension = SUPPORTED_CONTENT_TYPES.get(file.content_type or "")
    if extension is None:
        msg = "unsupported photo type"
        raise PhotoStorageError(msg)

    photo_id = uuid.uuid4()
    now = datetime.now(UTC)
    relative_path = Path(f"{now:%Y}") / f"{now:%m}" / f"{photo_id}{extension}"
    full_path = _storage_root() / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file.file.seek(0)
        data = _read_limited(file.file)
        if not data:
            msg = "photo file is empty"
            raise PhotoStorageError(msg)
        full_path.write_bytes(data)
    except Exception:
        full_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.seek(0)

    return relative_path.as_posix()


def get_full_path(rel_path: str) -> Path:
    """Return the absolute path for a stored photo."""
    return _storage_root() / _safe_relative_path(rel_path)


def delete(rel_path: str) -> None:
    """Delete a stored photo if it exists."""
    get_full_path(rel_path).unlink(missing_ok=True)
