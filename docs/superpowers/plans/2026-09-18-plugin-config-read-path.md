# Plugin-Config: ein Lesepfad statt keiner (#522) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gespeicherte Plugin-Konfiguration (`InstalledPlugin.config`) erreicht jedes gebündelte Plugin über genau einen Lesepfad, `PluginBase.get_config(db)` — validiert, mit Defaults aufgefüllt, auf allen Workern gleich.

**Architecture:** Pull statt Push. Die Config wird bei Bedarf aus der Datenbank gelesen (der einzige zwischen den 4 Uvicorn-Workern und dem Monitoring-Worker geteilte Zustand), statt von der `PUT`-Route an die Instanz des einen antwortenden Workers zugestellt zu werden. Die Logik liegt in einem neuen Modul `app/plugins/config.py`; `PluginBase.get_config()` delegiert dorthin. Alle heutigen Direktleser (`GET /config`-Route, Tapo-Dashboard, SmartDevice-Poller) werden umgestellt, `optical_drive` wird erstmals angebunden.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (sync Session), Pydantic v2, pytest.

**Spec:** Issue #522 und die Nachmessung im Kommentar https://github.com/Xveyn/BaluHost/issues/522#issuecomment-5733697084 — kein separates Design-Dokument.

## Global Constraints

- Kein Push-Hook (`on_config_change`) aus der Route: er würde nur den antwortenden Worker erreichen (Muster #448/#459/#465).
- Kein zweiter Lesepfad: nach diesem Plan liest **kein** Code außerhalb von `app/plugins/config.py` und `plugin_service.py` mehr `InstalledPlugin.config` direkt.
- `get_config()` wirft nie wegen kaputter gespeicherter Daten — ungültig/leer/fehlend ⇒ Defaults. DB-Fehler dürfen durchschlagen.
- Keine Config-Werte loggen (können Secrets enthalten, `.claude/rules/security-agent.md`): bei ungültiger Config nur Plugin-Name + Exception-Typ.
- Dateien ≤ 500 Zeilen (#301); Zeilen mit `wc -l` zählen, nicht mit `Measure-Object -Line`.
- Externe (sandboxed) Plugins sind **out of scope** — `get_plugin()` findet sie nicht, `PUT /config` bleibt dort 404.
- `optical_drive`: nur `auto_eject_after_operation` hat einen Konsumenten. Die übrigen vier Felder (`default_output_dir`, `default_burn_speed`, `scan_interval_seconds`, `max_concurrent_jobs`) werden **nicht** in diesem Plan angebunden.
- PowerShell 5.1: Befehle mit `;` bzw. `if ($?) { ... }` verketten, nie `&&`.

---

### Task 0: Branch anlegen

- [ ] **Step 1: main aktualisieren und abzweigen**

```powershell
git checkout main; if ($?) { git pull --ff-only origin main }; if ($?) { git checkout -b fix/plugin-config-read-path }
```

Expected: `Switched to a new branch 'fix/plugin-config-read-path'`. Der aktuelle Branch `fix/plugin-background-tasks-primary-gate` wird nicht angefasst.

---

### Task 1: `get_config()` — der eine Lesepfad

**Files:**
- Create: `backend/app/plugins/config.py`
- Modify: `backend/app/plugins/base.py` (Methode nach `validate_config`, ca. Zeile 453; Docstring von `get_config_schema` Zeile 293-302)
- Modify: `backend/app/plugins/CLAUDE.md` (Architektur-Baum + neuer Abschnitt)
- Test: `backend/tests/plugins/test_plugin_config.py` (neu)

**Interfaces:**
- Produces: `app.plugins.config.resolve_plugin_config(plugin: PluginBase, db: Session) -> Dict[str, Any]` und `PluginBase.get_config(self, db: Session) -> Dict[str, Any]`. Rückgabe ist immer ein neues `dict`; bei Plugins mit Schema enthält es **alle** Schema-Felder.

- [ ] **Step 1: Failing Tests schreiben**

`backend/tests/plugins/test_plugin_config.py`:

```python
"""PluginBase.get_config() - the one read path for stored plugin config (#522)."""
from typing import Any, Dict

from pydantic import BaseModel, Field

from app.plugins.base import PluginBase, PluginMetadata
from app.services import plugin_service


class _Cfg(BaseModel):
    interval: int = Field(default=10, ge=1)
    label: str = "default"


class _SchemaPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="cfg_plugin", version="1.0.0", display_name="Cfg",
            description="test", author="test",
        )

    def get_config_schema(self) -> type:
        return _Cfg

    def get_default_config(self) -> Dict[str, Any]:
        return _Cfg().model_dump()


class _NoSchemaPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="plain_plugin", version="1.0.0", display_name="Plain",
            description="test", author="test",
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {"a": 1}


def _store(db, name: str, config) -> None:
    plugin_service.update_config(db, name=name, validated_config=config)


def test_no_row_returns_defaults(db_session):
    assert _SchemaPlugin().get_config(db_session) == {"interval": 10, "label": "default"}


def test_stored_value_wins(db_session):
    _store(db_session, "cfg_plugin", {"interval": 5, "label": "mine"})
    assert _SchemaPlugin().get_config(db_session) == {"interval": 5, "label": "mine"}


def test_partial_row_is_filled_with_defaults(db_session):
    """A row written by an older plugin version lacks newer fields."""
    _store(db_session, "cfg_plugin", {"interval": 5})
    assert _SchemaPlugin().get_config(db_session) == {"interval": 5, "label": "default"}


def test_invalid_row_falls_back_to_defaults(db_session):
    _store(db_session, "cfg_plugin", {"interval": 0})  # violates ge=1
    assert _SchemaPlugin().get_config(db_session) == {"interval": 10, "label": "default"}


def test_empty_row_returns_defaults(db_session):
    _store(db_session, "cfg_plugin", {})
    assert _SchemaPlugin().get_config(db_session) == {"interval": 10, "label": "default"}


def test_json_string_row_is_parsed(db_session):
    """Tapo's former direct read tolerated a JSON string; keep that tolerance."""
    _store(db_session, "cfg_plugin", '{"interval": 7}')
    assert _SchemaPlugin().get_config(db_session) == {"interval": 7, "label": "default"}


def test_plugin_without_schema_returns_stored_dict(db_session):
    _store(db_session, "plain_plugin", {"a": 2, "b": 3})
    assert _NoSchemaPlugin().get_config(db_session) == {"a": 2, "b": 3}


def test_plugin_without_schema_and_row_returns_defaults(db_session):
    assert _NoSchemaPlugin().get_config(db_session) == {"a": 1}


def test_schema_without_default_override_gets_schema_defaults(db_session):
    class _Bare(_SchemaPlugin):
        def get_default_config(self) -> Dict[str, Any]:
            return {}

    assert _Bare().get_config(db_session) == {"interval": 10, "label": "default"}


def test_invalid_row_logs_name_not_values(db_session):
    # Patch the module logger directly: caplog depends on propagation to the
    # root logger, which the structured-logging setup may switch off.
    from unittest.mock import patch

    from app.plugins import config as config_mod

    _store(db_session, "cfg_plugin", {"interval": 0, "label": "s3cr3t"})
    with patch.object(config_mod.logger, "warning") as warn:
        _SchemaPlugin().get_config(db_session)

    rendered = warn.call_args.args[0] % warn.call_args.args[1:]
    assert "cfg_plugin" in rendered
    assert "s3cr3t" not in rendered
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend; python -m pytest tests/plugins/test_plugin_config.py -v`
Expected: alle FAIL — mit `AttributeError: ... has no attribute 'get_config'`, der Log-Test mit `ModuleNotFoundError: No module named 'app.plugins.config'`.

- [ ] **Step 3: `app/plugins/config.py` anlegen**

```python
"""The one read path for stored plugin configuration (#522).

``PUT /api/plugins/{name}/config`` writes ``InstalledPlugin.config``. Nothing
pushes that value into a running plugin instance, and nothing should: a push
from the route reaches only the Uvicorn worker that answered the request, while
three more workers and the monitoring worker keep their own instances. The
database is the only state they share, so plugins read it when they need it -
through ``PluginBase.get_config()``, which delegates here.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.plugins.base import PluginBase

logger = logging.getLogger(__name__)


def resolve_plugin_config(plugin: "PluginBase", db: "Session") -> Dict[str, Any]:
    """Return the plugin's effective configuration.

    Stored row, validated against ``get_config_schema()`` so missing fields get
    their defaults. A missing, empty, unparsable or invalid row yields
    ``get_default_config()`` - stored data never makes this raise. Database
    errors do propagate.
    """
    from app.services import plugin_service

    name = plugin.metadata.name
    record = plugin_service.get_installed_plugin(db, name)
    stored = record.config if record is not None else None

    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except ValueError:
            stored = None
    if not isinstance(stored, dict) or not stored:
        # Validate the defaults too: a plugin with a schema but no
        # get_default_config() override would otherwise get {}.
        stored = plugin.get_default_config()

    try:
        return dict(plugin.validate_config(dict(stored)))
    except (ValueError, TypeError) as exc:
        # Type only: pydantic's message would echo the stored values.
        logger.warning(
            "Stored config for plugin %s is invalid (%s); using defaults",
            name, type(exc).__name__,
        )
        return dict(plugin.get_default_config())
```

- [ ] **Step 4: `PluginBase.get_config()` in `base.py` ergänzen**

Direkt nach `validate_config` (vor `__repr__`) einfügen:

```python
    def get_config(self, db: "Session") -> Dict[str, Any]:
        """Return this plugin's effective, validated configuration.

        The only way a plugin should read what an admin saved via
        ``PUT /api/plugins/{name}/config``. Read it when you need it - there is
        no push on save, see ``app/plugins/config.py`` for why.
        """
        from app.plugins.config import resolve_plugin_config

        return resolve_plugin_config(self, db)
```

Und den Docstring von `get_config_schema` (Zeile 293-302) ersetzen:

```python
    def get_config_schema(self) -> Optional[type]:
        """Get the Pydantic model for plugin configuration.

        Override to provide a configuration schema. It drives the settings
        form, validates ``PUT /api/plugins/{name}/config`` and fills defaults
        in ``get_config()``.

        Returns:
            Pydantic BaseModel subclass or None
        """
        return None
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend; python -m pytest tests/plugins/test_plugin_config.py tests/plugins/test_plugins.py -v`
Expected: alle PASS.

- [ ] **Step 6: Doku in `backend/app/plugins/CLAUDE.md`**

Im Architektur-Baum nach der Zeile `├── base.py ...` einfügen:

```
├── config.py            # resolve_plugin_config() — the one read path for InstalledPlugin.config (#522)
```

Und nach dem Abschnitt `## Creating a Plugin` (vor `## SmartDevice Framework`) einfügen:

```markdown
## Plugin Configuration (#522)

`PUT /api/plugins/{name}/config` validates against `get_config_schema()` and
stores the result in `InstalledPlugin.config`. **Nothing is pushed into the
plugin on save**, deliberately: a hook called from the route would reach only
the worker that answered the request, not the other three nor the monitoring
worker's poller instances (same trap as #448/#459/#465).

A plugin reads its config with `self.get_config(db)` when it needs it. That is
the **only** read path (`app/plugins/config.py`): it validates the stored row,
fills fields missing from older rows with their defaults, and falls back to
`get_default_config()` on a missing, empty or invalid row. The `GET` route
serves the same value, so the settings form shows what the plugin actually uses.
**Do not read `InstalledPlugin.config` directly** — that is how `optical_drive`
ended up ignoring saved values while `tapo_smart_plug` honoured them.

External (sandboxed) plugins have no config channel at all: `get_plugin()`
only knows bundled plugins, so the route 404s for them, and the sandbox has no
DB access and no config scope.
```

- [ ] **Step 7: Zeilenzahl prüfen und committen**

```powershell
wc -l backend/app/plugins/base.py backend/app/plugins/config.py
git add backend/app/plugins/config.py backend/app/plugins/base.py backend/app/plugins/CLAUDE.md backend/tests/plugins/test_plugin_config.py
git commit -m "feat(plugins): PluginBase.get_config() als einziger Lesepfad fuer gespeicherte Config (#522)" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

Expected: `base.py` ≤ 500 Zeilen.

---

### Task 2: `GET /config` liefert die wirksame Config

**Files:**
- Modify: `backend/app/api/routes/plugins.py:616-617` (`get_plugin_config`)
- Test: `backend/tests/api/test_plugin_config_routes.py` (neu)

**Interfaces:**
- Consumes: `PluginBase.get_config(db)` aus Task 1.
- Produces: `GET /api/plugins/{name}/config` → `config` enthält alle Schema-Felder (wirksame Werte).

- [ ] **Step 1: Failing Test schreiben**

`backend/tests/api/test_plugin_config_routes.py`:

```python
"""GET /api/plugins/{name}/config serves the config the plugin actually uses (#522)."""
from typing import Any, Dict

import pytest
from pydantic import BaseModel, Field

from app.api.routes.plugins import get_plugin_manager
from app.main import app
from app.plugins.base import PluginBase, PluginMetadata
from app.services import plugin_service


class _Cfg(BaseModel):
    interval: int = Field(default=10, ge=1)
    label: str = "default"


class _SchemaPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="cfg_plugin", version="1.0.0", display_name="Cfg",
            description="test", author="test",
        )

    def get_config_schema(self) -> type:
        return _Cfg

    def get_default_config(self) -> Dict[str, Any]:
        return _Cfg().model_dump()


class _FakeManager:
    def __init__(self, plugin: PluginBase) -> None:
        self._plugin = plugin

    def get_plugin(self, name: str):
        return self._plugin if name == self._plugin.metadata.name else None


@pytest.fixture
def fake_manager():
    app.dependency_overrides[get_plugin_manager] = lambda: _FakeManager(_SchemaPlugin())
    yield
    app.dependency_overrides.pop(get_plugin_manager, None)


def test_get_fills_partial_row_with_defaults(client, admin_headers, db_session, fake_manager):
    plugin_service.update_config(db_session, name="cfg_plugin", validated_config={"interval": 5})

    r = client.get("/api/plugins/cfg_plugin/config", headers=admin_headers)

    assert r.status_code == 200
    assert r.json()["config"] == {"interval": 5, "label": "default"}


def test_get_invalid_row_shows_defaults(client, admin_headers, db_session, fake_manager):
    plugin_service.update_config(db_session, name="cfg_plugin", validated_config={"interval": 0})

    r = client.get("/api/plugins/cfg_plugin/config", headers=admin_headers)

    assert r.status_code == 200
    assert r.json()["config"] == {"interval": 10, "label": "default"}


def test_put_then_get_round_trips(client, admin_headers, fake_manager):
    r = client.put(
        "/api/plugins/cfg_plugin/config",
        json={"config": {"interval": 3, "label": "x"}},
        headers=admin_headers,
    )
    assert r.status_code == 200

    r = client.get("/api/plugins/cfg_plugin/config", headers=admin_headers)
    assert r.json()["config"] == {"interval": 3, "label": "x"}
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend; python -m pytest tests/api/test_plugin_config_routes.py -v`
Expected: `test_get_fills_partial_row_with_defaults` FAIL (`{'interval': 5}` statt mit `label`), `test_get_invalid_row_shows_defaults` FAIL (`{'interval': 0}`); `test_put_then_get_round_trips` PASS.

- [ ] **Step 3: Route umstellen**

In `get_plugin_config` die zwei Zeilen

```python
    db_record = plugin_service.get_installed_plugin(db, name)
    config = (db_record.config or {}) if db_record else (plugin.get_default_config() or {})
```

ersetzen durch

```python
    config = plugin.get_config(db)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend; python -m pytest tests/api/test_plugin_config_routes.py -v`
Expected: alle PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/routes/plugins.py backend/tests/api/test_plugin_config_routes.py
git commit -m "fix(plugins): GET /config zeigt die wirksame Config statt der Rohzeile (#522)" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Tapo und SmartDevice-Poller auf `get_config()` umstellen

**Files:**
- Modify: `backend/app/plugins/installed/tapo_smart_plug/__init__.py:202-214` (`get_dashboard_data`)
- Modify: `backend/app/plugins/smart_device/poller.py:501-514` (`_retention_days_for_plugin`)
- Modify: `backend/app/plugins/installed/tapo_smart_plug/CLAUDE.md` (Satz zu `panel_devices`)
- Test: `backend/tests/plugins/test_smart_device_retention.py:120-140` (anpassen + erweitern)
- Test: `backend/tests/plugins/tapo_smart_plug/test_dashboard_config.py` (neu)

**Interfaces:**
- Consumes: `PluginBase.get_config(db)` aus Task 1.
- Produces: `SmartDevicePoller._retention_days_for_plugin(db, plugin_name: str) -> int` — gleiche Signatur, liest jetzt über die Instanz in `self._plugins`.

- [ ] **Step 1: Failing Tests schreiben**

In `backend/tests/plugins/test_smart_device_retention.py` den bestehenden Test `test_retention_days_for_plugin_reads_config` (Zeile 120-140) ersetzen durch:

```python
def test_retention_days_for_plugin_reads_config(db_session):
    """Poller resolves retention via the plugin's get_config(), default 30."""
    from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin
    from app.plugins.smart_device.poller import SmartDevicePoller
    from app.services import plugin_service

    poller = SmartDevicePoller()
    poller._plugins["tapo_smart_plug"] = TapoSmartPlugPlugin()

    # No config row -> default 30
    assert poller._retention_days_for_plugin(db_session, "tapo_smart_plug") == 30

    # Configured value
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"retention_days": 7}
    )
    assert poller._retention_days_for_plugin(db_session, "tapo_smart_plug") == 7

    # Unlimited
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"retention_days": 0}
    )
    assert poller._retention_days_for_plugin(db_session, "tapo_smart_plug") == 0


