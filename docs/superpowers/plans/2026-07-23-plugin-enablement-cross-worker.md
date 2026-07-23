# Plugin-Aktivierung über Worker hinweg — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** „Ist dieses Plugin aktiviert?" wird aus der Datenbank beantwortet statt aus prozess-lokalem Zustand, und jeder Worker gleicht sich beim nächsten Request selbst an — damit ein Toggle ohne Neustart auf allen vier Prod-Workern wirkt (#448).

**Architecture:** Ein neuer Helper `services/plugin_enablement.py` hält `name -> granted_permissions` aus `installed_plugins` in einem TTL-Cache; der DB-Zugriff passiert ausschließlich in einer async `refresh()` über `asyncio.to_thread`. Synchrone Leser (`PluginManager.is_enabled()`, `get_all_plugins()`) konsumieren nur den warmen Cache. Eine async `reconcile_worker()` gleicht `PluginManager._enabled` an die DB an (single-flight), und `PluginGateMiddleware` wird zweiter Nutzer desselben Caches statt zweiter Implementierung.

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Pydantic v2, pytest (`asyncio_mode = "auto"`).

**Spec:** `docs/superpowers/specs/2026-07-23-plugin-enablement-cross-worker-design.md`

## Global Constraints

- Backend-Tests laufen aus `backend/`: `python -m pytest <pfad> -q --no-cov` (`--no-cov` nötig, der Repo-Default schaltet Coverage an).
- Lint: `python -m ruff check <geänderte dateien>` muss sauber sein (ein blankes `ruff` liegt nicht im PATH). Regelsatz `["E4","E7","E9","F"]`, `line-length = 100`.
- Keine neuen Dependencies, keine DB-Migration. Die Tabelle `installed_plugins` bleibt unverändert.
- Kommentare und Docstrings auf Englisch (Repo-Konvention); Commit-Betreff Englisch.
- **Kein synchroner DB-Zugriff in einem synchronen Getter.** Der einzige DB-Read liegt in `refresh()` und läuft über `asyncio.to_thread`.
- **Hintergrund-Tasks bleiben primary-only.** Der Reconcile übergibt `start_background_tasks=lifespan.IS_PRIMARY_WORKER`.
- **`IS_PRIMARY_WORKER` nur als Modulattribut lesen** (`from app.core import lifespan` … `lifespan.IS_PRIMARY_WORKER`). Es wird erst nach dem Fork gesetzt (`lifespan.py:478`); ein `from app.core.lifespan import IS_PRIMARY_WORKER` friert dauerhaft `False` ein.
- **Gegenläufige Fehlersemantik:** Anzeigepfade fallen bei DB-Fehler auf den letzten bekannten Zustand zurück; `PluginGateMiddleware` bleibt fail-closed.
- Plugin-Router werden nicht nachgerüstet (Mounting nur beim Start, `lifespan.py:630-633`).

---

## File Structure

**Neu:**

| Datei | Verantwortung |
|---|---|
| `backend/app/services/plugin_enablement.py` | TTL-Cache `name -> granted_permissions`, `refresh()`, synchrone Accessoren, `reconcile_worker()` |
| `backend/tests/services/test_plugin_enablement.py` | Cache, TTL, Fehlerweitergabe, Reconcile, Single-Flight, Primary-Gating |
| `backend/tests/plugins/test_manager_enabled_readers.py` | Manager-Statusleser gegen den Cache, inkl. „zweiter Worker"-Test |
| `backend/tests/middleware/test_plugin_gate_enablement.py` | Middleware nutzt den Helper und bleibt fail-closed |

**Geändert:**

| Datei | Änderung |
|---|---|
| `backend/app/plugins/manager.py` | `is_enabled()` und `get_all_plugins()` beantworten aus dem Cache (Fallback `_enabled`) |
| `backend/app/middleware/plugin_gate.py` | eigener Cache/Fetch entfällt; `invalidate_plugin_cache()` delegiert an den Helper |
| `backend/app/api/deps.py` | neue Dependency `reconciled_plugin_state` |
| `backend/app/api/routes/plugins.py` | Dependency an `list_plugins`, `get_ui_manifest`, `run_plugin_menu_action` |
| `backend/app/api/routes/status_bar.py` | Dependency an `get_statusbar_config`, `get_statusbar_state` |
| `backend/app/plugins/CLAUDE.md` | Operator-Note: aus „Restart nötig" wird „binnen weniger Sekunden, außer bei Router-Plugins" |

