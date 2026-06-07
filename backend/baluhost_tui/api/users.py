"""Users API wrapper. Plan 3 adds read-only list_users(); Plan 4 extends with CRUD."""
from __future__ import annotations

from typing import Any, Protocol

_EMPTY: dict[str, Any] = {"users": [], "total": 0, "active": 0, "inactive": 0, "admins": 0}


class _Client(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...
    def post(self, path: str, **kwargs: Any) -> Any: ...
    def put(self, path: str, **kwargs: Any) -> Any: ...
    def delete(self, path: str, **kwargs: Any) -> Any: ...


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


def _detail(resp: Any) -> str:
    """Best-effort '(HTTP <code>: <detail>)' message from an error response."""
    try:
        detail = resp.json().get("detail", "")
    except Exception:
        detail = ""
    return f"HTTP {resp.status_code}: {detail}".strip().rstrip(":").strip() or f"HTTP {resp.status_code}"


def create_user(
    client: _Client,
    username: str,
    password: str,
    email: str | None = None,
    role: str = "user",
) -> tuple[bool, str]:
    """POST /api/users/ -> (ok, message). email omitted from the body when empty."""
    body: dict[str, Any] = {"username": username, "password": password, "role": role}
    if email:
        body["email"] = email
    try:
        resp = client.post("/api/users/", json=body)
        if resp.status_code in (200, 201):
            return True, f"User '{username}' created"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"


def update_user(
    client: _Client,
    user_id: int,
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> tuple[bool, str]:
    """PUT /api/users/{id} with only the provided fields -> (ok, message)."""
    body: dict[str, Any] = {}
    if email is not None:
        body["email"] = email
    if role is not None:
        body["role"] = role
    if is_active is not None:
        body["is_active"] = is_active
    try:
        resp = client.put(f"/api/users/{user_id}", json=body)
        if resp.status_code == 200:
            return True, "User updated"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"


def set_password(client: _Client, user_id: int, password: str) -> tuple[bool, str]:
    """PUT /api/users/{id} with {password} (admin password reset) -> (ok, message)."""
    try:
        resp = client.put(f"/api/users/{user_id}", json={"password": password})
        if resp.status_code == 200:
            return True, "Password updated"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"


def delete_user(client: _Client, user_id: int) -> tuple[bool, str]:
    """DELETE /api/users/{id} -> (ok, message). Backend returns 204 on success."""
    try:
        resp = client.delete(f"/api/users/{user_id}")
        if resp.status_code in (200, 204):
            return True, "User deleted"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"
