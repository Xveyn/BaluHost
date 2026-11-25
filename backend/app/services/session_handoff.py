"""Einmal-Code-Handoff vom Tray in die Web-UI (#847).

Design: docs/superpowers/specs/2026-11-25-tray-session-handoff-always-awake-design.md,
Abschnitt "B1 — Auto-Login per Einmal-Code".

- ``issue_code`` stellt einen 30 s gueltigen Code aus; gespeichert wird nur
  sein SHA-256. Die Pruefung des Aufrufers (LAN-Gate, Geraete-Refresh-Token,
  PIN) macht die Route.
- ``redeem_code`` loest ihn atomar ein: ein einziges ``UPDATE`` mit allen
  Bedingungen, genau eine betroffene Zeile = gueltig. Damit kann ein Code auch
  ueber mehrere Worker hinweg nur einmal eingeloest werden.

Codes landen nie in Logs, Audit-Eintraegen oder Exceptions.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.models.session_handoff import SessionHandoffCode
from app.models.user import User

HANDOFF_TTL_SECONDS = 30

# Abgelaufene Codes bleiben einen Tag liegen (Nachvollziehbarkeit), dann
# raeumt das naechste Ausstellen sie weg — die Tabelle waechst nicht.
_PURGE_AFTER = timedelta(days=1)


def _now() -> datetime:
    """Aktuelle Zeit (UTC-aware); eigene Funktion, damit Tests sie patchen koennen."""
    return datetime.now(timezone.utc)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def issue_code(db: Session, user: User, ip: Optional[str]) -> str:
    """Neuen Einmal-Code fuer ``user`` ausstellen.

    Args:
        db: Datenbank-Session
        user: Nutzer, fuer den der Browser eine Sitzung bekommen soll
        ip: Adresse des ausstellenden Aufrufers (nur fuer die Zeile)

    Returns:
        Der Code im Klartext — nur fuer die Antwort an das Tray.
    """
    now = _now()
    db.execute(
        delete(SessionHandoffCode)
        .where(SessionHandoffCode.expires_at < now - _PURGE_AFTER)
        .execution_options(synchronize_session="fetch")
    )
    code = secrets.token_urlsafe(32)
    db.add(
        SessionHandoffCode(
            user_id=user.id,
            token_hash=_hash(code),
            expires_at=now + timedelta(seconds=HANDOFF_TTL_SECONDS),
            created_ip=ip[:45] if ip else None,
        )
    )
    db.commit()
    return code


def redeem_code(db: Session, code: str) -> Optional[User]:
    """Code einloesen.

    Returns:
        Den (aktiven) Nutzer, oder ``None`` — ohne Unterschied zwischen
        unbekannt, abgelaufen, schon benutzt und inaktivem Nutzer.
    """
    now = _now()
    token_hash = _hash(code)
    result = db.execute(
        update(SessionHandoffCode)
        .where(
            SessionHandoffCode.token_hash == token_hash,
            SessionHandoffCode.used_at.is_(None),
            SessionHandoffCode.expires_at > now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()

    row = db.query(SessionHandoffCode).filter(SessionHandoffCode.token_hash == token_hash).one()
    user = db.get(User, row.user_id)
    if user is None or not getattr(user, "is_active", True):
        return None
    return user
