"""File share database model for user-to-user file sharing."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class FileShare(Base):
    """File share model for sharing files between users."""
    
    __tablename__ = "file_shares"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_metadata.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_with_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Permissions
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_share: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # Can re-share with others
    
    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    __table_args__ = (
        UniqueConstraint('file_id', 'shared_with_user_id', name='uix_file_shared_with_user'),
    )
    
    def __repr__(self) -> str:
        return f"<FileShare(id={self.id}, file_id={self.file_id}, shared_with={self.shared_with_user_id})>"
    
    def is_expired(self) -> bool:
        """Check if the share has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_accessible(self) -> bool:
        """Check if the share is currently accessible."""
        return not self.is_expired()
