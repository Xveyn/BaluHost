"""Tests for /api/power authority endpoints (local-channel gated)."""
import pytest


def test_put_authority_requires_local_channel(remote_client, admin_headers):
    r = remote_client.put("/api/power/authority", json={"external_authority_enabled": True}, headers=admin_headers)
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "local_channel_required"


def test_get_authority_status_ok(client, admin_headers):
    r = client.get("/api/power/authority", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "external_authority_enabled" in body
    assert "ppd_active" in body


def test_enable_authority_fails_when_acquire_fails(client, admin_headers, monkeypatch):
    """If PPD can't be stood down, the flag must NOT be persisted (no split authority)."""
    from app.services.power import config_store

    config_store.save_authority_config({"external_authority_enabled": False})

    async def fake_acquire():
        return False

    monkeypatch.setattr("app.services.power.ppd_authority.acquire", fake_acquire)

    r = client.put("/api/power/authority", json={"external_authority_enabled": True}, headers=admin_headers)

    assert r.status_code == 500
    assert config_store.load_authority_config()["external_authority_enabled"] is False