def test_retention_days_invalid_row_does_not_disable_cleanup(db_session):
    """A corrupt negative value used to reach cleanup as 'unlimited' (<= 0)."""
    from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin
    from app.plugins.smart_device.poller import SmartDevicePoller
    from app.services import plugin_service

    poller = SmartDevicePoller()
    poller._plugins["tapo_smart_plug"] = TapoSmartPlugPlugin()
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"retention_days": -5}
    )

    assert poller._retention_days_for_plugin(db_session, "tapo_smart_plug") == 30


def test_retention_days_unknown_plugin_uses_default(db_session):
    from app.plugins.smart_device.poller import SmartDevicePoller

    assert SmartDevicePoller()._retention_days_for_plugin(db_session, "nope") == 30
```

Neue Datei `backend/tests/plugins/tapo_smart_plug/test_dashboard_config.py`:

```python
"""Tapo dashboard panel honours panel_devices via get_config() (#522)."""
from unittest.mock import patch

import pytest

from app.models.smart_device import SmartDevice
from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin
from app.services import plugin_service


def _device(db_session, name: str) -> SmartDevice:
    d = SmartDevice(
        name=name, plugin_name="tapo_smart_plug", device_type_id="tapo_p110",
        address="192.168.1.50", capabilities=["switch", "power_monitor"],
        is_active=True, is_online=True, created_by_user_id=1,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def _shm(*devices: SmartDevice) -> dict:
    return {"devices": {
        str(d.id): {"state": {"power_monitor": {"watts": 50.0, "energy_today_kwh": 1.0}}}
        for d in devices
    }}


@pytest.mark.asyncio
async def test_panel_devices_narrows_the_gauge(db_session):
    a, b = _device(db_session, "A"), _device(db_session, "B")
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"panel_devices": [a.id]}
    )

    with patch("app.plugins.installed.tapo_smart_plug.read_shm", return_value=_shm(a, b)):
        data = await TapoSmartPlugPlugin().get_dashboard_data(db_session)

    assert data["value"] == "50.0 W"


