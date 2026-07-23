# Plugin-Menü-Contribution + Gaming-Modus — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plugins können Aktionen ins System-Menü (`PowerMenu`) hängen; das `steam_gaming`-Plugin nutzt das als erster Konsument für „Gaming-Modus" — Displays an, dann Steams Big Picture öffnen.

**Architecture:** `PluginUIManifest` bekommt `menu_items` (reine Deklaration: id, Icon, Label-Key + Literal-Fallback), `PluginBase` bekommt `run_menu_action()`. Eine neue Core-Route `POST /api/plugins/{name}/menu-actions/{action_id}` besitzt Admin-Gate, Ratelimit, Audit, Deklarationsprüfung und Timeout — das Plugin liefert nur *was* passiert, nie *wer* es darf. Der Lesepfad läuft über das vorhandene `GET /api/plugins/ui/manifest` und den `PluginContext`, es kommt kein zweiter Fetch dazu.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 / SQLAlchemy 2.0, pytest (`asyncio_mode = "auto"`), React 18 + TypeScript + Vitest, lucide-react.

**Spec:** `docs/superpowers/specs/2026-07-23-plugin-menu-contribution-gaming-mode-design.md`

## Global Constraints

- Backend-Tests laufen aus `backend/`: `python -m pytest <pfad> -q --no-cov`. Der Repo-Default in `pyproject.toml` schaltet Coverage an; für Einzelläufe `--no-cov` verwenden.
- `ruff check <geänderte dateien>` muss sauber sein (CI-Gate).
- Frontend: `npx vitest run <pfad>` aus `client/`; vor dem Abschluss zusätzlich `npx eslint .` und `npm run build`.
- Keine neuen Dependencies. Alles mit Stdlib + vorhandenen Paketen.
- Keine neuen Sudoers-Regeln. Kein `shell=True`; Subprozesse ausschließlich mit Listen-Argumenten.
- Eine Plugin-Aktion darf **niemals** einen 5xx erzeugen und niemals Server-Interna in die Antwort schreiben: Exception und Timeout werden zu `ok=false` mit generischer Meldung, Details nur ins Log.
- `PluginMenuItem` hat bewusst **kein** `admin_only`-Feld — der Core erzwingt Admin, das Plugin kann das nicht aufweichen.
- Kommentare und Docstrings auf Englisch (Repo-Konvention); Commit-Betreff Englisch. Nutzersichtbare Strings de/en.
- Keine DB-Migration in diesem Teilprojekt. `menu_items` sind Laufzeit-Deklaration, kein persistenter Zustand.

---

## File Structure

**Neu:**

| Datei | Verantwortung |
|---|---|
| `backend/app/services/power/session_env.py` | Wayland-Session-Env (`XDG_RUNTIME_DIR`, `WAYLAND_DISPLAY`) — ein Helper für zwei Aufrufer |
| `backend/app/plugins/installed/steam_gaming/launcher.py` | Big Picture abgekoppelt starten |
| `backend/tests/plugins/test_plugin_menu_actions.py` | Extension-Point: Schemas, Manifest, Route, Middleware-Gate |
| `backend/tests/plugins/test_steam_gaming_launcher.py` | Launcher: argv, Detach-Flags, Fehlerpfade |
| `backend/tests/test_session_env.py` | Session-Env-Helper + Nutzung im Desktop-Backend |
| `client/src/__tests__/contexts/PluginContext.menuItems.test.tsx` | Flatten + Sortierung der Menü-Items |
| `client/src/__tests__/components/PowerMenu.pluginActions.test.tsx` | Rendern, Auslösen, Toast, Sperre, Icon-Fallback |

**Geändert:**

| Datei | Änderung |
|---|---|
| `backend/app/plugins/base.py` | `PluginMenuItem`, `MenuActionResult`; `PluginUIManifest.menu_items`; `get_menu_items()`, `run_menu_action()` |
| `backend/app/schemas/plugin.py` | `PluginMenuItemSchema`, `PluginMenuActionResponse`; `PluginUIInfo.menu_items` |
| `backend/app/plugins/manager.py` | `menu_items` in `get_ui_manifest()` aufnehmen |
| `backend/app/api/routes/plugins.py` | Route `POST /{name}/menu-actions/{action_id}` + Timeout-Konstante + Guard-Helper |
| `backend/app/services/power/desktop_backend.py` | `_session_env()` → gemeinsamer Helper; `_exec` in `asyncio.to_thread` |
| `backend/app/plugins/installed/steam_gaming/__init__.py` | `get_ui_manifest()` mit Menü-Item, `run_menu_action()`, neue Übersetzungen |
| `backend/tests/plugins/test_steam_gaming_plugin.py` | Tests für Menü-Item und Aktion |
| `client/src/api/plugins.ts` | Typen `PluginMenuItem`/`PluginMenuActionResult`, `PluginUIInfo.menu_items`, `runPluginMenuAction()` |
| `client/src/contexts/PluginContext.tsx` | `pluginMenuItems` (flach, sortiert, mit Plugin-Name + Translations) |
| `client/src/components/PowerMenu.tsx` | Plugin-Aktionen im Admin-Block rendern und auslösen |
| `client/src/i18n/locales/{de,en}/common.json` | `powerMenu.pluginActionFailed` |
| `backend/app/plugins/CLAUDE.md` | Extension-Point dokumentieren + Operator-Note erweitern |

---

## Task 1: `PluginMenuItem`, `MenuActionResult`, PluginBase-Hooks

**Files:**
- Modify: `backend/app/plugins/base.py:50-79` (Schemas neben `PluginNavItem`/`PluginUIManifest`), `:233-244` (Hooks neben den Pill-Hooks)
- Test: `backend/tests/plugins/test_plugin_menu_actions.py` (neu)

**Interfaces:**
- Consumes: nichts.
- Produces:
```python
class PluginMenuItem(BaseModel):
    id: str            # pattern ^[a-z0-9_]+$
    icon: str
    label_key: str
    label_text: str
    description_key: Optional[str] = None
    description_text: Optional[str] = None
    tone: Literal["neutral", "info", "success", "warning", "danger"] = "neutral"
    order: int = 100

class MenuActionResult(BaseModel):
    ok: bool
    message_key: Optional[str] = None
    message_text: str

PluginUIManifest.menu_items: List[PluginMenuItem]           # default []
PluginBase.get_menu_items() -> List[PluginMenuItem]          # default []
PluginBase.run_menu_action(action_id: str, db: Session) -> Optional[MenuActionResult]   # default None
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_plugin_menu_actions.py`:

```python
"""Tests for the plugin menu-action extension point."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.plugins.base import (
    MenuActionResult,
    PluginBase,
    PluginMenuItem,
    PluginMetadata,
    PluginUIManifest,
)


class TestPluginMenuItem:
    def test_minimal_item(self):
        item = PluginMenuItem(
            id="gaming_mode", icon="Gamepad2",
            label_key="menu_gaming_mode", label_text="Gaming Mode",
        )
        assert item.tone == "neutral"
        assert item.order == 100
        assert item.description_key is None

    @pytest.mark.parametrize("bad_id", ["Gaming", "gaming-mode", "gaming.mode", "../etc", "", "a b"])
    def test_rejects_ids_outside_the_namespace(self, bad_id):
        with pytest.raises(ValidationError):
            PluginMenuItem(
                id=bad_id, icon="Gamepad2",
                label_key="k", label_text="t",
            )

    def test_has_no_admin_only_field(self):
        """The core decides who may run an action - a plugin must not widen it."""
        assert "admin_only" not in PluginMenuItem.model_fields


class TestMenuActionResult:
    def test_message_text_is_required(self):
        with pytest.raises(ValidationError):
            MenuActionResult(ok=True)

    def test_key_is_optional(self):
        result = MenuActionResult(ok=False, message_text="boom")
        assert result.message_key is None


class _BarePlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bare", display_name="Bare", version="1.0.0",
            description="", author="test",
        )


class TestPluginBaseDefaults:
    def test_no_menu_items_by_default(self):
        assert _BarePlugin().get_menu_items() == []

    async def test_run_menu_action_returns_none_by_default(self):
        assert await _BarePlugin().run_menu_action("anything", db=None) is None

    def test_ui_manifest_menu_items_default_empty(self):
        assert PluginUIManifest().menu_items == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_menu_actions.py -q --no-cov`
Expected: FAIL — `ImportError: cannot import name 'MenuActionResult'`

- [ ] **Step 3: Add the schemas**

