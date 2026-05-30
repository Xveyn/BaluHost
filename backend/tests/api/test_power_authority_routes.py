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
