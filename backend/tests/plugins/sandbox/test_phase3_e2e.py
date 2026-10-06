"""End-to-end Phase 3 tests: fixture plugin through the full
proxy -> RPC -> capability path via a real worker subprocess.

Proves:
- granted storage + core.system_metrics scopes round-trip correctly and
  storage is bound to the host-resolved user_id (not anything the worker sends).
- a denied scope (core.notify) causes a 500 response and never invokes the notifier.
"""
import os
import shutil
import tempfile
from pathlib import Path

import pytest

import app.plugins.sandbox.capabilities as caps
from app.plugins.sandbox.capabilities import CapabilityRouter
from app.plugins.sandbox.supervisor import SandboxSupervisor

# Absolute path to the fixture plugin directory.
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_plugin")

# Host context injected for every dispatch call.
CTX = {"user_id": 11, "username": "ann", "role": "user"}


class _MemStore:
    """In-memory replacement for plugin_storage_service; records calls for assertions."""

    def __init__(self):
        self.d: dict = {}

    def set_value(self, db, p, u, k, v):
        self.d[(p, u, k)] = v

    def get_value(self, db, p, u, k):
        key = (p, u, k)
        return (key in self.d, self.d.get(key))

    def list_keys(self, db, p, u):
        return sorted(k for (pp, uu, k) in self.d if pp == p and uu == u)

    def delete_value(self, db, p, u, k):
        return self.d.pop((p, u, k), None) is not None


@pytest.fixture
def short_dir():
    """A directory with a very short path, for the worker's Unix socket.

    pytest's tmp_path is not short enough: under xdist it becomes
    /tmp/pytest-of-<user>/pytest-N/popen-gwN/<long test name>/..., which with the
    socket file name exceeds the ~107 byte AF_UNIX limit.
    """
    path = tempfile.mkdtemp(prefix="p3-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_supervisor(short_dir, router, *, plugin_dir, plugin_name):
    """Construct a real SandboxSupervisor with the default spawn, wired to router.

    The worker's Unix socket is created inside the plugin directory, and an
    AF_UNIX path is limited to ~107 bytes.  A checkout under a deep path pushes
    the in-repo fixture directory over that limit ("AF_UNIX path too long"), so
    the fixture is copied to a short temp directory first.  The supervisor
    passes the copy as --plugin-dir to the worker.
    """
    target_dir = Path(short_dir) / os.path.basename(plugin_dir)
    for root, dirs, files in os.walk(plugin_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        target = target_dir / os.path.relpath(root, plugin_dir)
        target.mkdir(parents=True, exist_ok=True)
        for name in files:
            src = os.path.join(root, name)
            # Regular files only: a worker that other tests spawned with this
            # directory as its socket dir leaves a stale plugin-*.sock behind,
            # and a socket cannot be opened for copying (ENXIO).
            if os.path.isfile(src) and not name.endswith(".sock"):
                shutil.copyfile(src, target / name)
    return SandboxSupervisor(plugin_name, str(target_dir), capability_router=router)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_e2e_storage_and_metrics_granted(short_dir):
    """POST /save -> GET /load round-trips the value; storage is bound to user_id=11.
    GET /metrics returns the injected metrics_reader snapshot.
    """
    store = _MemStore()
    orig = caps.plugin_storage_service
    caps.plugin_storage_service = store
    notifications: list = []
    try:
        router = CapabilityRouter(
            plugin_name="sample",
            granted_scopes=frozenset({"storage", "core.system_metrics"}),
            session_factory=lambda: object(),
            metrics_reader=lambda: {
                "cpu_usage": 9.0,
                "memory": {"used": 1, "total": 2, "percent": 50.0},
            },
            notifier=lambda ctx, payload: notifications.append(payload),
        )
        sup = _make_supervisor(short_dir, router, plugin_dir=FIXTURE, plugin_name="sample")
        await sup.start()
        try:
            save_resp = await sup.dispatch("POST", "/save", "hello", CTX)
            assert save_resp["body"] == {"saved": True}

            load_resp = await sup.dispatch("GET", "/load", b"", CTX)
            assert load_resp["body"] == {"note": "hello"}

            # Storage is bound to the HOST-resolved user_id (11), not worker-chosen.
            assert store.d[("sample", 11, "note")] == "hello"

            metrics_resp = await sup.dispatch("GET", "/metrics", b"", CTX)
            assert metrics_resp["body"]["cpu_usage"] == 9.0
        finally:
            await sup.stop()
    finally:
        caps.plugin_storage_service = orig


async def test_e2e_denied_scope_returns_500_and_does_not_notify(short_dir):
    """With core.notify NOT granted, GET /forbidden -> 500; notifier never called."""
    notifications: list = []
    router = CapabilityRouter(
        plugin_name="sample",
        granted_scopes=frozenset({"storage"}),  # core.notify NOT granted
        session_factory=lambda: object(),
        notifier=lambda ctx, payload: notifications.append(payload),
    )
    sup = _make_supervisor(short_dir, router, plugin_dir=FIXTURE, plugin_name="sample")
    await sup.start()
    try:
        resp = await sup.dispatch("GET", "/forbidden", b"", CTX)
        # PluginCapabilityError("denied") in the plugin -> 500
        assert resp["status"] == 500
        assert notifications == []
    finally:
        await sup.stop()