@pytest.mark.asyncio
async def test_invalid_config_counts_all_devices(db_session):
    a, b = _device(db_session, "A"), _device(db_session, "B")
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"retention_days": -1}
    )

    with patch("app.plugins.installed.tapo_smart_plug.read_shm", return_value=_shm(a, b)):
        data = await TapoSmartPlugPlugin().get_dashboard_data(db_session)

    assert data["value"] == "100.0 W"
```

Vorher prüfen, ob `backend/tests/plugins/tapo_smart_plug/` ein `__init__.py` hat; die Nachbardateien (`test_plugin_import_history.py`) zeigen die Konvention — neue Datei gleich behandeln.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend; python -m pytest tests/plugins/test_smart_device_retention.py tests/plugins/tapo_smart_plug/test_dashboard_config.py -v`
Expected: `test_retention_days_invalid_row_does_not_disable_cleanup` FAIL (`-5 != 30`). Die übrigen können bereits PASS sein — das ist in Ordnung, sie sichern das Verhalten über die Umstellung hinweg.

- [ ] **Step 3: Poller umstellen**

`_retention_days_for_plugin` in `poller.py` komplett ersetzen:

```python
    def _retention_days_for_plugin(self, db, plugin_name: str) -> int:
        """Resolve a plugin's configured sample retention (days).

        Reads through the plugin's get_config() (#522), so an invalid stored
        value falls back to the schema default instead of reaching cleanup.
        Falls back to SMART_DEVICE_SAMPLE_RETENTION_DAYS when the plugin is not
        loaded here or declares no retention_days field.
        """
        from app.plugins.smart_device.retention import SMART_DEVICE_SAMPLE_RETENTION_DAYS

        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return SMART_DEVICE_SAMPLE_RETENTION_DAYS
        try:
            cfg = plugin.get_config(db)
            return int(cfg.get("retention_days", SMART_DEVICE_SAMPLE_RETENTION_DAYS))
        except (TypeError, ValueError):
            return SMART_DEVICE_SAMPLE_RETENTION_DAYS
```

