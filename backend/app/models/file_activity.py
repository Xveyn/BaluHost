"""File activity tracking model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class FileActivity(Base):
    """Tracks all file operations for recent files / activity feed."""

    __tablename__ = "file_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_directory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="server"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_fa_user_created", "user_id", "created_at"),
        Index("idx_fa_action_created", "action_type", "created_at"),
        Index("idx_fa_user_path_action", "user_id", "file_path", "action_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<FileActivity(id={self.id}, user_id={self.user_id}, "
            f"action='{self.action_type}', path='{self.file_path}')>"
        )
