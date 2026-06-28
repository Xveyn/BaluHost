"""Phase 4: production-wired CapabilityRouter factory."""
import asyncio
from unittest.mock import AsyncMock

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


def test_notifier_uses_injected_session_factory_and_targets_user(monkeypatch):
    """Verify that notifier uses injected session_factory and targets acting user."""
    import app.plugins.sandbox.host_capabilities as hc

    # Record what the notification service's create method receives
    recorded_kwargs = {}

    async def stub_create(db, **kwargs):
        recorded_kwargs.update(kwargs)

    stub_service = AsyncMock()
    stub_service.create = stub_create

    # Stub get_notification_service to return our stub
    monkeypatch.setattr(hc, "get_notification_service", lambda: stub_service)

    # Stub SessionLocal to be a context manager that does nothing (no DB access)
    class FakeSessionContext:
        def __enter__(self):
            return None  # db session object (unused by stub)

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(hc, "SessionLocal", lambda: FakeSessionContext())

    # Build router with core.notify scope
    router = build_capability_router("test-plugin", {"core.notify"})

    # Dispatch core.notify with user_id=99
    ctx = CapabilityContext(user_id=99, username="testuser", role="user")
    payload = {"type": "info", "title": "Test Title", "message": "Test Message"}

    result = asyncio.run(router.dispatch("core.notify", payload, ctx))

    # Verify the dispatch succeeded
    assert "error" not in result, f"dispatch failed with error: {result.get('error')}"

    # Verify the notifier recorded the correct user_id
    assert recorded_kwargs.get("user_id") == 99
    assert recorded_kwargs.get("category") == "plugin"
    assert recorded_kwargs.get("notification_type") == "info"
    assert recorded_kwargs.get("title") == "Test Title"
    assert recorded_kwargs.get("message") == "Test Message"
