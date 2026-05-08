"""Tests for LoginScreen API-token acquisition."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


class _Resp:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_acquire_token_returns_jwt_on_success(monkeypatch):
    """On API login success, _acquire_api_token must return the access_token string."""
    from baluhost_tui.screens import login as login_mod

    captured: dict[str, Any] = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp(200, {"access_token": "jwt-abc123", "token_type": "bearer"})

    monkeypatch.setattr(login_mod.httpx, "post", fake_post)

    token = login_mod._acquire_api_token("http://localhost:8000", "admin", "pw")

    assert token == "jwt-abc123"
    assert captured["url"].endswith("/api/auth/login")
    assert captured["json"] == {"username": "admin", "password": "pw"}


def test_acquire_token_returns_none_on_http_failure(monkeypatch):
    """On any HTTP error, _acquire_api_token must return None (graceful fallback)."""
    from baluhost_tui.screens import login as login_mod

    def fake_post(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(login_mod.httpx, "post", fake_post)

    assert login_mod._acquire_api_token("http://localhost:8000", "admin", "pw") is None


def test_acquire_token_returns_none_on_4xx(monkeypatch):
    """4xx must be treated as no-token (caller falls back to local-only mode)."""
    from baluhost_tui.screens import login as login_mod

    def fake_post(*args, **kwargs):
        return _Resp(401, {"detail": "invalid credentials"})

    monkeypatch.setattr(login_mod.httpx, "post", fake_post)

    assert login_mod._acquire_api_token("http://localhost:8000", "admin", "pw") is None
