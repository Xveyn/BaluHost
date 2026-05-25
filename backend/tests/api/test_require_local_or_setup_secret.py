"""Tests for require_local_or_setup_secret (used by setup wizard)."""
import pytest
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.api import deps
from app.core.config import settings


class _Payload(BaseModel):
    setup_secret: str | None = None


def _wire(app: FastAPI):
    @app.post("/test/setup-gated")
    async def setup_gated(
        payload: _Payload,
        _: None = Depends(deps.require_local_or_setup_secret),
    ):
        return {"ok": True}


def test_passes_on_local_channel(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "local")
    monkeypatch.setattr(settings, "setup_secret", "")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={})
    assert resp.status_code == 200


def test_blocked_on_remote_without_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={})
    assert resp.status_code == 403


def test_passes_on_remote_with_matching_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "s3cret")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={"setup_secret": "s3cret"})
    assert resp.status_code == 200


def test_blocked_on_remote_with_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "s3cret")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={"setup_secret": "wrong"})
    assert resp.status_code == 403


def test_audit_log_written_on_remote_blocked_without_secret(client, monkeypatch, db_session):
    """Remote channel with no server-side secret → audit log entry."""
    from app.models.audit_log import AuditLog
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "")
    _wire(client.app)

    before = db_session.query(AuditLog).filter(
        AuditLog.action == "setup_local_channel_required"
    ).count()

    client.post("/test/setup-gated", json={})

    after = db_session.query(AuditLog).filter(
        AuditLog.action == "setup_local_channel_required"
    ).count()
    assert after == before + 1


def test_audit_log_written_on_wrong_secret(client, monkeypatch, db_session):
    """Remote channel with wrong secret → audit log entry."""
    from app.models.audit_log import AuditLog
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "s3cret")
    _wire(client.app)

    before = db_session.query(AuditLog).filter(
        AuditLog.action == "setup_secret_invalid"
    ).count()

    client.post("/test/setup-gated", json={"setup_secret": "wrong"})

    after = db_session.query(AuditLog).filter(
        AuditLog.action == "setup_secret_invalid"
    ).count()
    assert after == before + 1


def test_blocked_when_body_has_secret_but_server_has_no_secret(client, monkeypatch):
    """Defense in depth: client sends a secret but server has no secret configured.

    The body's secret is irrelevant — without a server-side secret to compare
    against, the bypass is never available.
    """
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "")
    _wire(client.app)
    resp = client.post(
        "/test/setup-gated", json={"setup_secret": "whatever"}
    )
    assert resp.status_code == 403
