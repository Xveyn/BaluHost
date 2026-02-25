"""
Benchmark confirmation token generation and validation.

This is a leaf module with no internal dependencies.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

# Raw device confirmation tokens (token -> (disk_name, profile, expires_at))
_confirmation_tokens: Dict[str, Tuple[str, str, datetime]] = {}
_TOKEN_EXPIRY_MINUTES = 5


def generate_confirmation_token(disk_name: str, profile: str) -> Tuple[str, datetime]:
    """Generate a confirmation token for raw device benchmark."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_EXPIRY_MINUTES)
    _confirmation_tokens[token] = (disk_name, profile, expires_at)

    # Clean up expired tokens
    now = datetime.now(timezone.utc)
    expired = [t for t, (_, _, exp) in _confirmation_tokens.items() if exp < now]
    for t in expired:
        del _confirmation_tokens[t]

    return token, expires_at


def validate_confirmation_token(token: str, disk_name: str, profile: str) -> bool:
    """Validate a confirmation token for raw device benchmark."""
    if token not in _confirmation_tokens:
        return False

    stored_disk, stored_profile, expires_at = _confirmation_tokens[token]

    if datetime.now(timezone.utc) > expires_at:
        del _confirmation_tokens[token]
        return False

    if stored_disk != disk_name or stored_profile != profile:
        return False

    # Token is valid, remove it (one-time use)
    del _confirmation_tokens[token]
    return True
