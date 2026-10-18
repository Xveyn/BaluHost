"""LocalOnlyMiddleware: LAN-Pruefung ueber `is_private_or_local_ip` (#324).

Die Middleware pflegte eine eigene String-Praefix-Liste; `startswith("172.16.")`
deckte nur 172.16.x.x statt 172.16.0.0/12 ab, sodass z. B. Docker-Netze
(172.17.x.x) faelschlich geblockt wurden. Die Klassifikation liegt jetzt
einzig in `core/network_utils.py`.
"""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.middleware.local_only import LocalOnlyMiddleware


def _client(ip: str | None, enforce: bool = True, **kwargs) -> TestClient:
    app = FastAPI()
    app.add_middleware(LocalOnlyMiddleware, enforce=enforce, **kwargs)

    @app.get("/api/auth/login")
    def protected():
        return {"ok": True}

    @app.get("/api/public")
    def public():
        return {"ok": True}

    return TestClient(app, client=(ip, 50000) if ip else None)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "::1",
        "10.8.0.5",
        "192.168.178.20",
        "172.16.0.1",
        "172.17.0.2",  # Docker-Standardnetz -- vorher geblockt
        "172.20.1.1",
        "172.31.255.254",
        "fd12:3456::1",
        "fc00::1",  # fc00::/7, nicht nur "fd"
        "::ffff:192.168.1.5",  # IPv4-in-IPv6, vorher nur bei Loopback erkannt
        "169.254.10.10",
        "fe80::1",
    ],
)
def test_local_addresses_are_allowed(ip):
    assert _client(ip).get("/api/auth/login").status_code == 200


@pytest.mark.parametrize(
    "ip",
    [
        "8.8.8.8",
        "172.15.255.255",
        "172.32.0.1",  # knapp ausserhalb von 172.16.0.0/12
        "100.64.0.1",  # CGNAT ist bewusst nicht lokal
        "2001:db8::1",  # Dokumentationsbereich: is_private=True, hier nicht lokal
        "11.0.0.1",
    ],
)
def test_non_local_addresses_are_blocked(ip):
    resp = _client(ip).get("/api/auth/login")
    assert resp.status_code == 403
    assert "only localhost allowed" in resp.json()["detail"]


def test_unprotected_path_is_not_checked():
    assert _client("8.8.8.8").get("/api/public").status_code == 200


def test_enforcement_off_lets_everything_through():
    assert _client("8.8.8.8", enforce=False).get("/api/auth/login").status_code == 200


def test_unknown_client_host_is_blocked():
    from starlette.requests import Request  # noqa: F401  (Scope ohne client)
    import asyncio

    mw = LocalOnlyMiddleware(app=None, enforce=True)
    scope = {
        "type": "http", "method": "GET", "path": "/api/auth/login",
        "headers": [], "query_string": b"", "client": None,
    }

    async def call_next(_request):  # pragma: no cover - darf nie erreicht werden
        raise AssertionError("call_next fuer unbekannten Client")

    resp = asyncio.run(mw.dispatch(Request(scope), call_next))
    assert resp.status_code == 403


def test_default_prefixes_are_not_shared_between_instances():
    a = LocalOnlyMiddleware(app=None, enforce=True)
    b = LocalOnlyMiddleware(app=None, enforce=True)
    a.protected_prefixes.append("/api/extra")
    assert "/api/extra" not in b.protected_prefixes


def test_localhost_hostname_is_allowed():
    # Der Host-String "localhost" kommt aus einigen ASGI-Servern/Testclients.
    assert _client("localhost").get("/api/auth/login").status_code == 200
