"""Plugin background tasks only ever tick on the primary worker (#465).

``start_background_tasks`` defaults to ``True``, and the enable endpoint
(``api/routes/plugins.py``) never passed it - so an admin toggling a plugin in
the UI started its poller on whichever of the four Uvicorn workers answered the
request, on top of the one the primary starts via the reconcile path. Two
pollers meant duplicate notifications: the cooldown cache
(``services/notifications/events.py``) is a module-level dict, so each process
passes its own check.

The gate therefore lives in ``PluginManager._start_background_tasks()`` rather
than in each caller: two of the three callers got it right, one did not,
because remembering it was the caller's job.
"""

import asyncio
from typing import List
from unittest.mock import MagicMock

import pytest

from app.core import lifespan
from app.plugins.base import BackgroundTaskSpec, PluginBase, PluginMetadata
from app.plugins.manager import PluginManager

pytestmark = pytest.mark.asyncio


class _TickingPlugin(PluginBase):
    """A plugin whose background task records that it ran."""

    def __init__(self) -> None:
        self.ticks = 0

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="ticking_plugin",
            version="1.0.0",
            display_name="Ticking",
            description="Counts its own background ticks",
            author="Test",
            category="utility",
        )

    def get_background_tasks(self) -> List[BackgroundTaskSpec]:
        # run_on_startup defaults to True, so the first tick happens as soon as
        # the task gets the event loop - that is the observable.
        return [
            BackgroundTaskSpec(
                name="poller",
                func=self._tick,
                interval_seconds=3600,
            )
        ]

    async def _tick(self) -> None:
        self.ticks += 1


async def _let_tasks_run() -> None:
    """Hand the event loop to freshly created tasks."""
    for _ in range(20):
        await asyncio.sleep(0)


@pytest.fixture
def manager(tmp_path) -> PluginManager:
    mgr = PluginManager(plugins_dir=tmp_path)
    mgr._plugins["ticking_plugin"] = _TickingPlugin()
    return mgr


class TestPrimaryWorkerGate:
    async def test_a_secondary_worker_never_ticks_the_poller(
        self, manager: PluginManager, monkeypatch
    ):
        """Called exactly the way the enable endpoint calls it: no
        ``start_background_tasks`` argument, so the default ``True`` applies."""
        monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", False)
        plugin: _TickingPlugin = manager._plugins["ticking_plugin"]

        try:
            await manager.enable_plugin("ticking_plugin", [], MagicMock())
            await _let_tasks_run()

            assert plugin.ticks == 0
        finally:
            await manager.disable_plugin("ticking_plugin")

    async def test_the_primary_worker_ticks_the_poller(
        self, manager: PluginManager, monkeypatch
    ):
        """The other half: the gate must not silence the primary too, or the
        poller would never run anywhere."""
        monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", True)
        plugin: _TickingPlugin = manager._plugins["ticking_plugin"]

        try:
            await manager.enable_plugin("ticking_plugin", [], MagicMock())
            await _let_tasks_run()

            assert plugin.ticks == 1
        finally:
            await manager.disable_plugin("ticking_plugin")

    async def test_an_explicit_no_still_wins_on_the_primary(
        self, manager: PluginManager, monkeypatch
    ):
        """``start_background_tasks=False`` stays a veto - the primary check is
        a floor under the callers, not a replacement for their intent."""
        monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", True)
        plugin: _TickingPlugin = manager._plugins["ticking_plugin"]

        try:
            await manager.enable_plugin(
                "ticking_plugin", [], MagicMock(), start_background_tasks=False
            )
            await _let_tasks_run()

            assert plugin.ticks == 0
        finally:
            await manager.disable_plugin("ticking_plugin")
