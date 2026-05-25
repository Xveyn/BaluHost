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
