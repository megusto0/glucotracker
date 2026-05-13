"""Filesystem storage for local pattern and restaurant database images."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from fastapi import UploadFile

from glucotracker.config import get_settings
from glucotracker.infra.storage.photo_store import MAX_PHOTO_BYTES
from glucotracker.infra.storage.product_image_store import (
    CONTENT_TYPES_BY_EXTENSION,
    SUPPORTED_CONTENT_TYPES,
)


class PatternImageStorageError(ValueError):
    """Raised when a pattern image cannot be stored."""


def _storage_root() -> Path:
    """Return the local pattern image storage root."""
    return get_settings().photo_storage_dir.parent / "pattern_images"


def _read_limited(file_obj: BinaryIO) -> bytes:
    """Read an upload while enforcing the shared image size limit."""
    data = file_obj.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        msg = "image exceeds 10MB limit"
        raise PatternImageStorageError(msg)
    return data


def _extension_for_upload(file: UploadFile) -> str:
    """Return a supported extension for the uploaded image."""
    extension = SUPPORTED_CONTENT_TYPES.get(file.content_type or "")
    if extension is not None:
        return extension

    filename_extension = Path(file.filename or "").suffix.casefold()
    if filename_extension == ".jpeg":
        return ".jpg"
    if filename_extension in CONTENT_TYPES_BY_EXTENSION:
        return filename_extension

    msg = "unsupported image type"
    raise PatternImageStorageError(msg)


def _candidate_paths(pattern_id: UUID) -> list[Path]:
    """Return possible stored paths for a pattern image."""
    root = _storage_root()
    return [
        root / f"{pattern_id}{extension}"
        for extension in {".jpg", ".png", ".webp"}
    ]


def save_upload(pattern_id: UUID, file: UploadFile) -> Path:
    """Persist an uploaded pattern image and return the absolute path."""
    extension = _extension_for_upload(file)
    root = _storage_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{pattern_id}{extension}"

    try:
        file.file.seek(0)
        data = _read_limited(file.file)
        if not data:
            msg = "image file is empty"
            raise PatternImageStorageError(msg)
        for candidate in _candidate_paths(pattern_id):
            if candidate != path:
                candidate.unlink(missing_ok=True)
        path.write_bytes(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.seek(0)

    return path


def get_full_path(pattern_id: UUID) -> Path:
    """Return the stored pattern image path or raise when missing."""
    for path in _candidate_paths(pattern_id):
        if path.exists():
            return path
    msg = "pattern image file not found"
    raise PatternImageStorageError(msg)


def content_type_for_path(path: Path) -> str:
    """Return the media type for a stored pattern image."""
    return CONTENT_TYPES_BY_EXTENSION.get(
        path.suffix.casefold(),
        "application/octet-stream",
    )
