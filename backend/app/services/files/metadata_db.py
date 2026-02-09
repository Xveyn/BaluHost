"""
Database-backed file metadata service.

This service manages file metadata in the database instead of JSON files.
It provides CRUD operations for file metadata with ownership tracking.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.file_metadata import FileMetadata

logger = logging.getLogger(__name__)


def _normalize_path(relative_path: str) -> str:
    """Normalize file path for consistency."""
    if not relative_path:
        return ""
    normalized = Path(relative_path.strip("/")).as_posix()
    return normalized


def _get_parent_path(path: str) -> Optional[str]:
    """Extract parent directory path from full path."""
    if not path or "/" not in path:
        return None
    return str(Path(path).parent.as_posix())


# ============================================================================
# Database Operations
# ============================================================================

def get_metadata(relative_path: str, db: Optional[Session] = None) -> Optional[FileMetadata]:
    """
    Get file metadata from database.
    
    Args:
        relative_path: Path relative to storage root
        db: Database session (optional, creates new if None)
    
    Returns:
        FileMetadata object or None if not found
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        path = _normalize_path(relative_path)
        return db.query(FileMetadata).filter(FileMetadata.path == path).first()
    finally:
        if should_close:
            db.close()


def create_metadata(
    relative_path: str,
    name: str,
    owner_id: int,
    size_bytes: int = 0,
    is_directory: bool = False,
    mime_type: Optional[str] = None,
    checksum: Optional[str] = None,
    db: Optional[Session] = None
) -> FileMetadata:
    """
    Create new file metadata entry in database.
    
    Args:
        relative_path: Path relative to storage root
        name: File or directory name
        owner_id: User ID of the owner
        size_bytes: File size in bytes
        is_directory: Whether this is a directory
        mime_type: MIME type (for files only)
        db: Database session (optional, creates new if None)
    
    Returns:
        Created FileMetadata object
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        path = _normalize_path(relative_path)
        parent_path = _get_parent_path(path)
        
        metadata = FileMetadata(
            path=path,
            name=name,
            owner_id=owner_id,
            size_bytes=size_bytes,
            is_directory=is_directory,
            mime_type=mime_type,
            checksum=checksum,
            parent_path=parent_path,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(metadata)
        db.commit()
        db.refresh(metadata)
        return metadata
    except Exception:
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()


def update_metadata(
    relative_path: str,
    size_bytes: Optional[int] = None,
    mime_type: Optional[str] = None,
    checksum: Optional[str] = None,
    db: Optional[Session] = None
) -> Optional[FileMetadata]:
    """
    Update existing file metadata.
    
    Args:
        relative_path: Path relative to storage root
        size_bytes: New file size (optional)
        mime_type: New MIME type (optional)
        db: Database session (optional, creates new if None)
    
    Returns:
        Updated FileMetadata object or None if not found
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        path = _normalize_path(relative_path)
        metadata = db.query(FileMetadata).filter(FileMetadata.path == path).first()
        
        if not metadata:
            return None
        
        if size_bytes is not None:
            metadata.size_bytes = size_bytes
        if mime_type is not None:
            metadata.mime_type = mime_type
        if checksum is not None:
            metadata.checksum = checksum

        # updated_at is set automatically by onupdate
        db.commit()
        db.refresh(metadata)
        return metadata
    except Exception:
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()


def delete_metadata(relative_path: str, db: Optional[Session] = None) -> bool:
    """
    Delete file metadata from database.
    
    Args:
        relative_path: Path relative to storage root
        db: Database session (optional, creates new if None)
    
    Returns:
        True if deleted, False if not found
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        path = _normalize_path(relative_path)
        metadata = db.query(FileMetadata).filter(FileMetadata.path == path).first()
        
        if not metadata:
            return False
        
        db.delete(metadata)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()


def rename_metadata(
    old_path: str,
    new_path: str,
    new_name: str,
    db: Optional[Session] = None
) -> Optional[FileMetadata]:
    """
    Rename/move file metadata in database.
    
    Args:
        old_path: Current path relative to storage root
        new_path: New path relative to storage root
        new_name: New file/directory name
        db: Database session (optional, creates new if None)
    
    Returns:
        Updated FileMetadata object or None if not found
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        old_normalized = _normalize_path(old_path)
        new_normalized = _normalize_path(new_path)
        
        metadata = db.query(FileMetadata).filter(FileMetadata.path == old_normalized).first()
        if not metadata:
            return None
        
        metadata.path = new_normalized
        metadata.name = new_name
        metadata.parent_path = _get_parent_path(new_normalized)
        # updated_at is set automatically by onupdate
        
        db.commit()
        db.refresh(metadata)
        return metadata
    except Exception:
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()


