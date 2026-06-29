"""Shared at-rest encryption (Fernet/MultiFernet).

Single seam for encrypting secrets at rest. Encrypts with TOTP_ENCRYPTION_KEY
when set (else VPN_ENCRYPTION_KEY); decrypts by trying the dedicated key first,
then the VPN key (dual-key fallback). A future RECOVERY_CODES_ENCRYPTION_KEY can
be added here without touching consumers.
"""
from cryptography.fernet import Fernet, MultiFernet


def get_at_rest_fernet() -> MultiFernet:
    from app.core.config import settings
    keys: list[Fernet] = []
    if settings.totp_encryption_key:
        keys.append(Fernet(settings.totp_encryption_key.encode()))
    if settings.vpn_encryption_key:
        keys.append(Fernet(settings.vpn_encryption_key.encode()))
    if not keys:
        raise ValueError("No encryption key configured (set TOTP_ENCRYPTION_KEY or VPN_ENCRYPTION_KEY)")
    return MultiFernet(keys)


def encrypt_at_rest(plaintext: str) -> str:
    return get_at_rest_fernet().encrypt(plaintext.encode()).decode()


def decrypt_at_rest(ciphertext: str) -> str:
    return get_at_rest_fernet().decrypt(ciphertext.encode()).decode()
