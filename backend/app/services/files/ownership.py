"""
File Ownership Transfer & User-Directory Residency Enforcement Service.

This service handles:
- Transferring file/folder ownership between users
- Physical movement of files to maintain user-directory residency invariant
- Cascading updates to child entries, shares, and share links
- Residency enforcement scanning and fixing
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from sqlalchemy import select, or_, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.file_metadata import FileMetadata
from app.models.file_share import FileShare
from app.models.share_link import ShareLink
from app.models.user import User
from app.services.audit.logger_db import get_audit_logger_db
from app.services.files import metadata_db as file_metadata_db

logger = logging.getLogger(__name__)

ROOT_DIR = Path(settings.nas_storage_path).expanduser().resolve()
SHARED_DIR_NAME = "Shared"

ConflictStrategy = Literal["rename", "skip", "overwrite"]


class OwnershipError(Exception):
    """Base exception for ownership operations."""
    pass


class OwnershipTransferError(OwnershipError):
    """Raised when ownership transfer fails."""
    pass


class ResidencyViolationError(OwnershipError):
    """Raised when a residency violation is detected."""
    pass


@dataclass
class ConflictInfo:
    """Information about a naming conflict during transfer."""
    original_path: str
    resolved_path: Optional[str]
    action: str  # "renamed", "skipped", "overwritten"


@dataclass
class OwnershipTransferResult:
    """Result of an ownership transfer operation."""
    success: bool
    message: str
    transferred_count: int = 0
    skipped_count: int = 0
    new_path: Optional[str] = None
    conflicts: list[ConflictInfo] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ResidencyViolation:
    """Information about a file that violates residency rules."""
    path: str
    current_owner_id: int
    current_owner_username: str
    expected_directory: str
    actual_directory: str


@dataclass
class ResidencyEnforcementResult:
    """Result of a residency enforcement operation."""
    violations: list[ResidencyViolation] = field(default_factory=list)
    fixed_count: int = 0


def _get_path_hash(path: str) -> int:
    """Generate a hash for PostgreSQL advisory lock."""
    return int(hashlib.md5(path.encode()).hexdigest()[:15], 16)


def _is_in_shared_dir(path: str) -> bool:
    """Check if path is in the Shared directory."""
    normalized = path.strip("/")
    return normalized == SHARED_DIR_NAME or normalized.startswith(f"{SHARED_DIR_NAME}/")


def _is_home_directory(path: str, username: str) -> bool:
    """Check if path is exactly a user's home directory (top-level)."""
    normalized = path.strip("/")
    return normalized == username


def _get_first_segment(path: str) -> Optional[str]:
    """Get the first path segment (directory)."""
    normalized = path.strip("/")
    if "/" in normalized:
        return normalized.split("/")[0]
    return normalized if normalized else None


def _resolve_name_conflict(
    target_dir: Path,
    filename: str,
    strategy: ConflictStrategy,
    max_attempts: int = 100
) -> tuple[Optional[str], ConflictInfo]:
    """
    Resolve naming conflicts when moving files.
    
    Returns:
        Tuple of (resolved_filename or None, conflict_info)
    """
    target_path = target_dir / filename
    
    if not target_path.exists():
        return filename, ConflictInfo(
            original_path=str(target_path),
            resolved_path=str(target_path),
            action="no_conflict"
        )
    
    if strategy == "skip":
        return None, ConflictInfo(
            original_path=str(target_path),
            resolved_path=None,
            action="skipped"
        )
    
    if strategy == "overwrite":
        return filename, ConflictInfo(
            original_path=str(target_path),
            resolved_path=str(target_path),
            action="overwritten"
        )
    
    # strategy == "rename"
    name_part = Path(filename).stem
    ext_part = Path(filename).suffix
    
    for i in range(2, max_attempts + 2):
        new_name = f"{name_part} ({i}){ext_part}"
        new_target = target_dir / new_name
        if not new_target.exists():
            return new_name, ConflictInfo(
                original_path=str(target_path),
                resolved_path=str(new_target),
                action="renamed"
            )
    
    # Exhausted attempts
    return None, ConflictInfo(
        original_path=str(target_path),
        resolved_path=None,
        action="skipped"
    )


def _get_user_by_id(user_id: int, db: Session) -> Optional[User]:
    """Get user by ID."""
    return db.query(User).filter(User.id == user_id).first()


def _ensure_home_directory_exists(username: str, user_id: int, db: Session) -> Path:
    """Ensure user's home directory exists on disk and in metadata."""
    home_dir = ROOT_DIR / username
    home_dir.mkdir(parents=True, exist_ok=True)
    
    existing = file_metadata_db.get_metadata(username, db=db)
    if not existing:
        file_metadata_db.create_metadata(
            relative_path=username,
            name=username,
            owner_id=user_id,
            size_bytes=0,
            is_directory=True,
            db=db,
        )
    
    return home_dir


