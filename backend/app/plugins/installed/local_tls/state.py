"""Zugriffsschicht fuer die Tabelle local_tls_state (genau eine Zeile).

Der Anbieter-Token wird nur verschluesselt gespeichert. Fehlt der
Verschluesselungsschluessel, wird abgelehnt -- nie Klartext. Token und
Schluessel tauchen weder in Exceptions noch in Logs auf.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.local_tls_state import LocalTlsState
from app.services.vpn.encryption import VPNEncryption

_REASON_MAX = 500


def get_state(db: Session) -> LocalTlsState:
    """Liefert die eine Zeile und legt sie bei Bedarf an."""
    row = db.query(LocalTlsState).order_by(LocalTlsState.id).first()
    if row is None:
        row = LocalTlsState()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def set_token(db: Session, token: str) -> None:
    try:
        encrypted = VPNEncryption.encrypt_key(token)
    except ValueError:
        # Absichtlich ohne die Originalmeldung/Ursache.
        raise ValueError("encryption key missing") from None
    row = get_state(db)
    row.provider_secret = encrypted
    db.commit()


def clear_token(db: Session) -> None:
    row = get_state(db)
    row.provider_secret = None
    db.commit()


def get_token(db: Session) -> Optional[str]:
    secret = get_state(db).provider_secret
    if not secret:
        return None
    return VPNEncryption.decrypt_key(secret)


def has_token(db: Session) -> bool:
    return bool(get_state(db).provider_secret)


def record_ip(db: Session, ip: str, now: datetime) -> None:
    row = get_state(db)
    row.last_ip = ip
    row.last_ip_set_at = now
    db.commit()


def record_renew(
    db: Session,
    ok: bool,
    reason: Optional[str],
    fingerprint: Optional[str],
    not_after: Optional[datetime],
    now: datetime,
) -> None:
    row = get_state(db)
    row.last_renew_at = now
    row.last_renew_ok = ok
    row.last_renew_reason = reason[:_REASON_MAX] if reason else None
    row.cert_fingerprint = fingerprint
    row.cert_not_after = not_after
    db.commit()