**Unverändert (und warum):** `iter_enabled_plugins()` und `PluginManager.get_ui_manifest()` lesen weiter `self._enabled`. Ihre Semantik ist **DB ∩ lokal geladen** — sie liefern Instanzen, und eine Instanz kann nur lokal existieren. Der Reconcile sorgt dafür, dass `_enabled` der DB entspricht; damit werden sie automatisch richtig, ohne Änderung.

---

## Task 1: Helper mit TTL-Cache

**Files:**
- Create: `backend/app/services/plugin_enablement.py`
- Test: `backend/tests/services/test_plugin_enablement.py`

**Interfaces:**
- Consumes: `app.core.database.SessionLocal`, `app.models.plugin.InstalledPlugin`.
- Produces:
```python
CACHE_TTL_SECONDS: float = 5.0
async def refresh(force: bool = False) -> None      # raises on DB error
def enabled_plugins() -> Optional[Dict[str, List[str]]]   # None = nie erfolgreich geladen
def is_enabled(name: str) -> Optional[bool]               # None = keine Daten
def invalidate() -> None
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_plugin_enablement.py`:

```python
"""Cross-worker plugin enablement: the DB-backed cache (#448)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import plugin_enablement as pe


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    yield
    pe.invalidate()


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/services/test_plugin_enablement.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: app.services.plugin_enablement`

- [ ] **Step 3: Implement the helper**

Create `backend/app/services/plugin_enablement.py`:

```python
"""Single source of truth for "which plugins are enabled" (#448).

The database is the only state shared by the four production workers.
``PluginManager._enabled`` is process-local and populated at startup, so a
runtime toggle reaches exactly one worker - which made the plugin list report
whatever the answering worker happened to know.

This module caches the database answer for a short window. The read itself
lives in the async ``refresh()`` and runs off the event loop; synchronous
readers consume the warm cache and never open a session of their own, because
the callers that need them (``PluginManager.get_all_plugins()``) have no
session to give.

The cache maps ``name -> granted_permissions`` rather than holding a bare set
of names: ``PluginGateMiddleware`` needs both out of the same read, and a
name-only cache would have forced it to keep a second query.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS: float = 5.0

_cache: Optional[Dict[str, List[str]]] = None
_cached_at: float = 0.0


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def _fetch() -> Dict[str, List[str]]:
    """Blocking DB read - always called through asyncio.to_thread."""
    from app.core.database import SessionLocal
    from app.models.plugin import InstalledPlugin

    db = SessionLocal()
    try:
        rows = (
            db.query(InstalledPlugin)
            .filter(InstalledPlugin.is_enabled == True)  # noqa: E712 - SQL boolean
            .all()
        )
        return {row.name: list(row.granted_permissions or []) for row in rows}
    finally:
        db.close()


async def refresh(force: bool = False) -> None:
    """Reload the cache if the TTL expired. Raises whatever the DB raises.

    Deliberately not swallowing: the display path wants to fall back to the
    last known state, the security gate wants to fail closed. Only the callers
    know which.
    """
    global _cache, _cached_at

    now = _monotonic()
    if not force and _cache is not None and (now - _cached_at) < CACHE_TTL_SECONDS:
        return

    fetched = await asyncio.to_thread(_fetch)
    _cache = fetched
    _cached_at = now


def enabled_plugins() -> Optional[Dict[str, List[str]]]:
    """Warm cache as ``name -> granted_permissions``; None if never loaded."""
    return dict(_cache) if _cache is not None else None


def is_enabled(name: str) -> Optional[bool]:
    """True/False from the cache, or None when there is no data yet."""
    if _cache is None:
        return None
    return name in _cache


def invalidate() -> None:
    """Drop the cache so the next refresh reloads (called after a local toggle)."""
    global _cache, _cached_at
    _cache = None
    _cached_at = 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/services/test_plugin_enablement.py -q --no-cov`
Expected: PASS (9 Tests)

- [ ] **Step 5: Lint + commit**

```bash
cd backend ; python -m ruff check app/services/plugin_enablement.py tests/services/test_plugin_enablement.py
git add backend/app/services/plugin_enablement.py backend/tests/services/test_plugin_enablement.py
git commit -m "feat(plugins): add the DB-backed plugin enablement cache"
```

