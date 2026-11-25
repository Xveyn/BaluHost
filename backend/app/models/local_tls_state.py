"""Zustand des Plugins local_tls (feste Adresse im Heimnetz).

Die Tabelle liegt in app/models/ statt im Plugin, weil Alembic-Autogenerate
nur sieht, was an Base.metadata haengt (wie steam_session.py). Es gibt genau
eine Zeile. ``provider_secret`` enthaelt den Anbieter-Token Fernet-verschluesselt.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LocalTlsState(Base):
    """Einzeilige Statustabelle des Plugins local_tls."""

    __tablename__ = "local_tls_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    last_ip_set_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Domain, fuer die ``last_ip`` gesetzt wurde: eine andere Domain ist faellig.
    last_ip_domain: Mapped[Optional[str]] = mapped_column(String(253), nullable=True)
    # Ergebnis des letzten DNS-Update-Versuchs (Erfolg wie Fehlschlag).
    last_dns_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_dns_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_dns_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_renew_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_renew_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_renew_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cert_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cert_not_after: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<LocalTlsState(id={self.id}, last_ip={self.last_ip!r})>"
