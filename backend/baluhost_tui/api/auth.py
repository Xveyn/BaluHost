"""Auth API wrapper: acquire a JWT over the BackendClient.

The backend's POST /api/auth/login returns either {access_token, user} or,
for 2FA-protected accounts, {pending_token}. This wrapper turns those into
a token string or a typed exception.
"""
from __future__ import annotations

from typing import Any, Protocol


class _Client(Protocol):
    def post(self, path: str, json: Any = ..., **kwargs: Any) -> Any: ...


class LoginError(Exception):
    """Login failed (bad credentials, network error, or unexpected response)."""


class TwoFactorRequired(Exception):
    """The account requires a second factor; carries the pending token."""

    def __init__(self, pending_token: str) -> None:
        super().__init__("two-factor authentication required")
        self.pending_token = pending_token


def login(client: _Client, username: str, password: str) -> str:
    """Log in and return the access token.

    Raises:
        TwoFactorRequired: account has 2FA enabled (carries pending_token).
        LoginError: invalid credentials, transport failure, or odd response.
    """
    try:
        resp = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
    except Exception as exc:  # transport-level failure
        raise LoginError(f"request failed: {exc}") from exc

    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, dict):
            token = data.get("access_token")
            if isinstance(token, str) and token:
                return token
            pending = data.get("pending_token")
            if isinstance(pending, str) and pending:
                raise TwoFactorRequired(pending)
        raise LoginError("unexpected login response")

    if resp.status_code == 401:
        raise LoginError("invalid username or password")
    raise LoginError(f"login failed: HTTP {resp.status_code}")
