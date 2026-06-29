"""Password recovery codes.

Single-use codes that let a user reset their own password without an admin or
shell access. Stored like 2FA backup codes: a Fernet-encrypted JSON array of
SHA-256 hashes (hash + encrypt; never plaintext). LAN-only reset is enforced at
the route layer.
"""
import hashlib
import json
import logging
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.core.crypto import encrypt_at_rest, decrypt_at_rest
from app.models.user import User

logger = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_HEX_BYTES = 5  # → 10 hex chars / 40 bits per code

_DUMMY_BLOB: Optional[str] = None


def _generate_codes() -> list[str]:
    return [secrets.token_hex(RECOVERY_CODE_HEX_BYTES).upper() for _ in range(RECOVERY_CODE_COUNT)]


def _store_codes(user: User, plain_codes: list[str]) -> None:
    hashed = [hashlib.sha256(c.encode()).hexdigest() for c in plain_codes]
    user.password_recovery_codes_encrypted = encrypt_at_rest(json.dumps(hashed))


def _load_hashes(user: User) -> list[str]:
    if not user.password_recovery_codes_encrypted:
        return []
    try:
        return json.loads(decrypt_at_rest(user.password_recovery_codes_encrypted))
    except Exception:
        return []


def _equalize_timing(code: str) -> None:
    """Run an equivalent decrypt+hash for unknown/disabled users (anti-enumeration)."""
    global _DUMMY_BLOB
    try:
        if _DUMMY_BLOB is None:
            _DUMMY_BLOB = encrypt_at_rest(json.dumps([hashlib.sha256(b"dummy").hexdigest()]))
        hashes = json.loads(decrypt_at_rest(_DUMMY_BLOB))
    except Exception:
        hashes = []
    _ = hashlib.sha256(code.strip().upper().encode()).hexdigest() in hashes


def generate_recovery_codes(db: Session, user_id: int) -> list[str]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    codes = _generate_codes()
    _store_codes(user, codes)
    db.commit()
    return codes


def verify_and_consume_recovery_code(db: Session, user_id: int, code: str) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    hashes = _load_hashes(user)
    if not hashes:
        return False
    code_hash = hashlib.sha256(code.strip().upper().encode()).hexdigest()
    if code_hash not in hashes:
        return False
    hashes.remove(code_hash)
    user.password_recovery_codes_encrypted = encrypt_at_rest(json.dumps(hashes))
    db.commit()
    logger.info("Recovery code consumed for user %d, %d remaining", user_id, len(hashes))
    return True


def verify_and_consume_for_username(db: Session, username: str, code: str) -> Optional[User]:
    """Resolve username, verify+consume a code. Returns the User on success, else None.
    Unknown or disabled users run a dummy verify to equalize timing (anti-enumeration)."""
    from app.services import users as user_service
    user = user_service.get_user_by_username(username, db=db)
    if not user or not user.is_active:
        _equalize_timing(code)
        return None
    if verify_and_consume_recovery_code(db, user.id, code):
        return user
    return None


def get_recovery_codes_remaining(db: Session, user_id: int) -> int:
    user = db.query(User).filter(User.id == user_id).first()
    return len(_load_hashes(user)) if user else 0


def has_recovery_codes(db: Session, user_id: int) -> bool:
    return get_recovery_codes_remaining(db, user_id) > 0
