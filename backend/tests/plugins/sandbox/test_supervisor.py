"""Real-subprocess tests for SandboxSupervisor."""
import asyncio
import sys

import pytest

from app.plugins.sandbox.protocol import MsgType
from app.plugins.sandbox.supervisor import (
    SandboxSupervisor,
    SupervisorError,
    _default_spawn as _default_spawn_passthrough,
)


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


def test_register_restart_budget_unit(tmp_path):
    # Unit-test the budget counter directly (no subprocess): max_restarts=2
    # allows 2 restarts, the 3rd registration trips the budget.
    sup = SandboxSupervisor("p", tmp_path, max_restarts=2)
    assert sup._register_restart() is True   # 1
    assert sup._register_restart() is True   # 2
    assert sup._register_restart() is False  # 3 -> over budget


async def test_auto_restart_after_unexpected_exit(tmp_path):
    sup = SandboxSupervisor("echo_plugin", tmp_path)
    await sup.start()
    try:
        assert await sup.health() is True
        # Kill the worker out from under the supervisor.
        sup._process.kill()
        # The supervise loop should detect the exit and respawn a healthy worker.
        async def _healthy_again() -> bool:
            for _ in range(50):
                if not sup.disabled and await sup.health():
                    return True
                await asyncio.sleep(0.1)
            return False
        assert await _healthy_again() is True
        # And it serves requests again.
        resp = await sup.dispatch("GET", "again", b"", {})
        assert resp.body["echo"]["path"] == "again"
    finally:
        await sup.stop()


async def test_auto_disable_when_restart_fails(tmp_path):
    # First spawn succeeds (real worker); subsequent spawns produce a process
    # that exits immediately, so the restart's handshake fails -> auto-disable.
    state = {"calls": 0}

    async def flaky_spawn(argv, cwd):
        state["calls"] += 1
        if state["calls"] == 1:
            return await _default_spawn_passthrough(argv, cwd)
        return await asyncio.create_subprocess_exec(
            sys.executable, "-c", "raise SystemExit(1)"
        )

    sup = SandboxSupervisor(
        "flaky_plugin", tmp_path, spawn_hook=flaky_spawn, handshake_timeout=2.0
    )
    await sup.start()
    try:
        sup._process.kill()  # force the unexpected exit -> restart attempt (fails)
        async def _disabled() -> bool:
            for _ in range(50):
                if sup.disabled:
                    return True
                await asyncio.sleep(0.1)
            return False
        assert await _disabled() is True
        with pytest.raises(SupervisorError):
            await sup.dispatch("GET", "x", b"", {})
    finally:
        await sup.stop()