def _acquire_advisory_lock(db: Session, path: str) -> None:
    """Acquire PostgreSQL advisory lock for path."""
    path_hash = _get_path_hash(path)
    db.execute(select(1).where(True))  # Ensure transaction is started
    # pg_advisory_xact_lock is automatically released at end of transaction
    db.execute(text(f"SELECT pg_advisory_xact_lock({path_hash})"))


def transfer_ownership(
    path: str,
    new_owner_id: int,
    requesting_user_id: int,
    requesting_user_is_admin: bool,
    db: Session,
    recursive: bool = True,
    conflict_strategy: ConflictStrategy = "rename",
) -> OwnershipTransferResult:
    """
    Transfer ownership of a file or directory to a new owner.
    
    This includes:
    - Validating permissions
    - Physical move (unless in Shared/)
    - Metadata updates
    - Child cascade for directories
    - Share/ShareLink updates
    - Audit logging
    
    Args:
        path: Relative path to the file/directory
        new_owner_id: User ID of the new owner
        requesting_user_id: User ID making the request
        requesting_user_is_admin: Whether requester is admin
        db: Database session
        recursive: Whether to recursively transfer children (for directories)
        conflict_strategy: How to handle naming conflicts
    
    Returns:
        OwnershipTransferResult with details of the operation
    """
    audit = get_audit_logger_db()
    normalized_path = path.strip("/")
    
    try:
        # 1. VALIDATION
        
        # Get current metadata
        metadata = file_metadata_db.get_metadata(normalized_path, db=db)
        if not metadata:
            return OwnershipTransferResult(
                success=False,
                message="File or directory not found",
                error="NOT_FOUND"
            )
        
        old_owner_id = metadata.owner_id
        
        # Check if new owner exists and is active
        new_owner = _get_user_by_id(new_owner_id, db)
        if not new_owner or not new_owner.is_active:
            return OwnershipTransferResult(
                success=False,
                message="Target user not found or inactive",
                error="INVALID_TARGET_USER"
            )
        
        # Self-transfer is a no-op
        if new_owner_id == old_owner_id:
            return OwnershipTransferResult(
                success=True,
                message="No transfer needed - already owned by target user",
                transferred_count=0,
                new_path=normalized_path
            )
        
        # Check authorization: must be current owner or admin
        if not requesting_user_is_admin and requesting_user_id != old_owner_id:
            audit.log_event(
                event_type="SECURITY",
                user=str(requesting_user_id),
                action="ownership_transfer_denied",
                resource=normalized_path,
                success=False,
                error_message="Unauthorized transfer attempt",
                db=db
            )
            return OwnershipTransferResult(
                success=False,
                message="Only the owner or an admin can transfer ownership",
                error="UNAUTHORIZED"
            )
        
        # Cannot transfer home directories themselves
        old_owner_user = _get_user_by_id(old_owner_id, db)
        if old_owner_user and _is_home_directory(normalized_path, old_owner_user.username):
            return OwnershipTransferResult(
                success=False,
                message="Cannot transfer a user's home directory",
                error="HOME_DIRECTORY"
            )
        
        # 2. DETERMINE IF PHYSICAL MOVE IS NEEDED
        
        in_shared = _is_in_shared_dir(normalized_path)
        needs_physical_move = not in_shared
        
        # 3. ACQUIRE LOCK
        _acquire_advisory_lock(db, normalized_path)
        
        # 4. PREPARE PATHS
        source_abs = ROOT_DIR / normalized_path
        
        if not source_abs.exists():
            return OwnershipTransferResult(
                success=False,
                message="Source file/directory does not exist on disk",
                error="DISK_NOT_FOUND"
            )
        
        conflicts: list[ConflictInfo] = []
        transferred_count = 0
        skipped_count = 0
        new_relative_path = normalized_path
        
        if needs_physical_move:
            # Ensure target user has home directory
            _ensure_home_directory_exists(new_owner.username, new_owner.id, db)
            
            target_dir = ROOT_DIR / new_owner.username
            filename = Path(normalized_path).name
            
            # Resolve conflicts
            resolved_name, conflict_info = _resolve_name_conflict(
                target_dir, filename, conflict_strategy
            )
            
            if conflict_info.action != "no_conflict":
                conflicts.append(conflict_info)
            
            if resolved_name is None:
                # Skip due to conflict
                skipped_count = 1
                if metadata.is_directory and recursive:
                    # Count children that would be skipped
                    children = db.query(FileMetadata).filter(
                        FileMetadata.path.startswith(f"{normalized_path}/")
                    ).count()
                    skipped_count += children
                
                return OwnershipTransferResult(
                    success=True,
                    message="Transfer skipped due to naming conflict",
                    transferred_count=0,
                    skipped_count=skipped_count,
                    new_path=normalized_path,
                    conflicts=conflicts
                )
            
            target_abs = target_dir / resolved_name
            new_relative_path = f"{new_owner.username}/{resolved_name}"
            
            # Handle overwrite
            if conflict_info.action == "overwritten" and target_abs.exists():
                _delete_path_and_metadata(str(target_abs.relative_to(ROOT_DIR)), db)
            
            # 5. PHYSICAL MOVE (atomic on same filesystem)
            os.rename(source_abs, target_abs)
            
        # 6. UPDATE METADATA
        
        old_path = metadata.path
        
        # Update the main entry
        metadata.owner_id = new_owner_id
        metadata.path = new_relative_path
        metadata.name = Path(new_relative_path).name
        metadata.parent_path = str(Path(new_relative_path).parent) if "/" in new_relative_path else None
        transferred_count = 1
        
        # 7. CASCADE TO CHILDREN (for directories)
        if metadata.is_directory and recursive:
            old_prefix = f"{old_path}/"
            new_prefix = f"{new_relative_path}/"
            
            children = db.query(FileMetadata).filter(
                FileMetadata.path.startswith(old_prefix)
            ).all()
            
            for child in children:
                # Update path prefix
                child.path = new_prefix + child.path[len(old_prefix):]
                # Update parent_path
                if child.parent_path:
                    if child.parent_path == old_path:
                        child.parent_path = new_relative_path
                    elif child.parent_path.startswith(old_prefix):
                        child.parent_path = new_prefix + child.parent_path[len(old_prefix):]
                # Update owner
                child.owner_id = new_owner_id
                transferred_count += 1
        
        # 8. CASCADE SHARES
        _cascade_shares_on_transfer(metadata.id, old_owner_id, new_owner_id, db)
        
        # 9. COMMIT
        db.commit()
        
        # 10. AUDIT LOG
        audit.log_event(
            event_type="FILE_MODIFY",
            user=str(requesting_user_id),
            action="ownership_transfer",
            resource=new_relative_path,
            details={
                "old_path": old_path,
                "new_path": new_relative_path,
                "old_owner_id": old_owner_id,
                "new_owner_id": new_owner_id,
                "transferred_count": transferred_count,
                "recursive": recursive,
                "physical_move": needs_physical_move,
            },
            success=True,
            db=db
        )
        
        return OwnershipTransferResult(
            success=True,
            message=f"Successfully transferred {transferred_count} item(s)",
            transferred_count=transferred_count,
            skipped_count=skipped_count,
            new_path=new_relative_path,
            conflicts=conflicts
        )
        
    except Exception as e:
        db.rollback()
        logger.exception("Ownership transfer failed for %s", path)
        audit.log_event(
            event_type="FILE_MODIFY",
            user=str(requesting_user_id),
            action="ownership_transfer",
            resource=normalized_path,
            success=False,
            error_message=str(e),
            db=db
        )
        return OwnershipTransferResult(
            success=False,
            message=f"Transfer failed: {e}",
            error="INTERNAL_ERROR"
        )


