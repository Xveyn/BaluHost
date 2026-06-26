"""Real-subprocess tests for SandboxSupervisor."""
import asyncio

import pytest

from app.plugins.sandbox.protocol import MsgType
from app.plugins.sandbox.supervisor import SandboxSupervisor, SupervisorError


async def test_start_health_dispatch_stop(tmp_path):
    sup = SandboxSupervisor("echo_plugin", tmp_path)
    await sup.start()
    try:
        assert await sup.health() is True
        resp = await sup.dispatch("GET", "ping", b"", {"user_id": 5})
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body["status"] == 200
        assert resp.body["echo"]["method"] == "GET"
        assert resp.body["echo"]["context"] == {"user_id": 5}
    finally:
        await sup.stop()


async def test_stop_is_idempotent(tmp_path):
    sup = SandboxSupervisor("echo_plugin", tmp_path)
    await sup.start()
    await sup.stop()
    await sup.stop()  # must not raise


async def test_handshake_timeout_raises_and_kills(tmp_path):
    # A spawn hook that starts a process which never connects back.
    async def silent_spawn(argv, cwd):
        return await asyncio.create_subprocess_exec(
            __import__("sys").executable, "-c", "import time; time.sleep(30)"
        )

    sup = SandboxSupervisor(
        "bad_plugin", tmp_path, spawn_hook=silent_spawn, handshake_timeout=1.0
    )
    with pytest.raises(SupervisorError):
        await sup.start()
    # No lingering process / clean state:
    assert await sup.health() is False


async def test_spawn_hook_failure_propagates_cleanly(tmp_path):
    async def failing_spawn(argv, cwd):
        raise RuntimeError("spawn boom")

    sup = SandboxSupervisor("boom_plugin", tmp_path, spawn_hook=failing_spawn)
    with pytest.raises(RuntimeError, match="spawn boom"):
        await sup.start()
    # Supervisor never came up: not running, channel-less, health False.
    assert await sup.health() is False
    assert sup.disabled is False
