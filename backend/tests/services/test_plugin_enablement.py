"""Cross-worker plugin enablement: the DB-backed cache (#448)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import plugin_enablement as pe


def _grant(permissions=None, scopes=None) -> dict:
    """Build a ``_fetch()``-shaped cache entry for one plugin."""
    return {
        "granted_permissions": list(permissions or []),
        "granted_api_scopes": list(scopes or []),
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    pe._failed_until.clear()
    pe._reconcile_lock = asyncio.Lock()
    yield
    pe.invalidate()
    pe._failed_until.clear()
    pe._reconcile_lock = asyncio.Lock()


class TestCache:
    async def test_refresh_loads_names_and_permissions(self):
        with patch.object(pe, "_fetch", return_value={"demo": _grant(["files.read"])}):
            await pe.refresh()
        assert pe.enabled_plugins() == {"demo": ["files.read"]}
        assert pe.is_enabled("demo") is True
        assert pe.is_enabled("other") is False

    async def test_second_refresh_inside_the_ttl_does_not_hit_the_db(self):
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}) as fetch:
            await pe.refresh()
            await pe.refresh()
        assert fetch.call_count == 1

    async def test_refresh_after_the_ttl_hits_the_db_again(self, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(pe, "_monotonic", lambda: clock["now"])
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}) as fetch:
            await pe.refresh()
            clock["now"] += pe.CACHE_TTL_SECONDS + 0.1
            await pe.refresh()
        assert fetch.call_count == 2

    async def test_force_bypasses_the_ttl(self):
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}) as fetch:
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
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}):
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
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}):
            await pe.refresh()
        with patch.object(pe, "_fetch", side_effect=AssertionError("sync read hit the DB")):
            assert pe.is_enabled("demo") is True
            assert pe.enabled_plugins() == {"demo": []}

    async def test_invalidate_forces_the_next_refresh(self):
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}) as fetch:
            await pe.refresh()
            pe.invalidate()
            await pe.refresh()
        assert fetch.call_count == 2

    async def test_invalidate_clears_the_failed_backoff(self):
        """An admin who fixes and re-enables a plugin must not have to wait
        out the full backoff on other workers - invalidate() is exactly the
        signal that the DB state changed."""
        pe._failed_until["demo"] = pe._monotonic() + pe.FAILED_RETRY_SECONDS
        pe.invalidate()
        assert pe._failed_until == {}

    async def test_enabled_plugins_carries_only_permissions_not_scopes(self):
        """enabled_plugins() must keep its documented ``name -> granted_permissions``
        contract even though the internal cache now also carries API scopes."""
        with patch.object(
            pe,
            "_fetch",
            return_value={"demo": _grant(["files.read"], ["read:storage"])},
        ):
            await pe.refresh()
        assert pe.enabled_plugins() == {"demo": ["files.read"]}


class TestFetchAgainstARealDatabase:
    """``_fetch()`` itself, against a real DB session (#448 review finding 4).

    Every other test in this file patches ``_fetch`` away, so the column
    names, the ``is_enabled == True`` filter, and the row -> dict shape were
    only eyeballed. A typo there raises inside ``asyncio.to_thread`` ->
    ``refresh()`` raises -> every gated plugin request 500s while the display
    silently falls back forever - and none of the mocked tests would notice.

    ``_fetch()`` opens its own ``SessionLocal()`` rather than taking a
    session. Rather than monkeypatching ``app.core.database.SessionLocal``
    itself (module-global, riskier to leave patched across tests sharing the
    same process), this rebinds a fresh sessionmaker to the ``db_session``
    fixture's own engine and hands that to ``_fetch`` via ``pe._fetch`` calling
    ``SessionLocal()`` -> the same underlying (StaticPool, single-connection)
    SQLite database the fixture already wrote to, so the rows are visible
    without needing the two sessions to share a transaction.
    """

    def test_fetch_returns_only_enabled_plugins_with_normalized_columns(
        self, db_session, monkeypatch
    ):
        from sqlalchemy.orm import sessionmaker

        import app.core.database as database_module
        from app.models.plugin import InstalledPlugin

        monkeypatch.setattr(
            database_module, "SessionLocal", sessionmaker(bind=db_session.get_bind())
        )

        db_session.add_all([
            InstalledPlugin(
                name="alpha", version="1.0.0", display_name="Alpha",
                is_enabled=True,
                granted_permissions=["files.read"],
                granted_api_scopes=["read:storage"],
            ),
            InstalledPlugin(
                name="beta", version="1.0.0", display_name="Beta",
                is_enabled=True,
                granted_permissions=None,
                granted_api_scopes=None,
            ),
            InstalledPlugin(
                name="gamma", version="1.0.0", display_name="Gamma",
                is_enabled=False,
                granted_permissions=["files.read"],
                granted_api_scopes=["read:storage"],
            ),
        ])
        db_session.commit()

        result = pe._fetch()

        assert result == {
            "alpha": {
                "granted_permissions": ["files.read"],
                "granted_api_scopes": ["read:storage"],
            },
            "beta": {"granted_permissions": [], "granted_api_scopes": []},
        }
        assert "gamma" not in result


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
        with patch.object(pe, "_fetch", return_value={"demo": _grant(["files.read"])}), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()

        manager.enable_plugin.assert_awaited_once()
        args, kwargs = manager.enable_plugin.await_args
        assert args[0] == "demo"
        assert args[1] == ["files.read"]

    async def test_grants_the_api_scopes_to_the_manager(self):
        """External plugins are routed through granted_api_scopes (manager.py:463-465);
        dropping it leaves a lazily-reconciled external plugin with zero
        capabilities even though it is now counted as enabled."""
        manager = _fake_manager(set())
        with patch.object(
            pe,
            "_fetch",
            return_value={"demo": _grant(["files.read"], ["read:storage", "read:network"])},
        ), patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()

        manager.enable_plugin.assert_awaited_once()
        args, kwargs = manager.enable_plugin.await_args
        assert args[0] == "demo"
        assert sorted(kwargs["granted_api_scopes"]) == ["read:network", "read:storage"]

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
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}), \
             patch.object(pe, "_get_manager", return_value=manager), \
             patch.object(lifespan, "IS_PRIMARY_WORKER", False):
            await pe.reconcile_worker()

        assert manager.enable_plugin.await_args.kwargs["start_background_tasks"] is False

        manager = _fake_manager(set())
        pe.invalidate()
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}), \
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

        with patch.object(
            pe, "_fetch", return_value={"bad": _grant(), "good": _grant()}
        ), patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()

        assert "good" in manager._enabled

    async def test_a_failed_plugin_is_not_retried_immediately(self):
        manager = _fake_manager(set())
        manager.enable_plugin = AsyncMock(return_value=False)

        with patch.object(pe, "_fetch", return_value={"demo": _grant()}), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()
            await pe.reconcile_worker()

        assert manager.enable_plugin.await_count == 1

    async def test_a_failed_plugin_is_retried_once_the_backoff_expires(self, monkeypatch):
        """Proves the release half of the backoff, not just the block: removing
        ``+ FAILED_RETRY_SECONDS`` (turning the pause permanent) leaves this red."""
        clock = {"now": 1000.0}
        monkeypatch.setattr(pe, "_monotonic", lambda: clock["now"])

        manager = _fake_manager(set())
        manager.enable_plugin = AsyncMock(return_value=False)

        with patch.object(pe, "_fetch", return_value={"demo": _grant()}), \
             patch.object(pe, "_get_manager", return_value=manager):
            await pe.reconcile_worker()
            assert manager.enable_plugin.await_count == 1

            clock["now"] += pe.FAILED_RETRY_SECONDS + 0.1
            pe.invalidate()
            await pe.reconcile_worker()

        assert manager.enable_plugin.await_count == 2

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

        with patch.object(pe, "_fetch", return_value={"demo": _grant()}), \
             patch.object(pe, "_get_manager", return_value=manager):
            first = asyncio.create_task(pe.reconcile_worker())
            try:
                await started.wait()
                # wait_for is what makes this test fail CLEANLY under mutation:
                # without the single-flight guard the second call queues on the
                # lock, release.set() is never reached, and the test would hang
                # forever instead of going red (no pytest timeout is configured).
                # With the guard it returns immediately; without it, TimeoutError.
                await asyncio.wait_for(pe.reconcile_worker(), timeout=1.0)
            finally:
                # If the assertion/wait_for above raises, `first` must still be
                # released and awaited - otherwise it stays pending forever
                # holding _reconcile_lock, and every later test in the process
                # single-flights out immediately (poisoned suite, see #448
                # review finding 3).
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

    async def test_get_manager_failure_does_not_propagate(self):
        """The docstring promises reconcile_worker() never raises. _get_manager()
        constructs the PluginManager singleton and can touch settings; a failure
        there must not fail the caller's request."""
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}), \
             patch.object(pe, "_get_manager", side_effect=RuntimeError("boom")):
            await pe.reconcile_worker()  # must not raise


