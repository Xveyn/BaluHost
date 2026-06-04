import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import deps
from app.services.power.desktop import DesktopService
from app.services.power.desktop_backend import DevDesktopBackend


@pytest.fixture
def client():
    class _User:
        id = 1
        username = "admin"
        role = "admin"
    app.dependency_overrides[deps.get_current_user] = lambda: _User()
    import app.services.power.desktop as desktop_mod
    desktop_mod._service = DesktopService(backend=DevDesktopBackend())
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    desktop_mod._service = None


def test_status_endpoint(client):
    r = client.get("/api/system/sleep/desktop/status")
    assert r.status_code == 200
    assert r.json()["state"] == "running"


def test_disable_then_status(client):
    r = client.post("/api/system/sleep/desktop/disable")
    assert r.status_code == 200
    assert r.json()["success"] is True
    r = client.get("/api/system/sleep/desktop/status")
    assert r.json()["state"] == "stopped"


def test_enable_endpoint(client):
    client.post("/api/system/sleep/desktop/disable")
    r = client.post("/api/system/sleep/desktop/enable")
    assert r.status_code == 200
    assert r.json()["success"] is True
    r = client.get("/api/system/sleep/desktop/status")
    assert r.json()["state"] == "running"
