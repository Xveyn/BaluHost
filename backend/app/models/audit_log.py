"""Audit log database model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AuditLog(Base):
    """Audit log model for tracking system events and user actions."""
    
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # FILE_ACCESS, FILE_MODIFY, DISK_MONITOR, SYSTEM, SECURITY
    
    user: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    
    # Additional metadata
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 compatible
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    __table_args__ = (
        # Composite indexes for common queries
        Index('idx_audit_event_type_timestamp', 'event_type', 'timestamp'),
        Index('idx_audit_user_timestamp', 'user', 'timestamp'),
        Index('idx_audit_success_timestamp', 'success', 'timestamp'),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, type='{self.event_type}', user='{self.user}', action='{self.action}')>"
