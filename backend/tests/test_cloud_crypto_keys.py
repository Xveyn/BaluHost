"""CLOUD_ENCRYPTION_KEY dedicated-key + SECRET_KEY-derived fallback (Posten 3 #1)."""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings
from app.services.cloud import crypto


def _secret_derived(secret: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()).decode()


def test_roundtrip_with_dedicated_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "cloud_encryption_key", key)
    ct = crypto.encrypt_credentials("s3cret")
    # Ciphertext is decryptable ONLY by the dedicated key (encrypt uses it first).
    assert Fernet(key.encode()).decrypt(ct.encode()).decode() == "s3cret"
    assert crypto.decrypt_credentials(ct) == "s3cret"


def test_legacy_secret_derived_ciphertext_still_decrypts(monkeypatch):
    """Data written before CLOUD_ENCRYPTION_KEY (SECRET_KEY-derived) still decrypts."""
    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 40)
    legacy = Fernet(_secret_derived("x" * 40).encode()).encrypt(b"legacy").decode()
    monkeypatch.setattr(settings, "cloud_encryption_key", Fernet.generate_key().decode())
    assert crypto.decrypt_credentials(legacy) == "legacy"


def test_no_dedicated_key_is_backward_compatible(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "y" * 40)
    monkeypatch.setattr(settings, "cloud_encryption_key", "")
    ct = crypto.encrypt_credentials("plain")
    # Identical to legacy behavior: decryptable by the SECRET_KEY-derived key.
    assert Fernet(_secret_derived("y" * 40).encode()).decrypt(ct.encode()).decode() == "plain"
    assert crypto.decrypt_credentials(ct) == "plain"


def test_legacy_config_blob_decrypts_after_dedicated_key(monkeypatch):
    """CloudConnection.encrypted_config (rclone INI / iCloud creds) also round-trips via the
    legacy fallback — it uses the same encrypt/decrypt functions as the OAuth client creds."""
    monkeypatch.setattr(settings, "SECRET_KEY", "z" * 40)
    blob = "[gdrive]\ntype = drive\ntoken = {\"access_token\": \"abc\"}\n"
    legacy = Fernet(_secret_derived("z" * 40).encode()).encrypt(blob.encode()).decode()
    monkeypatch.setattr(settings, "cloud_encryption_key", Fernet.generate_key().decode())
    assert crypto.decrypt_credentials(legacy) == blob
