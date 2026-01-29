"""Network utility functions for IP address validation."""
import ipaddress
from typing import Optional


def is_private_or_local_ip(ip_string: Optional[str]) -> bool:
    """
    Check if IP is private/local (localhost, 192.168.*, 10.*, 172.16-31.*, fd:*).

    This function validates whether an IP address belongs to:
    - Loopback addresses (127.0.0.1, ::1)
    - Private networks (RFC 1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local addresses (169.254.0.0/16, fe80::/10)
    - IPv6 unique local addresses (fc00::/7)
    - VPN networks (typically 10.8.0.0/24 for WireGuard)

    Args:
        ip_string: IP address string to validate (IPv4, IPv6, or "localhost")

    Returns:
        True if IP is private/local, False otherwise (including invalid IPs)
    """
    if not ip_string:
        return False

    # Handle "localhost" string
    if ip_string.lower() == "localhost":
        return True

    try:
        ip = ipaddress.ip_address(ip_string)

        # Check standard private/local properties
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return True

        # Handle IPv6-mapped IPv4 addresses (::ffff:192.168.1.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            mapped = ip.ipv4_mapped
            return mapped.is_loopback or mapped.is_private or mapped.is_link_local

        return False
    except ValueError:
        # Invalid IP address format
        return False


def is_localhost(ip_string: Optional[str]) -> bool:
    """
    Check if IP is strictly localhost (loopback only).

    This is more restrictive than is_private_or_local_ip() and only matches:
    - 127.0.0.1 (IPv4 loopback)
    - ::1 (IPv6 loopback)
    - "localhost" string
    - IPv6-mapped IPv4 loopback (::ffff:127.0.0.1)

    Args:
        ip_string: IP address string to validate

    Returns:
        True if IP is localhost, False otherwise
    """
    if not ip_string:
        return False

    # Handle "localhost" string
    if ip_string.lower() == "localhost":
        return True

    try:
        ip = ipaddress.ip_address(ip_string)

        # Check loopback
        if ip.is_loopback:
            return True

        # Handle IPv6-mapped IPv4 loopback (::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return ip.ipv4_mapped.is_loopback

        return False
    except ValueError:
        # Invalid IP address format
        return False
