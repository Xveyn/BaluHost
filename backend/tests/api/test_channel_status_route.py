"""Tests for GET /api/system/channel-status."""
import pytest
from app.core.config import settings


def test_channel_status_returns_remote_by_default(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    resp = client.get("/api/system/channel-status", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"channel": "remote"}


def test_channel_status_returns_local_when_configured(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "channel", "local")
    resp = client.get("/api/system/channel-status", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"channel": "local"}


def test_channel_status_requires_auth(client):
    resp = client.get("/api/system/channel-status")
    assert resp.status_code == 401


def test_channel_status_works_for_non_admin_user(client, user_headers, monkeypatch):
    """Channel status is visible to any authenticated user (not sensitive)."""
    monkeypatch.setattr(settings, "channel", "local")
    resp = client.get("/api/system/channel-status", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json() == {"channel": "local"}
