"""Track which remote folders are actively synced by desktop clients."""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class DesktopSyncFolder(Base):
    """Tracks remote folders that are actively synced by BaluDesk clients."""
    __tablename__ = "desktop_sync_folders"
    __table_args__ = (
        UniqueConstraint("device_id", "remote_path", name="uq_device_remote_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # "windows" | "mac" | "linux"
    remote_path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    sync_direction: Mapped[str] = mapped_column(String(50), nullable=False, default="bidirectional")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