---

## Task 2: Manager-Statusleser aus dem Cache

**Files:**
- Modify: `backend/app/plugins/manager.py` (`is_enabled()` bei Z. 864-873, `get_all_plugins()` — die beiden `"is_enabled": name in self._enabled` bei Z. 910 und Z. 934)
- Test: `backend/tests/plugins/test_manager_enabled_readers.py` (neu)

**Interfaces:**
- Consumes: `plugin_enablement.is_enabled()`, `plugin_enablement.enabled_plugins()` (Task 1).
- Produces: `PluginManager.is_enabled(name)` und der `is_enabled`-Schlüssel aus `get_all_plugins()` beantworten aus der DB-Wahrheit; `_enabled` bleibt Fallback.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_manager_enabled_readers.py`:

```python
"""The manager's status readers answer from the DB cache, not from _enabled (#448)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.plugins.manager import PluginManager
from app.services import plugin_enablement as pe


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    yield
    pe.invalidate()


def _manager(tmp_path) -> PluginManager:
    return PluginManager(plugins_dir=tmp_path)


class TestIsEnabled:
    async def test_reports_enabled_although_this_worker_never_loaded_it(self, tmp_path):
        """The bug, in one assertion.

        Worker B never handled the toggle, so its _enabled is empty - but the
        database says the plugin is on, and that is what a client must see.
        """
        worker_b = _manager(tmp_path)
        assert worker_b._enabled == set()

        with patch.object(pe, "_fetch", return_value={"demo": []}):
            await pe.refresh()

        assert worker_b.is_enabled("demo") is True

    async def test_reports_disabled_although_this_worker_still_has_it_loaded(self, tmp_path):
        """The reverse direction: disabling used to survive on other workers."""
        worker_b = _manager(tmp_path)
        worker_b._enabled = {"demo"}

        with patch.object(pe, "_fetch", return_value={}):
            await pe.refresh()

        assert worker_b.is_enabled("demo") is False

    def test_falls_back_to_local_state_when_the_cache_has_no_data(self, tmp_path):
        """A DB outage must not blank the plugin list."""
        worker = _manager(tmp_path)
        worker._enabled = {"demo"}

        assert pe.enabled_plugins() is None
        assert worker.is_enabled("demo") is True


class TestGetAllPlugins:
    async def test_status_flag_comes_from_the_cache(self, tmp_path):
        manager = _manager(tmp_path)
        plugin = MagicMock()
        plugin.metadata.name = "demo"
        plugin.metadata.version = "1.0.0"
        plugin.metadata.display_name = "Demo"
        plugin.metadata.description = ""
        plugin.metadata.author = "test"
        plugin.metadata.category = "general"
        plugin.metadata.required_permissions = []
        plugin.get_ui_manifest.return_value = None
        plugin.get_router.return_value = None
        manager._plugins = {"demo": plugin}
        manager._enabled = set()

        with patch.object(manager, "discover_plugins", return_value=["demo"]), \
             patch.object(manager, "get_discovered", return_value=None), \
             patch.object(pe, "_fetch", return_value={"demo": []}):
            await pe.refresh()
            info = manager.get_all_plugins()

        assert info["demo"]["is_enabled"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/plugins/test_manager_enabled_readers.py -q --no-cov`
Expected: FAIL — `assert False is True` (die Leser antworten noch aus `_enabled`)

- [ ] **Step 3: Add the effective-state helper to the manager**

In `backend/app/plugins/manager.py`, direkt **vor** `def is_enabled` (Z. 864) einfügen:

```python
    def _effective_enabled(self) -> set:
        """Names the database says are enabled, falling back to local state.

        The database is the only state shared across the production workers;
        ``_enabled`` only says what THIS worker loaded. Falling back to it when
        the cache has no data keeps a DB outage from blanking the plugin list -
        the gate fails closed instead, which is the opposite direction on
        purpose (see services/plugin_enablement).
        """
        from app.services import plugin_enablement

        cached = plugin_enablement.enabled_plugins()
        if cached is None:
            return set(self._enabled)
        return set(cached)
```

- [ ] **Step 4: Rewrite the two readers**

`is_enabled()` (Z. 864-873) ersetzen durch:

```python
    def is_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled per the database (not per this worker).

        Args:
            name: Plugin name

        Returns:
            True if plugin is enabled
        """
        return name in self._effective_enabled()
