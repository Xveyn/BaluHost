"""TOTP Two-Factor Authentication service.

Handles TOTP secret generation, QR code creation, code verification,
backup codes, and encryption of secrets at rest.
"""

import hashlib
import io
import json
import secrets
import base64
from datetime import datetime, timezone
from typing import Optional

import pyotp
import qrcode
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.vpn.encryption import VPNEncryption
import logging

logger = logging.getLogger(__name__)

BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8
ISSUER_NAME = "BaluHost"


def generate_setup(user: User) -> dict:
    """
    Generate TOTP setup data including secret, QR code, and provisioning URI.

    Args:
        user: The user setting up 2FA.

    Returns:
        Dict with 'secret', 'qr_code' (base64 PNG), and 'provisioning_uri'.
    """
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.username,
        issuer_name=ISSUER_NAME,
    )

    # Generate QR code as base64 PNG
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_base64}",
        "provisioning_uri": provisioning_uri,
    }


def verify_and_enable(db: Session, user_id: int, secret: str, code: str) -> list[str]:
    """
    Verify a TOTP code against the provided secret, then enable 2FA.

    Args:
        db: Database session.
        user_id: User ID.
        secret: Plain-text TOTP secret (from setup step).
        code: 6-digit TOTP code from authenticator app.

    Returns:
        List of plain-text backup codes (show once to user).

    Raises:
        ValueError: If code is invalid or user not found.
    """
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise ValueError("Invalid TOTP code")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    # Encrypt and store secret
    encrypted_secret = VPNEncryption.encrypt_key(secret)
    user.totp_secret_encrypted = encrypted_secret
    user.totp_enabled = True
    user.totp_enabled_at = datetime.now(timezone.utc)

    # Generate and store backup codes
    backup_codes = _generate_backup_codes()
    _store_backup_codes(user, backup_codes)

    db.commit()
    return backup_codes


def verify_code(db: Session, user_id: int, code: str) -> bool:
    """
    Verify a TOTP code during login.

    Args:
        db: Database session.
        user_id: User ID.
        code: 6-digit TOTP code.

    Returns:
        True if code is valid.

    Raises:
        ValueError: If user not found or 2FA not enabled.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    if not user.totp_enabled or not user.totp_secret_encrypted:
        raise ValueError("2FA is not enabled for this user")

    secret = VPNEncryption.decrypt_key(user.totp_secret_encrypted)
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def verify_backup_code(db: Session, user_id: int, code: str) -> bool:
    """
    Verify and consume a backup code (one-time use).

    Args:
        db: Database session.
        user_id: User ID.
        code: Backup code string.

    Returns:
        True if backup code was valid and consumed.

    Raises:
        ValueError: If user not found or 2FA not enabled.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    if not user.totp_enabled or not user.totp_backup_codes_encrypted:
        raise ValueError("2FA is not enabled or no backup codes available")

    # Decrypt backup codes
    decrypted_json = VPNEncryption.decrypt_key(user.totp_backup_codes_encrypted)
    hashed_codes: list[str] = json.loads(decrypted_json)

    # Hash the provided code and check
    code_hash = hashlib.sha256(code.strip().encode()).hexdigest()

    if code_hash not in hashed_codes:
        return False

    # Remove used code
    hashed_codes.remove(code_hash)

    # Re-encrypt and store
    updated_json = json.dumps(hashed_codes)
    user.totp_backup_codes_encrypted = VPNEncryption.encrypt_key(updated_json)
    db.commit()

    logger.info("Backup code consumed for user %d, %d remaining", user_id, len(hashed_codes))
    return True


def disable(db: Session, user_id: int) -> None:
    """
    Disable 2FA and clear all TOTP data.

    Args:
        db: Database session.
        user_id: User ID.

    Raises:
        ValueError: If user not found.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    user.totp_secret_encrypted = None
    user.totp_enabled = False
    user.totp_backup_codes_encrypted = None
    user.totp_enabled_at = None
    db.commit()


def regenerate_backup_codes(db: Session, user_id: int) -> list[str]:
    """
    Generate new backup codes, invalidating old ones.

    Args:
        db: Database session.
        user_id: User ID.

    Returns:
        List of new plain-text backup codes.

    Raises:
        ValueError: If user not found or 2FA not enabled.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    if not user.totp_enabled:
        raise ValueError("2FA is not enabled for this user")

    backup_codes = _generate_backup_codes()
    _store_backup_codes(user, backup_codes)
    db.commit()
    return backup_codes


def get_backup_codes_remaining(db: Session, user_id: int) -> int:
    """
    Get the number of remaining backup codes.

    Args:
        db: Database session.
        user_id: User ID.

    Returns:
        Number of remaining backup codes, or 0 if none.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.totp_backup_codes_encrypted:
        return 0

    try:
        decrypted_json = VPNEncryption.decrypt_key(user.totp_backup_codes_encrypted)
        hashed_codes = json.loads(decrypted_json)
        return len(hashed_codes)
    except Exception:
        return 0


def _generate_backup_codes() -> list[str]:
    """Generate a list of random backup codes."""
    return [
        secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper()
        for _ in range(BACKUP_CODE_COUNT)
    ]


def _store_backup_codes(user: User, plain_codes: list[str]) -> None:
    """Hash and encrypt backup codes, then store on user."""
    hashed = [hashlib.sha256(code.encode()).hexdigest() for code in plain_codes]
    json_str = json.dumps(hashed)
    user.totp_backup_codes_encrypted = VPNEncryption.encrypt_key(json_str)
