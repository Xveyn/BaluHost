"""Database model for user power permissions."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class UserPowerPermission(Base):
    """Per-user power action permissions, granted by an admin."""

    __tablename__ = "user_power_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    can_soft_sleep: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    can_wake: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    can_suspend: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    can_wol: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

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