In `backend/app/plugins/base.py`, direkt **nach** `class PluginNavItem` (endet Zeile 57) und **vor** `class PluginUIManifest`:

```python
class PluginMenuItem(BaseModel):
    """An action a plugin contributes to the system (power) menu.

    Declaration only: the plugin says what it offers, the core decides who may
    run it. There is deliberately no ``admin_only`` field (unlike
    PluginNavItem) - a menu action executes something, so widening its
    audience must not be the plugin's call.
    """

    id: str = Field(
        pattern=r"^[a-z0-9_]+$",
        description="Plugin-local action id, e.g. 'gaming_mode'",
    )
    icon: str = Field(description="lucide icon name, e.g. 'Gamepad2'")
    label_key: str = Field(description="Key into get_translations() for the label")
    label_text: str = Field(description="Literal fallback for the label")
    description_key: Optional[str] = Field(
        default=None, description="Key into get_translations() for the sub-label"
    )
    description_text: Optional[str] = Field(
        default=None, description="Literal fallback for the sub-label"
    )
    tone: Literal["neutral", "info", "success", "warning", "danger"] = "neutral"
    order: int = Field(default=100, description="Sort order within the plugin block")


class MenuActionResult(BaseModel):
    """Outcome of a menu action, rendered as a toast by the frontend.

    ``message_key`` is resolved client-side against the plugin's translations
    (same mechanic as pill labels) - the backend never picks a language.
    """

    ok: bool
    message_key: Optional[str] = None
    message_text: str = Field(description="Literal fallback, always set")
```

Im `class PluginUIManifest` (Zeile 60-79) nach dem Feld `nav_items` ergänzen:

```python
    menu_items: List[PluginMenuItem] = Field(
        default_factory=list,
        description="Actions to add to the system menu",
    )
```

- [ ] **Step 4: Add the PluginBase hooks**

In `backend/app/plugins/base.py`, direkt nach `collect_status_pill` (endet Zeile 244):

```python
    def get_menu_items(self) -> List["PluginMenuItem"]:
        """System-menu actions this plugin contributes. Default: none."""
        return []

    async def run_menu_action(
        self, action_id: str, db: "Session"
    ) -> Optional["MenuActionResult"]:
        """Execute one menu action, or None if this plugin does not know it.

        *action_id* is the plugin-local id from the declared menu item. The
        core validates it against get_menu_items() before calling, enforces the
        admin gate, and applies a timeout - implementations only do the work.
        Blocking work belongs in ``asyncio.to_thread`` so the timeout can
        actually take effect.
        """
        return None
```

