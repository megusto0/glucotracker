"""Filesystem storage for uploaded meal photos."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, NamedTuple, Protocol
from uuid import UUID

from fastapi import UploadFile

from glucotracker.config import get_settings

CHUNK_SIZE_BYTES = 64 * 1024
MAX_PHOTO_BYTES = 12 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
SUPPORTED_EXTENSIONS = {
    ".jpg": ("image/jpeg", ".jpg"),
    ".jpeg": ("image/jpeg", ".jpg"),
    ".png": ("image/png", ".png"),
    ".webp": ("image/webp", ".webp"),
}


class StorageKey(str):
    """Storage-relative photo key."""


class StorageMetadata(NamedTuple):
    """Stored photo metadata required for streaming responses."""

    content_length: int


class PhotoStorage(Protocol):
    """Adapter contract for photo storage backends."""

    def save_upload(
        self,
        file: UploadFile,
        *,
        owner_id: UUID | None = None,
        photo_id: UUID | None = None,
    ) -> StorageKey: ...

    def open_for_read(
        self,
        key: StorageKey | str,
    ) -> tuple[BinaryIO, StorageMetadata]: ...

    def delete(self, key: StorageKey | str) -> None: ...

    def exists(self, key: StorageKey | str) -> bool: ...


class StorageError(Exception):
    """Raised when an uploaded photo cannot be stored."""


class StorageNotFoundError(StorageError):
    """Raised when a stored photo key does not exist."""


class StorageIOError(StorageError):
    """Raised for filesystem I/O, disk, or permission failures."""


class PhotoStorageError(ValueError, StorageError):
    """Raised when an uploaded photo cannot be accepted."""


def _storage_root() -> Path:
    """Return the configured photo storage root."""
    return get_settings().photo_storage_dir


def _max_photo_bytes() -> int:
    """Return the configured upload limit."""
    return get_settings().photo_max_size_bytes


def _safe_relative_path(path: str) -> Path:
    """Return a normalized relative path or raise for unsafe values."""
    rel_path = Path(path)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        msg = "unsafe photo path"
        raise PhotoStorageError(msg)
    return rel_path


def _limit_message(limit: int) -> str:
    """Return a human-readable upload limit message."""
    whole_mb = limit // (1024 * 1024)
    if whole_mb * 1024 * 1024 == limit:
        return f"photo exceeds {whole_mb}MB limit"
    return f"photo exceeds {limit} byte limit"


def supported_upload_type(file: UploadFile) -> tuple[str, str]:
    """Return normalized content type and storage extension for an upload."""
    content_type = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    extension = SUPPORTED_CONTENT_TYPES.get(content_type)
    if extension is None and file.filename:
        inferred = SUPPORTED_EXTENSIONS.get(Path(file.filename).suffix.lower())
        if inferred is not None:
            content_type, extension = inferred
    if extension is None:
        msg = "unsupported photo type"
        raise PhotoStorageError(msg)
    return content_type, extension


def save_upload(
    file: UploadFile,
    *,
    owner_id: UUID | None = None,
    photo_id: UUID | None = None,
) -> str:
    """Persist an uploaded image and return its storage-relative path."""
    _, extension = supported_upload_type(file)

    photo_id = photo_id or uuid.uuid4()
    now = datetime.now(UTC)
    if owner_id is None:
        relative_path = Path(f"{now:%Y}") / f"{now:%m}" / f"{photo_id}{extension}"
    else:
        relative_path = Path(str(owner_id)) / f"{photo_id}{extension}"
    full_path = _storage_root() / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    bytes_written = 0
    max_bytes = _max_photo_bytes()
    try:
        file.file.seek(0)
        with full_path.open("wb") as stored:
            while chunk := file.file.read(CHUNK_SIZE_BYTES):
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise PhotoStorageError(_limit_message(max_bytes))
                stored.write(chunk)
        if bytes_written == 0:
            msg = "photo file is empty"
            raise PhotoStorageError(msg)
    except PhotoStorageError:
        full_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        full_path.unlink(missing_ok=True)
        raise StorageIOError(str(exc)) from exc
    except Exception:
        full_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.seek(0)

    return relative_path.as_posix()


def get_full_path(rel_path: str) -> Path:
    """Return the absolute path for a stored photo."""
    return _storage_root() / _safe_relative_path(rel_path)


def exists(rel_path: str) -> bool:
    """Return whether a stored photo exists."""
    return get_full_path(rel_path).exists()


def open_for_read(rel_path: str) -> tuple[BinaryIO, StorageMetadata]:
    """Open a stored photo for chunked reads."""
    full_path = get_full_path(rel_path)
    if not full_path.exists():
        raise StorageNotFoundError("photo file not found")
    try:
        return full_path.open("rb"), StorageMetadata(
            content_length=full_path.stat().st_size
        )
    except OSError as exc:
        raise StorageIOError(str(exc)) from exc


def iter_file(file_obj: BinaryIO) -> Iterator[bytes]:
    """Yield a file object in bounded chunks and close it when exhausted."""
    try:
        while chunk := file_obj.read(CHUNK_SIZE_BYTES):
            yield chunk
    finally:
        file_obj.close()


def delete(rel_path: str) -> None:
    """Tombstone a stored photo if it exists."""
    full_path = get_full_path(rel_path)
    if not full_path.exists():
        return
    deleted_path = full_path.with_name(f"{full_path.name}.deleted")
    if deleted_path.exists():
        deleted_path = full_path.with_name(
            f"{full_path.name}.{datetime.now(UTC):%Y%m%d%H%M%S}.deleted"
        )
    try:
        full_path.rename(deleted_path)
        now = datetime.now(UTC).timestamp()
        os.utime(deleted_path, (now, now))
    except OSError as exc:
        raise StorageIOError(str(exc)) from exc


def purge_deleted_older_than(cutoff: datetime) -> int:
    """Permanently remove tombstoned photos older than the cutoff."""
    root = _storage_root()
    if not root.exists():
        return 0
    cutoff_ts = cutoff.timestamp()
    deleted_count = 0
    for path in root.rglob("*.deleted"):
        try:
            if path.stat().st_mtime >= cutoff_ts:
                continue
            path.unlink()
            deleted_count += 1
        except FileNotFoundError:
            continue
    return deleted_count
