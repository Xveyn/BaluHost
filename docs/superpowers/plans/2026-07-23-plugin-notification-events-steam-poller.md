# Plugin-Notification-Events + Steam-Session-Poller — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plugins können Notification-Ereignisse deklarieren, die durch die vorhandene Zustellung laufen; das `steam_gaming`-Plugin nutzt das als erster Konsument über einen primary-only Poller, der Steam-Session-Start und -Ende meldet (Teilprojekt 3/4).

**Architecture:** `PluginBase.get_notification_events()` liefert `PluginEventSpec`s; eine `PluginEventRegistry` sammelt sie aus den aktivierten Plugins und beantwortet eine namespaced ID (`plugin:<name>:<suffix>`) mit einem Core-`EventConfig`. `EventEmitter.emit()` fragt die Registry als Fallback zu `EVENT_CONFIGS`. Ein Core-Helper `emit_plugin_event()` erzwingt den Cooldown selbst (der async Emit-Pfad trägt keine Cooldown-Maschinerie) und stellt an das deklarierte Target zu. Das Steam-Plugin deklariert einen `BackgroundTaskSpec` (läuft dank #448 primary-only), dessen Poller Flanken gegen den TP1-Detektor erkennt.

**Tech Stack:** Python 3.11+ / FastAPI / Pydantic v2 / SQLAlchemy 2.0, pytest (`asyncio_mode = "auto"`).

**Spec:** `docs/superpowers/specs/2026-07-23-plugin-notification-events-design.md`

## Global Constraints

- Backend-Tests aus `backend/`: `python -m pytest <pfad> -q --no-cov` (`--no-cov` nötig, der Repo-Default schaltet Coverage an).
- Lint: `python -m ruff check <geänderte dateien>` (ein blankes `ruff` liegt nicht im PATH). Regelsatz `["E4","E7","E9","F"]`, `line-length = 100`.
- Keine neuen Dependencies, keine DB-Migration. Der vorhandene Zustellpfad (`service.create`, Routing, Push, WebSocket) wird **nicht** angefasst.
- **Empfänger admin-fix** (`default_target="admins"`), serverseitig durchgesetzt. Ein Plugin liefert Daten, nie das Zustellziel zur Laufzeit.
- **Die Kategorie setzt der Core auf `plugin_name`** — sie ist der Routing-Schlüssel; `PluginEventSpec` hat **kein** `category`-Feld.
- Event-ID regexbeschränkt (`^[a-z0-9_]+$`) **und** vom Core namespaced (`plugin:<name>:<suffix>`).
- Notification-Texte werden serverseitig in einer Sprache gerendert (Deutsch, wie die Core-Events) — Template-Strings, keine clientseitige i18n.
- Kommentare und Docstrings auf Englisch (Repo-Konvention); Commit-Betreff Englisch.
- Kein `subprocess`, kein sudo. Der Poller liest nur `/proc` über den vorhandenen `detect_running_app_id()`.

---

## File Structure

**Neu:**

| Datei | Verantwortung |
|---|---|
| `backend/app/services/notifications/plugin_events.py` | `PluginEventRegistry` (lookup namespaced ID → Entry), `emit_plugin_event()` (Cooldown + Ziel) |
| `backend/app/plugins/installed/steam_gaming/poller.py` | `SteamSessionPoller`: Flankenerkennung Start/Ende, Baseline-Tick |
| `backend/tests/services/test_plugin_notification_events.py` | Spec-Validierung, Registry, Emit-Fallback, Cooldown, Kategorie |
| `backend/tests/plugins/test_steam_gaming_poller.py` | Flankenlogik gegen injizierten Detektor |

**Geändert:**

| Datei | Änderung |
|---|---|
| `backend/app/plugins/base.py` | `PluginEventSpec`; `get_notification_events()` |
| `backend/app/services/notifications/events.py` | `emit()` fragt die Registry als Fallback zu `EVENT_CONFIGS` |
| `backend/app/plugins/installed/steam_gaming/__init__.py` | `get_notification_events()`, `get_background_tasks()`, neue Übersetzungen |
| `backend/tests/plugins/test_steam_gaming_plugin.py` | Test für die neuen Deklarationen |
| `backend/app/plugins/CLAUDE.md` | Notification-Event-Extension-Point dokumentieren |

---

## Task 1: `PluginEventSpec` + PluginBase-Hook

**Files:**
- Modify: `backend/app/plugins/base.py` (`PluginEventSpec` neben `StatusPillSpec` bei Z. 142; `get_notification_events()` neben den Pill-Hooks)
- Test: `backend/tests/services/test_plugin_notification_events.py` (neu)

**Interfaces:**
- Consumes: nichts.
- Produces:
```python
class PluginEventSpec(BaseModel):
    id: str                       # pattern ^[a-z0-9_]+$
    notification_type: Literal["info","warning","critical"] = "info"
    priority: int = 0             # ge=0, le=3
    title_template: str
    message_template: str
    action_url: Optional[str] = None
    cooldown_seconds: int = 0
    default_target: Literal["admins","all_users"] = "admins"

PluginBase.get_notification_events() -> List[PluginEventSpec]   # default []
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_plugin_notification_events.py`:

```python
"""Plugin notification events: the extension point (Teilprojekt 3/4)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.plugins.base import (
    PluginBase,
    PluginEventSpec,
    PluginMetadata,
)


class TestPluginEventSpec:
    def test_minimal_spec(self):
        spec = PluginEventSpec(
            id="session_started",
            title_template="Started: {game}",
            message_template="Game {game} started.",
        )
        assert spec.notification_type == "info"
        assert spec.priority == 0
        assert spec.cooldown_seconds == 0
        assert spec.default_target == "admins"

    @pytest.mark.parametrize("bad_id", ["Session", "session-started", "session.started", "../x", "", "a b"])
    def test_rejects_ids_outside_the_namespace(self, bad_id):
        with pytest.raises(ValidationError):
            PluginEventSpec(id=bad_id, title_template="t", message_template="m")

    def test_priority_is_bounded(self):
        with pytest.raises(ValidationError):
            PluginEventSpec(id="x", title_template="t", message_template="m", priority=4)

    def test_has_no_category_field(self):
        """The category is the routing key - the core sets it to the plugin
        name, a plugin must not choose it (a plugin declaring category='backup'
        would reach every backup-routed user)."""
        assert "category" not in PluginEventSpec.model_fields


class _BarePlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bare", display_name="Bare", version="1.0.0",
            description="", author="test",
        )


class TestPluginBaseDefault:
    def test_no_events_by_default(self):
        assert _BarePlugin().get_notification_events() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/services/test_plugin_notification_events.py -q --no-cov`
Expected: FAIL — `ImportError: cannot import name 'PluginEventSpec'`

- [ ] **Step 3: Add the schema**

In `backend/app/plugins/base.py`, direkt **nach** `class StatusPillSpec` (endet bei Z. 118 vor `BackgroundTaskSpec`) einfügen:

```python
class PluginEventSpec(BaseModel):
    """A notification event a plugin contributes.

    The public event id is namespaced by the core as
    ``plugin:<plugin_name>:<id>`` - the plugin only picks the suffix. The
    category is deliberately NOT here: it is the delivery routing key, so the
    core derives it from the plugin name. A plugin free to set category="backup"
    would reach every user an admin routed for backups.
    """

    id: str = Field(
        pattern=r"^[a-z0-9_]+$",
        description="Plugin-local suffix, e.g. 'session_started'",
    )
    notification_type: Literal["info", "warning", "critical"] = "info"
    priority: int = Field(default=0, ge=0, le=3)
    title_template: str = Field(description="Server-rendered, one language")
    message_template: str = Field(description="Server-rendered, one language")
    action_url: Optional[str] = None
    cooldown_seconds: int = Field(
        default=0, ge=0,
        description="Suppress a repeat of the same event+entity within this window",
    )
    default_target: Literal["admins", "all_users"] = "admins"
```

`Literal` und `Optional` sind am Dateikopf bereits importiert (für `PanelType`/`StatusPillSpec`).

- [ ] **Step 4: Add the PluginBase hook**

In `backend/app/plugins/base.py`, direkt nach `collect_status_pill` (die letzte Pill-Methode) einfügen:

```python
    def get_notification_events(self) -> List["PluginEventSpec"]:
        """Notification events this plugin contributes. Default: none.

        The core namespaces each id to ``plugin:<name>:<suffix>``, derives the
        category from the plugin name, and owns delivery. The plugin emits an
        event via ``services.notifications.plugin_events.emit_plugin_event``.
        """
        return []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/services/test_plugin_notification_events.py -q --no-cov`
Expected: PASS (9 Tests — die 6 Parametrize-Fälle zählen einzeln)

- [ ] **Step 6: Lint + commit**

```bash
cd backend ; python -m ruff check app/plugins/base.py tests/services/test_plugin_notification_events.py
git add backend/app/plugins/base.py backend/tests/services/test_plugin_notification_events.py
git commit -m "feat(plugins): declare notification events on PluginBase"
```

---

## Task 2: `PluginEventRegistry`

**Files:**
- Create: `backend/app/services/notifications/plugin_events.py`
- Test: `backend/tests/services/test_plugin_notification_events.py` (anhängen)

**Interfaces:**
- Consumes: `PluginEventSpec` (Task 1); `PluginManager.iter_enabled_plugins()` (vorhanden, liefert `(name, plugin)`-Paare); `EventConfig` aus `services/notifications/events.py`.
- Produces:
```python
@dataclass
class PluginEventEntry:
    config: EventConfig          # priority, category=plugin_name, notification_type, templates, action_url
    cooldown_seconds: int
    default_target: str          # "admins" | "all_users"

def lookup_plugin_event(public_id: str) -> Optional[PluginEventEntry]
```

- [ ] **Step 1: Write the failing test**

An `backend/tests/services/test_plugin_notification_events.py` anhängen:

```python
from unittest.mock import MagicMock, patch


def _plugin_with_events(*specs):
    plugin = MagicMock()
    plugin.get_notification_events.return_value = list(specs)
    return plugin


class TestRegistryLookup:
    def _spec(self, suffix="session_started"):
        return PluginEventSpec(
            id=suffix,
            notification_type="info",
            priority=1,
            title_template="Started: {game}",
            message_template="Game {game} started.",
            action_url="/plugins",
            cooldown_seconds=60,
            default_target="admins",
        )

    def test_resolves_a_namespaced_id_to_an_entry(self):
        from app.services.notifications.plugin_events import lookup_plugin_event

        plugin = _plugin_with_events(self._spec())
        with patch(
            "app.services.notifications.plugin_events._iter_enabled_plugins",
            return_value=[("steam_gaming", plugin)],
        ):
            entry = lookup_plugin_event("plugin:steam_gaming:session_started")

        assert entry is not None
        assert entry.config.category == "steam_gaming"       # core-derived
        assert entry.config.priority == 1
        assert entry.config.notification_type == "info"
        assert entry.config.title_template == "Started: {game}"
        assert entry.cooldown_seconds == 60
        assert entry.default_target == "admins"

    def test_unknown_plugin_is_none(self):
        from app.services.notifications.plugin_events import lookup_plugin_event

        with patch(
            "app.services.notifications.plugin_events._iter_enabled_plugins",
            return_value=[],
        ):
            assert lookup_plugin_event("plugin:nope:session_started") is None

    def test_unknown_suffix_is_none(self):
        from app.services.notifications.plugin_events import lookup_plugin_event

        plugin = _plugin_with_events(self._spec("session_started"))
        with patch(
            "app.services.notifications.plugin_events._iter_enabled_plugins",
            return_value=[("steam_gaming", plugin)],
        ):
            assert lookup_plugin_event("plugin:steam_gaming:other") is None

    def test_non_plugin_id_is_none(self):
        """A core id like 'raid.degraded' must not be looked up here."""
        from app.services.notifications.plugin_events import lookup_plugin_event

        assert lookup_plugin_event("raid.degraded") is None
        assert lookup_plugin_event("plugin:only_two") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/services/test_plugin_notification_events.py -q --no-cov -k Registry`
Expected: FAIL — `ModuleNotFoundError: ...plugin_events`

- [ ] **Step 3: Implement the registry**

Create `backend/app/services/notifications/plugin_events.py`:

```python
"""Plugin-contributed notification events (Teilprojekt 3/4).

Plugins declare events via ``PluginBase.get_notification_events()``. This
module turns a namespaced public id (``plugin:<name>:<suffix>``) back into a
core ``EventConfig`` so ``EventEmitter.emit()`` can deliver it exactly like a
built-in event, and provides ``emit_plugin_event()`` for a plugin to fire one.

The category is derived from the plugin name here, never taken from the plugin:
it is the delivery routing key (see services/notification_routing), so a
plugin-chosen category would be a reach-widening hole.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

from app.services.notifications.events import (
    EventConfig,
    _check_cooldown,
    _set_cooldown,
    get_event_emitter,
)

logger = logging.getLogger(__name__)

_PREFIX = "plugin:"


def _iter_enabled_plugins() -> Iterator[Tuple[str, object]]:
    """Indirection so tests can inject plugins without the manager singleton."""
    from app.plugins.manager import PluginManager

    return iter(PluginManager.get_instance().iter_enabled_plugins())


@dataclass
class PluginEventEntry:
    config: EventConfig
    cooldown_seconds: int
    default_target: str


def _parse(public_id: str) -> Optional[Tuple[str, str]]:
    """``plugin:<name>:<suffix>`` -> ``(name, suffix)``; None if not that shape."""
    if not public_id.startswith(_PREFIX):
        return None
    rest = public_id[len(_PREFIX):]
    name, sep, suffix = rest.partition(":")
    if not sep or not name or not suffix:
        return None
    return name, suffix


def lookup_plugin_event(public_id: str) -> Optional[PluginEventEntry]:
    """Resolve a namespaced plugin event id to a deliverable entry, or None."""
    parsed = _parse(public_id)
    if parsed is None:
        return None
    plugin_name, suffix = parsed

    for name, plugin in _iter_enabled_plugins():
        if name != plugin_name:
            continue
        for spec in plugin.get_notification_events():
            if spec.id != suffix:
                continue
            config = EventConfig(
                priority=spec.priority,
                category=plugin_name,          # core-derived, never plugin-chosen
                notification_type=spec.notification_type,
                title_template=spec.title_template,
                message_template=spec.message_template,
                action_url=spec.action_url,
            )
            return PluginEventEntry(
                config=config,
                cooldown_seconds=spec.cooldown_seconds,
                default_target=spec.default_target,
            )
    return None
```

(`emit_plugin_event` folgt in Task 3 — dieselbe Datei.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/services/test_plugin_notification_events.py -q --no-cov -k Registry`
Expected: PASS (4 Tests)

- [ ] **Step 5: Lint + commit**

```bash
cd backend ; python -m ruff check app/services/notifications/plugin_events.py tests/services/test_plugin_notification_events.py
git add backend/app/services/notifications/plugin_events.py backend/tests/services/test_plugin_notification_events.py
git commit -m "feat(notifications): registry resolving plugin event ids to configs"
```

---

## Task 3: Emit-Fallback + `emit_plugin_event`

**Files:**
- Modify: `backend/app/services/notifications/events.py` (`emit()` bei Z. 515)
- Modify: `backend/app/services/notifications/plugin_events.py` (anhängen)
- Test: `backend/tests/services/test_plugin_notification_events.py` (anhängen)

**Interfaces:**
- Consumes: `lookup_plugin_event()` (Task 2); `EventEmitter.emit_for_admins()`/`emit_for_all_users()`, `_check_cooldown`/`_set_cooldown` (vorhanden).
- Produces:
```python
async def emit_plugin_event(plugin_name: str, event_id: str, entity_id: str = "", **kwargs) -> None
```

- [ ] **Step 1: Write the failing test**

An `backend/tests/services/test_plugin_notification_events.py` anhängen:

```python
from unittest.mock import AsyncMock


class TestEmitFallback:
    async def test_emit_uses_the_registry_when_the_id_is_not_a_core_event(self):
        """emit() already does EVENT_CONFIGS.get(); the plugin path is the
        registry fallback. Persisted notification carries the derived category."""
        from app.services.notifications.events import EventEmitter
        from app.plugins.base import PluginEventSpec
        from app.services.notifications import plugin_events

        spec = PluginEventSpec(
            id="session_started", priority=1,
            title_template="Started: {game}",
            message_template="Game {game} started.",
        )
        plugin = _plugin_with_events(spec)

        emitter = EventEmitter()
        created = {}

        class _Svc:
            async def create(self, **kw):
                created.update(kw)

        emitter.set_db_session_factory(lambda: MagicMock(close=lambda: None))

        with patch.object(plugin_events, "_iter_enabled_plugins",
                          return_value=[("steam_gaming", plugin)]), \
             patch("app.services.notifications.service.get_notification_service",
                   return_value=_Svc()):
            await emitter.emit("plugin:steam_gaming:session_started", game="Metro")

        assert created["category"] == "steam_gaming"
        assert created["title"] == "Started: Metro"
        assert created["priority"] == 1

    async def test_core_event_still_uses_event_configs(self):
        """Regression: the open path must not change built-in delivery."""
        from app.services.notifications.events import EventEmitter, EVENT_CONFIGS

        emitter = EventEmitter()
        created = {}

        class _Svc:
            async def create(self, **kw):
                created.update(kw)

        emitter.set_db_session_factory(lambda: MagicMock(close=lambda: None))
        with patch("app.services.notifications.service.get_notification_service",
                   return_value=_Svc()):
            await emitter.emit("raid.degraded", array_name="md0", details="")

        assert created["category"] == "raid"   # from EVENT_CONFIGS, not the registry


class TestEmitPluginEvent:
    def _entry(self, target="admins", cooldown=60):
        from app.services.notifications.plugin_events import PluginEventEntry
        from app.services.notifications.events import EventConfig
        return PluginEventEntry(
            config=EventConfig(priority=0, category="steam_gaming",
                               notification_type="info",
                               title_template="Started: {game}",
                               message_template="m", action_url=None),
            cooldown_seconds=cooldown, default_target=target,
        )

    async def test_admins_target_calls_emit_for_admins_with_namespaced_id(self):
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=self._entry()), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", game="Metro")

        emitter.emit_for_admins.assert_awaited_once()
        args, kwargs = emitter.emit_for_admins.await_args
        assert args[0] == "plugin:steam_gaming:session_started"
        assert kwargs["game"] == "Metro"

    async def test_unknown_event_is_a_warning_not_a_crash(self):
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=None), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "nope")

        emitter.emit_for_admins.assert_not_awaited()

    async def test_the_helper_enforces_the_cooldown(self):
        """The async emit path has no cooldown machinery (only emit_sync does);
        the helper must enforce it itself, or a declared cooldown is dead."""
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=self._entry(cooldown=60)), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="1449560", game="Metro")
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="1449560", game="Metro")

        assert emitter.emit_for_admins.await_count == 1

    async def test_different_entities_are_not_cooled_down_together(self):
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=self._entry(cooldown=60)), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="1", game="A")
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="2", game="B")

        assert emitter.emit_for_admins.await_count == 2
