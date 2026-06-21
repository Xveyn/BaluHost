"""Credential encryption/decryption for cloud connections."""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _secret_derived_key() -> bytes:
    """Legacy Fernet key derived from SECRET_KEY (fallback for pre-CLOUD_ENCRYPTION_KEY data)."""
    raw = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw)


def _fernet() -> MultiFernet:
    """Encrypt with CLOUD_ENCRYPTION_KEY when set (else the legacy SECRET_KEY-derived key);
    decrypt by trying the dedicated key first, then the legacy key (dual-key fallback +
    lazy re-encrypt on next write)."""
    keys: list[Fernet] = []
    if settings.cloud_encryption_key:
        keys.append(Fernet(settings.cloud_encryption_key.encode("utf-8")))
    keys.append(Fernet(_secret_derived_key()))
    return MultiFernet(keys)


def encrypt_credentials(plaintext: str) -> str:
    """Encrypt a credential string and return the ciphertext as a string."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credentials(ciphertext: str) -> str:
    """Decrypt a credential string. Raises ValueError on failure."""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Failed to decrypt credentials — key may have changed")
