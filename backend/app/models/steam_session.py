"""Steam play sessions recorded by the steam_gaming plugin (Teilprojekt 4/4).

The table lives in app/models/ rather than in the plugin because Alembic's
autogenerate only sees what is attached to Base.metadata — same reason
smart_device.py sits here for the Tapo plugin.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SteamSession(Base):
    """One play session. ``ended_at IS NULL`` means it is still running.

    The duration is deliberately NOT stored: it is derived from
    ``ended_at - started_at``. A stored value would be a second truth that can
    drift when a session is adopted across a backend restart.
    """

    __tablename__ = "steam_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    app_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    game_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SteamSession(app_id='{self.app_id}', started_at={self.started_at})>"