- [ ] **Step 4: Tapo umstellen**

In `get_dashboard_data` den Block

```python
        from app.models.plugin import InstalledPlugin
        from app.models.smart_device import SmartDevice

        # Read plugin config for panel_devices filter
        panel_device_ids: list[int] = []
        try:
            record = db.query(InstalledPlugin).filter(
                InstalledPlugin.name == "tapo_smart_plug"
            ).first()
            if record and record.config:
                cfg = record.config if isinstance(record.config, dict) else json.loads(record.config)
                panel_device_ids = cfg.get("panel_devices", [])
        except Exception:
            pass
```

ersetzen durch

```python
        from app.models.smart_device import SmartDevice

        panel_device_ids: list[int] = self.get_config(db).get("panel_devices", [])
```

Danach prüfen, ob `json` in `tapo_smart_plug/__init__.py` noch anderweitig benutzt wird (vectorgrep `search_code` nach `json.` mit `filePattern` auf die Datei, sonst Read). Wenn nicht: den `import json` entfernen.

- [ ] **Step 5: Tests laufen lassen (inkl. bestehendem Dashboard-Test mit MagicMock-DB)**

Run: `cd backend; python -m pytest tests/plugins/test_smart_device_retention.py tests/plugins/tapo_smart_plug/ tests/plugins/test_dashboard_panel.py -v`
Expected: alle PASS. `test_get_dashboard_data_aggregates_power` nutzt eine `MagicMock`-DB: `record.config` ist dort ein `MagicMock` (kein dict/str) ⇒ `get_config` liefert Defaults ⇒ kein Filter — das Ergebnis bleibt `100.0 W`.

