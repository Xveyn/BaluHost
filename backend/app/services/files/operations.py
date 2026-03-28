"""File CRUD operations (list, upload, delete, create, rename, move).

Formerly contained path utilities, permission checks, and quota logic —
those have been extracted to ``path_utils``, ``access``, and ``storage``
respectively.  This module re-exports every moved symbol so that existing
``from app.services.files.operations import X`` statements keep working.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Iterable, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.file_metadata import FileMetadata
    from app.models.file_share import FileShare

from app.core.config import settings
from app.schemas.files import FileItem
from app.schemas.user import UserPublic
from app.services.files import metadata_db as file_metadata_db
from app.services.files import path_utils
from app.services.files.folder_size import get_folder_size, invalidate_folder_sizes_for_path
from app.services.audit.logger_db import get_audit_logger_db
from app.services.permissions import PermissionDeniedError, can_view, ensure_owner_or_privileged

# ── Re-exports from path_utils (backward compatibility) ──────────────────────
from app.services.files.path_utils import (  # noqa: F401
    ROOT_DIR,
    SHARED_DIR_NAME,
    SHARED_WITH_ME_DIR,
    SYSTEM_DIR_NAME,
    SYSTEM_DIRS,
    SYSTEM_DIR_PREFIXES,
    FileAccessError,
    QuotaExceededError,
    SystemDirectoryError,
    is_system_directory,
    is_in_shared_dir,
    _resolve_path,
    _relative_posix,
    get_absolute_path,
)

# ── Re-exports from access (backward compatibility) ──────────────────────────
from app.services.files.access import (  # noqa: F401
    is_path_shared_with_user,
    get_share_permissions,
    get_owner,
    ensure_can_view,
    are_paths_shared_with_user_bulk,
    get_share_permissions_bulk,
)

# ── Re-exports from storage (backward compatibility) ─────────────────────────
from app.services.files.storage import (  # noqa: F401
    _used_bytes_cache,
    _used_bytes_cache_lock,
    _used_bytes_inflight,
    _USED_BYTES_CACHE_TTL,
    _invalidate_ssd_cache,
    _calculate_used_bytes_uncached,
    calculate_used_bytes,
    invalidate_used_bytes_cache,
    calculate_available_bytes,
    calculate_used_bytes_async,
    calculate_available_bytes_async,
)

logger = logging.getLogger(__name__)


# ── VCL helper (only used by save_uploads / chunked_upload) ──────────────────

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


# ── CRUD operations ──────────────────────────────────────────────────────────

def list_directory(relative_path: str = "", user: UserPublic | None = None, db: Optional[Session] = None) -> Iterable[FileItem]:
    """List files and directories with permission filtering.

    Uses batch DB queries to avoid the N+1 problem: instead of issuing 3-4
    individual queries per filesystem entry, all metadata, ownership, and share
    data is pre-fetched in 2-4 queries total regardless of directory size.
    """
    if user is None:
        raise PermissionDeniedError("Authentication required")

    target = path_utils._resolve_path(relative_path)
    if not target.exists():
        return []

    directory_owner = get_owner(relative_path, db=db)
    if directory_owner and not path_utils.is_in_shared_dir(relative_path) and not can_view(user, directory_owner):
        # Fallback: allow if path is shared with this user
        if not (db and is_path_shared_with_user(db, relative_path, user.id)):
            raise PermissionDeniedError("Operation not permitted")

    # ── Pass 1: collect filesystem entries and their relative paths ────────
    entries: list[tuple[Path, str, bool]] = []  # (entry, relative_path, is_dir)
    for entry in target.iterdir():
        # Hide system directories from non-admin users
        if path_utils.is_system_directory(entry.name) and user.role != "admin":
            continue
        relative_entry = str(entry.relative_to(path_utils.ROOT_DIR).as_posix())
        entries.append((entry, relative_entry, entry.is_dir()))

    if not entries:
        return []

    all_paths = [rel for _, rel, _ in entries]

    # ── Batch fetch: metadata + owners (1 query) ──────────────────────────
    metadata_map: dict[str, "FileMetadata"] = {}
    owner_map: dict[str, str | None] = {}
    if db:
        metadata_map = file_metadata_db.get_metadata_bulk(all_paths, db=db)
        # Build owner_map from the bulk metadata (no extra query needed)
        owner_map = {
            path: str(meta.owner_id) for path, meta in metadata_map.items()
        }
    else:
        # Without a db session, owners are always None
        pass

    # ── Batch fetch: share visibility + share permissions (1-2 queries) ───
    # Determine which entries need a share-based visibility check:
    # those not in shared dir and not viewable by the current user.
    needs_share_check: list[str] = []
    for _, rel, _ in entries:
        if not path_utils.is_in_shared_dir(rel) and not can_view(user, owner_map.get(rel)):
            needs_share_check.append(rel)

    shared_entries: set[str] = set()
    if db and needs_share_check:
        shared_entries = are_paths_shared_with_user_bulk(db, needs_share_check, user.id)

    # Determine which visible entries need share permissions attached:
    # non-owner, non-shared-dir entries that have an owner.
    needs_permissions: list[str] = []
    for _, rel, _ in entries:
        entry_owner = owner_map.get(rel)
        if not entry_owner:
            continue
        if path_utils.is_in_shared_dir(rel):
            continue
        if can_view(user, entry_owner):
            continue
        # Entry is visible only if shared — it needs permission info
        if rel in shared_entries:
            needs_permissions.append(rel)

    share_perms_map: dict[str, FileShare] = {}
    if db and needs_permissions:
        share_perms_map = get_share_permissions_bulk(db, needs_permissions, user.id)

    # ── Ensure metadata exists for directories (side-effect preservation) ─
    # Directories without metadata get auto-created via ensure_metadata.
    # We only need to call this for dirs NOT already in metadata_map.
    if db:
        dir_paths_needing_ensure = [
            rel for _, rel, is_dir in entries if is_dir and rel not in metadata_map
        ]
        for rel in dir_paths_needing_ensure:
            meta = file_metadata_db.ensure_metadata(rel, requesting_user_id=user.id, db=db)
            if meta:
                metadata_map[rel] = meta
                owner_map[rel] = str(meta.owner_id)

    # ── Pass 2: build FileItem list using pre-fetched data ────────────────
    items: list[FileItem] = []
    for entry, relative_entry, is_dir in entries:
        entry_owner = owner_map.get(relative_entry)

        # Permission check: skip entries the user cannot see
        if not path_utils.is_in_shared_dir(relative_entry) and not can_view(user, entry_owner):
            if relative_entry not in shared_entries:
                continue

        stats = entry.stat()

        # Determine mime type for files
        mime_type = None
        if not is_dir:
            mime_type, _ = mimetypes.guess_type(entry.name)

        # Get file_id from pre-fetched metadata
        file_id = None
        if db:
            meta = metadata_map.get(relative_entry)
            if meta:
                file_id = meta.id

        checksum = None
        if not is_dir and db:
            meta = metadata_map.get(relative_entry)
            if meta:
                checksum = meta.checksum

        item = FileItem(
            name=entry.name,
            path=relative_entry,
            size=get_folder_size(entry) if is_dir else stats.st_size,
            type="directory" if is_dir else "file",
            modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
            owner_id=entry_owner,
            mime_type=mime_type,
            file_id=file_id,
            checksum=checksum,
        )
        # Attach share permissions for non-owner shared files
        if db and entry_owner and not can_view(user, entry_owner) and not path_utils.is_in_shared_dir(relative_entry):
            share = share_perms_map.get(relative_entry)
            if share:
                item.can_read = share.can_read
                item.can_write = share.can_write
                item.can_delete = share.can_delete
        items.append(item)

    items.sort(key=lambda item: (item.type != "directory", item.name.lower()))
    return items


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

    target = path_utils._resolve_path(relative_path)
    # If the provided relative_path includes a filename (e.g. updating a single file),
    # use its parent directory as the target directory.
    override_filename: str | None = None
    if relative_path:
        last_part = PurePosixPath(relative_path).name
        # Heuristic: if the last part contains a dot and we only have a single upload,
        # treat the provided path as a file path and use its parent as the target dir.
        if "." in last_part:
            override_filename = last_part
            target = target.parent

    target.mkdir(parents=True, exist_ok=True)

    if relative_path and not path_utils.is_in_shared_dir(relative_path):
        # Determine ownership rules:
        # - If the provided path refers to a directory (no override filename),
        #   enforce ownership of that destination directory.
        # - If the provided path refers to a file (override_filename set),
        #   enforce ownership of the parent directory (if any).
        # Shared directory: all authenticated users may upload — skip check.
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

        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        try:
            existing_size = destination.stat().st_size if destination.exists() else 0

            if can_stream[idx]:
                # Stream file to disk — only one STREAM_CHUNK in memory at a time.
                written = 0
                hasher = hashlib.sha256()

                def _write_and_hash_chunk(f, data: bytes) -> None:
                    f.write(data)
                    hasher.update(data)

                f = await asyncio.to_thread(open, destination, 'wb')
                try:
                    while True:
                        chunk = await upload.read(STREAM_CHUNK)
                        if not chunk:
                            break
                        await asyncio.to_thread(_write_and_hash_chunk, f, chunk)
                        written += len(chunk)
                finally:
                    await asyncio.to_thread(f.close)
                await upload.close()
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
                        exceeded = shutil.disk_usage(path_utils.ROOT_DIR).free <= 0
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
            relative_destination = str(destination.relative_to(path_utils.ROOT_DIR).as_posix())
            saved_paths.append(relative_destination)

            # Create or update file metadata in database.
            # Run in thread pool with db=None so each call creates its own
            # session — avoids blocking the event loop with synchronous
            # db.commit() during bulk uploads.
            existing_meta = await asyncio.to_thread(
                file_metadata_db.get_metadata, relative_destination, db=None
            )
            if existing_meta:
                await asyncio.to_thread(
                    file_metadata_db.update_metadata,
                    relative_destination,
                    size_bytes=written,
                    checksum=file_checksum,
                    db=None,
                )
            else:
                await asyncio.to_thread(
                    file_metadata_db.create_metadata,
                    relative_path=relative_destination,
                    name=destination.name,
                    owner_id=int(owner_id),
                    size_bytes=written,
                    is_directory=False,
                    checksum=file_checksum,
                    db=None,
                )

            # Log file upload (also in thread pool to avoid blocking)
            await asyncio.to_thread(
                audit.log_file_access,
                user=user.username,
                action="upload",
                file_path=relative_destination,
                size_bytes=written,
                success=True,
                db=None,
            )

            # VCL: Check if a version is needed (fast DB queries), then
            # schedule the heavy create_version() work in a background task
            # so it doesn't block the HTTP response.
            try:
                from app.services.versioning.vcl import VCLService
                from app.core.database import SessionLocal as _VCLSessionLocal
                file_meta = existing_meta or await asyncio.to_thread(
                    file_metadata_db.get_metadata, relative_destination, db=None
                )
                if file_meta:
                    _fm = file_meta  # capture narrowed type for closure
                    def _vcl_check():
                        with _VCLSessionLocal() as vcl_db:
                            return VCLService(vcl_db).should_create_version(
                                _fm, file_checksum, int(owner_id)
                            )
                    should_create, _reason = await asyncio.to_thread(_vcl_check)
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

            # Invalidate SSD cache for overwritten files
            if existing_meta:
                _invalidate_ssd_cache(relative_destination, db=db)

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
    invalidate_folder_sizes_for_path(path_utils._resolve_path(relative_path), path_utils.ROOT_DIR)
    return saved_paths


def delete_path(relative_path: str, user: UserPublic | None = None, db: Optional[Session] = None) -> None:
    """Delete a file or directory and its metadata.

    For directories the deletion is recursive. If a child deletion fails
    the error propagates immediately so the caller sees a clear failure
    rather than a silently half-deleted tree.
    """
    audit = get_audit_logger_db()

    target = path_utils._resolve_path(relative_path)
    if not target.exists():
        return

    if target.parent == path_utils.ROOT_DIR and path_utils.is_system_directory(target.name):
        raise SystemDirectoryError(f"Cannot delete system directory '{target.name}'")

    is_directory = target.is_dir()

    if is_directory:
        target_relative = path_utils._relative_posix(target)
        if user:
            try:
                ensure_owner_or_privileged(user, get_owner(target_relative, db=db))
            except PermissionDeniedError:
                if db:
                    share = get_share_permissions(db, target_relative, user.id)
                    if not (share and share.can_delete):
                        raise
                else:
                    raise
        # Collect children first, then delete bottom-up so partial
        # failures don't leave orphaned metadata.
        children = list(target.iterdir())
        for child in children:
            delete_path(path_utils._relative_posix(child), user=user, db=db)
        target.rmdir()
    else:
        file_relative = path_utils._relative_posix(target)
        if user:
            try:
                ensure_owner_or_privileged(user, get_owner(file_relative, db=db))
            except PermissionDeniedError:
                if db:
                    share = get_share_permissions(db, file_relative, user.id)
                    if not (share and share.can_delete):
                        raise
                else:
                    raise
        target.unlink()

    # Delete metadata from database
    file_metadata_db.delete_metadata(relative_path, db=db)

    # Invalidate SSD cache
    if not is_directory:
        _invalidate_ssd_cache(relative_path, db=db)

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
    invalidate_folder_sizes_for_path(path_utils._resolve_path(relative_path), path_utils.ROOT_DIR)


def create_folder(parent_path: str, name: str, owner: UserPublic | None = None, db: Optional[Session] = None) -> Path:
    """Create a folder and store its metadata."""
    audit = get_audit_logger_db()

    base = path_utils._resolve_path(parent_path)
    base.mkdir(parents=True, exist_ok=True)

    if base == path_utils.ROOT_DIR and path_utils.is_system_directory(name):
        raise SystemDirectoryError(f"Cannot create folder with reserved name '{name}'")

    if owner and parent_path and not path_utils.is_in_shared_dir(parent_path):
        parent_owner = get_owner(parent_path, db=db)
        ensure_owner_or_privileged(owner, parent_owner)

    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    owner_id = owner.id if owner else None
    relative_folder = str(folder.relative_to(path_utils.ROOT_DIR).as_posix())

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
    source = path_utils._resolve_path(old_path)

    if source.parent == path_utils.ROOT_DIR and path_utils.is_system_directory(source.name):
        raise SystemDirectoryError(f"Cannot rename system directory '{source.name}'")

    source_relative = path_utils._relative_posix(source)

    if user:
        try:
            ensure_owner_or_privileged(user, get_owner(source_relative, db=db))
        except PermissionDeniedError:
            if db:
                share = get_share_permissions(db, source_relative, user.id)
                if not (share and share.can_write):
                    raise
            else:
                raise

    target_relative = (PurePosixPath(source_relative).parent / new_name).as_posix()
    target = path_utils._resolve_path(target_relative)

    is_dir = source.is_dir()
    source.rename(target)

    # Update metadata in database
    file_metadata_db.rename_metadata(
        old_path=source_relative,
        new_path=target_relative,
        new_name=new_name,
        db=db
    )

    # Invalidate SSD cache for renamed files
    if not is_dir:
        _invalidate_ssd_cache(source_relative, db=db)

    # Invalidate folder size cache for renamed directories
    if is_dir:
        invalidate_folder_sizes_for_path(source, path_utils.ROOT_DIR)
        invalidate_folder_sizes_for_path(target, path_utils.ROOT_DIR)

    return target


def move_path(source_path: str, target_path: str, user: UserPublic | None = None, db: Optional[Session] = None) -> Path:
    """Move a file or directory and update metadata."""
    audit = get_audit_logger_db()

    source = path_utils._resolve_path(source_path)

    if source.parent == path_utils.ROOT_DIR and path_utils.is_system_directory(source.name):
        raise SystemDirectoryError(f"Cannot move system directory '{source.name}'")

    source_relative = path_utils._relative_posix(source)

    if user:
        try:
            ensure_owner_or_privileged(user, get_owner(source_relative, db=db))
        except PermissionDeniedError:
            if db:
                share = get_share_permissions(db, source_relative, user.id)
                if not (share and share.can_write):
                    raise
            else:
                raise

    destination = path_utils._resolve_path(target_path)
    if destination.is_dir():
        target_parent = destination
        final_target = destination / source.name
    else:
        target_parent = destination.parent
        final_target = destination

    target_parent_relative = path_utils._relative_posix(target_parent) if target_parent != path_utils.ROOT_DIR else ""
    if user and target_parent_relative:
        ensure_owner_or_privileged(user, get_owner(target_parent_relative, db=db))

    if not target_parent.exists():
        target_parent.mkdir(parents=True, exist_ok=True)

    final_relative = path_utils._relative_posix(final_target)
    final_target_resolved = path_utils._resolve_path(final_relative)
    source_parent = source.parent
    is_file = source.is_file()
    source.rename(final_target_resolved)

    # Update metadata in database
    file_metadata_db.rename_metadata(
        old_path=source_relative,
        new_path=final_relative,
        new_name=final_target.name,
        db=db
    )

    # Invalidate SSD cache for moved files
    if is_file:
        _invalidate_ssd_cache(source_relative, db=db)

    # Invalidate folder size cache for source parent and destination
    invalidate_folder_sizes_for_path(source_parent, path_utils.ROOT_DIR)
    invalidate_folder_sizes_for_path(final_target_resolved.parent, path_utils.ROOT_DIR)

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


# ── Virtual directory listings for non-admin users ────────────────────────────

def list_user_root(user: UserPublic, db: Session) -> list[FileItem]:
    """Build the virtual root listing for a non-admin user.

    Shows: Shared/, user's home directory, and optionally "Shared with me".
    """
    from sqlalchemy import select, func, or_
    from app.models.file_share import FileShare
    from app.services.users import _create_home_directory

    # Ensure home dir exists
    try:
        _create_home_directory(user.username, user.id, db=db)
    except Exception:
        pass

    entries: list[FileItem] = []

    # Shared directory
    shared_path = _resolve_path(SHARED_DIR_NAME)
    if shared_path.exists():
        stats = shared_path.stat()
        entries.append(FileItem(
            name=SHARED_DIR_NAME,
            path=SHARED_DIR_NAME,
            size=0,
            type="directory",
            modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
            owner_id=None,
            mime_type=None,
            file_id=None,
        ))

    # User's home directory
    home_path = _resolve_path(user.username)
    if home_path.exists():
        stats = home_path.stat()
        entries.append(FileItem(
            name=user.username,
            path=user.username,
            size=0,
            type="directory",
            modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
            owner_id=str(user.id),
            mime_type=None,
            file_id=None,
        ))

    # "Shared with me" virtual folder — only show if user has active shares
    now = datetime.now(timezone.utc)
    share_count = db.execute(
        select(func.count(FileShare.id)).where(
            FileShare.shared_with_user_id == user.id,
            FileShare.owner_id != user.id,
            FileShare.can_read.is_(True),
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now,
            ),
        )
    ).scalar_one()
    if share_count > 0:
        entries.append(FileItem(
            name=SHARED_WITH_ME_DIR,
            path=SHARED_WITH_ME_DIR,
            size=0,
            type="directory",
            modified_at=datetime.now(timezone.utc),
            owner_id=None,
            mime_type=None,
            file_id=None,
        ))

    return entries


def list_shared_with_me(user: UserPublic, db: Session) -> list[FileItem]:
    """Build the "Shared with me" virtual directory listing for a user."""
    from sqlalchemy import select, or_
    from app.models.file_share import FileShare
    from app.models.file_metadata import FileMetadata
    from app.models.user import User as UserModel

    now = datetime.now(timezone.utc)
    shares = db.execute(
        select(FileShare).where(
            FileShare.shared_with_user_id == user.id,
            FileShare.owner_id != user.id,
            FileShare.can_read.is_(True),
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now,
            ),
        )
    ).scalars().all()

    entries: list[FileItem] = []
    for share in shares:
        file_meta = db.get(FileMetadata, share.file_id)
        if not file_meta:
            continue
        owner = db.get(UserModel, share.owner_id)
        owner_name = owner.username if owner else str(share.owner_id)
        entries.append(FileItem(
            name=f"{file_meta.name} (from {owner_name})",
            path=file_meta.path,
            size=file_meta.size_bytes,
            type="directory" if file_meta.is_directory else "file",
            modified_at=file_meta.updated_at or file_meta.created_at,
            owner_id=str(share.owner_id),
            mime_type=file_meta.mime_type,
            file_id=file_meta.id,
            can_read=share.can_read,
            can_write=share.can_write,
            can_delete=share.can_delete,
        ))

    return entries
