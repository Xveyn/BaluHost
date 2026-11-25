"""Ausgabe, Pruefung und gleitende Rotation von Geraete-Refresh-Tokens (#847).

Design: docs/superpowers/specs/2026-11-25-tray-session-handoff-always-awake-design.md,
Abschnitt "A1 — Gleitende Kopplung".

- ``issue_device_refresh_token`` ist der eine Ausgabeweg fuer Geraete-Tokens
  (Kopplung und Rotation).
- ``use_refresh_token`` prueft einen vorgelegten Token. Gemeinsam fuer
  ``/auth/refresh`` und spaetere Aufrufer (Handoff) — er rotiert nie.
- ``rotate_if_due`` rotiert, und nur ``/auth/refresh`` ruft es auf.

"Lazy revoke": Ein rotierter Token bleibt gueltig, bis sein Nachfolger zum
ersten Mal benutzt wird; erst dann bekommt er ``revocation_reason="rotated"``.
Wird ein so widerrufener (oder ein ``superseded``) Token danach noch einmal
vorgelegt, hat ihn jemand anderes als das Geraet — dann faellt die ganze
Kopplung dieses Geraets dieses Nutzers.

Rotiert werden nur Desktop-Kopplungen (SyncState-Zeile fuer Nutzer + Geraet);
Mobile-Tokens behalten die vom Admin gesetzte Laufzeit.

Token-Strings landen nie in Logs oder Exceptions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_refresh_token
from app.models.mobile import MobileDevice
from app.models.refresh_token import RefreshToken
from app.models.sync_state import SyncState
from app.models.user import User
from app.services import auth as auth_service
from app.services import users as user_service
from app.services.token_service import token_service

logger = logging.getLogger(__name__)

REASON_ROTATED = "rotated"
REASON_SUPERSEDED = "superseded"
REASON_REUSE = "reuse_detected"


class RefreshTokenInvalid(Exception):
    """Vorgelegter Token ist ungueltig — die Route antwortet generisch mit 401.

    ``audit_action``/``audit_user``/``detail`` erhalten die bisherigen
    Audit-Aktionen und 401-Texte der Route.
    """

    def __init__(
        self,
        audit_action: str,
        audit_user: Optional[str],
        error_message: str,
        detail: str = "Invalid refresh token",
    ) -> None:
        super().__init__(error_message)
        self.audit_action = audit_action
        self.audit_user = audit_user
        self.error_message = error_message
        self.detail = detail


class RefreshTokenReused(Exception):
    """Ein bereits rotierter Token wurde erneut vorgelegt (Diebstahlsignal)."""

    def __init__(self, device_id: Optional[str], user_id: int, revoked_count: int = 0) -> None:
        super().__init__("Refresh token reuse detected")
        self.device_id = device_id
        self.user_id = user_id
        self.revoked_count = revoked_count


def _aware(dt: datetime) -> datetime:
    """SQLite liefert naive Zeitstempel; alle sind UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _is_desktop_pairing(db: Session, row: RefreshToken) -> bool:
    """Gehoert ``row`` zu einer Desktop-Kopplung?

    Die Desktop-Kopplung legt eine SyncState-Zeile fuer genau diesen Nutzer und
    dieses Geraet an (desktop_pairing.py). Das allein reicht nicht:
    ``/sync/register-desktop`` legt SyncState frei an, auch unter der ID des
    eigenen Mobilgeraets. Mobile-Tokens tragen ``str(MobileDevice.id)``
    (UUID-String) als device_id — existiert so ein Geraet fuer den Nutzer, ist
    es nie eine Desktop-Kopplung.
    """
    is_mobile = (
        db.query(MobileDevice.id)
        .filter(MobileDevice.id == row.device_id, MobileDevice.user_id == row.user_id)
        .first()
        is not None
    )
    if is_mobile:
        return False
    return (
        db.query(SyncState.id)
        .filter(SyncState.user_id == row.user_id, SyncState.device_id == row.device_id)
        .first()
        is not None
    )


def issue_device_refresh_token(
    db: Session,
    user: User,
    device_id: str,
    parent_jti: Optional[str] = None,
    commit: bool = True,
) -> str:
    """Neuen Geraete-Refresh-Token mit voller Laufzeit ausstellen und speichern.

    Args:
        db: Datenbank-Session
        user: Eigentuemer des Tokens
        device_id: Geraet, an das der Token gebunden ist
        parent_jti: Vorgaenger bei Rotation (None = Erstausgabe)
        commit: False = nur flush, der Aufrufer committet

    Returns:
        Der Token-String (nur fuer die Antwort an das Geraet)
    """
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token, jti = create_refresh_token(user, expires_delta=expires_delta)
    token_service.store_refresh_token(
        db=db,
        jti=jti,
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.now(timezone.utc) + expires_delta,
        device_id=device_id,
        parent_jti=parent_jti,
        commit=commit,
    )
    return refresh_token