def _cascade_shares_on_transfer(
    file_id: int,
    old_owner_id: int,
    new_owner_id: int,
    db: Session
) -> None:
    """
    Update shares and share links when ownership changes.
    
    - FileShares where owner_id == old_owner_id -> update to new_owner_id
    - ShareLinks where owner_id == old_owner_id -> update to new_owner_id
    """
    # Update FileShares
    db.query(FileShare).filter(
        FileShare.file_id == file_id,
        FileShare.owner_id == old_owner_id
    ).update({"owner_id": new_owner_id}, synchronize_session=False)
    
    # Update ShareLinks
    db.query(ShareLink).filter(
        ShareLink.file_id == file_id,
        ShareLink.owner_id == old_owner_id
    ).update({"owner_id": new_owner_id}, synchronize_session=False)


def _delete_path_and_metadata(relative_path: str, db: Session) -> None:
    """Delete a file/directory and its metadata (for overwrite strategy)."""
    import shutil
    
    abs_path = ROOT_DIR / relative_path
    
    # Delete children metadata first
    db.query(FileMetadata).filter(
        FileMetadata.path.startswith(f"{relative_path}/")
    ).delete(synchronize_session=False)
    
    # Delete main metadata
    db.query(FileMetadata).filter(FileMetadata.path == relative_path).delete(synchronize_session=False)
    
    # Delete from disk
    if abs_path.exists():
        if abs_path.is_dir():
            shutil.rmtree(abs_path)
        else:
            abs_path.unlink()


