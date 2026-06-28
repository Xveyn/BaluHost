"""Real-subprocess tests for SandboxSupervisor."""
import asyncio
import os
import sys
import textwrap
from pathlib import Path

import pytest

from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.supervisor import (
    SandboxSupervisor,
    SupervisorError,
    SupervisorTimeout,
    _default_spawn as _default_spawn_passthrough,
)


# ---------------------------------------------------------------------------
# Fixture plugin helpers
# ---------------------------------------------------------------------------

def _write_echo_plugin(plugin_dir: Path) -> None:
    """Write a minimal plugin into plugin_dir that echoes method/path/context.

    This replaces the Phase-2b worker echo so tests that use the DEFAULT spawn
    (real worker.py, which now loads a plugin) can still assert on the response
    content without relying on the removed echo handler.
    """
    code = textwrap.dedent("""\
        def register(host):
            @host.route("GET", "ping")
            async def echo_ping(request):
                return {
                    "status": 200,
                    "body": {
                        "method": request["method"],
                        "path": request["path"],
                        "context": request["user"],
                    },
                }

            @host.route("GET", "again")
            async def echo_again(request):
                return {
                    "status": 200,
                    "body": {
                        "method": request["method"],
                        "path": request["path"],
                    },
                }
    """)
    (plugin_dir / "__init__.py").write_text(code, encoding="utf-8")


def _write_trivial_plugin(plugin_dir: Path) -> None:
    """Write a no-route plugin that satisfies the worker's plugin-load requirement."""
    (plugin_dir / "__init__.py").write_text(
        "def register(host):\n    pass\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Supervisor lifecycle tests
# ---------------------------------------------------------------------------

async def test_start_health_dispatch_stop(tmp_path):
    # Phase 3: the worker loads the plugin from tmp_path; we need a valid one.
    _write_echo_plugin(tmp_path)
    sup = SandboxSupervisor("echo_plugin", tmp_path)
    await sup.start()
    try:
        assert await sup.health() is True
        resp = await sup.dispatch(
            "GET", "ping", b"", {"user_id": 5, "username": "alice", "role": "user"}
        )
        # Response comes from the plugin's registered route (SDK dispatch).
        assert resp["status"] == 200
        assert resp["body"]["method"] == "GET"
        assert resp["body"]["context"] == {"user_id": 5, "username": "alice", "role": "user"}
    finally:
        await sup.stop()


async def test_stop_is_idempotent(tmp_path):
    _write_trivial_plugin(tmp_path)
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
    _write_echo_plugin(tmp_path)
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
        # And it serves requests again via the SDK-dispatched route.
        resp = await sup.dispatch("GET", "again", b"", {"user_id": 1, "username": "testuser", "role": "user"})
        assert resp["body"]["path"] == "again"
    finally:
        await sup.stop()


async def test_auto_disable_when_restart_fails(tmp_path):
    # First spawn succeeds (real worker + real plugin); subsequent spawns produce
    # a process that exits immediately, so the restart's handshake fails -> auto-disable.
    _write_trivial_plugin(tmp_path)
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
            await sup.dispatch("GET", "x", b"", {"user_id": 1, "username": "testuser", "role": "user"})
    finally:
        await sup.stop()


async def test_auto_disable_on_non_supervisor_error_restart(tmp_path):
    # Regression test: a NON-SupervisorError raised inside _spawn_and_connect
    # during a restart (e.g. OSError from listener.start() or the spawn hook)
    # must still auto-disable the supervisor and leave stop() safe to call.
    # Before the fix this exception escaped _supervise(), wedging the supervisor
    # (_running=True, _disabled=False, _channel=None) and poisoning stop().
    _write_trivial_plugin(tmp_path)
    state = {"calls": 0}

    async def spawn_then_os_error(argv, cwd):
        state["calls"] += 1
        if state["calls"] == 1:
            return await _default_spawn_passthrough(argv, cwd)
        # Second call simulates EMFILE / ENOMEM from the OS — not SupervisorError
        raise OSError("EMFILE: too many open files")

    sup = SandboxSupervisor(
        "os_error_plugin", tmp_path, spawn_hook=spawn_then_os_error
    )
    await sup.start()
    try:
        assert await sup.health() is True
        sup._process.kill()  # force unexpected exit -> restart raises OSError

        async def _disabled() -> bool:
            for _ in range(50):
                if sup.disabled:
                    return True
                await asyncio.sleep(0.1)
            return False

        assert await _disabled() is True, (
            "supervisor must auto-disable when OSError escapes _spawn_and_connect"
        )
    finally:
        await sup.stop()  # must NOT raise even though supervise task ended abnormally


# ---------------------------------------------------------------------------
# Scripted-worker helpers for cap_call round-trip test
# ---------------------------------------------------------------------------

# Minimal worker script: handles lifecycle health + an http_request that fires
# two cap_calls (storage.set then storage.get) and returns the fetched value.
_SCRIPTED_WORKER = """\
import asyncio
import sys
import argparse
from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import connect_to_host

_ch = None


async def _handler(msg):
    if msg.type == MsgType.LIFECYCLE:
        action = msg.body.get("action")
        if action == "health":
            return Message(id=msg.id, type=MsgType.LIFECYCLE_RESULT, body={"status": "ok"})
        return Message(id=msg.id, type=MsgType.LIFECYCLE_RESULT, body={"status": "stopping"})
    if msg.type == MsgType.HTTP_REQUEST:
        request_id = msg.body.get("request_id")
        await _ch.call(
            MsgType.CAP_CALL,
            {"capability": "storage.set", "request_id": request_id, "args": {"key": "k", "value": "v"}},
        )
        got = await _ch.call(
            MsgType.CAP_CALL,
            {"capability": "storage.get", "request_id": request_id, "args": {"key": "k"}},
        )
        return Message(
            id=msg.id,
            type=MsgType.HTTP_RESPONSE,
            body={"status": 200, "headers": {}, "body": {"stored": got.body.get("result")}},
        )
    return Message(id=msg.id, type=MsgType.ERROR, body={"error": "unsupported"})


async def run(address):
    global _ch
    reader, writer = await connect_to_host(address)
    _ch = RpcChannel(reader, writer, request_handler=_handler)
    _ch.start()
    try:
        await _ch.wait_closed()
    finally:
        await _ch.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.connect))
"""


def _make_supervisor_with_scripted_worker(
    tmp_path: Path,
    router,
) -> SandboxSupervisor:
    """Write the scripted worker to tmp_path and return a supervisor using it."""
    script_path = tmp_path / "scripted_worker.py"
    script_path.write_text(_SCRIPTED_WORKER, encoding="utf-8")

    # The backend/ directory must be on sys.path in the worker subprocess.
    # Path(__file__) is  …/backend/tests/plugins/sandbox/test_supervisor.py
    # so four parents up gives …/backend/.
    backend_dir = str(Path(__file__).resolve().parent.parent.parent.parent)

    async def _spawn(argv: list, cwd: str) -> asyncio.subprocess.Process:
        # Locate the connect address by position after "--connect" (not argv[-1],
        # because Phase 3 appends --plugin-dir / --plugin-name after the address).
        connect_addr = argv[argv.index("--connect") + 1]
        env = os.environ.copy()
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            backend_dir + os.pathsep + existing_pp if existing_pp else backend_dir
        )
        return await asyncio.create_subprocess_exec(
            sys.executable, str(script_path), "--connect", connect_addr, env=env
        )

    return SandboxSupervisor(
        "demo",
        tmp_path,
        spawn_hook=_spawn,
        capability_router=router,
    )


