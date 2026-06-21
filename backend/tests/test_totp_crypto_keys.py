"""TOTP_ENCRYPTION_KEY dedicated-key + VPN-key fallback (Posten 3 #3)."""
from cryptography.fernet import Fernet

from app.core.config import settings
from app.services import totp_service


def test_roundtrip_with_dedicated_key(monkeypatch):
    totp_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "totp_encryption_key", totp_key)
    monkeypatch.setattr(settings, "vpn_encryption_key", Fernet.generate_key().decode())
    ct = totp_service._totp_encrypt("JBSWY3DPEHPK3PXP")
    # Encrypted with the dedicated key (first in the MultiFernet).
    assert Fernet(totp_key.encode()).decrypt(ct.encode()).decode() == "JBSWY3DPEHPK3PXP"
    assert totp_service._totp_decrypt(ct) == "JBSWY3DPEHPK3PXP"


def test_legacy_vpn_key_ciphertext_still_decrypts(monkeypatch):
    """Secrets written under the VPN-key fallback still decrypt after a dedicated key is added."""
    vpn_key = Fernet.generate_key().decode()
    legacy = Fernet(vpn_key.encode()).encrypt(b"OLDSECRET").decode()
    monkeypatch.setattr(settings, "vpn_encryption_key", vpn_key)
    monkeypatch.setattr(settings, "totp_encryption_key", Fernet.generate_key().decode())
    assert totp_service._totp_decrypt(legacy) == "OLDSECRET"


def test_no_totp_key_uses_vpn_key(monkeypatch):
    vpn_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "totp_encryption_key", "")
    monkeypatch.setattr(settings, "vpn_encryption_key", vpn_key)
    ct = totp_service._totp_encrypt("S")
    assert Fernet(vpn_key.encode()).decrypt(ct.encode()).decode() == "S"
    assert totp_service._totp_decrypt(ct) == "S"
