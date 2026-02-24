"""Permission and sharing checks for file operations.

Imports ``path_utils`` as a *module* so monkeypatching ROOT_DIR in tests
propagates to all consumers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.schemas.user import UserPublic
from app.services.files import path_utils
from app.services.files import metadata_db as file_metadata_db
from app.services.permissions import PermissionDeniedError, can_view


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ancestor_paths(relative_path: str) -> list[str]:
    """Build list of candidate paths: the path itself + all parent paths."""
    parts = PurePosixPath(relative_path).parts
    candidates: list[str] = []
    for i in range(len(parts), 0, -1):
        candidates.append(str(PurePosixPath(*parts[:i])))
    return candidates


# ── Share queries ─────────────────────────────────────────────────────────────

def is_path_shared_with_user(db: Session, relative_path: str, user_id: int) -> bool:
    """Check if path or any parent is shared with user via FileShare.

    Returns True when *relative_path* itself — or any ancestor directory — has
    an active (non-expired) FileShare granting ``can_read`` to *user_id*.
    """
    if db is None:
        return False

    from app.models.file_share import FileShare
    from app.models.file_metadata import FileMetadata

    now = datetime.now(timezone.utc)

    candidates = _ancestor_paths(relative_path)
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


def get_share_permissions(db: Session, relative_path: str, user_id: int):
    """Return the FileShare object granting access to *relative_path* for *user_id*.

    Checks the path itself and all ancestor directories, returning the first
    matching active (non-expired) share, or ``None`` if no share exists.
    """
    if db is None:
        return None

    from app.models.file_share import FileShare
    from app.models.file_metadata import FileMetadata

    now = datetime.now(timezone.utc)

    candidates = _ancestor_paths(relative_path)
    if not candidates:
        return None

    stmt = (
        select(FileShare)
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
    return db.execute(stmt).scalars().first()


# ── Ownership / permission enforcement ────────────────────────────────────────

def get_owner(relative_path: str, db: Optional[Session] = None) -> str | None:
    """Get owner ID as string for a file/directory."""
    return file_metadata_db.get_owner(relative_path, db=db)


def ensure_can_view(relative_path: str, user: UserPublic, db: Optional[Session] = None) -> None:
    """Ensure user can view a file/directory."""
    if path_utils.is_in_shared_dir(relative_path):
        return  # All authenticated users may view Shared content
    if not can_view(user, file_metadata_db.get_owner(relative_path, db=db)):
        # Fallback: check if the path is shared with this user
        if db and is_path_shared_with_user(db, relative_path, user.id):
            return
        raise PermissionDeniedError("Operation not permitted")
