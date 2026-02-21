from __future__ import annotations

import asyncio
import logging
import mimetypes
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from sqlalchemy import select, or_

from app.core.config import settings

# Cache for calculate_used_bytes() - avoids expensive filesystem scans on every request
_used_bytes_cache: dict[str, tuple[int, float]] = {}  # {"value": (bytes, timestamp)}
_used_bytes_cache_lock = threading.Lock()
_USED_BYTES_CACHE_TTL = 30.0  # Cache for 30 seconds
from app.schemas.files import FileItem
from app.schemas.user import UserPublic
from app.services.files import metadata_db as file_metadata_db
from app.services.audit.logger_db import get_audit_logger_db
from app.services.permissions import PermissionDeniedError, can_view, ensure_owner_or_privileged

ROOT_DIR = Path(settings.nas_storage_path).expanduser().resolve()
ROOT_DIR.mkdir(parents=True, exist_ok=True)

SHARED_DIR_NAME = "Shared"
SHARED_WITH_ME_DIR = "Shared with me"
SYSTEM_DIR_NAME = ".system"
SYSTEM_DIRS = {".system", "lost+found"}
SYSTEM_DIR_PREFIXES = (".Trash-",)


def is_system_directory(name: str) -> bool:
    """Check if a directory name is a filesystem-managed system directory."""
    return name in SYSTEM_DIRS or any(name.startswith(p) for p in SYSTEM_DIR_PREFIXES)


def is_in_shared_dir(relative_path: str) -> bool:
    """Check if a relative path is inside (or is) the Shared directory."""
    return relative_path == SHARED_DIR_NAME or relative_path.startswith(f"{SHARED_DIR_NAME}/")


