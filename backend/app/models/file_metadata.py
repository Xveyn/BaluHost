"""File metadata database model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class FileMetadata(Base):
    """File and folder metadata model."""
    
    __tablename__ = "file_metadata"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    path: Mapped[str] = mapped_column(String(1000), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_directory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    parent_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, index=True)
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
    
    def __repr__(self) -> str:
        type_str = "dir" if self.is_directory else "file"
        return f"<FileMetadata(id={self.id}, path='{self.path}', type='{type_str}', owner_id={self.owner_id})>"
