from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile

from app.core.config import settings
from app.schemas.files import FileItem

ROOT_DIR = Path(settings.nas_storage_path).expanduser().resolve()
ROOT_DIR.mkdir(parents=True, exist_ok=True)


class FileAccessError(Exception):
    """Raised when an operation would leave the permitted storage sandbox."""


class QuotaExceededError(Exception):
    """Raised when an operation would exceed the configured NAS quota."""


def _resolve_path(relative_path: str) -> Path:
    normalized = Path(relative_path.strip("/")) if relative_path else Path()
    target = (ROOT_DIR / normalized).resolve()
    try:
        target.relative_to(ROOT_DIR)
    except ValueError as exc:  # pragma: no cover - simple guard
        raise FileAccessError("Path is outside of the NAS storage boundary") from exc
    return target


def get_absolute_path(relative_path: str) -> Path:
    """Expose resolved paths for read-only operations like downloads."""
    return _resolve_path(relative_path)


def list_directory(relative_path: str = "") -> Iterable[FileItem]:
    target = _resolve_path(relative_path)
    if not target.exists():
        return []

    items: list[FileItem] = []
    for entry in target.iterdir():
        stats = entry.stat()
        item = FileItem(
            name=entry.name,
            path=str(entry.relative_to(ROOT_DIR).as_posix()),
            size=stats.st_size,
            type="directory" if entry.is_dir() else "file",
            modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
        )
        items.append(item)

    items.sort(key=lambda item: (item.type != "directory", item.name.lower()))
    return items


def calculate_used_bytes() -> int:
    total = 0
    if not ROOT_DIR.exists():
        return total

    for entry in ROOT_DIR.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


async def save_uploads(relative_path: str, uploads: list[UploadFile]) -> int:
    target = _resolve_path(relative_path)
    target.mkdir(parents=True, exist_ok=True)

    quota = settings.nas_quota_bytes
    used_bytes = calculate_used_bytes()
    saved = 0
    for upload in uploads:
        data = await upload.read()
        filename = upload.filename or "upload.bin"
        destination = target / filename
        existing_size = destination.stat().st_size if destination.exists() else 0

        if quota is not None and used_bytes - existing_size + len(data) > quota:
            await upload.close()
            raise QuotaExceededError(
                f"Quota exceeded: attempting to store {used_bytes - existing_size + len(data)} bytes "
                f"with a limit of {quota} bytes"
            )

        destination.write_bytes(data)
        await upload.close()
        saved += 1
        used_bytes = used_bytes - existing_size + len(data)
    return saved


def delete_path(relative_path: str) -> None:
    target = _resolve_path(relative_path)
    if not target.exists():
        return
    if target.is_dir():
        for child in target.iterdir():
            delete_path(str(child.relative_to(ROOT_DIR).as_posix()))
        target.rmdir()
    else:
        target.unlink()


def create_folder(parent_path: str, name: str) -> Path:
    base = _resolve_path(parent_path)
    base.mkdir(parents=True, exist_ok=True)
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def rename_path(old_path: str, new_name: str) -> Path:
    source = _resolve_path(old_path)
    target = source.parent / new_name
    target = _resolve_path(str(target.relative_to(ROOT_DIR).as_posix()))
    source.rename(target)
    return target


def move_path(source_path: str, target_path: str) -> Path:
    source = _resolve_path(source_path)
    destination = _resolve_path(target_path)
    if destination.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        final_target = destination / source.name
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        final_target = destination
    final_target = _resolve_path(str(final_target.relative_to(ROOT_DIR).as_posix()))
    source.rename(final_target)
    return final_target
