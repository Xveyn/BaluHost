"""API Key database model for programmatic access."""
from datetime import datetime, timezone
from typing import Optional
import hashlib

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class ApiKey(Base):
    """
    API Key model for programmatic access to the BaluHost API.

    Keys are stored as SHA-256 hashes (like RefreshToken). The raw key
    is only returned once at creation time. Keys use a recognizable
    ``balu_`` prefix for secret-scanning tools.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Human-readable name chosen by admin
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # First 12 chars of the raw key for identification (e.g. "balu_Ab3x...")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # SHA-256 hash of full raw key
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Admin who created this key
    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # User identity the key acts as
    target_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Active / revoked state
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Optional expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_user_id])
    target_user: Mapped["User"] = relationship("User", foreign_keys=[target_user_id])

    # Composite indexes for efficient queries
    __table_args__ = (
        Index("idx_apikey_active_hash", "is_active", "key_hash"),
        Index("idx_apikey_creator_active", "created_by_user_id", "is_active"),
        Index("idx_apikey_target_active", "target_user_id", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<ApiKey(id={self.id}, name='{self.name}', "
            f"prefix='{self.key_prefix}', active={self.is_active})>"
        )

    def revoke(self, reason: Optional[str] = None) -> None:
        """Revoke this API key."""
        self.is_active = False
        self.revoked_at = datetime.now(timezone.utc)
        self.revocation_reason = reason

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """Create SHA-256 hash of the raw API key."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def is_valid(self) -> bool:
        """Check if key is valid (active and not expired)."""
        if not self.is_active:
            return False

        if self.expires_at is not None:
            now = datetime.now(timezone.utc)
            expires_at = self.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                return False

        return True

    def record_usage(self, ip: Optional[str] = None) -> None:
        """Record a usage event for this key."""
        self.last_used_at = datetime.now(timezone.utc)
        self.use_count += 1
        if ip:
            self.last_used_ip = ip
