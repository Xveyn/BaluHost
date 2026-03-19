"""Permission and sharing checks for file operations.

Imports ``path_utils`` as a *module* so monkeypatching ROOT_DIR in tests
propagates to all consumers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.file_share import FileShare

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


def are_paths_shared_with_user_bulk(
    db: Session,
    relative_paths: list[str],
    user_id: int,
) -> set[str]:
    """Check which paths (or their ancestors) are shared with a user.

    Returns the subset of *relative_paths* that have an active share granting
    ``can_read`` to *user_id*.  This replaces N individual calls to
    ``is_path_shared_with_user`` with a single query.
    """
    if db is None or not relative_paths:
        return set()

    from app.models.file_share import FileShare
    from app.models.file_metadata import FileMetadata

    now = datetime.now(timezone.utc)

    # Build a union of all candidate ancestor paths for every entry.
    # We also need to know which *original* path each candidate belongs to so
    # that we can map a match back to the entry.
    candidate_to_entries: dict[str, list[str]] = {}
    for rp in relative_paths:
        for anc in _ancestor_paths(rp):
            candidate_to_entries.setdefault(anc, []).append(rp)

    all_candidates = list(candidate_to_entries.keys())
    if not all_candidates:
        return set()

    # Single query: find which candidate paths have an active share
    stmt = (
        select(FileMetadata.path)
        .join(FileShare, FileShare.file_id == FileMetadata.id)
        .where(
            FileShare.shared_with_user_id == user_id,
            FileShare.owner_id != user_id,
            FileShare.can_read.is_(True),
            FileMetadata.path.in_(all_candidates),
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now,
            ),
        )
    )
    matched_candidates = {row[0] for row in db.execute(stmt).all()}

    # Map matched candidates back to original entry paths
    shared_entries: set[str] = set()
    for mc in matched_candidates:
        for entry_path in candidate_to_entries.get(mc, []):
            shared_entries.add(entry_path)

    return shared_entries


def get_share_permissions_bulk(
    db: Session,
    relative_paths: list[str],
    user_id: int,
) -> dict[str, "FileShare"]:
    """Return FileShare objects for multiple paths in bulk.

    For each path in *relative_paths*, checks the path itself and all ancestor
    directories for an active share.  Returns a dict mapping relative_path to
    the first matching FileShare, or omits the key if no share exists.
    """
    if db is None or not relative_paths:
        return {}

    from app.models.file_share import FileShare
    from app.models.file_metadata import FileMetadata

    now = datetime.now(timezone.utc)

    # Build candidate → entry-path mapping (same pattern as bulk shared check)
    candidate_to_entries: dict[str, list[str]] = {}
    for rp in relative_paths:
        for anc in _ancestor_paths(rp):
            candidate_to_entries.setdefault(anc, []).append(rp)

    all_candidates = list(candidate_to_entries.keys())
    if not all_candidates:
        return {}

    stmt = (
        select(FileShare, FileMetadata.path)
        .join(FileMetadata, FileShare.file_id == FileMetadata.id)
        .where(
            FileShare.shared_with_user_id == user_id,
            FileShare.owner_id != user_id,
            FileShare.can_read.is_(True),
            FileMetadata.path.in_(all_candidates),
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now,
            ),
        )
    )
    rows = db.execute(stmt).all()

    # Map: for each entry path, pick the first share found
    result: dict[str, FileShare] = {}
    for share_obj, matched_path in rows:
        for entry_path in candidate_to_entries.get(matched_path, []):
            if entry_path not in result:
                result[entry_path] = share_obj

    return result


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