- [ ] **Step 6: Tapo-Doku anpassen**

In `backend/app/plugins/installed/tapo_smart_plug/CLAUDE.md` den Satz

```
devices count; it is read straight off `InstalledPlugin.config`.
```

ersetzen durch

```
devices count; it is read through `self.get_config(db)` (#522), as is
`retention_days` in the poller's sample cleanup.
```

- [ ] **Step 7: Commit**

```powershell
git add backend/app/plugins/smart_device/poller.py backend/app/plugins/installed/tapo_smart_plug/__init__.py backend/app/plugins/installed/tapo_smart_plug/CLAUDE.md backend/tests/plugins/test_smart_device_retention.py backend/tests/plugins/tapo_smart_plug/test_dashboard_config.py
git commit -m "refactor(plugins): Tapo und SmartDevice-Poller lesen Config ueber get_config() (#522)" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `optical_drive` bekommt die gespeicherte Config

**Files:**
- Modify: `backend/app/plugins/installed/optical_drive/__init__.py` (`get_service` in `get_router`, ca. Zeile 86-88; neue Methode auf `OpticalDrivePlugin`)
- Modify: `backend/app/plugins/installed/optical_drive/CLAUDE.md` (Absatz „The stored config never reaches the service.")
- Test: `backend/tests/plugins/test_optical_drive_plugin.py` (Tests anhängen)

**Interfaces:**
- Consumes: `PluginBase.get_config(db)` aus Task 1.
- Produces: `OpticalDrivePlugin.service_with_current_config(self, db: Session) -> OpticalDriveService` — liefert das Modul-Singleton mit frisch gelesener Config.

Warum pro Request: der Service ist ein Singleton pro Worker; jeder Job startet aus einem Request, und die Jobs lesen `self.config.auto_eject_after_operation` erst am Ende (`reading.py`/`burning.py`). Das Auffrischen im Route-Dependency hält jeden Worker auf dem DB-Stand, ohne Zustellung.

- [ ] **Step 1: Failing Tests anhängen**

Ans Ende von `backend/tests/plugins/test_optical_drive_plugin.py`:

```python
# === Stored config reaches the service (#522) ===


