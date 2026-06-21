"""Service-token check must use a constant-time compare (audit #2)."""
import types

import pytest
from fastapi import HTTPException

from app.api.routes import power
from app.core.config import settings


def _req(token_value):
    return types.SimpleNamespace(headers={"X-Service-Token": token_value} if token_value else {})


@pytest.mark.asyncio
async def test_correct_service_token_accepted(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_service_token", "s3cr3t-token-value")
    # No JWT; a correct service token must pass without raising.
    result = await power._get_admin_or_service_token(_req("s3cr3t-token-value"), token=None)
    assert result is None


@pytest.mark.asyncio
async def test_wrong_service_token_falls_through_to_jwt(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_service_token", "s3cr3t-token-value")
    # Wrong token + no JWT → 401 (falls through to the JWT branch which has no token).
    with pytest.raises(HTTPException) as exc:
        await power._get_admin_or_service_token(_req("wrong"), token=None)
    assert exc.value.status_code == 401


def test_power_module_uses_secrets_compare():
    """Guard against regression to plain ==."""
    import inspect
    src = inspect.getsource(power._get_admin_or_service_token)
    assert "compare_digest" in src


@pytest.mark.asyncio
async def test_non_ascii_service_token_falls_through_to_401(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_service_token", "s3cr3t-token-value")
    # A non-ASCII header must NOT raise TypeError (500); it should deny -> 401.
    with pytest.raises(HTTPException) as exc:
        await power._get_admin_or_service_token(_req("tök\xffen"), token=None)
    assert exc.value.status_code == 401
