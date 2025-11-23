"""
Database-backed file metadata service.

This service manages file metadata in the database instead of JSON files.
It provides CRUD operations for file metadata with ownership tracking.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.file_metadata import FileMetadata


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
        
        metadata.updated_at = datetime.now(timezone.utc)
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
        metadata.updated_at = datetime.now(timezone.utc)
        
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
        metadata.updated_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
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
