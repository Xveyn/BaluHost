"""VPN key encryption/decryption using Fernet (AES-128)."""

from cryptography.fernet import Fernet
from app.core.config import settings


class VPNEncryption:
    """Handle encryption/decryption of VPN keys."""

    @staticmethod
    def encrypt_key(key: str) -> str:
        """
        Encrypt a WireGuard key using Fernet.

        Args:
            key: Plain text key (Base64 string)

        Returns:
            Encrypted key (Base64)

        Raises:
            ValueError: If VPN_ENCRYPTION_KEY not configured
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured in .env")

        cipher = Fernet(settings.vpn_encryption_key.encode())
        encrypted = cipher.encrypt(key.encode())
        return encrypted.decode()

    @staticmethod
    def decrypt_key(encrypted_key: str) -> str:
        """
        Decrypt a WireGuard key using Fernet.

        Args:
            encrypted_key: Encrypted key (Base64)

        Returns:
            Plain text key (Base64 string)

        Raises:
            ValueError: If VPN_ENCRYPTION_KEY not configured
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured in .env")

        cipher = Fernet(settings.vpn_encryption_key.encode())
        decrypted = cipher.decrypt(encrypted_key.encode())
        return decrypted.decode()
