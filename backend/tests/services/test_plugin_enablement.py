"""Cross-worker plugin enablement: the DB-backed cache (#448)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import plugin_enablement as pe


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    pe._failed_until.clear()
    yield
    pe.invalidate()
    pe._failed_until.clear()


class TestCache:
    async def test_refresh_loads_names_and_permissions(self):
        with patch.object(pe, "_fetch", return_value={"demo": ["files.read"]}):
            await pe.refresh()
        assert pe.enabled_plugins() == {"demo": ["files.read"]}
        assert pe.is_enabled("demo") is True
        assert pe.is_enabled("other") is False

    async def test_second_refresh_inside_the_ttl_does_not_hit_the_db(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            await pe.refresh()
        assert fetch.call_count == 1

    async def test_refresh_after_the_ttl_hits_the_db_again(self, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(pe, "_monotonic", lambda: clock["now"])
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            clock["now"] += pe.CACHE_TTL_SECONDS + 0.1
            await pe.refresh()
        assert fetch.call_count == 2

    async def test_force_bypasses_the_ttl(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            await pe.refresh(force=True)
        assert fetch.call_count == 2

    async def test_db_error_propagates_instead_of_being_swallowed(self):
        """The two callers must fail in opposite directions, so the helper
        does not get to decide - it hands the failure up."""
        with patch.object(pe, "_fetch", side_effect=RuntimeError("db down")):
            with pytest.raises(RuntimeError):
                await pe.refresh()

    async def test_stale_cache_survives_a_failed_refresh(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}):
            await pe.refresh()
        with patch.object(pe, "_fetch", side_effect=RuntimeError("db down")):
            with pytest.raises(RuntimeError):
                await pe.refresh(force=True)
        assert pe.enabled_plugins() == {"demo": []}

    def test_no_data_before_the_first_refresh(self):
        assert pe.enabled_plugins() is None
        assert pe.is_enabled("demo") is None

    async def test_sync_readers_never_touch_the_db(self):
        """Pinned because get_all_plugins() has no session to give them."""
        with patch.object(pe, "_fetch", return_value={"demo": []}):
            await pe.refresh()
        with patch.object(pe, "_fetch", side_effect=AssertionError("sync read hit the DB")):
            assert pe.is_enabled("demo") is True
            assert pe.enabled_plugins() == {"demo": []}

    async def test_invalidate_forces_the_next_refresh(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            pe.invalidate()
            await pe.refresh()
        assert fetch.call_count == 2


def _fake_manager(loaded: set) -> MagicMock:
    manager = MagicMock()
    manager._enabled = set(loaded)

    async def _enable(name, perms, db, start_background_tasks=True, **kw):
        manager._enabled.add(name)
        return True

    async def _disable(name):
        manager._enabled.discard(name)
        return True

    manager.enable_plugin = AsyncMock(side_effect=_enable)
    manager.disable_plugin = AsyncMock(side_effect=_disable)
    return manager


class TestReconcile:
    async def test_loads_what_the_database_says_is_missing(self):
        manager = _fake_manager(set())
        with patch.object(pe, "_fetch", return_value={"demo": ["files.read"]}), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()

        manager.enable_plugin.assert_awaited_once()
        args, kwargs = manager.enable_plugin.await_args
        assert args[0] == "demo"
        assert args[1] == ["files.read"]

    async def test_drops_what_the_database_no_longer_lists(self):
        manager = _fake_manager({"demo"})
        with patch.object(pe, "_fetch", return_value={}), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()

        manager.disable_plugin.assert_awaited_once_with("demo")

    async def test_background_tasks_only_on_the_primary_worker(self):
        """Four workers each starting a plugin's background tasks would turn a
        display bug into real damage."""
        from app.core import lifespan

        manager = _fake_manager(set())
        with patch.object(pe, "_fetch", return_value={"demo": []}), \
             patch.object(pe, "_get_manager", return_value=manager), \
             patch.object(lifespan, "IS_PRIMARY_WORKER", False):
            await pe.reconcile_worker()

        assert manager.enable_plugin.await_args.kwargs["start_background_tasks"] is False

        manager = _fake_manager(set())
        pe.invalidate()
        with patch.object(pe, "_fetch", return_value={"demo": []}), \
             patch.object(pe, "_get_manager", return_value=manager), \
             patch.object(lifespan, "IS_PRIMARY_WORKER", True):
            await pe.reconcile_worker()

        assert manager.enable_plugin.await_args.kwargs["start_background_tasks"] is True

    async def test_a_throwing_plugin_does_not_block_the_others(self):
        manager = _fake_manager(set())

        async def _enable(name, perms, db, start_background_tasks=True, **kw):
            if name == "bad":
                raise RuntimeError("on_startup blew up")
            manager._enabled.add(name)
            return True

        manager.enable_plugin = AsyncMock(side_effect=_enable)

        with patch.object(pe, "_fetch", return_value={"bad": [], "good": []}), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()

        assert "good" in manager._enabled

    async def test_a_failed_plugin_is_not_retried_immediately(self):
        manager = _fake_manager(set())
        manager.enable_plugin = AsyncMock(return_value=False)

        with patch.object(pe, "_fetch", return_value={"demo": []}), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()
            await pe.reconcile_worker()

        assert manager.enable_plugin.await_count == 1

    async def test_concurrent_reconciles_enable_only_once(self):
        """Status-strip poll and plugin list arrive together in practice; both
        would see the same diff and run on_startup() twice in parallel."""
        manager = _fake_manager(set())
        started = asyncio.Event()
        release = asyncio.Event()

        async def _slow_enable(name, perms, db, start_background_tasks=True, **kw):
            started.set()
            await release.wait()
            manager._enabled.add(name)
            return True

        manager.enable_plugin = AsyncMock(side_effect=_slow_enable)

        with patch.object(pe, "_fetch", return_value={"demo": []}), \
             patch.object(pe, "_get_manager", return_value=manager):
            first = asyncio.create_task(pe.reconcile_worker())
            await started.wait()
            # wait_for is what makes this test fail CLEANLY under mutation:
            # without the single-flight guard the second call queues on the
            # lock, release.set() is never reached, and the test would hang
            # forever instead of going red (no pytest timeout is configured).
            # With the guard it returns immediately; without it, TimeoutError.
            await asyncio.wait_for(pe.reconcile_worker(), timeout=1.0)
            release.set()
            await first

        assert manager.enable_plugin.await_count == 1

    async def test_db_failure_leaves_the_worker_untouched(self):
        manager = _fake_manager({"demo"})
        with patch.object(pe, "_fetch", side_effect=RuntimeError("db down")), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()

        manager.enable_plugin.assert_not_awaited()
        manager.disable_plugin.assert_not_awaited()