def list_children(parent_path: str, db: Optional[Session] = None) -> List[FileMetadata]:
    """
    List all files/directories in a directory.
    
    Args:
        parent_path: Parent directory path (empty string for root)
        db: Database session (optional, creates new if None)
    
    Returns:
        List of FileMetadata objects
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        normalized = _normalize_path(parent_path) if parent_path else None
        
        if normalized:
            return db.query(FileMetadata).filter(FileMetadata.parent_path == normalized).all()
        else:
            # Root level: entries with no parent_path
            return db.query(FileMetadata).filter(FileMetadata.parent_path.is_(None)).all()
    finally:
        if should_close:
            db.close()


def get_owner_id(relative_path: str, db: Optional[Session] = None) -> Optional[int]:
    """
    Get owner ID for a file/directory.
    
    Args:
        relative_path: Path relative to storage root
        db: Database session (optional, creates new if None)
    
    Returns:
        Owner user ID or None if not found
    """
    metadata = get_metadata(relative_path, db=db)
    return metadata.owner_id if metadata else None


def set_owner_id(relative_path: str, owner_id: int, db: Optional[Session] = None) -> bool:
    """
    Set owner ID for a file/directory.
    
    Args:
        relative_path: Path relative to storage root
        owner_id: User ID to set as owner
        db: Database session (optional, creates new if None)
    
    Returns:
        True if updated, False if not found
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        path = _normalize_path(relative_path)
        metadata = db.query(FileMetadata).filter(FileMetadata.path == path).first()
        
        if not metadata:
            return False
        
        metadata.owner_id = owner_id
        # updated_at is set automatically by onupdate
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()


def _infer_owner_id(
    normalized_path: str,
    requesting_user_id: int,
    db: Session,
) -> int:
    """Infer the owner of an untracked path on disk.

    Strategy (in order):
    1. First path segment matches a username → that user's ID.
    2. Path starts with ``Shared/`` → requesting user.
    3. Parent directory has metadata → inherit owner.
    4. Fallback → requesting user.
    """
    parts = Path(normalized_path).parts
    if parts:
        first_segment = parts[0]

        # "Shared" directory – attribute to requesting user
        if first_segment == "Shared":
            return requesting_user_id

        # Check if first segment is a username
        from app.services.users import get_user_by_username
        user = get_user_by_username(first_segment, db=db)
        if user is not None:
            return user.id

    # Inherit from parent metadata
    parent = _get_parent_path(normalized_path)
    if parent:
        parent_meta = get_metadata(parent, db=db)
        if parent_meta is not None:
            return parent_meta.owner_id

    return requesting_user_id


def ensure_metadata(
    relative_path: str,
    requesting_user_id: int,
    db: Optional[Session] = None,
) -> Optional[FileMetadata]:
    """Return metadata for *relative_path*, auto-creating it when the path
    exists on disk but has no database entry yet.

    Returns ``None`` only when the path does not exist on disk **and** has no
    DB entry (the caller should treat this as a 404).
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()

    try:
        # Fast path – entry already tracked
        meta = get_metadata(relative_path, db=db)
        if meta is not None:
            return meta

        # Check whether the path actually exists on disk
        from app.services.files.operations import _resolve_path
        try:
            resolved = _resolve_path(relative_path)
        except Exception:
            # Path traversal or invalid – treat as not found
            return None

        if not resolved.exists():
            return None

        # Path exists on disk but is untracked – create metadata now
        normalized = _normalize_path(relative_path)
        owner_id = _infer_owner_id(normalized, requesting_user_id, db)
        is_dir = resolved.is_dir()
        size = 0 if is_dir else resolved.stat().st_size
        name = resolved.name

        try:
            meta = create_metadata(
                relative_path=normalized,
                name=name,
                owner_id=owner_id,
                size_bytes=size,
                is_directory=is_dir,
                db=db,
            )
            logger.info("Auto-created metadata for untracked path: %s (owner=%s)", normalized, owner_id)
            return meta
        except IntegrityError:
            # Race condition – another request created the row first
            db.rollback()
            return get_metadata(relative_path, db=db)
    finally:
        if should_close:
            db.close()


# ============================================================================
# Legacy JSON Compatibility (Deprecated)
# ============================================================================

def get_owner(relative_path: str, db: Optional[Session] = None) -> Optional[str]:
    """
    Get owner ID as string (legacy compatibility).
    
    DEPRECATED: Use get_owner_id() instead.
    """
    owner_id = get_owner_id(relative_path, db=db)
    return str(owner_id) if owner_id is not None else None


def set_owner(relative_path: str, owner_id: str, db: Optional[Session] = None) -> None:
    """
    Set owner ID from string (legacy compatibility).
    
    DEPRECATED: Use set_owner_id() instead.
    """
    try:
        owner_id_int = int(owner_id)
        set_owner_id(relative_path, owner_id_int, db=db)
    except (ValueError, TypeError):
        pass
