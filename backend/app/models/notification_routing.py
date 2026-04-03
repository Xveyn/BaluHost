"""Database model for user notification routing."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class UserNotificationRouting(Base):
    """Per-user notification category routing, granted by an admin."""

    __tablename__ = "user_notification_routing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    receive_raid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_smart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_backup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_scheduler: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_security: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_vpn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    granted_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    granted_by_user = relationship("User", foreign_keys=[granted_by])
