from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from fastapi import UploadFile

from app.core.config import settings
from app.schemas.files import FileItem
from app.schemas.user import UserPublic
from app.services import file_metadata
from app.services.audit_logger import get_audit_logger
from app.services.permissions import PermissionDeniedError, can_view, ensure_owner_or_privileged

ROOT_DIR = Path(settings.nas_storage_path).expanduser().resolve()
ROOT_DIR.mkdir(parents=True, exist_ok=True)
file_metadata.ensure_root_metadata()


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


def _relative_posix(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def get_owner(relative_path: str) -> str | None:
    return file_metadata.get_owner(relative_path)


def ensure_can_view(relative_path: str, user: UserPublic) -> None:
    if not can_view(user, file_metadata.get_owner(relative_path)):
        raise PermissionDeniedError("Operation not permitted")


def get_absolute_path(relative_path: str) -> Path:
    """Expose resolved paths for read-only operations like downloads."""
    return _resolve_path(relative_path)


def list_directory(relative_path: str = "", user: UserPublic | None = None) -> Iterable[FileItem]:
    if user is None:
        raise PermissionDeniedError("Authentication required")

    target = _resolve_path(relative_path)
    if not target.exists():
        return []

    directory_owner = get_owner(relative_path)
    if directory_owner and not can_view(user, directory_owner):
        raise PermissionDeniedError("Operation not permitted")

    items: list[FileItem] = []
    for entry in target.iterdir():
        relative_entry = str(entry.relative_to(ROOT_DIR).as_posix())
        entry_owner = get_owner(relative_entry)
        if not can_view(user, entry_owner):
            continue

        stats = entry.stat()
        item = FileItem(
            name=entry.name,
            path=relative_entry,
            size=stats.st_size,
            type="directory" if entry.is_dir() else "file",
            modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
            owner_id=entry_owner,
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


def calculate_available_bytes() -> int | None:
    """Calculate remaining storage capacity. Returns None if no quota is set."""
    quota = settings.nas_quota_bytes
    if quota is None:
        return None
    used = calculate_used_bytes()
    return max(0, quota - used)


async def save_uploads(
    relative_path: str,
    uploads: list[UploadFile],
    user: UserPublic,
    folder_paths: list[str] | None = None,
) -> int:
    """
    Save uploaded files, optionally preserving folder structure.
    
    Args:
        relative_path: Base destination path
        uploads: List of uploaded files
        user: User performing the upload
        folder_paths: Optional list of relative paths from webkitRelativePath
    """
    audit = get_audit_logger()
    
    target = _resolve_path(relative_path)
    target.mkdir(parents=True, exist_ok=True)

    if relative_path:
        destination_owner = get_owner(relative_path)
        ensure_owner_or_privileged(user, destination_owner)

    owner_id = user.id

    quota = settings.nas_quota_bytes
    used_bytes = calculate_used_bytes()
    
    # Calculate total size of all uploads first
    total_upload_size = 0
    upload_data_list = []
    for upload in uploads:
        data = await upload.read()
        upload_data_list.append(data)
        total_upload_size += len(data)
        await upload.close()
    
    # Check if we have enough space for all files
    if quota is not None and used_bytes + total_upload_size > quota:
        raise QuotaExceededError(
            f"Quota exceeded: attempting to store {used_bytes + total_upload_size} bytes "
            f"with a limit of {quota} bytes. Available: {quota - used_bytes} bytes"
        )
    
    saved = 0
    for idx, upload in enumerate(uploads):
        data = upload_data_list[idx]
        
        # Use folder path if provided (for folder uploads)
        if folder_paths and idx < len(folder_paths) and folder_paths[idx]:
            # Create subdirectories as needed
            file_relative_path = folder_paths[idx]
            file_parts = Path(file_relative_path).parts
            if len(file_parts) > 1:
                subfolder = target / Path(*file_parts[:-1])
                subfolder.mkdir(parents=True, exist_ok=True)
            destination = target / file_relative_path
        else:
            filename = upload.filename or "upload.bin"
            destination = target / filename
        
        existing_size = destination.stat().st_size if destination.exists() else 0
        destination.write_bytes(data)
        saved += 1
        used_bytes = used_bytes - existing_size + len(data)
        relative_destination = str(destination.relative_to(ROOT_DIR).as_posix())
        file_metadata.set_owner(relative_destination, owner_id)
        
        # Log file upload
        audit.log_file_access(
            user=user.username,
            action="upload",
            file_path=relative_destination,
            size_bytes=len(data),
            success=True
        )
    
    return saved


def delete_path(relative_path: str, user: UserPublic | None = None) -> None:
    audit = get_audit_logger()
    
    target = _resolve_path(relative_path)
    if not target.exists():
        return
    
    is_directory = target.is_dir()
    
    if is_directory:
        target_relative = _relative_posix(target)
        if user:
            ensure_owner_or_privileged(user, get_owner(target_relative))
        for child in target.iterdir():
            delete_path(_relative_posix(child), user=user)
        target.rmdir()
    else:
        if user:
            ensure_owner_or_privileged(user, get_owner(_relative_posix(target)))
        target.unlink()
    
    file_metadata.clear_path(relative_path)
    
    # Log deletion
    audit.log_file_access(
        user=user.username if user else "system",
        action="delete",
        file_path=relative_path,
        is_directory=is_directory,
        success=True
    )


def create_folder(parent_path: str, name: str, owner: UserPublic | None = None) -> Path:
    audit = get_audit_logger()
    
    base = _resolve_path(parent_path)
    base.mkdir(parents=True, exist_ok=True)

    if owner and parent_path:
        parent_owner = get_owner(parent_path)
        ensure_owner_or_privileged(owner, parent_owner)

    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    owner_id = owner.id if owner else None
    relative_folder = str(folder.relative_to(ROOT_DIR).as_posix())
    if owner_id:
        file_metadata.set_owner(relative_folder, owner_id)
    
    # Log folder creation
    audit.log_file_access(
        user=owner.username if owner else "system",
        action="create_folder",
        file_path=relative_folder,
        success=True
    )
    
    return folder


def rename_path(old_path: str, new_name: str, user: UserPublic | None = None) -> Path:
    source = _resolve_path(old_path)
    source_relative = _relative_posix(source)

    if user:
        ensure_owner_or_privileged(user, get_owner(source_relative))

    target_relative = (PurePosixPath(source_relative).parent / new_name).as_posix()
    target = _resolve_path(target_relative)

    source.rename(target)
    file_metadata.move_path(source_relative, target_relative)
    return target


def move_path(source_path: str, target_path: str, user: UserPublic | None = None) -> Path:
    audit = get_audit_logger()
    
    source = _resolve_path(source_path)
    source_relative = _relative_posix(source)

    if user:
        ensure_owner_or_privileged(user, get_owner(source_relative))

    destination = _resolve_path(target_path)
    if destination.is_dir():
        target_parent = destination
        final_target = destination / source.name
    else:
        target_parent = destination.parent
        final_target = destination

    target_parent_relative = _relative_posix(target_parent) if target_parent != ROOT_DIR else ""
    if user and target_parent_relative:
        ensure_owner_or_privileged(user, get_owner(target_parent_relative))

    if not target_parent.exists():
        target_parent.mkdir(parents=True, exist_ok=True)

    final_relative = _relative_posix(final_target)
    final_target_resolved = _resolve_path(final_relative)
    source.rename(final_target_resolved)
    file_metadata.move_path(source_relative, final_relative)
    
    # Log move operation
    audit.log_file_access(
        user=user.username if user else "system",
        action="move",
        file_path=source_relative,
        target_path=final_relative,
        success=True
    )
    
    return final_target_resolved
