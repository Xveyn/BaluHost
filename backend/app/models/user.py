"""User database model."""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    smb_enabled: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )

    # TOTP 2FA fields
    totp_secret_encrypted: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    totp_backup_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    totp_enabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    mobile_devices: Mapped[List["MobileDevice"]] = relationship(
        "MobileDevice", back_populates="user", cascade="all, delete-orphan"
    )
    vpn_clients: Mapped[List["VPNClient"]] = relationship(
        "VPNClient", back_populates="user", cascade="all, delete-orphan"
    )
    server_profiles: Mapped[List["ServerProfile"]] = relationship(
        "ServerProfile", back_populates="user", cascade="all, delete-orphan"
    )
    vpn_profiles: Mapped[List["VPNProfile"]] = relationship(
        "VPNProfile", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    notification_preferences: Mapped[Optional["NotificationPreferences"]] = relationship(
        "NotificationPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
