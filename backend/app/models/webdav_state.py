"""WebDAV worker state tracking model.

Single-row table storing the runtime state of the WebDAV server worker process.
Read by the web API to display status without in-process globals.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class WebdavState(Base):
    """Tracks the runtime state of the WebDAV server worker process."""

    __tablename__ = "webdav_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Whether the cheroot server is running
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Port the WebDAV server is listening on
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=8080)

    # Whether SSL is enabled
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Worker heartbeat — updated every ~10s by the worker process
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # PID of the worker process that owns this state
    worker_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # When the server was started
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Last error message (if any)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Auto-updated timestamp
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<WebdavState(running={self.is_running}, port={self.port}, "
            f"pid={self.worker_pid})>"
        )
