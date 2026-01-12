"""Share link database model for public file sharing."""
from datetime import datetime, timezone
from typing import Optional
import secrets

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class ShareLink(Base):
    """Public share link model for sharing files via URL."""
    
    __tablename__ = "share_links"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_metadata.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Optional password protection
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Link settings
    allow_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_downloads: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = unlimited
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<ShareLink(id={self.id}, token='{self.token[:8]}...', file_id={self.file_id})>"
    
    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token for share links."""
        return secrets.token_urlsafe(32)
    
    def is_expired(self) -> bool:
        """Check if the share link has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_download_limit_reached(self) -> bool:
        """Check if the download limit has been reached."""
        if self.max_downloads is None:
            return False
        return self.download_count >= self.max_downloads
    
    def is_accessible(self) -> bool:
        """Check if the share link is currently accessible."""
        return not self.is_expired() and not self.is_download_limit_reached()