```

Ergänze eine Autouse-Fixture am Anfang der Datei, die den Cooldown-Cache leert (er ist Modulzustand):

```python
@pytest.fixture(autouse=True)
def _clear_cooldown():
    from app.services.notifications import events as ev
    ev._cooldown_cache.clear()
    yield
    ev._cooldown_cache.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/services/test_plugin_notification_events.py -q --no-cov -k "EmitFallback or EmitPluginEvent"`
Expected: FAIL — `emit` kennt die Plugin-ID nicht / `emit_plugin_event` fehlt

- [ ] **Step 3: Add the registry fallback to emit()**

In `backend/app/services/notifications/events.py`, `emit()` (Z. 514-518) ändern:

```python
        # Get event configuration (built-in first, then plugin registry)
        config = EVENT_CONFIGS.get(event_type)
        if config is None:
            from app.services.notifications.plugin_events import lookup_plugin_event

            entry = lookup_plugin_event(event_type)
            config = entry.config if entry is not None else None
        if not config:
            logger.warning(f"Unknown event type: {event_type}")
            return
```

Der Import ist lokal in der Funktion, um einen Zyklus zu vermeiden (`plugin_events` importiert aus `events`).

- [ ] **Step 4: Add emit_plugin_event to plugin_events.py**

Anhängen an `backend/app/services/notifications/plugin_events.py`:

```python
async def emit_plugin_event(
    plugin_name: str, event_id: str, entity_id: str = "", **kwargs
) -> None:
    """Fire a plugin-declared notification event.

    Namespaces the id, resolves it against the registry, enforces the declared
    cooldown (the async emit() path carries none - only emit_sync does), and
    delivers to the declared target. Never raises: a plugin firing an event
    must not take down its caller.
    """
    public_id = f"{_PREFIX}{plugin_name}:{event_id}"
    entry = lookup_plugin_event(public_id)
    if entry is None:
        logger.warning("emit_plugin_event: unknown event %s", public_id)
        return

    if _check_cooldown(public_id, entity_id):
        return

    emitter = get_event_emitter()
    try:
        if entry.default_target == "all_users":
            # emit_for_all_users needs a session to enumerate users; the async
            # emit() each user triggers opens its own via the factory. Reaching
            # the factory here is fine - same package as EventEmitter.
            db = emitter._db_session_factory()
            try:
                await emitter.emit_for_all_users(public_id, db, **kwargs)
            finally:
                db.close()
        else:
            await emitter.emit_for_admins(public_id, **kwargs)
    except Exception:  # broad on purpose: an emit failure must not crash the poller
        logger.warning("emit_plugin_event %s failed", public_id, exc_info=True)
        return

    _set_cooldown(public_id, entity_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/services/test_plugin_notification_events.py -q --no-cov`
Expected: PASS (alle bisherigen + die neuen)

- [ ] **Step 6: Run the notification suite for regressions**

Run: `cd backend ; python -m pytest tests/services -q --no-cov -k notification`
Expected: PASS, keine neuen Fehler (der Emit-Fallback darf Core-Events nicht verändern).

- [ ] **Step 7: Lint + commit**

```bash
cd backend ; python -m ruff check app/services/notifications/events.py app/services/notifications/plugin_events.py tests/services/test_plugin_notification_events.py
git add backend/app/services/notifications/events.py backend/app/services/notifications/plugin_events.py backend/tests/services/test_plugin_notification_events.py
git commit -m "feat(notifications): deliver plugin events through the existing emitter"
```

---

## Task 4: `SteamSessionPoller`

**Files:**
- Create: `backend/app/plugins/installed/steam_gaming/poller.py`
- Test: `backend/tests/plugins/test_steam_gaming_poller.py` (neu)

**Interfaces:**
- Consumes: `detect_running_app_id()`, `resolve_name()` (vorhanden); `emit_plugin_event()` (Task 3).
- Produces:
```python
class SteamSessionPoller:
    def __init__(self, detect=..., resolve=..., emit=...) -> None
    async def tick(self) -> None
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_steam_gaming_poller.py`:

```python
"""Steam session poller: play/not-play edge detection (Teilprojekt 3/4)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.plugins.installed.steam_gaming.poller import SteamSessionPoller


def _poller(sequence):
    """A poller whose detector yields the given app_ids across ticks."""
    calls = iter(sequence)
    detect = MagicMock(side_effect=lambda *a, **k: next(calls))
    resolve = MagicMock(side_effect=lambda app_id: f"Game {app_id}")
    emit = AsyncMock()
    return SteamSessionPoller(detect=detect, resolve=resolve, emit=emit), emit


class TestEdgeDetection:
    async def test_first_tick_only_establishes_a_baseline(self):
        """A game already running at startup must NOT fire 'started' - that
        would false-alarm after every backend restart."""
        poller, emit = _poller(["1449560"])
        await poller.tick()
        emit.assert_not_awaited()

    async def test_none_to_game_is_a_start(self):
        poller, emit = _poller([None, "1449560"])
        await poller.tick()   # baseline: None
        await poller.tick()   # None -> game
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", "session_started")
        assert kwargs["entity_id"] == "1449560"
        assert kwargs["game"] == "Game 1449560"

    async def test_game_to_none_is_an_end(self):
        poller, emit = _poller(["1449560", None])
        await poller.tick()   # baseline: game
        await poller.tick()   # game -> None
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", "session_ended")
        assert kwargs["entity_id"] == "1449560"
        assert kwargs["game"] == "Game 1449560"

    async def test_same_game_across_ticks_is_no_event(self):
        poller, emit = _poller([None, "1449560", "1449560"])
        await poller.tick()
        await poller.tick()   # start
        emit.reset_mock()
        await poller.tick()   # same game
        emit.assert_not_awaited()

    async def test_direct_switch_fires_nothing_but_tracks_the_new_game(self):
        """X -> Y fires no event, but the state must follow to Y so a later
        Y -> None correctly ends on Y."""
        poller, emit = _poller([None, "111", "222", None])
        await poller.tick()   # baseline None
        await poller.tick()   # None -> 111 (start)
        emit.reset_mock()
        await poller.tick()   # 111 -> 222: no event
        emit.assert_not_awaited()
        await poller.tick()   # 222 -> None: end, on 222
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", "session_ended")
        assert kwargs["entity_id"] == "222"

    async def test_unresolved_name_falls_back_to_the_app_id(self):
        poller, emit = _poller([None, "999"])
        poller._resolve = MagicMock(return_value=None)
        await poller.tick()
        await poller.tick()
        assert emit.await_args.kwargs["game"] == "999"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_poller.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: ...steam_gaming.poller`

- [ ] **Step 3: Implement the poller**

Create `backend/app/plugins/installed/steam_gaming/poller.py`:

```python
"""Steam session poller: detect play/not-play edges and emit notifications.

Runs as a plugin background task, which thanks to #448 executes primary-only -
so exactly one instance polls, and its last-seen state can live in the object
(no cross-worker sharing). The first tick only establishes a baseline: a game
already running when the backend starts must not be reported as 'started', or
every restart would false-alarm mid-session.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name
from app.services.notifications.plugin_events import emit_plugin_event

_PLUGIN = "steam_gaming"


class SteamSessionPoller:
    def __init__(
        self,
        detect: Callable[[], Optional[str]] = detect_running_app_id,
        resolve: Callable[[str], Optional[str]] = resolve_name,
        emit=emit_plugin_event,
    ) -> None:
        self._detect = detect
        self._resolve = resolve
        self._emit = emit
        self._initialized = False
        self._last_app_id: Optional[str] = None

    async def tick(self) -> None:
        # Blocking /proc + manifest reads off the event loop, same convention
        # as the menu action and the pill collector.
        app_id = await asyncio.to_thread(self._detect)

        if not self._initialized:
            self._last_app_id = app_id
            self._initialized = True
            return

        prev = self._last_app_id
        self._last_app_id = app_id

        if prev is None and app_id is not None:
            await self._fire("session_started", app_id)
        elif prev is not None and app_id is None:
            await self._fire("session_ended", prev)
        # prev == app_id, or a direct X->Y switch: no event; state already moved.

    async def _fire(self, event_id: str, app_id: str) -> None:
        name = await asyncio.to_thread(self._resolve, app_id) or app_id
        await self._emit(_PLUGIN, event_id, entity_id=app_id, game=name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_poller.py -q --no-cov`
Expected: PASS (6 Tests)

- [ ] **Step 5: Prove the baseline test discriminates**

Entferne testweise den `if not self._initialized`-Block, führe `python -m pytest tests/plugins/test_steam_gaming_poller.py -q --no-cov -k baseline` aus — der Test **muss** fehlschlagen (ein Startup mit laufendem Spiel würde „started" feuern). Danach zurückbauen.

- [ ] **Step 6: Lint + commit**

```bash
cd backend ; python -m ruff check app/plugins/installed/steam_gaming/poller.py tests/plugins/test_steam_gaming_poller.py
git add backend/app/plugins/installed/steam_gaming/poller.py backend/tests/plugins/test_steam_gaming_poller.py
git commit -m "feat(steam-gaming): session start/end edge poller"
```

---

## Task 5: Steam-Plugin verdrahten

**Files:**
- Modify: `backend/app/plugins/installed/steam_gaming/__init__.py`
- Test: `backend/tests/plugins/test_steam_gaming_plugin.py` (anhängen)

**Interfaces:**
- Consumes: `PluginEventSpec` (Task 1); `BackgroundTaskSpec` (vorhanden); `SteamSessionPoller` (Task 4).
- Produces: `SteamGamingPlugin.get_notification_events()`, `.get_background_tasks()`.

- [ ] **Step 1: Write the failing test**

An `backend/tests/plugins/test_steam_gaming_plugin.py` anhängen (die Datei importiert `SteamGamingPlugin` bereits):

```python
class TestNotificationEvents:
    def test_declares_start_and_end(self):
        events = SteamGamingPlugin().get_notification_events()
        assert {e.id for e in events} == {"session_started", "session_ended"}

    def test_events_carry_a_cooldown_and_admin_default(self):
        for e in SteamGamingPlugin().get_notification_events():
            assert e.cooldown_seconds == 60
            assert e.default_target == "admins"
            assert "{game}" in e.title_template or "{game}" in e.message_template


class TestBackgroundTask:
    def test_declares_the_session_poller(self):
        specs = SteamGamingPlugin().get_background_tasks()
        assert len(specs) == 1
        spec = specs[0]
        assert spec.interval_seconds == 30
        # run_on_startup True is fine: the poller's first tick is a baseline.
        assert callable(spec.func)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_plugin.py -q --no-cov -k "NotificationEvents or BackgroundTask"`
Expected: FAIL — die Methoden liefern noch die Defaults (`[]`)

- [ ] **Step 3: Wire the plugin**

In `backend/app/plugins/installed/steam_gaming/__init__.py`:

Imports ergänzen:

```python
from app.plugins.base import (
    BackgroundTaskSpec,
    MenuActionResult,
    PluginBase,
    PluginEventSpec,
    PluginMenuItem,
    PluginMetadata,
    PluginUIManifest,
    StatusPillSpec,
)
from app.plugins.installed.steam_gaming.poller import SteamSessionPoller
```

Konstanten neben `_PILL_ID`/`_MENU_ACTION_ID`:

```python
_EVENT_STARTED = "session_started"
_EVENT_ENDED = "session_ended"
_POLL_INTERVAL_SECONDS = 30.0
```

Methoden in der Klasse ergänzen (nach `run_menu_action`):

```python
    def get_notification_events(self) -> List[PluginEventSpec]:
        return [
            PluginEventSpec(
                id=_EVENT_STARTED,
                notification_type="info",
                priority=0,
                title_template="Gaming-Session gestartet: {game}",
                message_template="Auf BaluNode läuft jetzt {game}.",
                action_url="/plugins",
                cooldown_seconds=60,
                default_target="admins",
            ),
            PluginEventSpec(
                id=_EVENT_ENDED,
                notification_type="info",
                priority=0,
                title_template="Gaming-Session beendet",
                message_template="{game} wurde beendet.",
                action_url="/plugins",
                cooldown_seconds=60,
                default_target="admins",
            ),
        ]

    def get_background_tasks(self) -> List[BackgroundTaskSpec]:
        poller = SteamSessionPoller()
        return [BackgroundTaskSpec(
            name="session_poller",
            func=poller.tick,
            interval_seconds=_POLL_INTERVAL_SECONDS,
        )]
```

Hinweis: `List` ist am Dateikopf bereits importiert. `BackgroundTaskSpec` ist ein `@dataclass` mit Feldern `name`, `func`, `interval_seconds`, `run_on_startup=True` — der Poller-Zustand lebt in der `SteamSessionPoller`-Instanz, die die Closure `poller.tick` hält.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_plugin.py -q --no-cov`
Expected: PASS (bestehende + 3 neue)

- [ ] **Step 5: Run the plugin suite for regressions**

Run: `cd backend ; python -m pytest tests/plugins -q --no-cov`
Expected: PASS, keine neuen Fehler.

- [ ] **Step 6: Lint + commit**

```bash
cd backend ; python -m ruff check app/plugins/installed/steam_gaming/__init__.py tests/plugins/test_steam_gaming_plugin.py
git add backend/app/plugins/installed/steam_gaming/__init__.py backend/tests/plugins/test_steam_gaming_plugin.py
git commit -m "feat(steam-gaming): contribute session notifications and the poller"
```

---

## Task 6: Doku, Gates und Smoketest

**Files:**
- Modify: `backend/app/plugins/CLAUDE.md`

**Interfaces:**
- Consumes: alles Vorige. Produces: nichts.

- [ ] **Step 1: Document the extension point**

In `backend/app/plugins/CLAUDE.md`, in „Creating a Plugin" nach dem Menü-Action-Punkt als weiteren Punkt:

```markdown
8. Override `get_notification_events()` to contribute notification events, and
   `get_background_tasks()` if something needs to emit them on an interval. Each
   `PluginEventSpec` picks only a local `id` (`^[a-z0-9_]+$`); the core
   namespaces it to `plugin:<name>:<suffix>`, **derives the category from the
   plugin name** (the category is the delivery routing key — a plugin-chosen one
   would reach users routed for that category), and delivers through the
   existing machine (persistence, routing, push, WebSocket). Fire an event with
   `services.notifications.plugin_events.emit_plugin_event(plugin_name, event_id,
   entity_id="", **kwargs)`; it enforces the declared `cooldown_seconds` itself
   (the async emit path has none) and delivers to `default_target` (`admins` by
   default — a plugin cannot widen its own reach). Texts are server-rendered in
   one language (like the core events), so they are plain templates, not
   `resolvePluginString` keys. Background tasks run **primary-only** (#448), so a
   poller needs no cross-worker guard.
```

- [ ] **Step 2: Run the full backend gates**

```bash
cd backend
python -m pytest tests/plugins tests/services/test_plugin_notification_events.py -q --no-cov
python -m pytest tests/services -q --no-cov -k notification
python -m ruff check app tests
```
Expected: alles grün. (Bekannt und **nicht** von dieser Arbeit: `tests/test_desktop_backend.py` hat 3 Windows-only-Fehler wegen `os.getuid()`.)

- [ ] **Step 3: Frontend unberührt — nur gegenprüfen**

```bash
cd client ; npx vitest run src/__tests__/contexts src/__tests__/components/NotificationCenter*
```
Expected: PASS bzw. „no test files" für den zweiten Glob — diese Arbeit ändert kein Frontend; der Lauf belegt nur, dass die Notification-UI unberührt ist.

- [ ] **Step 4: Manueller Smoketest auf BaluNode (durch den Maintainer, nicht dispatchen)**

Nach dem Deploy, als Admin:

1. `steam_gaming` aktiviert (falls nicht), Backend nach dem Enable neu gestartet (damit der Poller auf dem Primary läuft).
2. Ein Steam-Spiel **starten** → binnen ~30 s eine Notification „Gaming-Session gestartet: <Spiel>" in App/Web.
3. Das Spiel **beenden** → binnen ~30 s „Gaming-Session beendet".
4. Als Nicht-Admin (zweiter Browser) → **keine** dieser Notifications sichtbar.
5. `sudo journalctl -u baluhost-backend -n 80 | grep -i "Event emitted"` → die zwei Emits tauchen auf, nur auf dem Primary.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/CLAUDE.md
git commit -m "docs(plugins): document the notification-event extension point"
```

---

## Self-Review

**Spec-Abdeckung:**

| Spec-Anforderung | Task |
|---|---|
| `PluginEventSpec`, `get_notification_events()` | 1 |
| Kein `category`-Feld (Core leitet aus Plugin-Namen ab) | 1 (Test), 2 (Ableitung) |
| ID-Namespace `plugin:<name>:<suffix>` | 2 |
| Registry aus aktivierten Plugins (`iter_enabled_plugins`) | 2 |
| `emit()` Registry-Fallback zu `EVENT_CONFIGS` | 3 |
| Core-Events unverändert (Regression) | 3 (Test) |
| `emit_plugin_event()` erzwingt Cooldown selbst | 3 (Test + Code) |
| `default_target` serverseitig; admins/all_users | 3 |
| Poller Flanken Start/Ende, Baseline-Tick | 4 |
| Direkter Wechsel X→Y feuert nichts, Zustand nachgezogen | 4 (Test) |
| primary-only ohne neuen Mechanismus | 5 (`get_background_tasks`) + Doku |
| Dev-Modus: kein `/proc` → nie ein Event | 4 (Detektor liefert None → nie Flanke) |
| Cooldown 60 s, entity_id = app_id | 4 (`_fire`) + 5 (Spec) |
| Poll-Intervall 30 s | 5 |
| Offener Messpunkt (echte Flanke → echte Notification) | 6, Step 4 |

**Baseline-Tick** ist eine Verfeinerung der Spec (die nur „Flanke Start/Ende" fordert): ohne ihn gäbe es nach jedem Restart bei laufendem Spiel einen Fehlalarm. In Task 4 implementiert und mit einem diskriminierenden Test (Step 5) gepinnt.

**Platzhalter-Scan:** keine TBD/TODO; jeder Code-Schritt enthält vollständigen Code, jeder Test-Schritt den vollständigen Test.

**Typ-Konsistenz:** `PluginEventSpec` (Felder id/notification_type/priority/title_template/message_template/action_url/cooldown_seconds/default_target) identisch in Task 1, 3, 5. `PluginEventEntry(config, cooldown_seconds, default_target)` identisch in Task 2, 3. `emit_plugin_event(plugin_name, event_id, entity_id="", **kwargs)` identisch in Task 3, 4, 5. `EventConfig`-Felder (priority, category, notification_type, title_template, message_template, action_url) stimmen mit dem Bestand in `events.py:131` überein.

**Bewusst nicht enthalten:** kein per-Nutzer-Kategorie-Toggle für Plugin-Events (TP4), keine Session-Dauer, kein Spielwechsel-Event (#462), kein `EventType`-Enum-Umbau, keine Frontend-Änderung.
