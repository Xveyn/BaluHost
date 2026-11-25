"""Routen-Tests des Plugins local_tls: Recht, Token-Handling, Audit, Laeufe."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.core.exception_handlers import register_exception_handlers
from app.plugins.installed.local_tls import paths, service, state
from app.plugins.installed.local_tls import routes as routes_module
from app.plugins.installed.local_tls.config import LocalTlsConfig
from app.schemas.user import UserPublic

BASE = "/api/plugins/local_tls"
DOMAIN = "box.duckdns.org"
TOKEN = "0123abcd-0123-4567-89ab-0123456789ab"
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _user(role: str) -> UserPublic:
    return UserPublic(id=1, username=role, role=role, created_at=NOW.isoformat(), is_active=True)


@pytest.fixture
def audit(monkeypatch):
    events: list[dict] = []

    class _Recorder:
        def log_event(self, **kwargs):
            events.append(kwargs)

    monkeypatch.setattr(routes_module, "get_audit_logger_db", lambda: _Recorder())
    return events


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(settings, "vpn_encryption_key", Fernet.generate_key().decode())


@pytest.fixture
def cfg(monkeypatch):
    config = LocalTlsConfig(domain=DOMAIN)
    monkeypatch.setattr(routes_module, "_load_config", lambda db: config)
    return config


def _make(db_session, role="admin"):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(routes_module.router, prefix=BASE)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user] = lambda: _user(role)
    return TestClient(app)


@pytest.fixture
def client(db_session, cfg, audit):
    return _make(db_session)


def _fake_status(**over):
    base = dict(
        configured=True, lego="ok", lego_version="4.35.2", current_ip="192.168.1.20",
        last_ip="192.168.1.20", last_ip_set_at=NOW, cert_not_after=NOW,
        cert_fingerprint="ab" * 32, served_matches=True, last_renew_at=NOW,
        last_renew_ok=True, last_renew_reason=None, running=False,
    )
    base.update(over)
    return service.Status(**base)


@pytest.fixture
def status_stub(monkeypatch):
    holder = {"status": _fake_status()}
    monkeypatch.setattr(service, "get_status", lambda db, config, now, **kw: holder["status"])
    return holder


@pytest.fixture
def checks(monkeypatch):
    calls: list[dict] = []

    async def fake_run_check(check, load_config, **kw):
        calls.append({"check": check.__name__, **kw})
        return []

    monkeypatch.setattr(service, "run_check", fake_run_check)
    return calls


def test_routes_require_admin(db_session, cfg, audit):
    c = _make(db_session, role="user")
    with patch("app.api.deps.get_audit_logger_db"):
        for method, path in [
            ("get", "/status"), ("put", "/credentials"), ("delete", "/credentials"),
            ("post", "/renew"), ("post", "/update-dns"),
        ]:
            kw = {"json": {"token": TOKEN}} if method == "put" else {}
            assert getattr(c, method)(BASE + path, **kw).status_code == 403, path


def test_status_never_contains_token(client, db_session, key, status_stub):
    state.set_token(db_session, TOKEN)
    resp = client.get(BASE + "/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_set"] is True
    assert body["nginx_hint"] is None
    assert TOKEN not in resp.text
    assert "provider_secret" not in resp.text


def test_status_nginx_hint_only_when_not_served(client, status_stub):
    status_stub["status"] = _fake_status(served_matches=False)
    hint = client.get(BASE + "/status").json()["nginx_hint"]
    assert f"ssl_certificate {paths.DATA_DIR}/live/fullchain.pem;" in hint
    assert f"ssl_certificate_key {paths.DATA_DIR}/live/privkey.pem;" in hint
    assert f"server_name {DOMAIN};" in hint
    status_stub["status"] = _fake_status(served_matches=None)
    assert client.get(BASE + "/status").json()["nginx_hint"] is None


def test_put_credentials_encrypts_and_audits(client, db_session, key, audit):
    resp = client.put(BASE + "/credentials", json={"token": TOKEN})
    assert resp.status_code == 204
    raw = state.get_state(db_session).provider_secret
    assert raw and TOKEN not in raw
    assert state.get_token(db_session) == TOKEN
    assert len(audit) == 1
    assert audit[0]["action"] == "local_tls_credentials_changed"
    assert audit[0]["details"] == {"action": "set"}
    assert TOKEN not in repr(audit)


def test_put_credentials_without_key_is_400(client, db_session, monkeypatch, audit):
    monkeypatch.setattr(settings, "vpn_encryption_key", "")
    resp = client.put(BASE + "/credentials", json={"token": TOKEN})
    assert resp.status_code == 400
    assert resp.json() == {"error": "encryption_key_missing"}
    assert TOKEN not in resp.text
    assert state.has_token(db_session) is False
    assert audit == []


def test_put_credentials_malformed_key_is_400(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "vpn_encryption_key", "not-a-fernet-key")
    resp = client.put(BASE + "/credentials", json={"token": TOKEN})
    assert resp.status_code == 400
    assert TOKEN not in resp.text
    assert state.has_token(db_session) is False


@pytest.mark.parametrize("token", ["", "x" * 201, "nicht-hex-" + "z" * 26, "abc"])
def test_put_credentials_validates_pattern(client, db_session, key, token):
    resp = client.put(BASE + "/credentials", json={"token": token})
    assert resp.status_code == 422
    assert state.has_token(db_session) is False
    if len(token) > 3:
        assert token not in resp.text


def test_delete_credentials(client, db_session, key, audit):
    state.set_token(db_session, TOKEN)
    resp = client.delete(BASE + "/credentials")
    assert resp.status_code == 204
    assert state.has_token(db_session) is False
    assert audit[-1]["action"] == "local_tls_credentials_changed"
    assert audit[-1]["details"] == {"action": "cleared"}


def test_renew_runs_forced_and_audits(client, status_stub, checks, audit):
    resp = client.post(BASE + "/renew")
    assert resp.status_code == 202
    assert resp.json()["configured"] is True
    assert checks == [
        {"check": "run_cert_check", "force": True, "raise_if_running": True}
    ]
    assert audit[-1]["action"] == "local_tls_renew_triggered"


def test_renew_while_running_is_409(client, status_stub, monkeypatch, tmp_path, key, db_session):
    data = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setattr(service.lego, "version", lambda: (4, 35, 2))
    real_run_check = service.run_check

    async def run_in_test_db(check, load_config, **kw):
        # Nie die echte Datenbank: eigene Session-Fabrik, die die Test-Session liefert.
        class _Session:
            def __getattr__(self, name):
                return getattr(db_session, name)

            def close(self):
                pass

        return await real_run_check(check, load_config, session_factory=_Session, **kw)

    monkeypatch.setattr(service, "run_check", run_in_test_db)
    state.set_token(db_session, TOKEN)
    paths.ensure_dirs(data)
    with paths.lock(data):
        resp = client.post(BASE + "/renew")
    assert resp.status_code == 409
    assert resp.json() == {"error": "already_running"}


def test_renew_already_running_from_check(client, status_stub, monkeypatch):
    async def boom(check, load_config, **kw):
        raise paths.AlreadyRunning("x")

    monkeypatch.setattr(service, "run_check", boom)
    assert client.post(BASE + "/renew").status_code == 409
    assert client.post(BASE + "/update-dns").status_code == 409


def test_update_dns_triggers_forced_check(client, status_stub, checks, audit):
    resp = client.post(BASE + "/update-dns")
    assert resp.status_code == 200
    assert checks == [
        {"check": "run_address_check", "force": True, "raise_if_running": True}
    ]
    assert audit[-1]["action"] == "local_tls_dns_update_triggered"


def test_rate_limit_key_registered():
    from app.core.rate_limiter import RATE_LIMITS
    from app.services.rate_limit_config import RateLimitConfigService

    assert RATE_LIMITS["local_tls"] == "30/minute"

    class _Db:
        def __init__(self):
            self.added = []

        def execute(self, *a, **k):
            class _R:
                def first(self_inner):
                    return None
            return _R()

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            pass

    db = _Db()
    RateLimitConfigService.seed_defaults(db)
    assert any(
        o.endpoint_type == "local_tls" and o.limit_string == "30/minute" for o in db.added
    )
