"""Database model for rate limit configuration."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class RateLimitConfig(Base):
    """Configuration for API rate limits."""

    __tablename__ = "rate_limit_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    endpoint_type: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    limit_string: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g., "5/minute", "100/hour"
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Audit fields
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # User ID who last updated

    def __repr__(self) -> str:
        return f"<RateLimitConfig(endpoint_type='{self.endpoint_type}', limit='{self.limit_string}')>"