Import-Zeile am Dateikopf prüfen: `Literal` muss aus `typing` importiert sein (ist es bereits für `PanelType`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_menu_actions.py -q --no-cov`
Expected: PASS (13 Tests — die 6 Parametrize-Fälle zählen einzeln)

- [ ] **Step 6: Lint + commit**

```bash
cd backend && ruff check app/plugins/base.py tests/plugins/test_plugin_menu_actions.py
git add backend/app/plugins/base.py backend/tests/plugins/test_plugin_menu_actions.py
git commit -m "feat(plugins): declare menu items and menu actions on PluginBase"
```

---

## Task 2: Manifest-Durchleitung (Schema + Manager)

**Files:**
- Modify: `backend/app/schemas/plugin.py:8-30`
- Modify: `backend/app/plugins/manager.py` (in `get_ui_manifest()`, im `nav_items`-Block)
- Test: `backend/tests/plugins/test_plugin_menu_actions.py` (anhängen)

**Interfaces:**
- Consumes: `PluginMenuItem` (Task 1).
- Produces:
```python
class PluginMenuItemSchema(BaseModel):
    id: str; icon: str
    label_key: str; label_text: str
    description_key: Optional[str] = None; description_text: Optional[str] = None
    tone: str = "neutral"; order: int = 100

PluginUIInfo.menu_items: List[PluginMenuItemSchema] = []
# manager.get_ui_manifest()["plugins"][i]["menu_items"] -> list[dict]
```

- [ ] **Step 1: Write the failing test**

An `backend/tests/plugins/test_plugin_menu_actions.py` anhängen:

```python
from unittest.mock import MagicMock

from app.plugins.manager import PluginManager
from app.schemas.plugin import PluginUIInfo


def _plugin_with_menu(name: str = "demo") -> MagicMock:
    plugin = MagicMock()
    plugin.metadata.display_name = "Demo"
    plugin.get_ui_manifest.return_value = PluginUIManifest(
        enabled=True,
        menu_items=[PluginMenuItem(
            id="do_it", icon="Zap", label_key="menu_do_it", label_text="Do it",
        )],
    )
    plugin.get_translations.return_value = {"en": {"menu_do_it": "Do it"}}
    return plugin


class TestManifestCarriesMenuItems:
    def test_enabled_plugin_menu_items_reach_the_manifest(self, tmp_path):
        manager = PluginManager(plugins_dir=tmp_path)
        manager._plugins = {"demo": _plugin_with_menu()}
        manager._enabled = {"demo"}

        entry = manager.get_ui_manifest()["plugins"][0]

        assert entry["menu_items"] == [{
            "id": "do_it", "icon": "Zap",
            "label_key": "menu_do_it", "label_text": "Do it",
            "description_key": None, "description_text": None,
            "tone": "neutral", "order": 100,
        }]

    def test_plugin_without_menu_items_yields_empty_list(self, tmp_path):
        plugin = _plugin_with_menu()
        plugin.get_ui_manifest.return_value = PluginUIManifest(enabled=True)
        manager = PluginManager(plugins_dir=tmp_path)
        manager._plugins = {"demo": plugin}
        manager._enabled = {"demo"}

        assert manager.get_ui_manifest()["plugins"][0]["menu_items"] == []

    def test_schema_defaults_to_empty(self):
        info = PluginUIInfo(name="demo", display_name="Demo")
        assert info.menu_items == []
```

Hinweis für die Umsetzung: `PluginManager(plugins_dir=tmp_path)` umgeht das Singleton und zeigt auf ein leeres Verzeichnis statt auf das echte `installed/` — dasselbe Muster wie `tests/plugins/test_plugin_manager.py:78`. Das direkte Setzen von `_plugins`/`_enabled` entspricht den internen Typen (`Dict[str, PluginBase]` / `Set[str]`, `manager.py:130-131`); auch die Sandbox-Tests legen Einträge direkt in `_enabled` ab.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_menu_actions.py -q --no-cov -k Manifest`
Expected: FAIL — `KeyError: 'menu_items'`

- [ ] **Step 3: Add the mirror schema**

In `backend/app/schemas/plugin.py` nach `class PluginNavItemSchema` (endet Zeile 15):

```python
class PluginMenuItemSchema(BaseModel):
    """System-menu action offered by a plugin (mirror of PluginMenuItem)."""

    id: str
    icon: str
    label_key: str
    label_text: str
    description_key: Optional[str] = None
    description_text: Optional[str] = None
    tone: str = "neutral"
    order: int = 100
```

In `class PluginUIInfo` nach `nav_items` (Zeile 23):

```python
    menu_items: List[PluginMenuItemSchema] = []
```

- [ ] **Step 4: Emit menu_items from the manager**

In `backend/app/plugins/manager.py`, in `get_ui_manifest()` im Dict für in-process Plugins, direkt nach dem `"nav_items"`-Eintrag:

```python
                        "menu_items": [
                            item.model_dump() for item in ui_manifest.menu_items
                        ],
```

Der externe (sandboxed) Zweig weiter unten bleibt **unverändert**: externe Plugins beschreiben ihre UI über `PluginManifestUI` (Bundle/Styles) und können keine Menü-Aktionen deklarieren. Das ist gewollt — ausführende Extension-Points für sandboxed Plugins sind eigener Scope.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_menu_actions.py -q --no-cov`
Expected: PASS (16 Tests)

- [ ] **Step 6: Run the neighbouring suites for regressions**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_manager.py tests/plugins/test_external_ui_manifest.py tests/plugins/test_plugins.py -q --no-cov`
Expected: PASS, keine neuen Fehler.

- [ ] **Step 7: Lint + commit**

```bash
cd backend && ruff check app/schemas/plugin.py app/plugins/manager.py tests/plugins/test_plugin_menu_actions.py
git add backend/app/schemas/plugin.py backend/app/plugins/manager.py backend/tests/plugins/test_plugin_menu_actions.py
git commit -m "feat(plugins): carry menu_items through the UI manifest"
```

---

## Task 3: Ausführungs-Route mit Gate, Timeout und Audit

**Files:**
- Modify: `backend/app/schemas/plugin.py` (Response-Schema)
- Modify: `backend/app/api/routes/plugins.py` (Route + Helper + Import-Block Zeile 20-37)
- Test: `backend/tests/plugins/test_plugin_menu_actions.py` (anhängen)

**Interfaces:**
- Consumes: `PluginMenuItem`, `MenuActionResult` (Task 1); `PluginMenuItemSchema` (Task 2).
- Produces:
```python
PLUGIN_MENU_ACTION_TIMEOUT_SECONDS = 20.0
class PluginMenuActionResponse(BaseModel):
    ok: bool; message_key: Optional[str] = None; message_text: str

async def run_plugin_menu_action(request, response, name: str, action_id: str,
                                 db: Session, current_user: User,
                                 plugin_manager: PluginManager) -> PluginMenuActionResponse
# route: POST /api/plugins/{name}/menu-actions/{action_id}
```

- [ ] **Step 1: Write the failing test**

An `backend/tests/plugins/test_plugin_menu_actions.py` anhängen:

```python
import asyncio
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.routes.plugins import (
    PLUGIN_MENU_ACTION_TIMEOUT_SECONDS,
    run_plugin_menu_action,
)


def _declaring_plugin(action_id: str = "do_it") -> MagicMock:
    plugin = MagicMock()
    plugin.get_menu_items.return_value = [PluginMenuItem(
        id=action_id, icon="Zap", label_key="k", label_text="Do it",
    )]
    return plugin


async def _call(plugin, name: str = "demo", action_id: str = "do_it"):
    manager = MagicMock()
    manager.get_plugin.return_value = plugin
    return await run_plugin_menu_action(
        request=MagicMock(client=MagicMock(host="127.0.0.1")),
        response=MagicMock(),
        name=name,
        action_id=action_id,
        db=MagicMock(),
        current_user=MagicMock(username="admin"),
        plugin_manager=manager,
    )


class TestMenuActionRoute:
    async def test_unknown_plugin_is_404(self):
        manager = MagicMock()
        manager.get_plugin.return_value = None
        with pytest.raises(HTTPException) as exc:
            await run_plugin_menu_action(
                request=MagicMock(), response=MagicMock(),
                name="nope", action_id="do_it", db=MagicMock(),
                current_user=MagicMock(username="admin"), plugin_manager=manager,
            )
        assert exc.value.status_code == 404

    async def test_undeclared_action_is_404_and_never_dispatches(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await _call(plugin, action_id="something_else")
        assert exc.value.status_code == 404
        plugin.run_menu_action.assert_not_awaited()

    async def test_happy_path_returns_result_and_audits_success(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(
            return_value=MenuActionResult(ok=True, message_key="ok_key", message_text="done")
        )
        with patch("app.api.routes.plugins.get_audit_logger_db") as audit:
            result = await _call(plugin)
        assert (result.ok, result.message_key, result.message_text) == (True, "ok_key", "done")
        kwargs = audit.return_value.log_event.call_args.kwargs
        assert kwargs["event_type"] == "PLUGIN"
        assert kwargs["action"] == "menu_action"
        assert kwargs["resource"] == "demo:do_it"
        assert kwargs["success"] is True

    async def test_raising_action_stays_200_with_generic_message(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(side_effect=RuntimeError("secret path /opt/baluhost"))
        with patch("app.api.routes.plugins.get_audit_logger_db") as audit:
            result = await _call(plugin)
        assert result.ok is False
        assert "secret path" not in result.message_text
        assert audit.return_value.log_event.call_args.kwargs["success"] is False

    async def test_hanging_action_is_cut_off_by_the_timeout(self):
        async def _hang(action_id, db):
            await asyncio.sleep(60)

        plugin = _declaring_plugin()
        plugin.run_menu_action = _hang
        with patch("app.api.routes.plugins.PLUGIN_MENU_ACTION_TIMEOUT_SECONDS", 0.01), \
             patch("app.api.routes.plugins.get_audit_logger_db"):
            result = await _call(plugin)
        assert result.ok is False

    async def test_plugin_returning_none_despite_declaration_is_not_ok(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(return_value=None)
        with patch("app.api.routes.plugins.get_audit_logger_db"):
            result = await _call(plugin)
        assert result.ok is False

    def test_timeout_is_generous_enough_for_kscreen_doctor(self):
        """kscreen-doctor carries a 30s subprocess timeout of its own."""
        assert PLUGIN_MENU_ACTION_TIMEOUT_SECONDS >= 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_menu_actions.py -q --no-cov -k MenuActionRoute`
Expected: FAIL — `ImportError: cannot import name 'run_plugin_menu_action'`

- [ ] **Step 3: Add the response schema**

In `backend/app/schemas/plugin.py` nach `PluginMenuItemSchema`:

```python
class PluginMenuActionResponse(BaseModel):
    """Outcome of a plugin menu action (mirror of MenuActionResult)."""

    ok: bool
    message_key: Optional[str] = None
    message_text: str
```

- [ ] **Step 4: Add the route**

In `backend/app/api/routes/plugins.py`:

Imports ergänzen — `import asyncio` oben bei `import html`, und im Schema-Import-Block (Zeile 20-37) alphabetisch `PluginMenuActionResponse` einfügen. Zusätzlich am Kopf:

```python
from app.plugins.base import MenuActionResult, PluginBase
```

Konstante direkt unter `router = APIRouter(...)` (Zeile 42):

```python
# Generous compared to the 2s pill-collector timeout: a menu action may shell
# out (kscreen-doctor carries a 30s subprocess timeout of its own). Note that
# wait_for cannot preempt work already running inside asyncio.to_thread - it
# frees the request, the thread finishes on its own. That is acceptable: it
# occupies a thread, not the event loop.
PLUGIN_MENU_ACTION_TIMEOUT_SECONDS = 20.0
```

Route ans Dateiende:

```python
@router.post("/{name}/menu-actions/{action_id}", response_model=PluginMenuActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def run_plugin_menu_action(
    request: Request,
    response: Response,
    name: str,
    action_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> PluginMenuActionResponse:
    """Run a menu action a plugin declared in its UI manifest. Admin only.

    Requests for a disabled plugin never reach this handler - PluginGateMiddleware
    rejects them with 403 based on the DB (see middleware/plugin_gate.py).
    """
    plugin = plugin_manager.get_plugin(name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found or not enabled",
        )

    # Only declared actions are dispatchable - never call through on an
    # arbitrary path segment.
    declared = {item.id for item in plugin.get_menu_items()}
    if action_id not in declared:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown menu action",
        )

    result = await _execute_menu_action(plugin, name, action_id, db)

    get_audit_logger_db().log_event(
        event_type="PLUGIN",
        user=current_user.username,
        action="menu_action",
        resource=f"{name}:{action_id}",
        details={"ok": result.ok},
        success=result.ok,
        ip_address=request.client.host if request.client else None,
    )
    return PluginMenuActionResponse(**result.model_dump())


async def _execute_menu_action(
    plugin: PluginBase, name: str, action_id: str, db: Session
) -> MenuActionResult:
    """Run the action under a timeout and an exception guard.

    A plugin fault must never become a 5xx and must never leak internals into
    the response - the detail goes to the log, the caller gets a generic
    failure. Mirrors the pill-collector guard in services/status_bar/service.py.
    """
    try:
        result = await asyncio.wait_for(
            plugin.run_menu_action(action_id, db),
            timeout=PLUGIN_MENU_ACTION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("plugin %s menu action %s timed out", name, action_id)
        return MenuActionResult(ok=False, message_text="Action timed out")
    except Exception:  # noqa: BLE001 - a plugin fault must not 5xx the endpoint
        logger.warning(
            "plugin %s menu action %s failed", name, action_id, exc_info=True
        )
        return MenuActionResult(ok=False, message_text="Action failed")

    if result is None:
        # Declared but not handled - a plugin bug, not a user error.
        logger.warning(
            "plugin %s declared menu action %s but returned None", name, action_id
        )
        return MenuActionResult(ok=False, message_text="Action failed")
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_menu_actions.py -q --no-cov`
Expected: PASS (23 Tests)

- [ ] **Step 6: Pin the middleware gate (no production code changes)**

An dieselbe Testdatei anhängen:

```python
from app.middleware.plugin_gate import _is_management_route


class TestMenuActionIsGatedByMiddleware:
    def test_menu_action_path_is_not_a_management_route(self):
        """A disabled plugin must not be able to run actions.

        Management routes (toggle/config/ui) stay reachable while a plugin is
        disabled - menu actions must NOT, or disabling a plugin would leave its
        actions live.
        """
        assert _is_management_route("/menu-actions/gaming_mode") is False

    def test_management_routes_still_bypass(self):
        assert _is_management_route("/toggle") is True
        assert _is_management_route("/config") is True
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_menu_actions.py -q --no-cov -k Middleware`
Expected: PASS (2 Tests) — ohne Produktionsänderung; falls es fehlschlägt, wäre die Spec-Annahme falsch und der Fund muss gemeldet werden, **nicht** durch Aufweichen der Middleware „gefixt".

- [ ] **Step 8: Lint + commit**

```bash
cd backend && ruff check app/api/routes/plugins.py app/schemas/plugin.py tests/plugins/test_plugin_menu_actions.py
git add backend/app/api/routes/plugins.py backend/app/schemas/plugin.py backend/tests/plugins/test_plugin_menu_actions.py
git commit -m "feat(plugins): add the admin-gated menu-action endpoint"
```

---

## Task 4: Session-Env-Helper + nicht-blockierendes Desktop-Backend

**Files:**
- Create: `backend/app/services/power/session_env.py`
- Modify: `backend/app/services/power/desktop_backend.py:63-111`
- Test: `backend/tests/test_session_env.py` (neu)

**Interfaces:**
- Consumes: nichts.
- Produces:
```python
# app/services/power/session_env.py
def wayland_session_env(uid: Optional[int] = None) -> dict
```

**Warum die zweite Änderung mit hier hineingehört:** `LinuxDesktopBackend.enable()` ruft heute `subprocess.run` synchron aus einer `async def` heraus — das blockiert den Event-Loop, und ein `asyncio.wait_for` aus Task 3 könnte es nicht abbrechen. Beide Änderungen betreffen dieselbe Datei und denselben Aufrufpfad.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_session_env.py`:

```python
"""Wayland session environment helper."""
from __future__ import annotations

from app.services.power.session_env import wayland_session_env


class TestWaylandSessionEnv:
    def test_sets_runtime_dir_and_display_for_the_uid(self):
        env = wayland_session_env(uid=1000)
        assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"
        assert env["WAYLAND_DISPLAY"] == "wayland-0"

    def test_keeps_existing_environment(self, monkeypatch):
        monkeypatch.setenv("PATH", "/custom/bin")
        assert wayland_session_env(uid=1000)["PATH"] == "/custom/bin"

    def test_does_not_override_an_explicit_session(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-7")
        assert wayland_session_env(uid=1000)["WAYLAND_DISPLAY"] == "wayland-7"


class TestDesktopBackendUsesTheHelper:
    def test_linux_backend_env_matches_the_helper(self):
        from app.services.power.desktop_backend import LinuxDesktopBackend

        backend = LinuxDesktopBackend(uid=1000)
        assert backend._session_env() == wayland_session_env(uid=1000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_session_env.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: app.services.power.session_env`

- [ ] **Step 3: Create the helper**

```python
# backend/app/services/power/session_env.py
"""Environment for reaching the logged-in user's Wayland session.

The backend runs as the session user (uid match) but outside the graphical
session, so XDG_RUNTIME_DIR and WAYLAND_DISPLAY have to be supplied for
commands like kscreen-doctor or steam to talk to it.

Two callers share this: the desktop (DPMS) backend and the steam_gaming
plugin's Big Picture launcher.
"""
from __future__ import annotations

import os
from typing import Optional


def wayland_session_env(uid: Optional[int] = None) -> dict:
    """Return os.environ plus the session variables, without overriding them."""
    resolved = uid if uid is not None else os.getuid()
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{resolved}")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    return env
```

Hinweis: `os.getuid()` existiert auf Windows nicht. Der Default-Zweig wird nur auf Linux erreicht (dev-Mode nutzt `DevDesktopBackend`); Tests übergeben `uid` immer explizit.

- [ ] **Step 4: Use it in the desktop backend**

In `backend/app/services/power/desktop_backend.py` den Import ergänzen:

```python
from app.services.power.session_env import wayland_session_env
```

`_session_env()` (Zeile 67-76) ersetzen durch:

```python
    def _session_env(self) -> dict:
        """Env so kscreen-doctor can reach the user's Wayland session."""
        return wayland_session_env(self._uid)
```

- [ ] **Step 5: Stop blocking the event loop**

In derselben Datei `enable()`/`disable()` (Zeile 96-100) so ändern, dass der Subprozess in einem Thread läuft:

```python
    async def enable(self) -> Tuple[bool, str]:
        return await asyncio.to_thread(self._exec, ["kscreen-doctor", "--dpms", "on"])

    async def disable(self) -> Tuple[bool, str]:
        return await asyncio.to_thread(self._exec, ["kscreen-doctor", "--dpms", "off"])
```

und `import asyncio` am Dateikopf ergänzen. `_exec` selbst bleibt unverändert synchron.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_session_env.py tests/test_desktop_backend.py tests/test_desktop_routes.py -q --no-cov`
Expected: PASS. Die vorhandenen Desktop-Tests müssen **unverändert** grün bleiben — schlagen sie fehl, ist die `to_thread`-Umstellung schuld und nicht der Test.

- [ ] **Step 7: Lint + commit**

```bash
cd backend && ruff check app/services/power/session_env.py app/services/power/desktop_backend.py tests/test_session_env.py
git add backend/app/services/power/session_env.py backend/app/services/power/desktop_backend.py backend/tests/test_session_env.py
git commit -m "refactor(power): share the Wayland session env and run kscreen-doctor off-loop"
```

---

## Task 5: Big-Picture-Launcher

**Files:**
- Create: `backend/app/plugins/installed/steam_gaming/launcher.py`
- Test: `backend/tests/plugins/test_steam_gaming_launcher.py` (neu)

**Interfaces:**
- Consumes: `wayland_session_env` (Task 4).
- Produces:
```python
BIG_PICTURE_URL = "steam://open/bigpicture"
def open_big_picture() -> tuple[bool, str]     # blocking; call via asyncio.to_thread
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_steam_gaming_launcher.py`:

```python
"""Big Picture launcher for the steam_gaming plugin."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.plugins.installed.steam_gaming.launcher import BIG_PICTURE_URL, open_big_picture


class TestOpenBigPicture:
    def test_launches_steam_with_the_big_picture_url(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen:
            cfg.is_dev_mode = False
            ok, _detail = open_big_picture()

        assert ok is True
        args, kwargs = popen.call_args
        assert args[0] == ["steam", BIG_PICTURE_URL]

    def test_detaches_so_steam_does_not_hang_off_the_backend(self):
        """steam:// hands off to a running instance and exits - but if Steam is
        NOT running, the same call starts it in the foreground."""
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen:
            cfg.is_dev_mode = False
            open_big_picture()

        kwargs = popen.call_args.kwargs
        assert kwargs["start_new_session"] is True
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "shell" not in kwargs  # never shell=True

    def test_passes_the_wayland_session_env(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen, \
             patch(
                 "app.plugins.installed.steam_gaming.launcher.wayland_session_env",
                 return_value={"XDG_RUNTIME_DIR": "/run/user/1000"},
             ):
            cfg.is_dev_mode = False
            open_big_picture()

        assert popen.call_args.kwargs["env"] == {"XDG_RUNTIME_DIR": "/run/user/1000"}

    def test_missing_steam_binary_is_reported_not_raised(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen", side_effect=FileNotFoundError()):
            cfg.is_dev_mode = False
            ok, detail = open_big_picture()

        assert ok is False
        assert "steam" in detail.lower()

    def test_unexpected_os_error_is_reported_not_raised(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen", side_effect=OSError("no display")):
            cfg.is_dev_mode = False
            ok, _detail = open_big_picture()

        assert ok is False

    def test_dev_mode_does_not_spawn_anything(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen:
            cfg.is_dev_mode = True
            ok, _detail = open_big_picture()

        assert ok is True
        popen.assert_not_called()

    def test_never_waits_for_the_process(self):
        handle = MagicMock()
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen", return_value=handle):
            cfg.is_dev_mode = False
            open_big_picture()

        handle.wait.assert_not_called()
        handle.communicate.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_launcher.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: ...steam_gaming.launcher`

- [ ] **Step 3: Implement the launcher**

```python
# backend/app/plugins/installed/steam_gaming/launcher.py
"""Open Steam's Big Picture mode in the user's desktop session.

On the production box Steam runs permanently (app-steam@autostart.service), so
this hands a steam:// URL to the running instance, which then switches to Big
Picture and the invoked process exits immediately.

The call is deliberately detached: if Steam is NOT running, the very same
command starts it in the foreground, and an attached child would live for as
long as the gaming session - hanging off the backend process. start_new_session
puts it in its own session/process group and nothing is ever waited on.
"""
from __future__ import annotations

import logging
import subprocess

from app.core.config import settings
from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

BIG_PICTURE_URL = "steam://open/bigpicture"


def open_big_picture() -> tuple[bool, str]:
    """Ask Steam to show Big Picture. Blocking - call via asyncio.to_thread.

    Returns:
        (ok, detail). ok=True means the request was dispatched, not that Big
        Picture is on screen - the process is detached, so anything beyond the
        spawn is unobservable from here.
    """
    if settings.is_dev_mode:
        # No desktop session on a Windows dev box.
        return True, "big picture requested (dev)"

    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no user input
            ["steam", BIG_PICTURE_URL],
            env=wayland_session_env(),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False, "steam binary not found"
    except OSError as exc:
        logger.warning("failed to launch Big Picture: %s", exc)
        return False, "could not start steam"

    return True, "big picture requested"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_launcher.py -q --no-cov`
Expected: PASS (7 Tests)

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/plugins/installed/steam_gaming/launcher.py tests/plugins/test_steam_gaming_launcher.py
git add backend/app/plugins/installed/steam_gaming/launcher.py backend/tests/plugins/test_steam_gaming_launcher.py
git commit -m "feat(steam-gaming): launch Big Picture detached from the backend"
```

---

## Task 6: Gaming-Modus im Steam-Plugin

**Files:**
- Modify: `backend/app/plugins/installed/steam_gaming/__init__.py`
- Test: `backend/tests/plugins/test_steam_gaming_plugin.py` (anhängen)

**Interfaces:**
- Consumes: `PluginMenuItem`, `MenuActionResult`, `PluginUIManifest` (Task 1); `open_big_picture` (Task 5); `get_desktop_service` (vorhanden).
- Produces: `SteamGamingPlugin.get_ui_manifest()`, `.run_menu_action()`; Übersetzungsschlüssel `menu_gaming_mode`, `menu_gaming_mode_desc`, `menu_gaming_mode_started`, `menu_displays_failed`, `menu_steam_failed`.

- [ ] **Step 1: Write the failing test**

An `backend/tests/plugins/test_steam_gaming_plugin.py` anhängen (Imports oben ergänzen: `from unittest.mock import AsyncMock, MagicMock, patch`):

```python
from app.plugins.installed.steam_gaming import SteamGamingPlugin

_ACTION = "gaming_mode"


def _patch_desktop(ok: bool, message: str = ""):
    service = MagicMock()
    service.enable = AsyncMock(return_value=(ok, message))
    return patch(
        "app.plugins.installed.steam_gaming.get_desktop_service",
        return_value=service,
    ), service


class TestGamingModeMenuItem:
    def test_manifest_declares_the_action(self):
        manifest = SteamGamingPlugin().get_ui_manifest()
        assert [item.id for item in manifest.menu_items] == [_ACTION]

    def test_item_carries_key_and_literal_fallback(self):
        item = SteamGamingPlugin().get_ui_manifest().menu_items[0]
        assert item.label_key == "menu_gaming_mode"
        assert item.label_text
        assert item.icon == "Gamepad2"

    def test_translations_cover_every_key_the_item_uses(self):
        plugin = SteamGamingPlugin()
        item = plugin.get_ui_manifest().menu_items[0]
        translations = plugin.get_translations()
        for lang in ("en", "de"):
            assert item.label_key in translations[lang]
            assert item.description_key in translations[lang]


class TestGamingModeAction:
    async def test_unknown_action_returns_none(self):
        assert await SteamGamingPlugin().run_menu_action("nope", db=None) is None

    async def test_turns_displays_on_then_opens_big_picture(self):
        desktop_patch, service = _patch_desktop(True, "ok")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            return_value=(True, "requested"),
        ) as launcher:
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        service.enable.assert_awaited_once()
        launcher.assert_called_once()
        assert result.ok is True
        assert result.message_key == "menu_gaming_mode_started"

    async def test_does_not_open_big_picture_on_dark_displays(self):
        desktop_patch, _service = _patch_desktop(False, "kscreen-doctor not found")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
        ) as launcher:
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        launcher.assert_not_called()
        assert result.ok is False
        assert result.message_key == "menu_displays_failed"

    async def test_reports_partial_success_when_steam_is_missing(self):
        desktop_patch, _service = _patch_desktop(True, "ok")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            return_value=(False, "steam binary not found"),
        ):
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        assert result.ok is False
        assert result.message_key == "menu_steam_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_plugin.py -q --no-cov -k GamingMode`
