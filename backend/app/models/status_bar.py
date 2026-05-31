"""Database models for the topbar status strip."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class StatusBarPillConfig(Base):
    """Per-pill admin configuration (one row per catalog pill)."""
    __tablename__ = "status_bar_pill_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pill_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(String(8), nullable=False, default="admin")  # "admin" | "all"
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display_mode: Mapped[str] = mapped_column(
        String(8), nullable=False, default="always", server_default="always"
    )  # "always" | "when_off" | "when_on" — only meaningful for display_mode_configurable pills
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<StatusBarPillConfig(pill_id='{self.pill_id}', enabled={self.enabled})>"


class StatusBarSettings(Base):
    """Singleton settings row (id=1) for status-strip-wide toggles."""
    __tablename__ = "status_bar_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    show_bottom_upload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<StatusBarSettings(show_bottom_upload={self.show_bottom_upload})>"