```

In `get_all_plugins()` beide Vorkommen von `"is_enabled": name in self._enabled,` (Z. 910 und Z. 934) ersetzen durch `"is_enabled": name in effective,` und am Anfang der Methode, direkt nach `result = {}`, ergänzen:

```python
        effective = self._effective_enabled()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/plugins/test_manager_enabled_readers.py -q --no-cov`
Expected: PASS (4 Tests)

- [ ] **Step 6: Run the plugin suite for regressions**

Run: `cd backend ; python -m pytest tests/plugins -q --no-cov`
Expected: PASS, keine neuen Fehler (die vorhandenen Suites laufen mit leerem Cache und damit über den Fallback).

- [ ] **Step 7: Lint + commit**

```bash
cd backend ; python -m ruff check app/plugins/manager.py tests/plugins/test_manager_enabled_readers.py
git add backend/app/plugins/manager.py backend/tests/plugins/test_manager_enabled_readers.py
git commit -m "fix(plugins): answer enabled-state from the database, not per-worker memory"
```

---

## Task 3: Reconcile mit Single-Flight

**Files:**
- Modify: `backend/app/services/plugin_enablement.py` (anfügen)
- Test: `backend/tests/services/test_plugin_enablement.py` (anfügen)

**Interfaces:**
- Consumes: `refresh()`, `enabled_plugins()` (Task 1); `PluginManager.enable_plugin(name, granted_permissions, db, start_background_tasks=...)`, `PluginManager.disable_plugin(name)`.
- Produces:
```python
FAILED_RETRY_SECONDS: float = 60.0
async def reconcile_worker() -> None
```

- [ ] **Step 1: Write the failing test**

An `backend/tests/services/test_plugin_enablement.py` anhängen:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


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
            await pe.reconcile_worker()      # must return immediately, not enable again
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
```

Ergänze die `_clean_cache`-Fixture in dieser Datei um `pe._failed_until.clear()` vor und nach dem `yield`, damit die Backoff-Sperre nicht zwischen Tests leckt.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/services/test_plugin_enablement.py -q --no-cov -k Reconcile`
Expected: FAIL — `AttributeError: module ... has no attribute 'reconcile_worker'`

- [ ] **Step 3: Implement the reconcile**

An `backend/app/services/plugin_enablement.py` anhängen:

```python
FAILED_RETRY_SECONDS: float = 60.0

_reconcile_lock = asyncio.Lock()
_failed_until: Dict[str, float] = {}


def _get_manager():
    """Indirection so tests can inject a manager double."""
    from app.plugins.manager import PluginManager

    return PluginManager.get_instance()


