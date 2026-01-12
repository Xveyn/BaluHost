"""RefreshToken database model for token revocation support."""
from datetime import datetime
from typing import Optional
import hashlib

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class RefreshToken(Base):
    """
    Refresh token model for secure token revocation.

    ✅ Security Fix #6: Enables refresh token revocation to prevent
    compromised tokens from being used indefinitely.

    Stores refresh token metadata to enable:
    - Token revocation on logout or security events
    - Device-specific token management
    - Audit trail of token usage
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # JWT ID (JTI) - unique identifier for this specific token
    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)

    # User who owns this token
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Optional device ID for mobile/desktop clients
    device_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Hashed token value (for verification without storing plaintext)
    # We hash the token so even if DB is compromised, tokens can't be used
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Expiration timestamp
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )

    # Revocation status
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # IP address tracking (for security audit)
    created_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 max length
    last_used_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # User agent (browser/app identification)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationship to user
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    # Composite indexes for efficient queries
    __table_args__ = (
        # Fast lookup for active tokens by user
        Index("idx_user_active_tokens", "user_id", "revoked", "expires_at"),
        # Fast lookup by device
        Index("idx_device_tokens", "device_id", "revoked"),
        # Cleanup of expired tokens
        Index("idx_expired_tokens", "expires_at", "revoked"),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, jti='{self.jti}', user_id={self.user_id}, revoked={self.revoked})>"

    def revoke(self, reason: Optional[str] = None) -> None:
        """
        Revoke this refresh token.

        Args:
            reason: Optional reason for revocation (e.g., "logout", "security_event")
        """
        self.revoked = True
        self.revoked_at = datetime.utcnow()
        self.revocation_reason = reason

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Create SHA-256 hash of refresh token for secure storage.

        Args:
            token: The plaintext refresh token (JWT string)

        Returns:
            Hex-encoded SHA-256 hash of the token
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def is_valid(self) -> bool:
        """
        Check if token is valid (not revoked and not expired).

        Returns:
            True if token can be used, False otherwise
        """
        if self.revoked:
            return False

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # Handle naive datetime (SQLite compatibility)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return expires_at > now
