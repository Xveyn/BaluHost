"""get_current_user_optional must reject inactive users on the JWT path (audit #1)."""
import types

import pytest

from app.api import deps


class _FakeReq:
    client = None
    state = types.SimpleNamespace()


@pytest.mark.asyncio
async def test_optional_auth_returns_none_for_inactive_user(monkeypatch):
    inactive = types.SimpleNamespace(id=1, username="u", is_active=False, role="user")
    monkeypatch.setattr(deps.auth_service, "decode_token",
                        lambda t: types.SimpleNamespace(sub="1"))
    monkeypatch.setattr(deps.user_service, "get_user", lambda sub, db=None: inactive)
    result = await deps.get_current_user_optional(_FakeReq(), token="jwt.token.here", db=None)
    assert result is None


@pytest.mark.asyncio
async def test_optional_auth_returns_active_user(monkeypatch):
    active = types.SimpleNamespace(id=1, username="u", is_active=True, role="user")
    monkeypatch.setattr(deps.auth_service, "decode_token",
                        lambda t: types.SimpleNamespace(sub="1"))
    monkeypatch.setattr(deps.user_service, "get_user", lambda sub, db=None: active)
    monkeypatch.setattr(deps.user_service, "serialize_user", lambda u: u)
    result = await deps.get_current_user_optional(_FakeReq(), token="jwt.token.here", db=None)
    assert result is active
