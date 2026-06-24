"""Per-(plugin, user) key-value storage for sandboxed plugin UIs."""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Integer, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class PluginStorage(Base):
    """A single key-value entry owned by (plugin_name, user_id)."""

    __tablename__ = "plugin_storage"
    __table_args__ = (
        UniqueConstraint("plugin_name", "user_id", "key", name="uq_plugin_storage_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plugin_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
