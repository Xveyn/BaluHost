"""Shared Pydantic validators reusable across schemas."""
import ipaddress
import re
from typing import Optional
from urllib.parse import urlparse

from app.core.network_utils import is_private_or_local_ip

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_MAC_RE = re.compile(
    r"^([0-9A-Fa-f]{2})[:\-]"
    r"([0-9A-Fa-f]{2})[:\-]"
    r"([0-9A-Fa-f]{2})[:\-]"
    r"([0-9A-Fa-f]{2})[:\-]"
    r"([0-9A-Fa-f]{2})[:\-]"
    r"([0-9A-Fa-f]{2})$"
)


def validate_mac_address(value: Optional[str]) -> Optional[str]:
    """Validate and normalize a MAC address.

    - None → None (field not updated)
    - "" → None (field cleared)
    - Valid MAC → uppercase colon-separated (AA:BB:CC:DD:EE:FF)
    - Invalid → raises ValueError
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    match = _MAC_RE.match(value)
    if not match:
        raise ValueError(
            f"Invalid MAC address format: '{value}'. "
            "Expected AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF"
        )
    return ":".join(g.upper() for g in match.groups())


def validate_lan_host(value: Optional[str]) -> Optional[str]:
    """Validate a host that must live on the local network (SSRF hardening).

    Used for admin-configured integration targets (Fritz!Box, Tapo, Pi-hole)
    that legitimately point at LAN devices. Prevents the configured value from
    being abused to make the server reach an arbitrary public host.

    Policy:
    - None → None; empty/whitespace → None.
    - IP literal → must be private/local (RFC1918, loopback, link-local,
      IPv6-ULA), otherwise ValueError.
    - Hostname → allowed as-is (NOT resolved — no DNS lookup here).

    Returns the stripped value on success.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None

    try:
        ipaddress.ip_address(stripped)
    except ValueError:
        # Not an IP literal → treat as a hostname and allow it through.
        return stripped

    if not is_private_or_local_ip(stripped):
        raise ValueError(
            f"Host '{stripped}' is a public IP address; only private/local "
            "network addresses are allowed."
        )
    return stripped


def validate_lan_url(value: Optional[str]) -> Optional[str]:
    """Validate an http(s) URL whose host must live on the local network.

    SSRF hardening for admin-configured URLs (e.g. Pi-hole remote URL).

    Policy:
    - None → None; empty/whitespace → None.
    - Scheme must be http or https.
    - Host must pass :func:`validate_lan_host` (private IP or hostname).

    Returns the stripped value on success.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None

    parsed = urlparse(stripped)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL must use the http or https scheme, got: '{parsed.scheme or stripped[:30]}'"
        )
    host = parsed.hostname
    if not host:
        raise ValueError("URL must include a host")

    validate_lan_host(host)
    return stripped


def validate_username(v: str) -> str:
    """Validate and normalise a username.

    Rules:
    - Leading/trailing whitespace is stripped
    - 3–32 characters
    - Only letters, digits, hyphens, and underscores allowed
    """
    v = v.strip()
    if len(v) < 3:
        raise ValueError("Username must be at least 3 characters long")
    if len(v) > 32:
        raise ValueError("Username must be less than 32 characters")
    if not _USERNAME_RE.match(v):
        raise ValueError(
            "Username can only contain letters, numbers, hyphens, and underscores"
        )
    return v
