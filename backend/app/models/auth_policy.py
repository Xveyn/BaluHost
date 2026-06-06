"""Singleton auth policy: PIN-login window + global kill switch."""
from __future__ import annotations

from sqlalchemy import Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuthPolicy(Base):
    """Single row (id=1) holding system-wide auth policy."""

    __tablename__ = "auth_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    pin_login_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    pin_grace_window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=86400, server_default="86400"
    )