def is_path_shared_with_user(db: Session, relative_path: str, user_id: int) -> bool:
    """Check if path or any parent is shared with user via FileShare.

    Returns True when *relative_path* itself — or any ancestor directory — has
    an active (non-expired) FileShare granting ``can_read`` to *user_id*.
    """
    if db is None:
        return False

    from app.models.file_share import FileShare
    from app.models.file_metadata import FileMetadata
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    # Build list of candidate paths: the path itself + all parent paths
    candidates: list[str] = []
    parts = PurePosixPath(relative_path).parts
    for i in range(len(parts), 0, -1):
        candidates.append(str(PurePosixPath(*parts[:i])))

    if not candidates:
        return False

    # Single query: join FileShare → FileMetadata, filter by path candidates + user
    stmt = (
        select(FileShare.id)
        .join(FileMetadata, FileShare.file_id == FileMetadata.id)
        .where(
            FileShare.shared_with_user_id == user_id,
            FileShare.owner_id != user_id,
            FileShare.can_read.is_(True),
            FileMetadata.path.in_(candidates),
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now,
            ),
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None


class FileAccessError(Exception):
    """Raised when an operation would leave the permitted storage sandbox."""


class QuotaExceededError(Exception):
    """Raised when an operation would exceed the configured NAS quota."""


class SystemDirectoryError(FileAccessError):
    """Raised when an operation targets a protected system directory."""


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


def get_owner(relative_path: str, db: Optional[Session] = None) -> str | None:
    """Get owner ID as string for a file/directory."""
    return file_metadata_db.get_owner(relative_path, db=db)


def ensure_can_view(relative_path: str, user: UserPublic, db: Optional[Session] = None) -> None:
    """Ensure user can view a file/directory."""
    if is_in_shared_dir(relative_path):
        return  # All authenticated users may view Shared content
    if not can_view(user, file_metadata_db.get_owner(relative_path, db=db)):
        # Fallback: check if the path is shared with this user
        if db and is_path_shared_with_user(db, relative_path, user.id):
            return
        raise PermissionDeniedError("Operation not permitted")


def get_absolute_path(relative_path: str) -> Path:
    """Expose resolved paths for read-only operations like downloads."""
    return _resolve_path(relative_path)


def list_directory(relative_path: str = "", user: UserPublic | None = None, db: Optional[Session] = None) -> Iterable[FileItem]:
    """List files and directories with permission filtering."""
    if user is None:
        raise PermissionDeniedError("Authentication required")

    target = _resolve_path(relative_path)
    if not target.exists():
        return []

    directory_owner = get_owner(relative_path, db=db)
    if directory_owner and not is_in_shared_dir(relative_path) and not can_view(user, directory_owner):
        # Fallback: allow if path is shared with this user
        if not (db and is_path_shared_with_user(db, relative_path, user.id)):
            raise PermissionDeniedError("Operation not permitted")

    items: list[FileItem] = []
    for entry in target.iterdir():
        # Hide system directories from non-admin users
        if is_system_directory(entry.name) and user.role != "admin":
            continue
        relative_entry = str(entry.relative_to(ROOT_DIR).as_posix())
        entry_owner = get_owner(relative_entry, db=db)
        if not is_in_shared_dir(relative_entry) and not can_view(user, entry_owner):
            # Fallback: show entry if it (or a parent) is shared with user
            if not (db and is_path_shared_with_user(db, relative_entry, user.id)):
                continue

        stats = entry.stat()
        
        # Determine mime type for files
        mime_type = None
        if entry.is_file():
            mime_type, _ = mimetypes.guess_type(entry.name)
        
        # Get file_id from metadata if exists
        file_id = None
        if db and entry.is_file():
            from app.services import file_metadata_db
            metadata = file_metadata_db.get_metadata(relative_entry, db=db)
            if metadata:
                file_id = metadata.id
        
        item = FileItem(
            name=entry.name,
            path=relative_entry,
            size=stats.st_size,
            type="directory" if entry.is_dir() else "file",
            modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
            owner_id=entry_owner,
            mime_type=mime_type,
            file_id=file_id,
        )
        items.append(item)

    items.sort(key=lambda item: (item.type != "directory", item.name.lower()))
    return items


def _calculate_used_bytes_uncached() -> int:
    """Internal: Actually scan the filesystem. Called by calculate_used_bytes()."""
    total = 0
    if not ROOT_DIR.exists():
        return total

    excluded_dirs: set[Path] = set()
    for child in ROOT_DIR.iterdir():
        if child.is_dir() and is_system_directory(child.name):
            excluded_dirs.add(child)

    for entry in ROOT_DIR.rglob("*"):
        if any(entry == d or d in entry.parents for d in excluded_dirs):
            continue
        if entry.is_file():
            total += entry.stat().st_size
    return total


def calculate_used_bytes() -> int:
    """Calculate total used bytes in storage.
    
    Uses a 30-second TTL cache to avoid expensive filesystem scans on every request.
    The Settings page and other UI elements call this frequently.
    """
    global _used_bytes_cache
    
    now = time.time()
    
    with _used_bytes_cache_lock:
        if "value" in _used_bytes_cache:
            cached_value, cached_time = _used_bytes_cache["value"]
            if now - cached_time < _USED_BYTES_CACHE_TTL:
                return cached_value
    
    # Cache miss or expired - do the expensive calculation
    total = _calculate_used_bytes_uncached()
    
    with _used_bytes_cache_lock:
        _used_bytes_cache["value"] = (total, now)
    
    return total


def invalidate_used_bytes_cache() -> None:
    """Invalidate the used_bytes cache. Call after file uploads/deletions."""
    global _used_bytes_cache
    with _used_bytes_cache_lock:
        _used_bytes_cache.clear()


def calculate_available_bytes() -> int:
    """Calculate remaining storage capacity.

    When a quota is configured (dev mode), returns ``quota - used``.
    When no quota is set (production), returns actual free disk space
    via ``shutil.disk_usage()`` on the storage root.
    """
    quota = settings.nas_quota_bytes
    if quota is not None:
        used = calculate_used_bytes()
        return max(0, quota - used)
    # No quota — check real disk space on the storage path
    import shutil
    try:
        usage = shutil.disk_usage(ROOT_DIR)
        return usage.free
    except OSError:
        return 0


async def calculate_used_bytes_async() -> int:
    """Async wrapper for calculate_used_bytes() — runs in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(calculate_used_bytes)


async def calculate_available_bytes_async() -> int:
    """Async wrapper for calculate_available_bytes() — runs in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(calculate_available_bytes)


def _schedule_vcl_version(
    destination: Path,
    file_meta_id: int,
    owner_id: int,
    checksum: str,
    is_update: bool,
) -> None:
    """Schedule VCL version creation in a background task."""

    async def _create() -> None:
        from app.core.database import SessionLocal
        from app.models.file_metadata import FileMetadata
        from app.services.versioning.vcl import VCLService

        db = SessionLocal()
        try:
            file_meta = db.get(FileMetadata, file_meta_id)
            if not file_meta:
                return
            content = await asyncio.to_thread(destination.read_bytes)
            vcl_service = VCLService(db)
            vcl_service.create_version(
                file=file_meta,
                content=content,
                user_id=owner_id,
                checksum=checksum,
                change_type="update" if is_update else "create",
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logging.getLogger(__name__).warning(
                "Background VCL version creation failed: %s", e
            )
        finally:
            db.close()

    asyncio.create_task(_create())


async def save_uploads(
    relative_path: str,
    uploads: list[UploadFile],
    user: UserPublic,
    folder_paths: list[str] | None = None,
    db: Optional[Session] = None,
    upload_ids: list[str] | None = None,
) -> list[str]:
    """
    Save uploaded files, optionally preserving folder structure.
    
    Args:
        relative_path: Base destination path
        uploads: List of uploaded files
        user: User performing the upload
        folder_paths: Optional list of relative paths from webkitRelativePath
        db: Database session (optional)
        upload_ids: Optional list of upload session IDs for progress tracking
    """
    from app.services.upload_progress import get_upload_progress_manager
    
    audit = get_audit_logger_db()
    progress_manager = get_upload_progress_manager()
    
    target = _resolve_path(relative_path)
    # If the provided relative_path includes a filename (e.g. updating a single file),
    # use its parent directory as the target directory.
    from pathlib import PurePosixPath
    override_filename: str | None = None
    if relative_path:
        last_part = PurePosixPath(relative_path).name
        # Heuristic: if the last part contains a dot and we only have a single upload,
        # treat the provided path as a file path and use its parent as the target dir.
        if "." in last_part:
            override_filename = last_part
            target = target.parent

    target.mkdir(parents=True, exist_ok=True)

    if relative_path and not is_in_shared_dir(relative_path):
        # Determine ownership rules:
        # - If the provided path refers to a directory (no override filename),
        #   enforce ownership of that destination directory.
        # - If the provided path refers to a file (override_filename set),
        #   enforce ownership of the parent directory (if any).
        # Shared directory: all authenticated users may upload — skip check.
        from pathlib import PurePosixPath
        path_obj = PurePosixPath(relative_path)
        if override_filename is None:
            # Destination is a directory path -> check its owner
            dest_owner = get_owner(path_obj.as_posix(), db=db)
            ensure_owner_or_privileged(user, dest_owner)
        else:
            # Destination was a file path -> check parent directory owner if present
            parent = path_obj.parent.as_posix() if str(path_obj.parent) not in ('.', '/') else ""
            parent_owner = get_owner(parent, db=db) if parent else None
            if parent_owner is not None:
                ensure_owner_or_privileged(user, parent_owner)

    owner_id = user.id

    quota = settings.nas_quota_bytes
    used_bytes = calculate_used_bytes()

    # Pre-check total size using seek on the underlying file object.
    # This avoids reading the entire file into memory just to measure it.
    total_upload_size = 0
    upload_sizes: list[int] = []
    can_stream: list[bool] = []
    for upload in uploads:
        sz = 0
        seekable = False
        try:
            upload.file.seek(0, 2)
            sz = upload.file.tell()
            upload.file.seek(0)
            seekable = True
        except (AttributeError, OSError):
            pass  # Mock or non-seekable — will fall back to full read
        upload_sizes.append(sz)
        can_stream.append(seekable)
        total_upload_size += sz

    # Check available space (quota-based in dev, real disk space in prod)
    available = calculate_available_bytes()
    if total_upload_size > 0 and total_upload_size > available:
        if upload_ids:
            for upload_id in upload_ids:
                await progress_manager.fail_upload(upload_id, "Quota exceeded")
        raise QuotaExceededError(
            f"Not enough space: need {total_upload_size} bytes, "
            f"available {available} bytes"
        )

    STREAM_CHUNK = 8 * 1024 * 1024  # 8 MB read/write buffer

    saved_paths: list[str] = []
    for idx, upload in enumerate(uploads):
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
            filename = override_filename or upload.filename or "upload.bin"
            destination = target / filename

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing_size = destination.stat().st_size if destination.exists() else 0

            import hashlib

            if can_stream[idx]:
                # Stream file to disk — only one STREAM_CHUNK in memory at a time.
                # Read chunks from the upload, then write + hash in a thread.
                written = 0
                hasher = hashlib.sha256()

                # Read all chunks from the async upload into memory first,
                # then write + hash in a single thread call.
                chunks: list[bytes] = []
                while True:
                    chunk = await upload.read(STREAM_CHUNK)
                    if not chunk:
                        break
                    chunks.append(chunk)
                await upload.close()

                def _write_and_hash_stream() -> int:
                    total = 0
                    with open(destination, 'wb') as f:
                        for c in chunks:
                            f.write(c)
                            hasher.update(c)
                            total += len(c)
                    return total

                written = await asyncio.to_thread(_write_and_hash_stream)
                file_checksum = hasher.hexdigest()
            else:
                # Fallback: read entire content at once (small files or test mocks).
                data = await upload.read()
                await upload.close()

                def _write_and_hash_small() -> str:
                    destination.write_bytes(data)
                    return hashlib.sha256(data).hexdigest()

                file_checksum = await asyncio.to_thread(_write_and_hash_small)
                written = len(data)

            # Post-write check for uploads where size was unknown beforehand
            if not can_stream[idx]:
                exceeded = False
                if quota is not None:
                    # Quota mode: use local running total (cache may be stale)
                    exceeded = used_bytes + written > quota
                else:
                    # No quota: check real disk free space
                    import shutil
                    try:
                        exceeded = shutil.disk_usage(ROOT_DIR).free <= 0
                    except OSError:
                        pass
                if exceeded:
                    destination.unlink(missing_ok=True)
                    if upload_ids and idx < len(upload_ids):
                        await progress_manager.fail_upload(upload_ids[idx], "Not enough space")
                    raise QuotaExceededError(
                        f"Not enough space after writing {written} bytes"
                    )

            # Update progress after writing each file
            if upload_ids and idx < len(upload_ids):
                await progress_manager.update_progress(upload_ids[idx], written)

            used_bytes = used_bytes - existing_size + written
            relative_destination = str(destination.relative_to(ROOT_DIR).as_posix())
            saved_paths.append(relative_destination)

            # Create or update file metadata in database
            existing_meta = file_metadata_db.get_metadata(relative_destination, db=db)
            if existing_meta:
                file_metadata_db.update_metadata(
                    relative_destination,
                    size_bytes=written,
                    checksum=file_checksum,
                    db=db
                )
            else:
                file_metadata_db.create_metadata(
                    relative_path=relative_destination,
                    name=destination.name,
                    owner_id=int(owner_id),
                    size_bytes=written,
                    is_directory=False,
                    checksum=file_checksum,
                    db=db
                )

            # Log file upload
            audit.log_file_access(
                user=user.username,
                action="upload",
                file_path=relative_destination,
                size_bytes=written,
                success=True,
                db=db
            )

            # VCL: Check if a version is needed (fast DB queries), then
            # schedule the heavy create_version() work in a background task
            # so it doesn't block the HTTP response.
            try:
                from app.services.versioning.vcl import VCLService
                file_meta = existing_meta or file_metadata_db.get_metadata(relative_destination, db=db)
                if file_meta:
                    should_create, _reason = VCLService(db).should_create_version(
                        file_meta, file_checksum, int(owner_id)
                    )
                    if should_create:
                        _schedule_vcl_version(
                            destination=destination,
                            file_meta_id=file_meta.id,
                            owner_id=int(owner_id),
                            checksum=file_checksum,
                            is_update=bool(existing_meta),
                        )
            except Exception as e:
                logging.getLogger(__name__).warning("VCL check failed: %s", e)

            # Mark upload as completed
            if upload_ids and idx < len(upload_ids):
                await progress_manager.complete_upload(upload_ids[idx])

        except Exception as e:
            # Mark upload as failed
            if upload_ids and idx < len(upload_ids):
                await progress_manager.fail_upload(upload_ids[idx], str(e))
            raise

    # Invalidate storage quota cache after uploads
    invalidate_used_bytes_cache()
    return saved_paths


def delete_path(relative_path: str, user: UserPublic | None = None, db: Optional[Session] = None) -> None:
    """Delete a file or directory and its metadata."""
    audit = get_audit_logger_db()
    
    target = _resolve_path(relative_path)
    if not target.exists():
        return

    if target.parent == ROOT_DIR and is_system_directory(target.name):
        raise SystemDirectoryError(f"Cannot delete system directory '{target.name}'")

    is_directory = target.is_dir()

    if is_directory:
        target_relative = _relative_posix(target)
        if user:
            ensure_owner_or_privileged(user, get_owner(target_relative, db=db))
        for child in target.iterdir():
            delete_path(_relative_posix(child), user=user, db=db)
        target.rmdir()
    else:
        if user:
            ensure_owner_or_privileged(user, get_owner(_relative_posix(target), db=db))
        target.unlink()
    
    # Delete metadata from database
    file_metadata_db.delete_metadata(relative_path, db=db)
    
    # Log deletion
    audit.log_file_access(
        user=user.username if user else "system",
        action="delete",
        file_path=relative_path,
        is_directory=is_directory,
        success=True,
        db=db
    )
    
    # Invalidate storage quota cache after deletion
    invalidate_used_bytes_cache()


def create_folder(parent_path: str, name: str, owner: UserPublic | None = None, db: Optional[Session] = None) -> Path:
    """Create a folder and store its metadata."""
    audit = get_audit_logger_db()
    
    base = _resolve_path(parent_path)
    base.mkdir(parents=True, exist_ok=True)

    if base == ROOT_DIR and is_system_directory(name):
        raise SystemDirectoryError(f"Cannot create folder with reserved name '{name}'")

    if owner and parent_path and not is_in_shared_dir(parent_path):
        parent_owner = get_owner(parent_path, db=db)
        ensure_owner_or_privileged(owner, parent_owner)

    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    owner_id = owner.id if owner else None
    relative_folder = str(folder.relative_to(ROOT_DIR).as_posix())
    
    if owner_id:
        # Create directory metadata in database
        existing = file_metadata_db.get_metadata(relative_folder, db=db)
        if not existing:
            file_metadata_db.create_metadata(
                relative_path=relative_folder,
                name=name,
                owner_id=int(owner_id),
                size_bytes=0,
                is_directory=True,
                db=db
            )
    
    # Log folder creation
    audit.log_file_access(
        user=owner.username if owner else "system",
        action="create_folder",
        file_path=relative_folder,
        success=True,
        db=db
    )
    
    return folder


def rename_path(old_path: str, new_name: str, user: UserPublic | None = None, db: Optional[Session] = None) -> Path:
    """Rename a file or directory and update metadata."""
    source = _resolve_path(old_path)

    if source.parent == ROOT_DIR and is_system_directory(source.name):
        raise SystemDirectoryError(f"Cannot rename system directory '{source.name}'")

    source_relative = _relative_posix(source)

    if user:
        ensure_owner_or_privileged(user, get_owner(source_relative, db=db))

    target_relative = (PurePosixPath(source_relative).parent / new_name).as_posix()
    target = _resolve_path(target_relative)

    source.rename(target)
    
    # Update metadata in database
    file_metadata_db.rename_metadata(
        old_path=source_relative,
        new_path=target_relative,
        new_name=new_name,
        db=db
    )
    
    return target


def move_path(source_path: str, target_path: str, user: UserPublic | None = None, db: Optional[Session] = None) -> Path:
    """Move a file or directory and update metadata."""
    audit = get_audit_logger_db()

    source = _resolve_path(source_path)

    if source.parent == ROOT_DIR and is_system_directory(source.name):
        raise SystemDirectoryError(f"Cannot move system directory '{source.name}'")

    source_relative = _relative_posix(source)

    if user:
        ensure_owner_or_privileged(user, get_owner(source_relative, db=db))

    destination = _resolve_path(target_path)
    if destination.is_dir():
        target_parent = destination
        final_target = destination / source.name
    else:
        target_parent = destination.parent
        final_target = destination

    target_parent_relative = _relative_posix(target_parent) if target_parent != ROOT_DIR else ""
    if user and target_parent_relative:
        ensure_owner_or_privileged(user, get_owner(target_parent_relative, db=db))

    if not target_parent.exists():
        target_parent.mkdir(parents=True, exist_ok=True)

    final_relative = _relative_posix(final_target)
    final_target_resolved = _resolve_path(final_relative)
    source.rename(final_target_resolved)
    
    # Update metadata in database
    file_metadata_db.rename_metadata(
        old_path=source_relative,
        new_path=final_relative,
        new_name=final_target.name,
        db=db
    )
    
    # Log move operation
    audit.log_file_access(
        user=user.username if user else "system",
        action="move",
        file_path=source_relative,
        target_path=final_relative,
        success=True,
        db=db
    )
    
    return final_target_resolved
