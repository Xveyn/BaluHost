"""Database model for NAS lifecycle events (suspend/resume/shutdown/startup)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class SystemLifecycleEvent(Base):
    """Single NAS lifecycle transition (suspend/resume/shutdown/startup).

    Used by the lifecycle-notifications feature to compute downtime
    ("Letzter Shutdown vor X") on cold boot. New rows are inserted from
    `services/power/sleep.py` and `core/lifespan.py`.
    """

    __tablename__ = "system_lifecycle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    trigger: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_lifecycle_type_ts", "event_type", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<SystemLifecycleEvent({self.event_type} @ {self.timestamp})>"
