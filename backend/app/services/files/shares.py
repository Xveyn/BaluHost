"""Service for file sharing functionality."""
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session, joinedload

from app.models.file_share import FileShare
from app.models.file_metadata import FileMetadata
from app.models.user import User
from app.schemas.shares import (
    FileShareCreate, FileShareUpdate, FileShareResponse,
    SharedWithMeResponse, ShareStatistics
)
from app.schemas.user import UserPublic
from app.services.permissions import is_privileged, ensure_owner_or_privileged, PermissionDeniedError


class ShareService:
    """Service for managing file shares between users."""

    # ===========================
    # File Share Methods
    # ===========================

    @staticmethod
    def create_file_share(db: Session, current_user: UserPublic, data: FileShareCreate) -> FileShare:
        """Share a file with another user."""
        # Verify file exists and user owns it (or is privileged)
        file_metadata = db.get(FileMetadata, data.file_id)
        if not file_metadata:
            raise ValueError("File not found")
        try:
            ensure_owner_or_privileged(current_user, str(file_metadata.owner_id))
        except PermissionDeniedError:
            raise PermissionError("You don't own this file")

        # Verify target user exists
        target_user = db.get(User, data.shared_with_user_id)
        if not target_user:
            raise ValueError("Target user not found")

        # Check if already shared
        existing = db.execute(
            select(FileShare).where(
                FileShare.file_id == data.file_id,
                FileShare.shared_with_user_id == data.shared_with_user_id
            )
        ).scalar_one_or_none()

        if existing:
            raise ValueError("File already shared with this user")

        # Create file share (owner is always the file owner, even when admin creates)
        file_share = FileShare(
            file_id=data.file_id,
            owner_id=file_metadata.owner_id,
            shared_with_user_id=data.shared_with_user_id,
            can_read=data.can_read,
            can_write=data.can_write,
            can_delete=data.can_delete,
            can_share=data.can_share,
            expires_at=data.expires_at
        )

        db.add(file_share)
        db.commit()
        db.refresh(file_share)

        return file_share

    @staticmethod
    def get_file_share(db: Session, share_id: int, current_user: UserPublic) -> Optional[FileShare]:
        """Get a file share by ID (owner or privileged)."""
        if is_privileged(current_user):
            stmt = select(FileShare).where(FileShare.id == share_id)
        else:
            stmt = select(FileShare).where(
                FileShare.id == share_id,
                FileShare.owner_id == current_user.id
            )
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_file_shares_by_file(db: Session, file_id: int, current_user: UserPublic) -> List[FileShare]:
        """Get all shares for a specific file (owner or privileged)."""
        if is_privileged(current_user):
            stmt = select(FileShare).where(FileShare.file_id == file_id)
        else:
            stmt = select(FileShare).where(
                FileShare.file_id == file_id,
                FileShare.owner_id == current_user.id
            )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def get_files_shared_with_user(db: Session, user_id: int) -> List[FileShare]:
        """Get all files shared with a user."""
        stmt = select(FileShare).where(
            FileShare.shared_with_user_id == user_id
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def get_files_shared_by_user(db: Session, owner_id: int, current_user: UserPublic) -> List[FileShare]:
        """Get all files shared by a user. Admins see all shares."""
        if is_privileged(current_user):
            stmt = select(FileShare)
        else:
            stmt = select(FileShare).where(FileShare.owner_id == owner_id)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def update_file_share(
        db: Session,
        share_id: int,
        current_user: UserPublic,
        data: FileShareUpdate
    ) -> FileShare:
        """Update a file share."""
        file_share = ShareService.get_file_share(db, share_id, current_user)
        if not file_share:
            raise ValueError("File share not found")

        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(file_share, field, value)

        db.commit()
        db.refresh(file_share)

        return file_share

    @staticmethod
    def delete_file_share(db: Session, share_id: int, current_user: UserPublic) -> bool:
        """Delete a file share."""
        file_share = ShareService.get_file_share(db, share_id, current_user)
        if not file_share:
            return False

        db.delete(file_share)
        db.commit()
        return True

    @staticmethod
    def check_user_file_access(
        db: Session,
        user_id: int,
        file_id: int
    ) -> Optional[FileShare]:
        """Check if a user has access to a file via sharing."""
        stmt = select(FileShare).where(
            FileShare.file_id == file_id,
            FileShare.shared_with_user_id == user_id
        )
        share = db.execute(stmt).scalar_one_or_none()

        if share and share.is_accessible():
            # Update last access time
            share.last_accessed_at = datetime.now(timezone.utc)
            db.commit()
            return share

        return None

    @staticmethod
    def get_share_statistics(db: Session, user_id: int) -> ShareStatistics:
        """Get sharing statistics for a user."""
        now = datetime.now(timezone.utc)

        # File shares stats
        total_shares = db.execute(
            select(func.count(FileShare.id)).where(FileShare.owner_id == user_id)
        ).scalar_one()

        active_shares = db.execute(
            select(func.count(FileShare.id)).where(
                FileShare.owner_id == user_id,
                or_(
                    FileShare.expires_at.is_(None),
                    FileShare.expires_at > now
                )
            )
        ).scalar_one()

        shared_with_me = db.execute(
            select(func.count(FileShare.id)).where(
                FileShare.shared_with_user_id == user_id,
                or_(
                    FileShare.expires_at.is_(None),
                    FileShare.expires_at > now
                )
            )
        ).scalar_one()

        return ShareStatistics(
            total_file_shares=total_shares,
            active_file_shares=active_shares,
            files_shared_with_me=shared_with_me
        )
