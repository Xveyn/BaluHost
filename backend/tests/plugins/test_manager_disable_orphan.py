from pathlib import Path

import pytest

from app.plugins.manager import PluginManager


class _RaisingSupervisor:
    def __init__(self):
        self.hard_killed = False
    async def stop(self):
        raise RuntimeError("stop boom")
    async def _hard_kill(self):
        self.hard_killed = True


class _CleanSupervisor:
    def __init__(self):
        self.stopped = False
        self.hard_killed = False
    async def stop(self):
        self.stopped = True
    async def _hard_kill(self):
        self.hard_killed = True


@pytest.mark.asyncio
async def test_disable_hard_kills_when_stop_raises(tmp_path: Path):
    mgr = PluginManager(plugins_dir=tmp_path)
    sup = _RaisingSupervisor()
    mgr._sandboxes["demo"] = sup
    mgr._enabled.add("demo")

    ok = await mgr.disable_plugin("demo")

    assert ok is True
    assert sup.hard_killed is True          # no orphan
    assert "demo" not in mgr._sandboxes     # handle removed
    assert "demo" not in mgr._enabled


@pytest.mark.asyncio
async def test_disable_clean_path_does_not_hard_kill(tmp_path: Path):
    mgr = PluginManager(plugins_dir=tmp_path)
    sup = _CleanSupervisor()
    mgr._sandboxes["demo"] = sup
    mgr._enabled.add("demo")

    ok = await mgr.disable_plugin("demo")

    assert ok is True
    assert sup.stopped is True
    assert sup.hard_killed is False
    assert "demo" not in mgr._sandboxes
