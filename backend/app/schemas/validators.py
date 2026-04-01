"""Shared Pydantic validators reusable across schemas."""
import re
from typing import Optional

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
