"""Filesystem storage for local product database images."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from fastapi import UploadFile

from glucotracker.config import get_settings
from glucotracker.infra.storage.photo_store import MAX_PHOTO_BYTES

SUPPORTED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
CONTENT_TYPES_BY_EXTENSION = {
    extension: content_type
    for content_type, extension in SUPPORTED_CONTENT_TYPES.items()
}
CONTENT_TYPES_BY_EXTENSION[".jpeg"] = "image/jpeg"


class ProductImageStorageError(ValueError):
    """Raised when a product image cannot be stored."""


def _storage_root() -> Path:
    """Return the local product image storage root."""
    return get_settings().photo_storage_dir.parent / "product_images"


def _read_limited(file_obj: BinaryIO) -> bytes:
    """Read an upload while enforcing the shared image size limit."""
    data = file_obj.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        msg = "image exceeds 10MB limit"
        raise ProductImageStorageError(msg)
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
    raise ProductImageStorageError(msg)


def _candidate_paths(product_id: UUID) -> list[Path]:
    """Return possible stored paths for a product image."""
    root = _storage_root()
    return [
        root / f"{product_id}{extension}"
        for extension in {".jpg", ".png", ".webp"}
    ]


def save_upload(product_id: UUID, file: UploadFile) -> Path:
    """Persist an uploaded product image and return the absolute path."""
    extension = _extension_for_upload(file)
    root = _storage_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{product_id}{extension}"

    try:
        file.file.seek(0)
        data = _read_limited(file.file)
        if not data:
            msg = "image file is empty"
            raise ProductImageStorageError(msg)
        for candidate in _candidate_paths(product_id):
            if candidate != path:
                candidate.unlink(missing_ok=True)
        path.write_bytes(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.seek(0)

    return path


def get_full_path(product_id: UUID) -> Path:
    """Return the stored product image path or raise when missing."""
    for path in _candidate_paths(product_id):
        if path.exists():
            return path
    msg = "product image file not found"
    raise ProductImageStorageError(msg)


def content_type_for_path(path: Path) -> str:
    """Return the media type for a stored product image."""
    return CONTENT_TYPES_BY_EXTENSION.get(
        path.suffix.casefold(),
        "application/octet-stream",
    )