class TestReconcileDependency:
    async def test_dependency_runs_the_reconcile(self):
        from app.api.deps import reconciled_plugin_state

        with patch.object(pe, "reconcile_worker", new=AsyncMock()) as reconcile:
            await reconciled_plugin_state()

        reconcile.assert_awaited_once()

    def test_every_entry_point_declares_the_dependency(self):
        """The routes that must not report stale state.

        A route added later without the dependency would silently reintroduce
        the bug for its own view, so the list is asserted rather than trusted.
        """
        import inspect

        from app.api.deps import reconciled_plugin_state
        from app.api.routes import dashboard as dashboard_routes
        from app.api.routes import plugins as plugins_routes
        from app.api.routes import status_bar as status_bar_routes

        expected = [
            (plugins_routes.list_plugins, "list_plugins"),
            (plugins_routes.get_ui_manifest, "get_ui_manifest"),
            (plugins_routes.run_plugin_menu_action, "run_plugin_menu_action"),
            (status_bar_routes.get_statusbar_config, "get_statusbar_config"),
            (status_bar_routes.get_statusbar_state, "get_statusbar_state"),
            (dashboard_routes.get_plugin_panel, "get_plugin_panel"),
        ]
        for func, label in expected:
            deps = [
                param.default.dependency
                for param in inspect.signature(func).parameters.values()
                if hasattr(param.default, "dependency")
            ]
            assert reconciled_plugin_state in deps, f"{label} misses the reconcile dependency"

    def test_toggle_plugin_does_not_declare_the_dependency(self):
        """toggle_plugin must NOT reconcile - it would race the toggle's own
        local enable/disable call with a reconcile reading the pre-toggle DB
        state.
        """
        import inspect

        from app.api.deps import reconciled_plugin_state
        from app.api.routes import plugins as plugins_routes

        deps = [
            param.default.dependency
            for param in inspect.signature(plugins_routes.toggle_plugin).parameters.values()
            if hasattr(param.default, "dependency")
        ]
        assert reconciled_plugin_state not in deps
