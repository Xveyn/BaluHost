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


def test_failed_toggle_by_a_delegated_user_is_a_failed_security_event(monkeypatch):
    # #647: delegated_power_action was success=True even when the toggle failed.
    import app.api.routes.desktop as desktop_routes
    import app.services.power.desktop as desktop_mod

    security: list[dict] = []

    class _Recorder:
        def log_event(self, **kwargs):
            pass

        def log_security_event(self, **kwargs):
            security.append(kwargs)

    class _Delegated:
        id = 2
        username = "someone"
        role = "user"

    class _FailingBackend(DevDesktopBackend):
        async def disable(self):
            return False, "kscreen-doctor failed"

    monkeypatch.setattr(desktop_routes, "get_audit_logger_db", lambda: _Recorder())
    app.dependency_overrides[deps.require_power_toggle_desktop] = lambda: _Delegated()
    desktop_mod._service = DesktopService(backend=_FailingBackend())
    try:
        with TestClient(app) as c:
            r = c.post("/api/system/sleep/desktop/disable")
    finally:
        app.dependency_overrides.clear()
        desktop_mod._service = None

    assert r.json()["success"] is False
    assert security[-1]["action"] == "delegated_power_action"
    assert security[-1]["success"] is False