async def reconcile_worker() -> None:
    """Align this worker's loaded plugins with the database.

    Single-flight: a second caller returns immediately rather than queueing.
    Two requests arriving together (status-strip poll plus plugin list is the
    realistic pair) would otherwise both see the same diff and run the same
    plugin's on_startup() twice, in parallel. The loser proceeds on the current
    state - the winner's reconcile is a moment away.

    Never raises: a reconcile is best-effort maintenance on a request path.
    """
    if _reconcile_lock.locked():
        return

    async with _reconcile_lock:
        try:
            await refresh()
        except Exception:  # noqa: BLE001 - a DB blip must not fail the request
            logger.warning("plugin enablement refresh failed", exc_info=True)
            return

        desired = enabled_plugins()
        if desired is None:
            return

        # Read as a module attribute: lifespan sets this after the fork, so a
        # from-import would freeze the pre-fork False forever.
        from app.core import lifespan

        manager = _get_manager()
        loaded = set(manager._enabled)
        now = _monotonic()

        for name, permissions in desired.items():
            if name in loaded:
                continue
            if _failed_until.get(name, 0.0) > now:
                continue
            try:
                from app.core.database import SessionLocal

                with SessionLocal() as db:
                    ok = await manager.enable_plugin(
                        name,
                        permissions,
                        db,
                        start_background_tasks=lifespan.IS_PRIMARY_WORKER,
                    )
            except Exception:  # noqa: BLE001 - one bad plugin must not stop the rest
                logger.warning("lazy enable of plugin %s failed", name, exc_info=True)
                ok = False
            if not ok:
                _failed_until[name] = now + FAILED_RETRY_SECONDS

        for name in loaded - set(desired):
            try:
                await manager.disable_plugin(name)
            except Exception:  # noqa: BLE001 - same reasoning as above
                logger.warning("lazy disable of plugin %s failed", name, exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/services/test_plugin_enablement.py -q --no-cov`
Expected: PASS (16 Tests)

- [ ] **Step 5: Prove the single-flight test discriminates**

Entferne testweise die beiden Zeilen `if _reconcile_lock.locked(): return`, führe `python -m pytest tests/services/test_plugin_enablement.py -q --no-cov -k concurrent` aus — der Test **muss** fehlschlagen (`await_count == 2`). Danach zurückbauen und erneut laufen lassen.

- [ ] **Step 6: Lint + commit**

```bash
cd backend ; python -m ruff check app/services/plugin_enablement.py tests/services/test_plugin_enablement.py
git add backend/app/services/plugin_enablement.py backend/tests/services/test_plugin_enablement.py
git commit -m "feat(plugins): reconcile a worker's loaded plugins against the database"
```

---

## Task 4: Middleware auf denselben Cache

**Files:**
- Modify: `backend/app/middleware/plugin_gate.py:23-46` (Cache + `_fetch_plugin_status`), `:122-151` (Gate-Block)
- Test: `backend/tests/middleware/test_plugin_gate_enablement.py` (neu)

**Interfaces:**
- Consumes: `plugin_enablement.refresh()`, `enabled_plugins()`, `invalidate()` (Task 1).
- Produces: `invalidate_plugin_cache(name)` bleibt als öffentliche Funktion erhalten (Aufrufer: `routes/plugins.py`), delegiert aber an den Helper.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/middleware/test_plugin_gate_enablement.py`:

```python
"""PluginGateMiddleware reads the shared enablement cache (#448)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.middleware import plugin_gate
from app.services import plugin_enablement as pe


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    yield
    pe.invalidate()


def _request(path: str) -> MagicMock:
    request = MagicMock()
    request.url.path = path
    return request


async def _dispatch(path: str):
    middleware = plugin_gate.PluginGateMiddleware(app=MagicMock())

    async def _call_next(_request):
        return "PASSED"

    return await middleware.dispatch(_request(path), _call_next)


class TestGateUsesTheSharedCache:
    async def test_enabled_plugin_passes(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}), \
             patch.object(plugin_gate.PluginManager, "get_instance") as manager:
            manager.return_value.get_required_permissions.return_value = []
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result == "PASSED"

    async def test_disabled_plugin_is_403(self):
        with patch.object(pe, "_fetch", return_value={}):
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result.status_code == 403

    async def test_missing_permission_is_403(self):
        with patch.object(pe, "_fetch", return_value={"demo": ["files.read"]}), \
             patch.object(plugin_gate.PluginManager, "get_instance") as manager:
            manager.return_value.get_required_permissions.return_value = ["files.write"]
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result.status_code == 403

    async def test_db_failure_fails_closed(self):
        """Opposite direction to the display path: no state, no entry."""
        with patch.object(pe, "_fetch", side_effect=RuntimeError("db down")):
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result.status_code == 500

    async def test_management_routes_still_bypass_the_gate(self):
        with patch.object(pe, "_fetch", side_effect=AssertionError("should not be consulted")):
            assert await _dispatch("/api/plugins/demo/toggle") == "PASSED"
            assert await _dispatch("/api/plugins/ui/manifest") == "PASSED"
```

Hinweis: `PluginManager` muss in `plugin_gate` als Modulname importierbar sein, damit `patch.object(plugin_gate.PluginManager, ...)` greift — der bisherige lokale Import innerhalb von `dispatch()` wandert dafür an den Dateikopf.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/middleware/test_plugin_gate_enablement.py -q --no-cov`
Expected: FAIL — `AttributeError: module 'app.middleware.plugin_gate' has no attribute 'PluginManager'`

- [ ] **Step 3: Replace the private cache with the shared one**

In `backend/app/middleware/plugin_gate.py`:

Den Block `_plugin_cache`, `CACHE_TTL_SECONDS` und `_fetch_plugin_status` (Z. 23-25 und Z. 49-68) **löschen**. Am Dateikopf ergänzen:

```python
from app.plugins.manager import PluginManager
from app.services import plugin_enablement
```

`invalidate_plugin_cache` ersetzen durch:

```python
def invalidate_plugin_cache(name: str) -> None:
    """Drop the cached enablement state after a local toggle.

    Kept as a named function because routes/plugins.py calls it; the state now
    lives in services/plugin_enablement, shared with the manager's readers.
    """
    plugin_enablement.invalidate()
```

Im `dispatch()` den Gate-Block (Z. 122-151) ersetzen durch:

```python
        # --- Gate: check plugin status ---
        try:
            await plugin_enablement.refresh()
        except Exception:
            logger.exception("Failed to fetch plugin status for %s", name)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal error checking plugin status"},
            )

        enabled = plugin_enablement.enabled_plugins() or {}
        if name not in enabled:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Plugin '{name}' is disabled"},
            )
        granted_perms = enabled[name]