def scan_residency_violations(
    db: Session,
    scope: Optional[str] = None
) -> list[ResidencyViolation]:
    """
    Scan for files that violate the residency invariant.
    
    A violation occurs when a file's owner doesn't match the top-level
    directory containing the file (except for Shared/).
    
    Args:
        db: Database session
        scope: Optional username to limit scan to, or None for all users
    
    Returns:
        List of ResidencyViolation objects
    """
    violations: list[ResidencyViolation] = []
    
    # Build query
    query = db.query(FileMetadata, User).join(User, FileMetadata.owner_id == User.id)
    
    if scope:
        # Scan only for specific user
        query = query.filter(User.username == scope)
    
    entries = query.all()
    
    for metadata, user in entries:
        path = metadata.path
        
        # Skip Shared directory
        if _is_in_shared_dir(path):
            continue
        
        # Get first path segment
        first_segment = _get_first_segment(path)
        if not first_segment:
            continue
        
        # File should be in owner's directory
        expected_dir = user.username
        actual_dir = first_segment
        
        if actual_dir != expected_dir:
            violations.append(ResidencyViolation(
                path=path,
                current_owner_id=user.id,
                current_owner_username=user.username,
                expected_directory=expected_dir,
                actual_directory=actual_dir
            ))
    
    return violations


def enforce_residency(
    db: Session,
    dry_run: bool = True,
    scope: Optional[str] = None,
    requesting_user_id: int = 0,
    conflict_strategy: ConflictStrategy = "rename"
) -> ResidencyEnforcementResult:
    """
    Scan and fix residency violations.
    
    Args:
        db: Database session
        dry_run: If True, only report violations without fixing
        scope: Optional username to limit to, or None for all
        requesting_user_id: User ID making the request (for audit)
        conflict_strategy: How to handle naming conflicts
    
    Returns:
        ResidencyEnforcementResult with violations and fix count
    """
    audit = get_audit_logger_db()
    
    violations = scan_residency_violations(db, scope)
    fixed_count = 0
    
    if not dry_run:
        for violation in violations:
            # Calculate correct path
            filename = Path(violation.path).name
            correct_path = f"{violation.expected_directory}/{filename}"
            
            # Check for conflict
            target_abs = ROOT_DIR / correct_path
            resolved_name, _ = _resolve_name_conflict(
                ROOT_DIR / violation.expected_directory,
                filename,
                conflict_strategy
            )
            
            if resolved_name is None:
                continue
            
            correct_path = f"{violation.expected_directory}/{resolved_name}"
            
            try:
                # Physical move
                source_abs = ROOT_DIR / violation.path
                target_abs = ROOT_DIR / correct_path
                
                if source_abs.exists():
                    # Ensure parent directory exists
                    target_abs.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(source_abs, target_abs)
                
                # Update metadata
                metadata = file_metadata_db.get_metadata(violation.path, db=db)
                if metadata:
                    old_path = metadata.path
                    metadata.path = correct_path
                    metadata.name = resolved_name
                    metadata.parent_path = violation.expected_directory
                    
                    # Update children paths if directory
                    if metadata.is_directory:
                        old_prefix = f"{old_path}/"
                        new_prefix = f"{correct_path}/"
                        children = db.query(FileMetadata).filter(
                            FileMetadata.path.startswith(old_prefix)
                        ).all()
                        for child in children:
                            child.path = new_prefix + child.path[len(old_prefix):]
                            if child.parent_path:
                                if child.parent_path == old_path:
                                    child.parent_path = correct_path
                                elif child.parent_path.startswith(old_prefix):
                                    child.parent_path = new_prefix + child.parent_path[len(old_prefix):]
                
                fixed_count += 1
                
            except Exception as e:
                logger.exception("Failed to fix residency violation for %s", violation.path)
                continue
        
        db.commit()
        
        audit.log_event(
            event_type="FILE_MODIFY",
            user=str(requesting_user_id),
            action="residency_enforcement",
            resource=scope or "all",
            details={
                "violations_found": len(violations),
                "fixed_count": fixed_count,
                "dry_run": dry_run,
            },
            success=True,
            db=db
        )
    
    return ResidencyEnforcementResult(
        violations=violations,
        fixed_count=fixed_count
    )


def check_active_uploads(path: str) -> bool:
    """
    Check if there are active uploads to the given path.
    
    This is a placeholder - implementation depends on chunked upload tracking.
    
    Returns:
        True if active uploads exist, False otherwise
    """
    # TODO: Integrate with chunked_upload.py to check active uploads
    # For now, return False (allow transfer)
    return False
