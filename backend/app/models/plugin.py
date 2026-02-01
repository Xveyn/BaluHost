"""Database model for installed plugins."""
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import String, DateTime, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class InstalledPlugin(Base):
    """Model for tracking installed and enabled plugins."""

    __tablename__ = "installed_plugins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    granted_permissions: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True, default=list
    )
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=dict
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    enabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    installed_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    def __repr__(self) -> str:
        status = "enabled" if self.is_enabled else "disabled"
        return f"<InstalledPlugin({self.name} v{self.version}, {status})>"
