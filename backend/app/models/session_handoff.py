"""Einmal-Codes fuer den Session-Handoff vom Tray in die Web-UI (#847).

In der Datenbank statt im Speicher, weil vier Uvicorn-Worker plus die
Local-Channel-Worker denselben Code sehen muessen. Gespeichert wird nur der
SHA-256 des Codes; der Spaltenname ``token_hash`` wird von ``REDACT_PATTERN``
(services/audit/admin_db.py) erfasst.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class SessionHandoffCode(Base):
    """Kurzlebiger, einmal gueltiger Code fuer eine neue Browser-Sitzung."""

    __tablename__ = "session_handoff_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    def __repr__(self) -> str:
        return f"<SessionHandoffCode(id={self.id}, user_id={self.user_id}, used={self.used_at is not None})>"
