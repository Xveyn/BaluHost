"""Zweiter Nachweis vor einer Aktion, die ein gültiges Token allein nicht decken soll.

Ein gekoppeltes Gerät hält sein Token tagelang. Für eine Aktion, die den Dienst
unterbricht, ist "dieses Gerät war einmal angemeldet" zu wenig — verlangt wird
derselbe Nachweis wie bei einer Anmeldung.

Was tatsächlich akzeptiert wird, und zwar genau so wie in den 2FA-Routen: bei
aktivem 2FA ein Code im aktuellen ±1-Zeitfenster (~90 s, **ohne**
Frischeprüfung — derselbe Code geht mehrfach, Issue #697) oder ein Backup-Code;
sonst das Passwort. Der Name "Step-up" beschreibt den Zweck, nicht eine
Einmaligkeitsgarantie, die es hier nicht gibt.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services import auth as auth_service
from app.services import totp_service


def verify_step_up(
    db: Optional[Session],
    user_record: Any,
    current_password: str | None,
    code: str | None,
) -> bool:
    """True, wenn der zweite Nachweis erbracht ist.

    Ein falscher Code oder ein falsches Passwort ergeben False, nie eine
    Exception. Eine kaputte 2FA-Konfiguration dagegen wirft weiter — z. B.
    ein nicht mehr entschlüsselbares Secret (`cryptography.fernet.InvalidToken`
    aus `_totp_decrypt`) oder ein Secret, das `pyotp.TOTP(...)` nicht als
    gültiges Base32 akzeptiert (`binascii.Error`). Das ist gewollt fail-closed:
    ein 500 statt eines fälschlichen True.
    """
    if user_record.totp_enabled:
        # Mit 2FA zählt ausschließlich der Code. Ein Passwort würde den zweiten
        # Faktor aushebeln, den der Nutzer gerade eingeschaltet hat.
        if not code:
            return False
        try:
            if totp_service.verify_code(db, user_record.id, code):
                return True
        except ValueError:
            pass
        try:
            return bool(totp_service.verify_backup_code(db, user_record.id, code))
        except ValueError:
            return False

    if not current_password:
        return False
    return bool(
        auth_service.authenticate_user(user_record.username, current_password, db=db)
    )
