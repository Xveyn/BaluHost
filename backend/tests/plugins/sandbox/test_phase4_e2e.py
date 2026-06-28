"""Phase 4 E2E: external plugin through supervisor.dispatch -> RPC -> capability."""
import asyncio
from pathlib import Path

import msgpack
import pytest

from app.plugins.sandbox.host_capabilities import build_capability_router
from app.plugins.sandbox.supervisor import SandboxSupervisor

FIXTURE = Path(__file__).parent / "fixtures" / "e2e_plugin"


@pytest.mark.timeout(30)
def test_external_plugin_storage_roundtrip(monkeypatch):
    # Stub the storage capability's DB so the test needs no real database.
    import app.plugins.sandbox.capabilities as caps

    store: dict = {}

    def fake_get(db, plugin, uid, key):
        k = (plugin, uid, key)
        return (k in store, store.get(k))

    def fake_set(db, plugin, uid, key, value):
        store[(plugin, uid, key)] = value

    monkeypatch.setattr(caps.plugin_storage_service, "get_value", fake_get)
    monkeypatch.setattr(caps.plugin_storage_service, "set_value", fake_set)

    async def run():
        router = build_capability_router("e2e_plugin", {"storage"})
        sup = SandboxSupervisor("e2e_plugin", FIXTURE, capability_router=router)
        await sup.start()
        try:
            ctx = {"user_id": 42, "username": "alice", "role": "user"}
            resp = await sup.dispatch("POST", "echo", msgpack.packb({"hi": 1}), ctx)
            assert resp["status"] == 200
            assert resp["body"]["user"]["user_id"] == 42
        finally:
            await sup.stop()

    asyncio.run(run())