async def test_cap_call_roundtrips_with_host_resolved_context(tmp_path):
    """Worker issues a storage.set+get cap_call while serving a request;
    the host resolves user_id from its in-flight map, not from the worker."""
    from app.plugins.sandbox.capabilities import CapabilityContext, CapabilityRouter  # noqa: F401

    writes: dict = {}

    class _Store:
        def set_value(self, db, plugin_name, user_id, key, value):
            writes[(plugin_name, user_id, key)] = value

        def get_value(self, db, plugin_name, user_id, key):
            k = (plugin_name, user_id, key)
            return (k in writes, writes.get(k))

        def list_keys(self, db, plugin_name, user_id):
            return []

        def delete_value(self, db, plugin_name, user_id, key):
            return False

    import app.plugins.sandbox.capabilities as caps

    caps_orig = caps.plugin_storage_service
    caps.plugin_storage_service = _Store()
    try:
        router = CapabilityRouter(
            plugin_name="demo",
            granted_scopes=frozenset({"storage"}),
            session_factory=lambda: object(),
        )
        supervisor = _make_supervisor_with_scripted_worker(tmp_path, router)
        await supervisor.start()
        try:
            resp = await supervisor.dispatch(
                "GET", "/ping", b"", {"user_id": 42, "username": "bob", "role": "user"}
            )
            assert resp["status"] == 200
            assert resp["body"]["stored"] == "v"
            assert writes[("demo", 42, "k")] == "v"
        finally:
            await supervisor.stop()
    finally:
        caps.plugin_storage_service = caps_orig


# ---------------------------------------------------------------------------
# Phase 4 — query + headers forwarding, timeout, in-flight cap
# ---------------------------------------------------------------------------

class _FakeChannel:
    """Records the last HTTP_REQUEST body; returns a canned response."""

    def __init__(self):
        self.last_body = None

    async def call(self, msg_type, body, timeout=None):
        self.last_body = body
        return Message(id="x", type=MsgType.HTTP_RESPONSE, body={"status": 200, "headers": {}, "body": {"ok": True}})


def _supervisor_with_channel(channel):
    sup = SandboxSupervisor("weather", ".")
    sup._channel = channel
    return sup


def test_dispatch_forwards_query_and_headers():
    channel = _FakeChannel()
    sup = _supervisor_with_channel(channel)
    ctx = {"user_id": 1, "username": "u", "role": "user"}
    asyncio.run(
        sup.dispatch("GET", "status", b"", ctx, query={"a": "1"}, headers={"content-type": "application/json"})
    )
    assert channel.last_body["query"] == {"a": "1"}
    assert channel.last_body["headers"] == {"content-type": "application/json"}
    assert "authorization" not in channel.last_body["headers"]


def test_dispatch_timeout_raises_supervisor_timeout():
    class _SlowChannel:
        async def call(self, msg_type, body, timeout=None):
            raise asyncio.TimeoutError

    sup = _supervisor_with_channel(_SlowChannel())
    with pytest.raises(SupervisorTimeout):
        asyncio.run(sup.dispatch("GET", "x", b"", {"user_id": 1, "username": "u", "role": "user"}, timeout=0.01))
