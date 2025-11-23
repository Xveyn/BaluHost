"""Service for file sharing functionality."""
from datetime import datetime
from typing import List, Optional, Tuple
from passlib.context import CryptContext
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session, joinedload

from app.models.share_link import ShareLink
from app.models.file_share import FileShare
from app.models.file_metadata import FileMetadata
from app.models.user import User
from app.schemas.shares import (
    ShareLinkCreate, ShareLinkUpdate, ShareLinkResponse,
    FileShareCreate, FileShareUpdate, FileShareResponse,
    SharedWithMeResponse, ShareStatistics
)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class ShareService:
    """Service for managing file shares and public links."""
    
    @staticmethod
    def create_share_link(db: Session, owner_id: int, data: ShareLinkCreate) -> ShareLink:
        """Create a new public share link."""
        # Verify file exists and user owns it
        file_metadata = db.get(FileMetadata, data.file_id)
        if not file_metadata:
            raise ValueError("File not found")
        if file_metadata.owner_id != owner_id:
            raise PermissionError("You don't own this file")
        
        # Create share link
        share_link = ShareLink(
            token=ShareLink.generate_token(),
            file_id=data.file_id,
            owner_id=owner_id,
            hashed_password=pwd_context.hash(data.password) if data.password else None,
            allow_download=data.allow_download,
            allow_preview=data.allow_preview,
            max_downloads=data.max_downloads,
            expires_at=data.expires_at,
            description=data.description
        )
        
        db.add(share_link)
        db.commit()
        db.refresh(share_link)
        
        return share_link
    
    @staticmethod
    def get_share_link(db: Session, link_id: int, owner_id: int) -> Optional[ShareLink]:
        """Get a share link by ID (owner only)."""
        stmt = select(ShareLink).where(
            ShareLink.id == link_id,
            ShareLink.owner_id == owner_id
        )
        return db.execute(stmt).scalar_one_or_none()
    
    @staticmethod
    def get_share_link_by_token(db: Session, token: str) -> Optional[ShareLink]:
        """Get a share link by token (public access)."""
        stmt = select(ShareLink).where(ShareLink.token == token)
        return db.execute(stmt).scalar_one_or_none()
    
    @staticmethod
    def get_user_share_links(
        db: Session,
        owner_id: int,
        include_expired: bool = False
    ) -> List[ShareLink]:
        """Get all share links created by a user."""
        stmt = select(ShareLink).where(ShareLink.owner_id == owner_id)
        
        if not include_expired:
            now = datetime.utcnow()
            stmt = stmt.where(
                or_(
                    ShareLink.expires_at.is_(None),
                    ShareLink.expires_at > now
                )
            )
        
        return list(db.execute(stmt).scalars().all())
    
    @staticmethod
    def update_share_link(
        db: Session,
        link_id: int,
        owner_id: int,
        data: ShareLinkUpdate
    ) -> ShareLink:
        """Update a share link."""
        share_link = ShareService.get_share_link(db, link_id, owner_id)
        if not share_link:
            raise ValueError("Share link not found")
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        
        # Handle password update
        if "password" in update_data:
            password = update_data.pop("password")
            if password:
                share_link.hashed_password = pwd_context.hash(password)
            elif password == "":  # Empty string = remove password
                share_link.hashed_password = None
        
        for field, value in update_data.items():
            setattr(share_link, field, value)
        
        db.commit()
        db.refresh(share_link)
        
        return share_link
    
    @staticmethod
    def delete_share_link(db: Session, link_id: int, owner_id: int) -> bool:
        """Delete a share link."""
        share_link = ShareService.get_share_link(db, link_id, owner_id)
        if not share_link:
            return False
        
        db.delete(share_link)
        db.commit()
        return True
    
    @staticmethod
    def verify_share_link_password(share_link: ShareLink, password: Optional[str]) -> bool:
        """Verify share link password."""
        if not share_link.hashed_password:
            return True  # No password required
        if not password:
            return False  # Password required but not provided
        return pwd_context.verify(password, share_link.hashed_password)
    
    @staticmethod
    def increment_download_count(db: Session, share_link: ShareLink) -> None:
        """Increment download count and update last access time."""
        share_link.download_count += 1
        share_link.last_accessed_at = datetime.utcnow()
        db.commit()
    
    # ===========================
    # File Share Methods
    # ===========================
    
    @staticmethod
    def create_file_share(db: Session, owner_id: int, data: FileShareCreate) -> FileShare:
        """Share a file with another user."""
        # Verify file exists and user owns it
        file_metadata = db.get(FileMetadata, data.file_id)
        if not file_metadata:
            raise ValueError("File not found")
        if file_metadata.owner_id != owner_id:
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
        
        # Create file share
        file_share = FileShare(
            file_id=data.file_id,
            owner_id=owner_id,
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
    def get_file_share(db: Session, share_id: int, owner_id: int) -> Optional[FileShare]:
        """Get a file share by ID (owner only)."""
        stmt = select(FileShare).where(
            FileShare.id == share_id,
            FileShare.owner_id == owner_id
        )
        return db.execute(stmt).scalar_one_or_none()
    
    @staticmethod
    def get_file_shares_by_file(db: Session, file_id: int, owner_id: int) -> List[FileShare]:
        """Get all shares for a specific file."""
        stmt = select(FileShare).where(
            FileShare.file_id == file_id,
            FileShare.owner_id == owner_id
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
    def get_files_shared_by_user(db: Session, owner_id: int) -> List[FileShare]:
        """Get all files shared by a user."""
        stmt = select(FileShare).where(FileShare.owner_id == owner_id)
        return list(db.execute(stmt).scalars().all())
    
    @staticmethod
    def update_file_share(
        db: Session,
        share_id: int,
        owner_id: int,
        data: FileShareUpdate
    ) -> FileShare:
        """Update a file share."""
        file_share = ShareService.get_file_share(db, share_id, owner_id)
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
    def delete_file_share(db: Session, share_id: int, owner_id: int) -> bool:
        """Delete a file share."""
        file_share = ShareService.get_file_share(db, share_id, owner_id)
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
            share.last_accessed_at = datetime.utcnow()
            db.commit()
            return share
        
        return None
    
    @staticmethod
    def get_share_statistics(db: Session, user_id: int) -> ShareStatistics:
        """Get sharing statistics for a user."""
        now = datetime.utcnow()
        
        # Share links stats
        total_links = db.execute(
            select(func.count(ShareLink.id)).where(ShareLink.owner_id == user_id)
        ).scalar_one()
        
        active_links = db.execute(
            select(func.count(ShareLink.id)).where(
                ShareLink.owner_id == user_id,
                or_(
                    ShareLink.expires_at.is_(None),
                    ShareLink.expires_at > now
                )
            )
        ).scalar_one()
        
        total_downloads = db.execute(
            select(func.sum(ShareLink.download_count)).where(ShareLink.owner_id == user_id)
        ).scalar_one() or 0
        
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
            total_share_links=total_links,
            active_share_links=active_links,
            expired_share_links=total_links - active_links,
            total_downloads=total_downloads,
            total_file_shares=total_shares,
            active_file_shares=active_shares,
            files_shared_with_me=shared_with_me
        )
