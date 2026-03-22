"""Database model for desktop device pairing codes (Device Code Flow)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class DesktopPairingCode(Base):
    """Temporary pairing codes for BaluDesk device registration."""

    __tablename__ = "desktop_pairing_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_code: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
