"""Service heartbeat model.

Primary worker writes service status here periodically so that secondary
workers can report accurate service states without in-process globals.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ServiceHeartbeat(Base):
    """Stores latest service status written by the primary worker."""

    __tablename__ = "service_heartbeats"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ServiceHeartbeat(name='{self.name}', running={self.is_running})>"