Expected: FAIL — `get_ui_manifest()` liefert `None`

- [ ] **Step 3: Implement the menu item and the action**

In `backend/app/plugins/installed/steam_gaming/__init__.py`:

Imports ergänzen:

```python
from app.plugins.base import (
    MenuActionResult,
    PluginBase,
    PluginMenuItem,
    PluginMetadata,
    PluginUIManifest,
    StatusPillSpec,
)
from app.plugins.installed.steam_gaming.launcher import open_big_picture
from app.services.power.desktop import get_desktop_service
```

Konstante neben `_PILL_ID` (Zeile 22):

```python
_MENU_ACTION_ID = "gaming_mode"
```

Methoden in der Klasse ergänzen (nach `collect_status_pill`):

```python
    def get_ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(
            enabled=True,
            menu_items=[PluginMenuItem(
                id=_MENU_ACTION_ID,
                icon="Gamepad2",
                tone="info",
                order=10,
                label_key="menu_gaming_mode",
                label_text="Gaming Mode",
                description_key="menu_gaming_mode_desc",
                description_text="Turn displays on and open Big Picture",
            )],
        )

    async def run_menu_action(self, action_id: str, db: Session) -> Optional[MenuActionResult]:
        if action_id != _MENU_ACTION_ID:
            return None

        # Displays first: opening Big Picture onto dark screens helps nobody.
        # LinuxDesktopBackend.enable() runs kscreen-doctor in a thread, so the
        # core's wait_for stays effective.
        ok, detail = await get_desktop_service().enable()
        if not ok:
            return MenuActionResult(
                ok=False,
                message_key="menu_displays_failed",
                message_text=f"Displays could not be turned on: {detail}",
            )

        launched, detail = await asyncio.to_thread(open_big_picture)
        if not launched:
            return MenuActionResult(
                ok=False,
                message_key="menu_steam_failed",
                message_text=f"Displays are on, but Steam did not start: {detail}",
            )

        # "started", not "Big Picture is running": the process is detached, so
        # anything past the spawn is not observable from here.
        return MenuActionResult(
            ok=True,
            message_key="menu_gaming_mode_started",
            message_text="Gaming mode started",
        )
```