```

Der darauffolgende Permission-Block (`required = manager.get_required_permissions(name)` …) bleibt unverändert, nutzt aber den nun am Dateikopf importierten `PluginManager` statt des lokalen Imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/middleware/test_plugin_gate_enablement.py -q --no-cov`
Expected: PASS (5 Tests)

- [ ] **Step 5: Port the existing gate suite — es hängt am entfernten Symbol**

`backend/tests/middleware/test_plugin_gate.py` importiert `CACHE_TTL_SECONDS`, `_plugin_cache` und patcht an **14 Stellen** `plugin_gate._fetch_plugin_status`. Alle drei Symbole verschwinden in Step 3 — die Datei bricht also beim Import, nicht erst in einer Assertion. Sie ist zu portieren, **nicht** zu löschen: sie deckt Pfad-Matching, Management-Bypässe und die `_storage`-Backdoor-Fälle ab, die dieser Umbau nicht ersetzt.

Mechanische Übersetzung, Assertions bleiben unangetastet:

| alt | neu |
|---|---|
| `from ... import CACHE_TTL_SECONDS, _plugin_cache` | `from app.services.plugin_enablement import CACHE_TTL_SECONDS` |
| `_plugin_cache.clear()` (Z. 76, 78) | `plugin_enablement.invalidate()` |
| `@patch("...plugin_gate._fetch_plugin_status", return_value=(True, ["files:read"]))` | `@patch("app.services.plugin_enablement._fetch", return_value={"my_plugin": ["files:read"]})` |
| `return_value=(False, [])` | `return_value={}` |
| `side_effect=Exception(...)` (Z. 294-297) | unverändert, nur am neuen Patch-Punkt |
| Cache-Ablauf über `_plugin_cache[name] = (..., time.monotonic() - TTL - 1)` (Z. 268-269) | `plugin_enablement.invalidate()` — der neue Cache ist global, nicht pro Name; der Test prüft weiterhin, dass danach erneut gelesen wird |

Achtung beim Plugin-Namen: die alten Patches lieferten den Zustand **für jeden** Namen zurück; der neue Cache ist ein Mapping, also muss der im Test verwendete Name (`my_plugin`) als Schlüssel auftauchen, sonst gilt das Plugin als deaktiviert.

Ebenso in `backend/tests/plugins/test_plugin_menu_actions.py`: `TestMenuActionThroughTheRealStack` patcht `plugin_gate._fetch_plugin_status` → auf `plugin_enablement._fetch` umstellen (`{"demo": []}` für aktiviert, `{}` für deaktiviert) und `plugin_gate._plugin_cache.clear()` → `plugin_enablement.invalidate()`.

- [ ] **Step 6: Run the ported suites**

Run: `cd backend ; python -m pytest tests/middleware tests/plugins/test_plugin_menu_actions.py -q --no-cov`
Expected: PASS — die portierte Datei mit **derselben Testanzahl** wie vorher (nichts gestrichen).

- [ ] **Step 7: Lint + commit**

```bash
cd backend ; python -m ruff check app/middleware/plugin_gate.py tests/middleware tests/plugins/test_plugin_menu_actions.py
git add backend/app/middleware/plugin_gate.py backend/tests/middleware backend/tests/plugins/test_plugin_menu_actions.py
git commit -m "refactor(plugins): let the gate share the enablement cache"
```

---

## Task 5: Reconcile an den Einstiegspunkten

