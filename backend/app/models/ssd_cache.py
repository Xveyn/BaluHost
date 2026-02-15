"""Database models for SSD cache (bcache) configuration."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class SsdCacheConfig(Base):
    """Persistent SSD cache configuration."""
    __tablename__ = "ssd_cache_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    array_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    cache_device: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="writethrough", nullable=False)
    sequential_cutoff_bytes: Mapped[int] = mapped_column(Integer, default=4 * 1024 * 1024, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SsdCacheConfig(array='{self.array_name}', device='{self.cache_device}', mode='{self.mode}')>"
