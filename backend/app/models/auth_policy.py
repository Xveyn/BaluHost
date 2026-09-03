"""Singleton auth policy: PIN-login window, kill switch, session limits."""
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
    # Session limits. The defaults reproduce the values that were hardcoded
    # before (frontend hook: 4 min + 60 s; config.py: 15 min), so landing the
    # migration changes no behavior - only who may change it afterwards.
    idle_timeout_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, server_default="4"
    )  # 0 disables the idle logout entirely
    idle_warning_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    access_token_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15, server_default="15"
    )