`get_translations()` (Zeile 97-101) erweitern:

```python
    def get_translations(self) -> Optional[Dict[str, Dict[str, str]]]:
        return {
            "en": {
                "pill_name": "Gaming Session",
                "pill_label": "Gaming Session",
                "menu_gaming_mode": "Gaming Mode",
                "menu_gaming_mode_desc": "Displays on + Big Picture",
                "menu_gaming_mode_started": "Gaming mode started",
                "menu_displays_failed": "Displays could not be turned on",
                "menu_steam_failed": "Displays are on, but Steam did not start",
            },
            "de": {
                "pill_name": "Gaming-Session",
                "pill_label": "Gaming-Session",
                "menu_gaming_mode": "Gaming-Modus",
                "menu_gaming_mode_desc": "Displays an + Big Picture",
                "menu_gaming_mode_started": "Gaming-Modus gestartet",
                "menu_displays_failed": "Displays konnten nicht eingeschaltet werden",
                "menu_steam_failed": "Displays sind an, aber Steam startete nicht",
            },
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_plugin.py -q --no-cov`
Expected: PASS (bestehende Pill-Tests + 7 neue)

- [ ] **Step 5: Run the plugin suite for regressions**

Run: `cd backend && python -m pytest tests/plugins -q --no-cov`
Expected: PASS, keine neuen Fehler.

- [ ] **Step 6: Lint + commit**

```bash
cd backend && ruff check app/plugins/installed/steam_gaming/__init__.py tests/plugins/test_steam_gaming_plugin.py
git add backend/app/plugins/installed/steam_gaming/__init__.py backend/tests/plugins/test_steam_gaming_plugin.py
git commit -m "feat(steam-gaming): contribute the Gaming Mode menu action"
```

