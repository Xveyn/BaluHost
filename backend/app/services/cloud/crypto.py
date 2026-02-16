"""Credential encryption/decryption for cloud connections."""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_fernet_key() -> bytes:
    """Derive a Fernet-compatible key from the app's SECRET_KEY."""
    # Fernet requires a 32-byte URL-safe base64-encoded key.
    # Derive one deterministically from SECRET_KEY via SHA-256.
    raw = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt_credentials(plaintext: str) -> str:
    """Encrypt a credential string and return the ciphertext as a string."""
    f = Fernet(_get_fernet_key())
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credentials(ciphertext: str) -> str:
    """Decrypt a credential string. Raises ValueError on failure."""
    f = Fernet(_get_fernet_key())
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Failed to decrypt credentials — key may have changed")
