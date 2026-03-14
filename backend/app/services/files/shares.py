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
        # Verify file exists and user owns it (or is privileged, or has can_share)
        file_metadata = db.get(FileMetadata, data.file_id)
        if not file_metadata:
            raise ValueError("File not found")
        try:
            ensure_owner_or_privileged(current_user, str(file_metadata.owner_id))
        except PermissionDeniedError:
            # Not the owner and not privileged — check if user has can_share permission
            existing_share = db.execute(
                select(FileShare).where(
                    FileShare.file_id == data.file_id,
                    FileShare.shared_with_user_id == current_user.id,
                    FileShare.can_share == True,
                )
            ).scalar_one_or_none()
            if not existing_share or existing_share.is_expired():
                raise PermissionError("You don't have permission to share this file")

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
        """Get all active (non-expired) files shared with a user."""
        now = datetime.now(timezone.utc)
        stmt = select(FileShare).where(
            FileShare.shared_with_user_id == user_id,
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now
            )
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
        """Check if a user has access to a file via sharing (read-only check)."""
        now = datetime.now(timezone.utc)
        stmt = select(FileShare).where(
            FileShare.file_id == file_id,
            FileShare.shared_with_user_id == user_id,
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now
            )
        )
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def list_shareable_users(db: Session, exclude_user_id: int) -> list[dict]:
        """Get a minimal user list for share target selection."""
        stmt = select(User).where(User.is_active == True).order_by(User.username)  # noqa: E712
        users = db.execute(stmt).scalars().all()
        return [
            {"id": u.id, "username": u.username}
            for u in users
            if u.id != exclude_user_id
        ]

    @staticmethod
    def build_share_response(share: "FileShare", db: Session) -> FileShareResponse:
        """Build a FileShareResponse with related entity lookups."""
        file_metadata = db.get(FileMetadata, share.file_id)
        target_user = db.get(User, share.shared_with_user_id)
        owner = db.get(User, share.owner_id)

        return FileShareResponse(
            id=share.id,
            file_id=share.file_id,
            owner_id=share.owner_id,
            shared_with_user_id=share.shared_with_user_id,
            can_read=share.can_read,
            can_write=share.can_write,
            can_delete=share.can_delete,
            can_share=share.can_share,
            expires_at=share.expires_at,
            created_at=share.created_at,
            last_accessed_at=share.last_accessed_at,
            is_expired=share.is_expired(),
            is_accessible=share.is_accessible(),
            owner_username=owner.username if owner else None,
            shared_with_username=target_user.username if target_user else None,
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None,
            is_directory=file_metadata.is_directory if file_metadata else False,
        )

    @staticmethod
    def build_shared_with_me_response(share: "FileShare", db: Session) -> Optional[SharedWithMeResponse]:
        """Build a SharedWithMeResponse with related entity lookups."""
        file_metadata = db.get(FileMetadata, share.file_id)
        owner = db.get(User, share.owner_id)
        if not file_metadata or not owner:
            return None
        return SharedWithMeResponse(
            share_id=share.id,
            file_id=share.file_id,
            file_name=file_metadata.name,
            file_path=file_metadata.path,
            file_size=file_metadata.size_bytes,
            is_directory=file_metadata.is_directory,
            owner_username=owner.username,
            owner_id=owner.id,
            can_read=share.can_read,
            can_write=share.can_write,
            can_delete=share.can_delete,
            can_share=share.can_share,
            shared_at=share.created_at,
            expires_at=share.expires_at,
            is_expired=share.is_expired(),
        )

    @staticmethod
    def get_file_path_for_share(share: "FileShare", db: Session) -> Optional[str]:
        """Get the file path for audit logging."""
        file_metadata = db.get(FileMetadata, share.file_id)
        return file_metadata.path if file_metadata else None

    @staticmethod
    def get_username(db: Session, user_id: int) -> Optional[str]:
        """Get a username by user ID."""
        user = db.get(User, user_id)
        return user.username if user else None

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