@pytest.fixture
def fresh_singleton(monkeypatch):
    from app.plugins.installed.optical_drive import service as service_mod

    monkeypatch.setattr(service_mod, "_service_instance", None)


def test_service_uses_saved_config(db_session, fresh_singleton):
    from app.plugins.installed.optical_drive import OpticalDrivePlugin
    from app.services import plugin_service

    plugin_service.update_config(
        db_session, name="optical_drive",
        validated_config={"auto_eject_after_operation": False},
    )

    svc = OpticalDrivePlugin().service_with_current_config(db_session)

    assert svc.config.auto_eject_after_operation is False


def test_service_follows_config_change(db_session, fresh_singleton):
    from app.plugins.installed.optical_drive import OpticalDrivePlugin
    from app.services import plugin_service

    plugin = OpticalDrivePlugin()
    assert plugin.service_with_current_config(db_session).config.auto_eject_after_operation is True

    plugin_service.update_config(
        db_session, name="optical_drive",
        validated_config={"auto_eject_after_operation": False},
    )

    assert plugin.service_with_current_config(db_session).config.auto_eject_after_operation is False
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend; python -m pytest tests/plugins/test_optical_drive_plugin.py -k "saved_config or follows_config" -v`
Expected: FAIL mit `AttributeError: 'OpticalDrivePlugin' object has no attribute 'service_with_current_config'`.

- [ ] **Step 3: Methode ergänzen**

In `OpticalDrivePlugin` (nach `on_shutdown`) einfügen:

```python
    def service_with_current_config(self, db: "Session") -> OpticalDriveService:
        """Return the service singleton with the admin's saved config applied.

        Re-read per request (#522): the singleton lives once per worker, and a
        saved config reaches every worker only through the database.
        """
        service = get_optical_drive_service()
        service.config = OpticalDriveConfig(**self.get_config(db))
        return service
