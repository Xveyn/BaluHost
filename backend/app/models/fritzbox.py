"""Database model for Fritz!Box integration configuration."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class FritzBoxConfig(Base):
    """Singleton Fritz!Box configuration (id=1)."""
    __tablename__ = "fritzbox_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    host: Mapped[str] = mapped_column(String(255), default="192.168.178.1", nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=49000, nullable=False)
    username: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    nas_mac_address: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<FritzBoxConfig(id={self.id}, host={self.host}, enabled={self.enabled})>"
