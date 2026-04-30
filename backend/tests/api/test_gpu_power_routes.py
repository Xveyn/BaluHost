"""Integration tests for /api/gpu-power/* endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_manager():
    from app.services.power.gpu.manager import GpuPowerManagerService
    GpuPowerManagerService._instance = None
    yield
    GpuPowerManagerService._instance = None


def test_get_status_requires_auth(client: TestClient):
    resp = client.get("/api/gpu-power/status")
    assert resp.status_code in (401, 403)


def test_get_status_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "current_state" in data
    assert data["current_state"] in ("active", "standby", "deep_idle")


def test_get_config_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/config", headers=auth_headers)
    assert resp.status_code == 200
    assert "idle_window_seconds" in resp.json()


def test_put_config_admin_only(client: TestClient, auth_headers):
    """Non-admin user gets 403."""
    body = {"enabled": True, "idle_window_seconds": 60}
    resp = client.put("/api/gpu-power/config", json=body, headers=auth_headers)
    assert resp.status_code == 403


def test_put_config_admin_succeeds(client: TestClient, admin_headers):
    body = {"enabled": True, "idle_window_seconds": 60}
    resp = client.put("/api/gpu-power/config", json=body, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert resp.json()["idle_window_seconds"] == 60


def test_put_config_validation_rejects_out_of_range(client: TestClient, admin_headers):
    body = {"idle_window_seconds": 5}  # below ge=10
    resp = client.put("/api/gpu-power/config", json=body, headers=admin_headers)
    assert resp.status_code == 422


def test_get_capabilities_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/capabilities", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "vendor" in body


def test_register_demand(client: TestClient, auth_headers):
    body = {"source": "test_demand", "timeout_seconds": 60, "description": "test"}
    resp = client.post("/api/gpu-power/demand", json=body, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["source"] == "test_demand"


def test_unregister_demand(client: TestClient, auth_headers):
    client.post("/api/gpu-power/demand", json={"source": "drop_me"}, headers=auth_headers)
    resp = client.delete("/api/gpu-power/demand/drop_me", headers=auth_headers)
    assert resp.status_code == 200


def test_unregister_unknown_demand_returns_404(client: TestClient, auth_headers):
    resp = client.delete("/api/gpu-power/demand/never_registered", headers=auth_headers)
    assert resp.status_code == 404


def test_history_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/history", headers=auth_headers)
    assert resp.status_code == 200
    assert "entries" in resp.json()
    assert "total" in resp.json()