```

Oben im Modul ergänzen:

```python
from typing import TYPE_CHECKING, Any, Dict, Optional
```

(bestehende `typing`-Zeile erweitern) und nach den Imports:

```python
if TYPE_CHECKING:
    from sqlalchemy.orm import Session
```

- [ ] **Step 4: Route-Dependency umstellen**

In `get_router()` die Imports ergänzen (neben `from app.api.deps import get_current_user`):

```python
        from sqlalchemy.orm import Session
        from app.api.deps import get_current_user, get_db
```

und `get_service` ersetzen:

```python
        def get_service(db: Session = Depends(get_db)) -> OpticalDriveService:
            """Dependency: the service with the currently saved config."""
            return self.service_with_current_config(db)
```

`get_service` bleibt synchron — FastAPI führt es im Threadpool aus, der DB-Read blockiert also nicht den Event-Loop.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend; python -m pytest tests/plugins/test_optical_drive_plugin.py -v`
Expected: alle PASS.

- [ ] **Step 6: Doku anpassen**

In `backend/app/plugins/installed/optical_drive/CLAUDE.md` den Absatz, der mit `**The stored config never reaches the service.**` beginnt und mit `codebase.` endet, ersetzen durch:

```markdown
**The stored config is re-read per request (#522).** The route dependency
`get_service()` calls `service_with_current_config(db)`, which applies
`self.get_config(db)` to the per-worker singleton, so every worker follows the
database. Only `auto_eject_after_operation` has a consumer (read at the end of
every job); `max_concurrent_jobs`, `scan_interval_seconds`,
`default_output_dir` and `default_burn_speed` are shown in the settings form
but still read nowhere. `on_startup()` builds the singleton with defaults —
harmless, the first request overwrites them.
```