**Files:**
- Modify: `backend/app/api/deps.py` (neue Dependency)
- Modify: `backend/app/api/routes/plugins.py` (`list_plugins` Z. 62, `get_ui_manifest` Z. 136, `run_plugin_menu_action` Z. 819)
- Modify: `backend/app/api/routes/status_bar.py` (`get_statusbar_config` Z. 32, `get_statusbar_state` Z. 81)
- Test: `backend/tests/services/test_plugin_enablement.py` (anfügen)

**Interfaces:**
- Consumes: `plugin_enablement.reconcile_worker()` (Task 3).
- Produces: `app.api.deps.reconciled_plugin_state` — async FastAPI-Dependency ohne Rückgabewert.

- [ ] **Step 1: Write the failing test**

An `backend/tests/services/test_plugin_enablement.py` anhängen:

```python
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
        from app.api.routes import plugins as plugins_routes
        from app.api.routes import status_bar as status_bar_routes

        expected = [
            (plugins_routes.list_plugins, "list_plugins"),
            (plugins_routes.get_ui_manifest, "get_ui_manifest"),
            (plugins_routes.run_plugin_menu_action, "run_plugin_menu_action"),
            (status_bar_routes.get_statusbar_config, "get_statusbar_config"),
            (status_bar_routes.get_statusbar_state, "get_statusbar_state"),
        ]
        for func, label in expected:
            deps = [
                param.default.dependency
                for param in inspect.signature(func).parameters.values()
                if hasattr(param.default, "dependency")
            ]
            assert reconciled_plugin_state in deps, f"{label} misses the reconcile dependency"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/services/test_plugin_enablement.py -q --no-cov -k Dependency`
Expected: FAIL — `ImportError: cannot import name 'reconciled_plugin_state'`

- [ ] **Step 3: Add the dependency**

An `backend/app/api/deps.py` anhängen:

```python
async def reconciled_plugin_state() -> None:
    """Align this worker's loaded plugins with the database before answering.

    Plugin enablement lives in the database; a runtime toggle only reaches the
    worker that handled it. Routes whose answer depends on which plugins are
    enabled declare this so their view does not depend on which of the four
    workers replied (#448). Best-effort: it never raises.
    """
    from app.services.plugin_enablement import reconcile_worker

    await reconcile_worker()
```

- [ ] **Step 4: Declare it on the five routes**

In `backend/app/api/routes/plugins.py` bei `list_plugins`, `get_ui_manifest` und `run_plugin_menu_action` jeweils als letzten Parameter ergänzen:

```python
    _reconciled: None = Depends(deps_reconciled_plugin_state),
```

und am Dateikopf importieren:

```python
from app.api.deps import reconciled_plugin_state as deps_reconciled_plugin_state
```

