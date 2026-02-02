"""
VPN services package.

Provides VPN management with:
- WireGuard configuration and key generation
- Fritz!Box VPN config parsing and upload
- OpenVPN and WireGuard config validation
- Secure key encryption/decryption
"""

from app.services.vpn.service import VPNService
from app.services.vpn.profiles import VPNService as VPNProfileService
from app.services.vpn.encryption import VPNEncryption

__all__ = [
    "VPNService",
    "VPNProfileService",
    "VPNEncryption",
]
