"""Network utility functions for IP address validation."""
import ipaddress
from typing import Optional

# Explicit allowlist instead of Python's ``is_private`` (#642/#475).
# ``is_private`` means "not globally routable", not "our own network": it also
# covers Teredo (2001::/32), the documentation ranges (192.0.2.0/24,
# 198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32) and more — and its table
# changes between Python patch releases. A security gate must not depend on
# either. 100.64.0.0/10 (CGNAT) is deliberately absent: the BaluHost VPN uses
# 10.8.0.0/24, nothing here runs on a CGNAT overlay.
_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",  # IPv4 loopback
        "10.0.0.0/8",  # RFC 1918 (includes the WireGuard VPN 10.8.0.0/24)
        "172.16.0.0/12",  # RFC 1918
        "192.168.0.0/16",  # RFC 1918
        "169.254.0.0/16",  # IPv4 link-local
        "::1/128",  # IPv6 loopback
        "fc00::/7",  # IPv6 unique local
        "fe80::/10",  # IPv6 link-local
    )
)


def _in_local_networks(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(ip in net for net in _LOCAL_NETWORKS)


def is_private_or_local_ip(ip_string: Optional[str]) -> bool:
    """
    Check if IP is private/local (localhost, 192.168.*, 10.*, 172.16-31.*, fd:*).

    This function validates whether an IP address belongs to:
    - Loopback addresses (127.0.0.0/8, ::1)
    - Private networks (RFC 1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local addresses (169.254.0.0/16, fe80::/10)
    - IPv6 unique local addresses (fc00::/7)
    - VPN networks (typically 10.8.0.0/24 for WireGuard)

    Anything else is False — including ranges Python's ``is_private`` accepts
    (Teredo, documentation prefixes, NAT64, CGNAT). See ``_LOCAL_NETWORKS``.

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

        # Handle IPv6-mapped IPv4 addresses (::ffff:192.168.1.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        return _in_local_networks(ip)
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
