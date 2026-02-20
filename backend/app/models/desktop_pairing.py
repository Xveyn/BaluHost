"""Database model for desktop device pairing codes (Device Code Flow)."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.models.base import Base


class DesktopPairingCode(Base):
    """Temporary pairing codes for BaluDesk device registration."""

    __tablename__ = "desktop_pairing_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_code = Column(String(64), unique=True, index=True, nullable=False)
    user_code = Column(String(6), index=True, nullable=False)
    device_name = Column(String(255), nullable=False)
    device_id = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    failed_attempts = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
