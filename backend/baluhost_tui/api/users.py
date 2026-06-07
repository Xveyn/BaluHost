"""Users API wrapper. Plan 3 adds read-only list_users(); Plan 4 extends with CRUD."""
from __future__ import annotations

from typing import Any, Protocol

_EMPTY: dict[str, Any] = {"users": [], "total": 0, "active": 0, "inactive": 0, "admins": 0}


class _Client(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...


def list_users(client: _Client) -> dict:
    """GET /api/users/ -> {users, total, active, inactive, admins}.

    Returns an empty skeleton (counts 0, users []) on any failure so callers
    can render without None-checks.
    """
    try:
        resp = client.get("/api/users/")
        if resp.status_code != 200:
            return dict(_EMPTY)
        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("users"), list):
            return data
        return dict(_EMPTY)
    except Exception:
        return dict(_EMPTY)
