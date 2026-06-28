"""Phase 4 E2E: external plugin through supervisor.dispatch -> RPC -> capability.

Covers:
- Storage user-binding: stored value is keyed to host-resolved user_id=42, not
  anything the plugin controls.
- core.system_metrics (granted): GET metrics -> projected cpu_usage from a
  monkeypatched read_shm snapshot.
- Denied scope (core.notify NOT granted): GET forbidden -> worker returns 500.
"""
import asyncio
from pathlib import Path

import msgpack
import pytest

import app.plugins.sandbox.capabilities as caps
import app.plugins.sandbox.host_capabilities as host_caps
from app.plugins.sandbox.host_capabilities import build_capability_router
from app.plugins.sandbox.supervisor import SandboxSupervisor

FIXTURE = Path(__file__).parent / "fixtures" / "e2e_plugin"

CTX = {"user_id": 42, "username": "alice", "role": "user"}


@pytest.mark.timeout(30)
def test_external_plugin_storage_and_metrics(monkeypatch):
    """POST echo stores+echoes value bound to host user_id=42; GET metrics returns
    injected snapshot with cpu_usage=9.0.
    """
    store: dict = {}

    def fake_get(db, plugin, uid, key):
        k = (plugin, uid, key)
        return (k in store, store.get(k))

    def fake_set(db, plugin, uid, key, value):
        store[(plugin, uid, key)] = value

    monkeypatch.setattr(caps.plugin_storage_service, "get_value", fake_get)
    monkeypatch.setattr(caps.plugin_storage_service, "set_value", fake_set)
    monkeypatch.setattr(
        host_caps,
        "read_shm",
        lambda _path: {
            "latest_cpu_usage": 9.0,
            "latest_memory_sample": {"percent": 40.0},
        },
    )

    async def run():
        router = build_capability_router("e2e_plugin", {"storage", "core.system_metrics"})
        sup = SandboxSupervisor("e2e_plugin", FIXTURE, capability_router=router)
        await sup.start()
        try:
            body_bytes = msgpack.packb({"hi": 1})

            # --- storage: user-binding -----------------------------------------
            resp = await sup.dispatch("POST", "echo", body_bytes, CTX)
            assert resp["status"] == 200
            assert resp["body"]["user"]["user_id"] == 42
            # Store key is bound to the HOST-resolved user_id (42), not the plugin.
            assert store[("e2e_plugin", 42, "last")] == body_bytes
            assert resp["body"]["stored"] == body_bytes

            # --- core.system_metrics (granted) ---------------------------------
            metrics_resp = await sup.dispatch("GET", "metrics", b"", CTX)
            assert metrics_resp["status"] == 200
            assert metrics_resp["body"]["cpu_usage"] == 9.0
        finally:
            await sup.stop()

    asyncio.run(run())


@pytest.mark.timeout(30)
def test_external_plugin_denied_scope(monkeypatch):
    """GET forbidden calls un-granted core.notify -> PluginCapabilityError in the
    worker -> 500 response. core.notify is NOT in the router's granted_scopes.
    """
    async def run():
        # core.notify deliberately absent from granted scopes
        router = build_capability_router("e2e_plugin", {"storage", "core.system_metrics"})
        sup = SandboxSupervisor("e2e_plugin", FIXTURE, capability_router=router)
        await sup.start()
        try:
            resp = await sup.dispatch("GET", "forbidden", b"", CTX)
            # PluginCapabilityError("denied") in the plugin -> 500
            assert resp["status"] == 500
        finally:
            await sup.stop()

    asyncio.run(run())