- [ ] **Step 7: Commit**

```powershell
git add backend/app/plugins/installed/optical_drive/__init__.py backend/app/plugins/installed/optical_drive/CLAUDE.md backend/tests/plugins/test_optical_drive_plugin.py
git commit -m "fix(optical-drive): gespeicherte Config erreicht den Service (#522)" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Abschluss-Verifikation

- [ ] **Step 1: Kein Direktleser mehr übrig**

vectorgrep `search_code` (projectPath `D:/Programme (x86)/Baluhost`, `filePattern: backend/app/**`) mit der Query „reads InstalledPlugin.config record.config directly". Erwartet: Treffer nur noch in `app/plugins/config.py`, `app/services/plugin_service.py` (Schreibpfad) und `app/api/routes/plugins.py` (nur noch `update_plugin_config`, schreibend). Jeder andere Leser ⇒ zurück zu Task 3 bzw. neuer Task.

- [ ] **Step 2: Relevante Suiten**

Run: `cd backend; python -m pytest tests/plugins/ tests/api/test_plugin_config_routes.py tests/services/test_plugin_service.py -v`
Expected: alle PASS. Die volle Backend-Suite gehört der CI (hängt auf Windows).

- [ ] **Step 3: Ruff**

Run: `cd backend; python -m ruff check app/plugins app/api/routes/plugins.py tests/plugins tests/api/test_plugin_config_routes.py`
Expected: keine Befunde. Kein `--fix` blind anwenden (F401 kann Monkeypatch-Ziele entfernen, E711/E712 brechen SQLAlchemy-Filter).

- [ ] **Step 4: Zeilenlimit**

Run: `wc -l backend/app/plugins/base.py backend/app/plugins/installed/optical_drive/__init__.py backend/app/plugins/installed/tapo_smart_plug/__init__.py`
Expected: jede ≤ 500.

- [ ] **Step 5: PR**

PR gegen `main`, Titel `fix(plugins): gespeicherte Plugin-Config erreicht das Plugin (#522)`. Body: Problem, Pull-statt-Push-Begründung (Multi-Worker), Liste der umgestellten Leser, bewusst nicht enthalten (externe Plugins, vier unkonsumierte `optical_drive`-Felder) mit Verweis auf die Folge-Issues. `Closes #522`. Body per Write-Tool in eine Datei schreiben und `gh pr create --body-file` nutzen.

---

## Nebenbefunde (nicht in diesem Plan — vor Issue-Anlage nachfragen)

1. **Externe Plugins haben keinen Config-Kanal.** `PluginManager.get_plugin()` (`plugins/manager.py:931`) kennt nur gebündelte Plugins ⇒ `PUT/GET /config` = 404; die Sandbox hat weder DB-Zugriff noch einen Scope. Vorschlag: Capability-Scope `config:read` über die UDS-RPC, Schema aus dem Manifest.
2. **Vier `OpticalDriveConfig`-Felder ohne Konsument** (`default_output_dir`, `default_burn_speed`, `scan_interval_seconds`, `max_concurrent_jobs`): im Formular sichtbar, wirkungslos. Entweder anbinden oder aus dem Schema entfernen.
