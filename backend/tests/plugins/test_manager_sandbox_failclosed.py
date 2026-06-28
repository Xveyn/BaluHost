import asyncio
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from app.plugins.manager import PluginManager, DiscoveredPlugin


def _external_discovered(tmp_path: Path) -> DiscoveredPlugin:
    return DiscoveredPlugin(
        name="demo", path=tmp_path, source="external",
        manifest=object(),  # truthy manifest → external+manifest path
    )


@pytest.mark.asyncio
async def test_enable_external_fails_closed_when_hook_none(tmp_path):
    mgr = PluginManager(plugins_dir=tmp_path)
    disc = _external_discovered(tmp_path)
    with patch("app.plugins.sandbox.spawn.select_spawn_hook", return_value=None), \
         patch("app.plugins.manager.get_audit_logger_db") as audit:
        ok = await mgr._enable_external("demo", disc, [])
    assert ok is False
    assert "demo" not in mgr._sandboxes
    audit.return_value.log_security_event.assert_called_once()
    kwargs = audit.return_value.log_security_event.call_args.kwargs
    assert kwargs["action"] == "plugin_sandbox_hardening_unavailable"
    assert kwargs["success"] is False
    assert kwargs["user"] == "system"


@pytest.mark.asyncio
async def test_enable_external_uses_selected_hook(tmp_path, monkeypatch):
    mgr = PluginManager(plugins_dir=tmp_path)
    disc = _external_discovered(tmp_path)

    captured = {}

    class _FakeSupervisor:
        def __init__(self, name, path, *, capability_router=None, spawn_hook=None):
            captured["spawn_hook"] = spawn_hook
        async def start(self):
            return None

    class _NoopAudit:
        def log_security_event(self, **kwargs):
            pass

    monkeypatch.setattr("app.plugins.manager.get_audit_logger_db", lambda: _NoopAudit())
    sentinel_hook = lambda argv, cwd: None  # noqa: E731
    with patch("app.plugins.sandbox.spawn.select_spawn_hook", return_value=sentinel_hook), \
         patch("app.plugins.sandbox.supervisor.SandboxSupervisor", _FakeSupervisor), \
         patch("app.plugins.sandbox.host_capabilities.build_capability_router", return_value=object()):
        ok = await mgr._enable_external("demo", disc, [])
    assert ok is True
    assert captured["spawn_hook"] is sentinel_hook
    assert "demo" in mgr._sandboxes


def test_enable_external_emits_spawned_audit_on_success(tmp_path, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()
    discovered = DiscoveredPlugin(
        name="weather", path=pdir, source="external",
        manifest=types.SimpleNamespace(name="weather", display_name="Weather", ui=None),
    )

    class _Supervisor:
        async def start(self):
            return None

    monkeypatch.setattr(mgr, "_supervisor_factory", lambda *a, **k: _Supervisor())
    monkeypatch.setattr(
        "app.plugins.sandbox.host_capabilities.build_capability_router",
        lambda name, scopes: object(),
    )

    events = []

    class _Audit:
        def log_security_event(self, **kwargs):
            events.append(kwargs)

    monkeypatch.setattr("app.plugins.manager.get_audit_logger_db", lambda: _Audit())

    ok = asyncio.run(mgr._enable_external("weather", discovered, ["storage", "core.notify"]))
    assert ok is True
    spawned = [e for e in events if e.get("action") == "plugin_sandbox_spawned"]
    assert len(spawned) == 1
    assert spawned[0]["success"] is True
    assert spawned[0]["user"] == "system"
    assert spawned[0]["resource"] == "plugin:weather"
    assert spawned[0]["details"]["granted_api_scopes"] == ["core.notify", "storage"]
