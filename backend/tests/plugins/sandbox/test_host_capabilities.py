"""Phase 4: production-wired CapabilityRouter factory."""
import asyncio

from app.plugins.sandbox.capabilities import CapabilityContext, CapabilityRouter
from app.plugins.sandbox.host_capabilities import build_capability_router


def test_build_returns_capability_router_with_filtered_scopes():
    router = build_capability_router("weather", {"storage", "core.notify", "bogus"})
    assert isinstance(router, CapabilityRouter)
    # Unknown scope strings are dropped; known ones survive.
    assert router._granted_scopes == frozenset({"storage", "core.notify"})


def test_metrics_reader_projects_telemetry(monkeypatch):
    import app.plugins.sandbox.host_capabilities as hc

    # Stub with the REAL telemetry SHM shape (latest_cpu_usage + latest_memory_sample.percent).
    monkeypatch.setattr(
        hc,
        "read_shm",
        lambda *_a, **_k: {
            "latest_cpu_usage": 12.5,
            "latest_memory_sample": {"percent": 40.0, "used": 1, "total": 2},
            "cpu": [],
        },
    )
    router = build_capability_router("weather", {"core.system_metrics"})
    ctx = CapabilityContext(user_id=1, username="u", role="user")
    result = asyncio.run(router.dispatch("core.system_metrics", {}, ctx))
    assert result == {"result": {"cpu_usage": 12.5, "memory_percent": 40.0}}
