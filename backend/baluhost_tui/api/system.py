"""System API wrappers: trust channel + app lifecycle (restart/shutdown).

These cover the app-process restart/shutdown endpoints (admin-only, any
channel). OS-level reboot/poweroff is an open item — no backend endpoint yet.
"""
from __future__ import annotations

from typing import Any, Protocol


class _Client(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...
    def post(self, path: str, **kwargs: Any) -> Any: ...


def get_channel_status(client: _Client) -> str:
    """GET /api/system/channel-status -> 'local' | 'remote'.

    Fails safe to 'remote' on any error so the UI defaults to the
    more-restricted view (destructive actions shown as unavailable).

    NOTE: this endpoint is auth-gated. Call only after set_token() /
    api.auth.login() succeeds; a 401 is silently absorbed as 'remote'.
    """
    try:
        resp = client.get("/api/system/channel-status")
        data = resp.json()
        channel = data.get("channel") if isinstance(data, dict) else None
        return channel if channel in ("local", "remote") else "remote"
    except Exception:
        return "remote"


def _post_action(client: _Client, path: str) -> tuple[bool, str]:
    try:
        resp = client.post(path, json={})
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
            msg = f"HTTP {resp.status_code}: {detail}" if detail else f"HTTP {resp.status_code}"
            return False, msg
        try:
            message = resp.json().get("message", "ok")
        except Exception:
            message = "ok"
        return True, message
    except Exception as exc:
        return False, f"request failed: {exc}"


def restart_app(client: _Client) -> tuple[bool, str]:
    """POST /api/system/restart — restart the backend app process."""
    return _post_action(client, "/api/system/restart")


def shutdown_app(client: _Client) -> tuple[bool, str]:
    """POST /api/system/shutdown — stop the backend app process."""
    return _post_action(client, "/api/system/shutdown")


def storage(client: _Client) -> dict | None:
    """GET /api/system/storage -> dict (total/used/available/use_percent) | None."""
    try:
        resp = client.get("/api/system/storage")
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def raid_status(client: _Client) -> list:
    """GET /api/system/raid/status -> list of array dicts ([] on any failure)."""
    try:
        resp = client.get("/api/system/raid/status")
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, dict):
            arrays = data.get("arrays")
            return arrays if isinstance(arrays, list) else []
        return []
    except Exception:
        return []