In `backend/app/api/routes/status_bar.py` dasselbe bei `get_statusbar_config` und `get_statusbar_state` — Import analog ergänzen.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/services/test_plugin_enablement.py -q --no-cov`
Expected: PASS (18 Tests)

- [ ] **Step 6: Run the affected route suites**

Run: `cd backend ; python -m pytest tests/plugins tests/api/test_status_bar_routes.py -q --no-cov`
Expected: PASS. Direkt aufgerufene Routenfunktionen (das etablierte Testmuster hier) müssen den neuen Parameter nicht übergeben — er hat einen Default.

- [ ] **Step 7: Lint + commit**

```bash
cd backend ; python -m ruff check app/api/deps.py app/api/routes/plugins.py app/api/routes/status_bar.py
git add backend/app/api/deps.py backend/app/api/routes/plugins.py backend/app/api/routes/status_bar.py backend/tests/services/test_plugin_enablement.py
git commit -m "feat(plugins): reconcile worker state on the routes that report it"
```

---

## Task 6: Doku und Gesamt-Gates

**Files:**
- Modify: `backend/app/plugins/CLAUDE.md` (Operator-Note im Abschnitt „Creating a Plugin")

**Interfaces:**
- Consumes: alles Vorige. Produces: nichts.

- [ ] **Step 1: Rewrite the operator note**

Die bestehende **Operator note** (sie sagt heute, ein Toggle wirke erst nach `baluhost-backend`-Restart auf allen Workern) ersetzen durch:

```markdown
   **Operator note:** plugin enablement lives in the database and every worker
   reconciles itself against it on the next request that needs the state
   (`services/plugin_enablement.py`), so a toggle now takes effect within a few
   seconds across all four production workers — no restart needed for status
   pills, menu actions or dashboard panels (#448).
   **One exception:** plugin HTTP routes are mounted once at startup
   (`core/lifespan.py`), so a plugin that ships its own router still needs a
   `baluhost-backend` restart before its endpoints exist. Its
   method-based contributions work immediately.
```

- [ ] **Step 2: Run the full backend gates**

```bash
cd backend
python -m pytest tests/plugins tests/services/test_plugin_enablement.py tests/middleware tests/api/test_status_bar_routes.py -q --no-cov
python -m ruff check app tests
```
Expected: alles grün. (Bekannt und **nicht** von dieser Arbeit verursacht: `tests/test_desktop_backend.py` hat 3 Windows-only-Fehlschläge wegen `os.getuid()` im Konstruktor.)

- [ ] **Step 3: Frontend unberührt — nur gegenprüfen**

```bash
cd client ; npx vitest run src/__tests__/api/plugins.menuActions.test.ts src/__tests__/contexts
```
Expected: PASS. Diese Arbeit ändert kein Frontend; der Lauf belegt nur, dass die API-Form unverändert ist.

- [ ] **Step 4: Manueller Smoketest (durch den Maintainer, nicht dispatchen)**

Auf BaluNode nach dem Deploy:

1. `steam_gaming` unter *Plugins* deaktivieren, Seite 5–6× hart neu laden → bleibt **jedes Mal** deaktiviert.
2. Aktivieren, Seite 5–6× hart neu laden → bleibt **jedes Mal** aktiviert (vorher: etwa drei von vier Reloads falsch).
3. Ohne Neustart ins Power-Menü: „Gaming-Modus" ist da und der Klick liefert kein 404.
4. `sudo journalctl -u baluhost-backend -n 50 | grep -i "enabled plugin"` → das Nachladen taucht auf den anderen Workern auf, nicht nur einmal.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/CLAUDE.md
git commit -m "docs(plugins): the enablement note now matches how it behaves"
```

---

## Self-Review

**Spec-Abdeckung:**

| Spec-Anforderung | Task |
|---|---|
| Helper mit `name -> granted_permissions`, TTL-Cache | 1 |
| DB-Read nur async über `to_thread`; sync Leser nur Cache | 1 (Test „sync readers never touch the DB") |
| DB-Fehler wird nach oben gereicht statt verschluckt | 1 |
| Statusleser antworten aus der DB-Wahrheit | 2 |
| Fallback auf lokalen Zustand bei fehlenden Daten | 2 |
| `iter_enabled_plugins`/`get_ui_manifest` = DB ∩ geladen, unverändert | 2 (File-Structure-Begründung) |
| Reconcile lädt nach / räumt ab | 3 |
| Single-Flight | 3 (+ Mutationsnachweis in Step 5) |
| Hintergrund-Tasks primary-only | 3 |
| `IS_PRIMARY_WORKER` als Modulattribut | 3 (Global Constraints + Code-Kommentar) |
| Backoff nach Fehlschlag | 3 |
| Middleware nutzt denselben Cache, bleibt fail-closed | 4 |
| `invalidate_plugin_cache` bleibt für die Aufrufer bestehen | 4 |
| Reconcile an den async Einstiegspunkten | 5 |
| Operator-Note korrigiert, Router-Ausnahme benannt | 6 |
| „Zwei Worker, eine DB"-Test | 2 (`test_reports_enabled_although_this_worker_never_loaded_it`) |

**Platzhalter-Scan:** keine TBD/TODO; jeder Code-Schritt enthält den vollständigen Code, jeder Test-Schritt den vollständigen Test.

**Typ-Konsistenz:** `enabled_plugins() -> Optional[Dict[str, List[str]]]` wird in Task 2 (`_effective_enabled`), Task 3 (`desired`) und Task 4 (`enabled[name]`) identisch behandelt — überall `None`-geprüft. `is_enabled()` heißt im Helper wie in `PluginManager`, hat aber unterschiedliche Rückgaben (`Optional[bool]` vs. `bool`); der Manager wandelt bewusst um, indem er `enabled_plugins()` statt `pe.is_enabled()` benutzt. `_fetch`, `_monotonic`, `_get_manager` sind in allen Tests dieselben Patch-Punkte.

**Nicht enthalten (bewusst):** kein Broadcast/SHM zwischen Workern, kein Hot-Mounting von Routern, keine Änderung am Toggle-Endpunkt, keine Migration, keine Frontend-Änderung.