---

## Task 7: Frontend-Typen und API-Funktion

**Files:**
- Modify: `client/src/api/plugins.ts:7-63` (Typen), Dateiende (Funktion)
- Test: `client/src/__tests__/api/plugins.menuActions.test.ts` (neu)

**Interfaces:**
- Consumes: Route aus Task 3.
- Produces:
```ts
export interface PluginMenuItem {
  id: string; icon: string;
  label_key: string; label_text: string;
  description_key?: string | null; description_text?: string | null;
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
  order: number;
}
export interface PluginMenuActionResult { ok: boolean; message_key?: string | null; message_text: string }
PluginUIInfo.menu_items: PluginMenuItem[]
export async function runPluginMenuAction(pluginName: string, actionId: string): Promise<PluginMenuActionResult>
```

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/api/plugins.menuActions.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: { post: vi.fn() },
}));

import { apiClient } from '../../lib/api';
import { runPluginMenuAction } from '../../api/plugins';

describe('runPluginMenuAction', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts to the namespaced menu-action endpoint', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ok: true, message_key: 'menu_gaming_mode_started', message_text: 'Gaming mode started' },
    });

    const result = await runPluginMenuAction('steam_gaming', 'gaming_mode');

    expect(apiClient.post).toHaveBeenCalledWith('/api/plugins/steam_gaming/menu-actions/gaming_mode');
    expect(result.ok).toBe(true);
    expect(result.message_key).toBe('menu_gaming_mode_started');
  });

  it('returns the failure result unchanged', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ok: false, message_key: 'menu_steam_failed', message_text: 'Steam did not start' },
    });

    expect((await runPluginMenuAction('steam_gaming', 'gaming_mode')).ok).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/api/plugins.menuActions.test.ts`
Expected: FAIL — `runPluginMenuAction is not a function`

- [ ] **Step 3: Add types and the client function**

In `client/src/api/plugins.ts` nach `interface PluginNavItem` (Zeile 13):

```ts
export interface PluginMenuItem {
  id: string;
  icon: string;
  label_key: string;
  label_text: string;
  description_key?: string | null;
  description_text?: string | null;
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
  order: number;
}

export interface PluginMenuActionResult {
  ok: boolean;
  message_key?: string | null;
  message_text: string;
}
```

In `interface PluginUIInfo` nach `nav_items` (Zeile 52):

```ts
  menu_items: PluginMenuItem[];
```

Ans Dateiende:

```ts
/**
 * Run a plugin-contributed system-menu action. Admin only (server-enforced).
 *
 * Resolves with the plugin's own outcome — a failed action is a normal `ok:
 * false` response, not an HTTP error.
 */
export async function runPluginMenuAction(
  pluginName: string,
  actionId: string,
): Promise<PluginMenuActionResult> {
  const res = await apiClient.post<PluginMenuActionResult>(
    `/api/plugins/${pluginName}/menu-actions/${actionId}`,
  );
  return res.data;
}
```

Hinweis: `menu_items` ist im Typ **nicht** optional; ältere Backends liefern das Feld nicht. Der Kontext in Task 8 greift deshalb defensiv über `?? []` zu — genau wie er es heute für `nav_items` tut.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/api/plugins.menuActions.test.ts`
Expected: PASS (2 Tests)

- [ ] **Step 5: Commit**

```bash
git add client/src/api/plugins.ts client/src/__tests__/api/plugins.menuActions.test.ts
git commit -m "feat(plugins): add the menu-action API client"
```

---

## Task 8: `pluginMenuItems` im PluginContext

**Files:**
- Modify: `client/src/contexts/PluginContext.tsx:17-95`
- Test: `client/src/__tests__/contexts/PluginContext.menuItems.test.tsx` (neu)

**Interfaces:**
- Consumes: `PluginMenuItem`, `PluginUIInfo` (Task 7).
- Produces:
```ts
export interface PluginMenuItemWithSource extends PluginMenuItem {
  _pluginName: string;
  _translations?: PluginTranslations;
}
// PluginContextType.pluginMenuItems: PluginMenuItemWithSource[]
```

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/contexts/PluginContext.menuItems.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../lib/features', () => ({ isPi: false }));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ token: 'tok' }) }));
vi.mock('../../api/plugins', () => ({
  listPlugins: vi.fn(),
  getUIManifest: vi.fn(),
}));

import { PluginProvider, usePlugins } from '../../contexts/PluginContext';
import { listPlugins, getUIManifest } from '../../api/plugins';

function Probe() {
  const { pluginMenuItems } = usePlugins();
  return <div data-testid="items">{pluginMenuItems.map((i) => `${i._pluginName}:${i.id}`).join(',')}</div>;
}

const uiPlugin = (name: string, items: unknown[]) => ({
  name, display_name: name, nav_items: [], menu_items: items,
  bundle_path: 'ui/bundle.js', dashboard_widgets: [], granted_api_scopes: [],
  translations: { en: { k: 'v' } },
});

const item = (id: string, order: number) => ({
  id, icon: 'Zap', label_key: 'k', label_text: id, tone: 'neutral', order,
});

