"""Audit-log API wrapper + client-side free-text filter.

query_audit() hits GET /api/logging/audit with server-side filters
(user/action/days) and returns the logs list ([] on failure). filter_logs()
applies the TUI's free-text search term across action/resource/user, which
the backend has no equivalent for.
"""
from __future__ import annotations

from typing import Any, Protocol


class _Client(Protocol):
    def get(self, path: str, params: dict | None = ..., **kwargs: Any) -> Any: ...


def query_audit(
    client: _Client,
    limit: int = 100,
    user: str | None = None,
    action: str | None = None,
    days: int = 7,
) -> list:
    """GET /api/logging/audit -> list of log dicts ([] on any failure).

    page_size is capped at 100 (the backend's max). user/action are sent as
    server-side filters only when non-empty.
    """
    params: dict[str, Any] = {"page_size": min(max(int(limit), 1), 100), "days": days}
    if user:
        params["user"] = user
    if action:
        params["action"] = action
    try:
        resp = client.get("/api/logging/audit", params=params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, dict):
            logs = data.get("logs")
            return logs if isinstance(logs, list) else []
        return []
    except Exception:
        return []


def filter_logs(logs: list, term: str) -> list:
    """Return logs whose action/resource/user contains *term* (case-insensitive).

    An empty term returns the list unchanged.
    """
    if not term:
        return logs
    needle = term.lower()
    out = []
    for log in logs:
        haystack = " ".join(
            str(log.get(k) or "") for k in ("action", "resource", "user")
        ).lower()
        if needle in haystack:
            out.append(log)
    return out
