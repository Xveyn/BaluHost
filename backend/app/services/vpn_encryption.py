"""VPN and SSH key encryption/decryption using Fernet (AES-128)."""

from cryptography.fernet import Fernet
from app.core.config import settings


class VPNEncryption:
    """Handle encryption/decryption of VPN and SSH sensitive data."""

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
    
    @staticmethod
    def encrypt_ssh_private_key(private_key: str) -> str:
        """
        Encrypt an SSH private key using Fernet.
        
        Args:
            private_key: SSH private key content as string
            
        Returns:
            Encrypted private key (Base64)
            
        Raises:
            ValueError: If encryption key not configured
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured in .env")
        
        cipher = Fernet(settings.vpn_encryption_key.encode())
        encrypted = cipher.encrypt(private_key.encode())
        return encrypted.decode()
    
    @staticmethod
    def decrypt_ssh_private_key(encrypted_key: str) -> str:
        """
        Decrypt an SSH private key using Fernet.
        
        Args:
            encrypted_key: Encrypted private key (Base64)
            
        Returns:
            Plain text SSH private key
            
        Raises:
            ValueError: If decryption fails
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured in .env")
        
        cipher = Fernet(settings.vpn_encryption_key.encode())
        decrypted = cipher.decrypt(encrypted_key.encode())
        return decrypted.decode()
    
    @staticmethod
    def encrypt_vpn_config(config_content: str) -> str:
        """
        Encrypt VPN configuration file using Fernet.
        
        Args:
            config_content: VPN config file content
            
        Returns:
            Encrypted config (Base64)
            
        Raises:
            ValueError: If encryption key not configured
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured in .env")
        
        cipher = Fernet(settings.vpn_encryption_key.encode())
        encrypted = cipher.encrypt(config_content.encode())
        return encrypted.decode()
    
    @staticmethod
    def decrypt_vpn_config(encrypted_config: str) -> str:
        """
        Decrypt VPN configuration file using Fernet.
        
        Args:
            encrypted_config: Encrypted config (Base64)
            
        Returns:
            Plain text VPN config content
            
        Raises:
            ValueError: If decryption fails
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured in .env")
        
        cipher = Fernet(settings.vpn_encryption_key.encode())
        decrypted = cipher.decrypt(encrypted_config.encode())
        return decrypted.decode()
