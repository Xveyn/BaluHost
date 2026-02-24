from __future__ import annotations

import logging
import time
import uuid
from typing import Dict

from app.schemas.system import (
    CreateArrayRequest,
    DeleteArrayRequest,
    FormatDiskRequest,
    RaidActionResponse,
)

from app.services.hardware.raid.api import (
    _audit_event,
    _payload_to_dict,
    create_array,
    delete_array,
    format_disk,
)

logger = logging.getLogger(__name__)

# Two-step confirmation store for destructive operations
_confirmations: Dict[str, Dict] = {}


def request_confirmation(action: str, payload: object, ttl_seconds: int = 3600) -> dict:
    """Create a one-time confirmation token for a destructive RAID action.

    Returns a dict with `token` and `expires_at` (unix timestamp).
    """
    token = uuid.uuid4().hex
    expires_at = int(time.time()) + int(ttl_seconds)
    _confirmations[token] = {
        "action": action,
        "payload": _payload_to_dict(payload),
        "expires_at": expires_at,
    }
    logger.info("RAID confirmation requested: %s token=%s expires_at=%s", action, token, expires_at)
    _audit_event("request_confirmation", {"action": action, "token": token}, dry_run=False)
    return {"token": token, "expires_at": expires_at}


def execute_confirmation(token: str) -> RaidActionResponse:
    """Execute a previously requested confirmation token.

    Raises KeyError if token invalid or expired, or RuntimeError on action failure.
    """
    entry = _confirmations.get(token)
    if not entry:
        raise KeyError("Invalid confirmation token")
    if int(time.time()) > int(entry.get("expires_at", 0)):
        del _confirmations[token]
        raise KeyError("Confirmation token expired")

    action = entry["action"]
    payload = entry["payload"]

    # Remove token to make it one-time
    del _confirmations[token]

    # Dispatch supported destructive actions
    try:
        if action == "delete_array":
            req = DeleteArrayRequest(**payload)
            resp = delete_array(req)
        elif action == "format_disk":
            req = FormatDiskRequest(**payload)
            resp = format_disk(req)
        elif action == "create_array":
            req = CreateArrayRequest(**payload)
            resp = create_array(req)
        else:
            raise RuntimeError(f"Unsupported confirmed action: {action}")
    except Exception as exc:
        logger.exception("Failed to execute confirmed action %s: %s", action, exc)
        _audit_event("execute_confirmation_failed", {"action": action, "error": str(exc)}, dry_run=False)
        raise

    _audit_event("execute_confirmation", {"action": action, "token": token}, dry_run=False)
    return resp
