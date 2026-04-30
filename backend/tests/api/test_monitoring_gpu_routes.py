"""GPU monitoring API routes."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def force_dev_gpu_backend():
    """Pin the GPU backend to DevGpuBackend so tests don't depend on host hardware.

    The collector picks a real backend (NVIDIA/AMD) when one is present, which
    breaks vendor-specific assertions on machines that aren't headless.
    """
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    from app.services.monitoring.gpu.dev_backend import DevGpuBackend

    orch = get_monitoring_orchestrator()
    original = orch.gpu_collector.backend
    orch.gpu_collector.backend = DevGpuBackend()
    try:
        yield
    finally:
        orch.gpu_collector.backend = original


def test_gpu_info_requires_auth(client: TestClient):
    r = client.get("/api/monitoring/gpu/info")
    assert r.status_code == 401


def test_gpu_info_returns_device_when_detected(client: TestClient, admin_headers: dict):
    """In dev mode a mock GPU is always detected."""
    r = client.get("/api/monitoring/gpu/info", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["vendor"] == "amd"
    assert "7900 XT" in body["device_name"]
    assert body["vram_total_bytes"] > 0


def test_gpu_current_eventually_available(client: TestClient, admin_headers: dict):
    """/gpu/current returns 503 until the first sample, then 200."""
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    orch = get_monitoring_orchestrator()
    orch.gpu_collector.process_sample(None)

    r = client.get("/api/monitoring/gpu/current", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["vendor"] == "amd"
    assert body["usage_percent"] is not None


def test_gpu_history_returns_list(client: TestClient, admin_headers: dict):
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    orch = get_monitoring_orchestrator()
    for _ in range(3):
        orch.gpu_collector.process_sample(None)

    r = client.get("/api/monitoring/gpu/history?time_range=10m", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "samples" in body
    assert body["sample_count"] == len(body["samples"])
    assert body["source"] in ("memory", "database", "memory (fallback)", "database (fallback)")


def test_gpu_endpoints_404_when_not_detected(client: TestClient, admin_headers: dict):
    """Force detected=False and verify 404 on all three endpoints."""
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    orch = get_monitoring_orchestrator()

    class _Fake:
        detected = False
    original = orch.gpu_collector.backend
    orch.gpu_collector.backend = _Fake()
    try:
        assert client.get("/api/monitoring/gpu/info", headers=admin_headers).status_code == 404
        assert client.get("/api/monitoring/gpu/current", headers=admin_headers).status_code == 404
        assert client.get("/api/monitoring/gpu/history", headers=admin_headers).status_code == 404
    finally:
        orch.gpu_collector.backend = original
