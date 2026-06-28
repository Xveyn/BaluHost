import asyncio
import sys
from unittest.mock import AsyncMock, patch

import pytest

from app.plugins.sandbox import spawn
from app.plugins.sandbox.supervisor import _default_spawn


# --- scrub_env -------------------------------------------------------------

def test_scrub_env_drops_secrets_keeps_path():
    fake_environ = {
        "PATH": "/opt/baluhost/backend/.venv/bin:/usr/bin",
        "LANG": "en_US.UTF-8",
        "SECRET_KEY": "supersecret",
        "VPN_ENCRYPTION_KEY": "key",
        "DATABASE_URL": "postgresql://u:p@h/db",
        "PYTHONUNBUFFERED": "1",
    }
    with patch.object(spawn.os, "environ", fake_environ):
        env = spawn.scrub_env()
    assert env["PATH"] == "/opt/baluhost/backend/.venv/bin:/usr/bin"
    assert env["LANG"] == "en_US.UTF-8"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert "SECRET_KEY" not in env
    assert "VPN_ENCRYPTION_KEY" not in env
    assert "DATABASE_URL" not in env


def test_scrub_env_supplies_path_when_missing():
    with patch.object(spawn.os, "environ", {}):
        env = spawn.scrub_env()
    assert env["PATH"]  # non-empty fallback


# --- hardened_spawn --------------------------------------------------------

@pytest.mark.asyncio
async def test_hardened_spawn_wraps_with_sudo_and_scrubbed_env():
    argv = [
        sys.executable, "-m", "app.plugins.sandbox.worker",
        "--connect", "/run/x.sock",
        "--plugin-dir", "/var/lib/baluhost/plugins/demo",
        "--plugin-name", "demo",
    ]
    fake_proc = object()
    with patch.object(spawn.settings, "plugin_sandbox_wrapper_path", "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"), \
         patch.object(spawn.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=fake_proc)) as mock_exec, \
         patch.object(spawn, "scrub_env", return_value={"PATH": "/usr/bin"}):
        proc = await spawn.hardened_spawn(argv, "/var/lib/baluhost/plugins/demo")
    assert proc is fake_proc
    called_args = list(mock_exec.call_args.args)
    assert called_args[:3] == ["sudo", "-n", "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"]
    assert called_args[3:] == argv  # full argv forwarded; wrapper parses the flags it needs
    assert mock_exec.call_args.kwargs["cwd"] == "/var/lib/baluhost/plugins/demo"
    assert mock_exec.call_args.kwargs["env"] == {"PATH": "/usr/bin"}


# --- select_spawn_hook -----------------------------------------------------

def test_select_dev_returns_default():
    with patch.object(spawn.settings, "environment", "development"):
        assert spawn.select_spawn_hook() is _default_spawn


def test_select_non_linux_returns_default(monkeypatch):
    monkeypatch.setattr(spawn.sys, "platform", "win32")
    with patch.object(spawn.settings, "environment", "production"):
        assert spawn.select_spawn_hook() is _default_spawn


def test_select_prod_linux_provisioned_returns_hardened(monkeypatch):
    monkeypatch.setattr(spawn.sys, "platform", "linux")
    monkeypatch.setattr(spawn, "_wrapper_ready", lambda: True)
    monkeypatch.setattr(spawn, "_user_exists", lambda: True)
    with patch.object(spawn.settings, "environment", "production"):
        assert spawn.select_spawn_hook() is spawn.hardened_spawn


def test_select_prod_linux_unprovisioned_returns_none(monkeypatch):
    monkeypatch.setattr(spawn.sys, "platform", "linux")
    monkeypatch.setattr(spawn, "_wrapper_ready", lambda: False)
    monkeypatch.setattr(spawn, "_user_exists", lambda: True)
    with patch.object(spawn.settings, "environment", "production"):
        assert spawn.select_spawn_hook() is None


# --- grant_plugin_group_access -------------------------------------------