def use_refresh_token(
    db: Session,
    raw_token: str,
    ip_address: Optional[str],
) -> tuple[User, RefreshToken]:
    """Vorgelegten Refresh-Token pruefen und seine Nutzung vermerken.

    Reihenfolge: Decodieren, Reuse-Check (``rotated``/``superseded``, vor dem
    generischen Widerruf, sonst saehe er den Grund nie), Widerruf/unbekannt,
    Nutzer. Bei Erfolg wird ein
    noch gueltiger Vorgaenger als ``rotated`` widerrufen; alles in einem Commit.

    Raises:
        RefreshTokenReused: Token war bereits rotiert; das Geraet ist widerrufen.
        RefreshTokenInvalid: jeder andere Fehler.
    """
    try:
        token_data = auth_service.decode_token(raw_token, token_type="refresh")
    except Exception as exc:
        raise RefreshTokenInvalid(
            audit_action="refresh_token_failed",
            audit_user="unknown",
            error_message=str(exc),
        ) from exc

    user_id = token_data.sub
    jti = token_data.jti
    audit_user = f"user_id:{user_id}"

    row = token_service.get_token_by_jti(db, jti) if jti else None

    # "rotated": der Nachfolger wurde nachweislich benutzt. "superseded": der
    # Nachfolger kam beim Geraet nie an — wer ihn vorlegt, hat ihn abgefangen.
    if (
        row is not None
        and row.revoked
        and row.revocation_reason in (REASON_ROTATED, REASON_SUPERSEDED)
    ):
        revoked_count = 0
        if row.device_id:
            revoked_count = token_service.revoke_device_tokens(
                db,
                row.device_id,
                reason=REASON_REUSE,
                commit=False,
                user_id=row.user_id,
            )
        db.commit()
        logger.warning(
            "Refresh token reuse detected: user_id=%s device_id=%s jti=%s",
            row.user_id, row.device_id, row.jti,
        )
        raise RefreshTokenReused(
            device_id=row.device_id, user_id=row.user_id, revoked_count=revoked_count
        )

    # Unbekannter jti (oder Token ohne jti) gilt wie bisher als widerrufen.
    if row is None or not row.is_valid():
        raise RefreshTokenInvalid(
            audit_action="refresh_token_revoked",
            audit_user=audit_user,
            error_message="Refresh token has been revoked",
            detail="Refresh token has been revoked",
        )

    try:
        user_record = user_service.get_user(int(user_id), db=db)
    except (TypeError, ValueError) as exc:
        raise RefreshTokenInvalid(
            audit_action="refresh_token_failed",
            audit_user="unknown",
            error_message=str(exc),
        ) from exc
    if not user_record:
        raise RefreshTokenInvalid(
            audit_action="refresh_token_invalid_user",
            audit_user=audit_user,
            error_message="User not found",
        )
    if not getattr(user_record, "is_active", True):
        raise RefreshTokenInvalid(
            audit_action="refresh_token_inactive_user",
            audit_user=getattr(user_record, "username", None),
            error_message="User account is inactive",
            detail="User account is inactive",
        )

    # Erste Nutzung eines Nachfolgers: jetzt erst den Vorgaenger widerrufen.
    if row.parent_jti:
        parent = token_service.get_token_by_jti(db, row.parent_jti)
        if parent is not None and not parent.revoked:
            parent.revoke(reason=REASON_ROTATED)

    row.last_used_at = datetime.now(timezone.utc)
    if ip_address:
        row.last_used_ip = ip_address

    db.commit()
    return user_record, row


def rotate_if_due(
    db: Session,
    row: RefreshToken,
    user: User,
    now: datetime,
) -> Optional[str]:
    """Nachfolger ausstellen, wenn ``row`` ein Geraete-Token in der zweiten
    Lebenshaelfte ist; sonst None.

    Ein noch unbenutzter frueherer Nachfolger (Antwort ging verloren) wird als
    ``superseded`` widerrufen — pro Geraet gibt es hoechstens einen
    unbenutzten Nachfolger. Ein Commit fuer alles.
    """
    if not row.device_id:
        return None
    # Nur Desktop-Kopplungen gleiten. Mobile-Tokens tragen auch ein device_id,
    # ihre Laufzeit ist aber die vom Admin gesetzte Geraetefreigabe.
    if not _is_desktop_pairing(db, row):
        return None

    half_life = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS) / 2
    if _aware(row.expires_at) - _aware(now) >= half_life:
        return None

    pending = (
        db.query(RefreshToken)
        .filter(RefreshToken.parent_jti == row.jti, RefreshToken.revoked == False)  # noqa: E712
        .all()
    )
    for successor in pending:
        successor.revoke(reason=REASON_SUPERSEDED)

    new_token = issue_device_refresh_token(
        db, user, row.device_id, parent_jti=row.jti, commit=False
    )
    db.commit()
    logger.info(
        "Rotated refresh token: user_id=%s device_id=%s parent_jti=%s superseded=%d",
        user.id, row.device_id, row.jti, len(pending),
    )
    return new_token
