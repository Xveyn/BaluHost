"""Shared Pydantic validators reusable across schemas."""
import re
from typing import Optional

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
