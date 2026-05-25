"""Tests for the require_local_admin dependency.

We exercise it via a temporary endpoint mounted in the test app so we don't
have to pick one of the real category-S endpoints (those get gated later).
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import settings
from app.middleware.channel_marker import ChannelMarkerMiddleware
from app.schemas.user import UserPublic


def _wire(app: FastAPI):
    """Mount a tiny endpoint that uses require_local_admin."""
    @app.post("/test/locally-gated")
    async def locally_gated(
        current_admin: UserPublic = Depends(deps.require_local_admin),
    ):
        return {"username": current_admin.username, "ok": True}


def test_local_admin_passes(client, admin_headers, monkeypatch):
    """channel=local + admin token → 200."""
    monkeypatch.setattr(settings, "channel", "local")
    _wire(client.app)
    resp = client.post("/test/locally-gated", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_remote_admin_blocked_with_structured_error(client, admin_headers, monkeypatch):
    """channel=remote + admin token → 403 local_channel_required."""
    monkeypatch.setattr(settings, "channel", "remote")
    _wire(client.app)
    resp = client.post("/test/locally-gated", headers=admin_headers)
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["error"] == "local_channel_required"


def test_unauth_returns_401_not_403(client, monkeypatch):
    """No token → 401 (auth fires first), not 403 local_channel_required."""
    monkeypatch.setattr(settings, "channel", "remote")
    _wire(client.app)
    resp = client.post("/test/locally-gated")
    assert resp.status_code == 401


def test_non_admin_user_blocked_with_admin_required(client, user_headers, monkeypatch):
    """User token + channel=local → 403 (admin gate fires before channel check)."""
    monkeypatch.setattr(settings, "channel", "local")
    _wire(client.app)
    resp = client.post("/test/locally-gated", headers=user_headers)
    assert resp.status_code == 403
    # Existing get_current_admin returns the legacy string detail
    assert "Admin" in str(resp.json()["detail"])


def test_audit_log_written_on_remote_block(client, admin_headers, monkeypatch, db_session):
    """A remote-blocked admin call writes an audit log entry with the username."""
    from app.models.audit_log import AuditLog
    monkeypatch.setattr(settings, "channel", "remote")
    _wire(client.app)

    before = db_session.query(AuditLog).filter(
        AuditLog.action == "local_channel_required_denied"
    ).count()

    client.post("/test/locally-gated", headers=admin_headers)

    after = db_session.query(AuditLog).filter(
        AuditLog.action == "local_channel_required_denied"
    ).count()
    assert after == before + 1

    entry = db_session.query(AuditLog).filter(
        AuditLog.action == "local_channel_required_denied"
    ).order_by(AuditLog.id.desc()).first()
    assert entry.user == settings.admin_username