describe('PluginContext.pluginMenuItems', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listPlugins as ReturnType<typeof vi.fn>).mockResolvedValue({ plugins: [] });
  });

  it('flattens items across plugins and sorts by order', async () => {
    (getUIManifest as ReturnType<typeof vi.fn>).mockResolvedValue({
      plugins: [uiPlugin('a', [item('late', 50)]), uiPlugin('b', [item('early', 10)])],
    });

    render(<PluginProvider><Probe /></PluginProvider>);

    await waitFor(() => expect(screen.getByTestId('items')).toHaveTextContent('b:early,a:late'));
  });

  it('carries the plugin translations for client-side label resolution', async () => {
    (getUIManifest as ReturnType<typeof vi.fn>).mockResolvedValue({
      plugins: [uiPlugin('a', [item('one', 10)])],
    });

    function TranslationProbe() {
      const { pluginMenuItems } = usePlugins();
      return <div data-testid="tr">{JSON.stringify(pluginMenuItems[0]?._translations ?? null)}</div>;
    }

    render(<PluginProvider><TranslationProbe /></PluginProvider>);

    await waitFor(() => expect(screen.getByTestId('tr')).toHaveTextContent('"k":"v"'));
  });

  it('tolerates a manifest without menu_items', async () => {
    (getUIManifest as ReturnType<typeof vi.fn>).mockResolvedValue({
      plugins: [{ name: 'legacy', display_name: 'Legacy', nav_items: [] }],
    });

    render(<PluginProvider><Probe /></PluginProvider>);

    await waitFor(() => expect(screen.getByTestId('items')).toBeEmptyDOMElement());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/contexts/PluginContext.menuItems.test.tsx`
Expected: FAIL — `pluginMenuItems` ist `undefined`

- [ ] **Step 3: Extend the context**

In `client/src/contexts/PluginContext.tsx`:

Import-Block (Zeile 5-9) erweitern:

```tsx
import type {
  PluginInfo,
  PluginUIInfo,
  PluginNavItem,
  PluginMenuItem,
  PluginTranslations,
} from '../api/plugins';
```

Typ und Kontext-Interface ergänzen (vor `const PluginContext = createContext...`):

```tsx
export interface PluginMenuItemWithSource extends PluginMenuItem {
  _pluginName: string;
  _translations?: PluginTranslations;
}
```

In `interface PluginContextType` nach `pluginNavItems`:

```tsx
  pluginMenuItems: PluginMenuItemWithSource[];
```

Nach der `pluginNavItems`-Ableitung (Zeile 72-85):

```tsx
  // Flatten menu items from all enabled plugins, sorted by order.
  // menu_items may be absent when talking to an older backend.
  const pluginMenuItems: PluginMenuItemWithSource[] = (enabledPlugins ?? [])
    .flatMap((plugin) =>
      (plugin.menu_items ?? []).map((item) => ({
        ...item,
        _pluginName: plugin.name,
        _translations: plugin.translations ?? undefined,
      }))
    )
    .sort((a, b) => a.order - b.order);
```

und in das `value`-Objekt aufnehmen:

```tsx
    pluginMenuItems,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/contexts/PluginContext.menuItems.test.tsx src/__tests__/contexts/PluginContext.externalNav.test.tsx`
Expected: PASS (3 neue + der bestehende Test)

- [ ] **Step 5: Commit**

```bash
git add client/src/contexts/PluginContext.tsx client/src/__tests__/contexts/PluginContext.menuItems.test.tsx
git commit -m "feat(plugins): expose plugin menu items through PluginContext"
```

---

## Task 9: Plugin-Aktionen im PowerMenu

**Files:**
- Modify: `client/src/components/PowerMenu.tsx:1-16` (Imports/State), `:196-216` (Rendering im Admin-Block)
- Modify: `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json` (`powerMenu.pluginActionFailed`)
- Test: `client/src/__tests__/components/PowerMenu.pluginActions.test.tsx` (neu)

**Interfaces:**
- Consumes: `usePlugins().pluginMenuItems` (Task 8), `runPluginMenuAction` (Task 7), `resolveIcon` aus `components/topbar/iconMap` (vorhanden, enthält `Gamepad2` seit Teilprojekt 1), `resolvePluginString` aus `lib/pluginI18n`.
- Produces: nichts.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/PowerMenu.pluginActions.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key: string, def?: string) => def ?? _key }),
}));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/sleep', () => ({
  getSleepStatus: vi.fn(), enterSoftSleep: vi.fn(), enterSuspend: vi.fn(),
}));
vi.mock('../../api/desktop', () => ({
  getDesktopStatus: vi.fn(), disableDesktop: vi.fn(), enableDesktop: vi.fn(),
}));
vi.mock('../../api/plugins', () => ({ runPluginMenuAction: vi.fn() }));

// vi.mock factories are hoisted above this file's const declarations — a plain
// top-level array would hit the temporal dead zone. vi.hoisted lifts the state
// alongside the mock.
const menuItems = vi.hoisted(() => [] as unknown[]);
vi.mock('../../contexts/PluginContext', () => ({
  usePlugins: () => ({ pluginMenuItems: menuItems }),
}));

import PowerMenu from '../../components/PowerMenu';
import { getSleepStatus } from '../../api/sleep';
import { getDesktopStatus } from '../../api/desktop';
import { runPluginMenuAction } from '../../api/plugins';
import toast from 'react-hot-toast';

const baseProps = {
  isAdmin: true,
  onShutdown: vi.fn().mockResolvedValue(undefined),
  onRestart: vi.fn().mockResolvedValue(undefined),
  onLogout: vi.fn(),
};

const gamingItem = {
  id: 'gaming_mode', icon: 'Gamepad2', tone: 'info', order: 10,
  label_key: 'menu_gaming_mode', label_text: 'Gaming Mode',
  description_key: 'menu_gaming_mode_desc', description_text: 'Displays on + Big Picture',
  _pluginName: 'steam_gaming',
  _translations: { en: { menu_gaming_mode: 'Gaming Mode' } },
};

function setItems(items: unknown[]) {
  menuItems.length = 0;
  menuItems.push(...items);
}

const openMenu = () => fireEvent.click(screen.getByTitle('Power'));

describe('PowerMenu — plugin menu actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getSleepStatus as ReturnType<typeof vi.fn>).mockResolvedValue({});
    (getDesktopStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped', display_manager: 'sddm', detail: null,
    });
    setItems([gamingItem]);
  });

  it('renders a plugin action with its resolved label', async () => {
    render(<PowerMenu {...baseProps} />);
    openMenu();
    expect(await screen.findByText('Gaming Mode')).toBeInTheDocument();
  });

  it('posts to the right plugin and action on click', async () => {
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true, message_key: null, message_text: 'Gaming mode started',
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByText('Gaming Mode'));

    await waitFor(() =>
      expect(runPluginMenuAction).toHaveBeenCalledWith('steam_gaming', 'gaming_mode'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Gaming mode started'));
  });

  it('shows an error toast when the action reports ok:false', async () => {
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false, message_key: null, message_text: 'Steam did not start',
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByText('Gaming Mode'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Steam did not start'));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('shows an error toast when the request itself fails', async () => {
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network'));
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByText('Gaming Mode'));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it('renders an item whose icon is unknown instead of crashing', async () => {
    setItems([{ ...gamingItem, icon: 'NotARealIcon' }]);
    render(<PowerMenu {...baseProps} />);
    openMenu();
    expect(await screen.findByText('Gaming Mode')).toBeInTheDocument();
  });

  it('renders no plugin actions for a non-admin', async () => {
    render(<PowerMenu {...baseProps} isAdmin={false} />);
    openMenu();
    expect(screen.queryByText('Gaming Mode')).not.toBeInTheDocument();
  });

  it('locks the plugin actions while one is running', async () => {
    let resolveAction!: (value: unknown) => void;
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((resolve) => { resolveAction = resolve; }),
    );
    render(<PowerMenu {...baseProps} />);
    openMenu();
    const button = (await screen.findByText('Gaming Mode')).closest('button')!;
    fireEvent.click(button);

    await waitFor(() => expect(button).toBeDisabled());

    resolveAction({ ok: true, message_key: null, message_text: 'done' });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('done'));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/PowerMenu.pluginActions.test.tsx`
Expected: FAIL — „Gaming Mode" wird nicht gerendert

- [ ] **Step 3: Add the i18n fallback key**

In `client/src/i18n/locales/de/common.json` im Block `"powerMenu"`:

```json
    "pluginActionFailed": "Aktion fehlgeschlagen",
```

In `client/src/i18n/locales/en/common.json` im selben Block:

```json
    "pluginActionFailed": "Action failed",
```

- [ ] **Step 4: Render and wire the actions**

In `client/src/components/PowerMenu.tsx`:

Imports ergänzen:

```tsx
import { usePlugins } from '../contexts/PluginContext';
import { runPluginMenuAction } from '../api/plugins';
import { resolvePluginString } from '../lib/pluginI18n';
import { resolveIcon } from './topbar/iconMap';
```

und `Plug` in den **vorhandenen** `lucide-react`-Import (Zeile 3) aufnehmen — keinen zweiten Import derselben Quelle anlegen.

State und Handler in der Komponente (nach `const [desktopState, ...]`):

```tsx
  const { pluginMenuItems } = usePlugins();
  const [runningAction, setRunningAction] = useState<string | null>(null);

  const handlePluginAction = async (item: (typeof pluginMenuItems)[number]) => {
    const key = `${item._pluginName}:${item.id}`;
    setRunningAction(key);
    try {
      const result = await runPluginMenuAction(item._pluginName, item.id);
      const message = resolvePluginString(
        item._translations,
        result.message_key ?? '',
        result.message_text,
      );
      if (result.ok) {
        toast.success(message);
        setIsOpen(false);
      } else {
        toast.error(message);
      }
    } catch {
      toast.error(t('powerMenu.pluginActionFailed', 'Action failed'));
    } finally {
      setRunningAction(null);
    }
  };
```

Rendering im Admin-Block, direkt **nach** dem `desktopState === 'stopped'`-Button (Zeile 198-211) und **vor** dem schließenden `</div>` des `p-1.5`-Containers:

```tsx
                  {pluginMenuItems.map((item) => {
                    const Icon = resolveIcon(item.icon) ?? Plug;
                    const key = `${item._pluginName}:${item.id}`;
                    const label = resolvePluginString(item._translations, item.label_key, item.label_text);
                    const description = item.description_key
                      ? resolvePluginString(item._translations, item.description_key, item.description_text ?? '')
                      : item.description_text;
                    return (
                      <button
                        key={key}
                        onClick={() => { void handlePluginAction(item); }}
                        disabled={runningAction !== null}
                        className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-sky-500/10 disabled:opacity-50"
                      >
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-sky-500/30 bg-sky-500/10">
                          <Icon className="h-4 w-4 text-sky-400" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-slate-100">{label}</p>
                          {description && <p className="text-xs text-slate-400">{description}</p>}
                        </div>
                      </button>
                    );
                  })}
```

Der Block steht innerhalb von `{isAdmin && (...)}` — Nicht-Admins sehen ihn dadurch gar nicht, und die Route lehnt sie ohnehin ab.

- [ ] **Step 5: Fix the existing PowerMenu suite — it WILL break**

`PowerMenu` ruft nach diesem Task `usePlugins()` unconditional auf; die bestehende Suite `src/__tests__/components/PowerMenu.test.tsx` rendert ohne Provider und wirft „usePlugins must be used within a PluginProvider". In dieser Datei nach den vorhandenen `vi.mock`-Blöcken (Zeile 19-23) ergänzen:

```tsx
vi.mock('../../contexts/PluginContext', () => ({
  usePlugins: () => ({ pluginMenuItems: [] }),
}));
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/components/PowerMenu.pluginActions.test.tsx src/__tests__/components/PowerMenu.test.tsx`
Expected: PASS (7 neue Tests + die bestehende PowerMenu-Suite unverändert grün).

- [ ] **Step 7: Commit**

```bash
git add client/src/components/PowerMenu.tsx client/src/i18n/locales/de/common.json client/src/i18n/locales/en/common.json client/src/__tests__/components/PowerMenu.pluginActions.test.tsx client/src/__tests__/components/PowerMenu.test.tsx
git commit -m "feat(power-menu): render plugin-contributed menu actions"
```

---

## Task 10: Doku, Gates und Smoketest

**Files:**
- Modify: `backend/app/plugins/CLAUDE.md` (Extension-Point + Operator-Note)

**Interfaces:**
- Consumes: alles Vorige.
- Produces: nichts.

- [ ] **Step 1: Document the extension point**

In `backend/app/plugins/CLAUDE.md`, in „Creating a Plugin" nach Punkt 6 (den Status-Pills) als Punkt 7:

```markdown
7. Override `get_ui_manifest()` with `menu_items` + `run_menu_action()` to
   contribute an action to the system (power) menu. The plugin picks only a
   local `id` (validated against `^[a-z0-9_]+$`); the core enforces the admin
   gate, the rate limit, the audit entry, a declaration check (an `action_id`
   not present in `get_menu_items()` is a 404 and never dispatches) and a
   `PLUGIN_MENU_ACTION_TIMEOUT_SECONDS` (20s) timeout. `PluginMenuItem`
   deliberately has **no** `admin_only` field — unlike `PluginNavItem`, an
   action executes something, so its audience is not the plugin's call.
   Failures and timeouts become `ok=false` with a generic message; details
   stay in the log. Labels come from `get_translations()`, resolved
   client-side via `resolvePluginString`. Blocking work belongs in
   `asyncio.to_thread`, otherwise the timeout cannot take effect.
   Disabled plugins are rejected by `PluginGateMiddleware` (403, DB-backed) —
   `menu-actions` is intentionally **not** a management route.
```

Die vorhandene **Operator note** im selben Abschnitt so erweitern, dass sie Menü-Aktionen einschließt:

```markdown
   **Operator note:** `PluginManager._enabled` is process-local, populated at
   startup. Toggling a pill- or menu-contributing plugin on/off through the UI
   only updates the worker that handled that request — in production (4 Uvicorn
   workers) the pill then appears on roughly one in four status-strip polls, and
   a menu action fails with 404 on the three workers that never loaded it, until
   the backend is restarted. Restart `baluhost-backend` after enabling or
   disabling such a plugin so all workers agree (#448).
```

- [ ] **Step 2: Run the full backend gates**

```bash
cd backend
python -m pytest tests/plugins tests/test_session_env.py tests/test_desktop_backend.py tests/test_desktop_routes.py -q --no-cov
ruff check app tests
```
Expected: alles grün.

- [ ] **Step 3: Run the full frontend gates**

```bash
cd client
npx vitest run
npx eslint .
npm run build
```
Expected: Tests grün, ESLint 0 Fehler, Build erfolgreich.

- [ ] **Step 4: Dev-mode smoketest (Windows)**

1. `python start_dev.py`, als Admin anmelden (`admin` / `DevMode2024`).
2. Plugin-Verwaltung öffnen, `steam_gaming` aktivieren (falls nicht aktiv).
3. Power-Menü öffnen → Eintrag **„Gaming-Modus"** mit Gamepad-Icon erscheint
   unter den Desktop-Einträgen.
4. Klicken → Erfolgs-Toast „Gaming-Modus gestartet"; das Menü schließt.
   (Dev-Modus: `DevDesktopBackend` und Launcher sind no-ops.)
5. Sprache auf Englisch stellen, Menü erneut öffnen → „Gaming Mode".
6. Als Nicht-Admin anmelden → das Power-Menü zeigt nur „Logout", kein
   Plugin-Eintrag.
7. `steam_gaming` deaktivieren, Backend neu starten, Menü öffnen → Eintrag weg.

- [ ] **Step 5: Production smoketest on BaluNode — the open measurement**

**Das ist der Schritt, der die Annahme prüft, auf der die ganze Aktionswahl
steht.** Vor dem Merge auf der Box ausführen:

1. Displays per Power-Menü ausschalten („Desktop deaktivieren").
2. Prüfen, dass Steam läuft: `systemctl --user status app-steam@autostart.service`
3. Den Aufruf **von Hand** gegen die laufende Instanz testen:
   `XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 steam steam://open/bigpicture`
   Erwartet: Steam wechselt in den Big-Picture-Modus, das Kommando kehrt sofort zurück.
4. Hält das **nicht**: Fund melden und `BIG_PICTURE_URL`/argv in
   `launcher.py` auf die Variante ändern, die auf der Box wirkt (Kandidaten:
   `steam -bigpicture`, oder `steam` ohne Argument, das nur das Fenster nach
   vorn holt). Nur diese eine Stelle ändert sich — Extension-Point, Route und
   Frontend bleiben unberührt. Testerwartung in
   `test_steam_gaming_launcher.py` mitziehen.
5. Displays wieder aus, dann im Web-UI „Gaming-Modus" klicken → Displays gehen
   an **und** Big Picture erscheint; Toast meldet Erfolg.
6. Audit-Log prüfen (Admin → Logging): Eintrag `menu_action` mit Ressource
   `steam_gaming:gaming_mode` und `success=true`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/CLAUDE.md
git commit -m "docs(plugins): document the menu-action extension point"
```

---

## Self-Review

**Spec-Abdeckung:**

| Spec-Anforderung | Task |
|---|---|
| `PluginMenuItem` mit id/icon/label_key/label_text/description/tone/order | 1 |
| Kein `admin_only` am Menü-Item (Core erzwingt Admin) | 1 (Test), 3 (Route) |
| `MenuActionResult` mit key + Literal-Fallback | 1 |
| `get_menu_items()` / `run_menu_action()` auf `PluginBase` | 1 |
| `menu_items` reisen im vorhandenen `/ui/manifest` mit | 2 |
| Route `POST /{name}/menu-actions/{action_id}`, Admin, Ratelimit, Audit | 3 |
| Deklarationsprüfung (404, kein Dispatch) | 3 |
| Exception/Timeout → `ok=false`, keine Interna, nie 5xx | 3 |
| `PluginGateMiddleware` blockt deaktivierte Plugins (403) | 3 (Regressionstest) |
| Audit nach Ausführung mit `success=ok` | 3 |
| Gemeinsamer Session-Env-Helper | 4 |
| Displays-an vor Big Picture, Abbruch bei Fehlschlag | 6 |
| Abgekoppelter Start, kein `wait()` | 5 |
| Teilerfolg als Teilerfolg melden | 6 |
| Dev-Modus klickbar ohne Linux | 5 (Launcher), 9 (Smoketest) |
| Frontend: Flatten + Sortierung, Translations mitführen | 8 |
| Frontend: Icon-Allowlist mit Fallback | 9 |
| Frontend: Sperre während des Laufs | 9 |
| Frontend: Toast bei beiden Ausgängen | 9 |
| Kein zusätzlicher Desktop-Status-Refetch | 9 (bewusst nicht implementiert) |
| Offener Messpunkt `steam://open/bigpicture` | 10, Step 5 |
| Operator-Note #448 auf Menü-Aktionen erweitert | 10 |

**Platzhalter-Scan:** keine TBD/TODO; jeder Code-Schritt enthält den vollständigen Code, jeder Test-Schritt den vollständigen Test.

**Typ-Konsistenz:** `PluginMenuItem` (Python) ↔ `PluginMenuItemSchema` (Schema) ↔ `PluginMenuItem` (TS) tragen dieselben Feldnamen; `MenuActionResult` ↔ `PluginMenuActionResponse` ↔ `PluginMenuActionResult` ebenfalls (`ok`, `message_key`, `message_text`). `_MENU_ACTION_ID = "gaming_mode"` wird in Task 6 gesetzt und in den Tests von Task 6 und 9 identisch verwendet. `run_menu_action(action_id, db)` hat in Base (Task 1), Route (Task 3) und Plugin (Task 6) dieselbe Signatur. `_pluginName`/`_translations` sind in Task 8 definiert und in Task 9 identisch benutzt.

**Bewusste Nicht-Ziele, die kein Task ist:** kein „Gaming-Modus beenden", kein feineres Berechtigungsmodell, keine Zustandsanzeige im Menüpunkt, kein Bestätigungsdialog, keine Migration, keine Menü-Aktionen für externe (sandboxed) Plugins.