def test_grant_plugin_group_access_chowns_socket_and_dir():
    from unittest.mock import MagicMock, patch

    stat_result = MagicMock()
    stat_result.st_mode = 0o750

    # Production format: supervisor passes "unix:<path>" — the scheme must be stripped
    argv = [
        "--connect", "unix:/run/x.sock",
        "--plugin-dir", "/d",
        "-m", "worker",
        "--plugin-name", "demo",
    ]

    # os.chown is POSIX-only; use create=True so the test works on Windows too.
    with patch.object(spawn, "_plugin_group_gid", return_value=4242), \
         patch.object(spawn.os.path, "exists", return_value=True), \
         patch.object(spawn.os.path, "isdir", return_value=True), \
         patch.object(spawn.os.path, "islink", return_value=False), \
         patch.object(spawn.os, "walk", return_value=iter([("/d", [], ["__init__.py"])])), \
         patch.object(spawn.os, "chown", create=True) as mock_chown, \
         patch.object(spawn.os, "chmod") as mock_chmod, \
         patch.object(spawn.os, "stat", return_value=stat_result):
        spawn.grant_plugin_group_access(argv)

    import os as _os

    # UDS socket: unix: scheme must be stripped → chown/chmod on the bare path "/run/x.sock".
    # This assertion FAILS against the buggy version that passed the full "unix:/run/x.sock"
    # to os.path.exists (which returned True due to mock) and then chowned the wrong path.
    mock_chown.assert_any_call("/run/x.sock", -1, 4242)
    mock_chmod.assert_any_call("/run/x.sock", 0o660)

    # Plugin dir root
    mock_chown.assert_any_call("/d", -1, 4242)
    # File inside dir — use os.path.join so the separator matches the platform
    mock_chown.assert_any_call(_os.path.join("/d", "__init__.py"), -1, 4242)


def test_grant_plugin_group_access_noop_when_group_absent():
    from unittest.mock import patch

    # Use production unix: format here too for consistency
    argv = ["--connect", "unix:/run/x.sock", "--plugin-dir", "/d"]
    # os.chown is POSIX-only; use create=True so the test works on Windows too.
    with patch.object(spawn, "_plugin_group_gid", return_value=None), \
         patch.object(spawn.os, "chown", create=True) as mock_chown:
        spawn.grant_plugin_group_access(argv)

    mock_chown.assert_not_called()


def test_grant_group_rx_tree_skips_symlinks():
    """Symlinks inside the plugin dir must be skipped — no chown/chmod on them."""
    import os as _os
    from unittest.mock import MagicMock, patch

    stat_result = MagicMock()
    stat_result.st_mode = 0o755

    symlink_path = _os.path.join("/d", "link.py")
    normal_path = _os.path.join("/d", "__init__.py")

    def _is_link(path):
        return path == symlink_path

    # os.chown is POSIX-only; use create=True so the test works on Windows too.
    with patch.object(spawn.os.path, "islink", side_effect=_is_link), \
         patch.object(spawn.os, "walk", return_value=iter([("/d", [], ["__init__.py", "link.py"])])), \
         patch.object(spawn.os, "chown", create=True) as mock_chown, \
         patch.object(spawn.os, "chmod") as mock_chmod, \
         patch.object(spawn.os, "stat", return_value=stat_result):
        spawn._grant_group_rx_tree("/d", 4242)

    # The symlink must never be chowned or chmoded
    for call in mock_chown.call_args_list:
        assert call.args[0] != symlink_path, "symlink must not be chowned"
    for call in mock_chmod.call_args_list:
        assert call.args[0] != symlink_path, "symlink must not be chmoded"

    # The regular file IS chowned
    mock_chown.assert_any_call(normal_path, -1, 4242)


@pytest.mark.asyncio
async def test_hardened_spawn_grants_access_before_exec():
    from unittest.mock import AsyncMock, MagicMock, patch

    argv = [
        sys.executable, "-m", "app.plugins.sandbox.worker",
        "--connect", "/run/x.sock",
        "--plugin-dir", "/var/lib/baluhost/plugins/demo",
        "--plugin-name", "demo",
    ]
    fake_proc = object()
    call_order = []

    def _grant(a):
        call_order.append("grant")

    async def _exec(*args, **kwargs):
        call_order.append("exec")
        return fake_proc

    with patch.object(spawn.settings, "plugin_sandbox_wrapper_path", "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"), \
         patch.object(spawn, "grant_plugin_group_access", side_effect=_grant) as mock_grant, \
         patch.object(spawn.asyncio, "create_subprocess_exec", side_effect=_exec), \
         patch.object(spawn, "scrub_env", return_value={"PATH": "/usr/bin"}):
        proc = await spawn.hardened_spawn(argv, "/var/lib/baluhost/plugins/demo")

    assert proc is fake_proc
    mock_grant.assert_called_once_with(argv)
    assert call_order == ["grant", "exec"]
