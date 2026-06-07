# TUI Companion Rebuild — Destructive Ops (Plan 5 of N) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable confirmation dialog and wire up the first destructive operations: app restart/shutdown (Power screen) and local-channel RAID array deletion (RAID screen, replacing the legacy token-confirm flow and dropping `get_context`).

**Architecture:** A `ConfirmDialog` modal (with optional type-to-confirm for dangerous actions) is shared by the Power and RAID screens. `api/system.py` gains `delete_array()` (the `require_local_admin` direct endpoint — the TUI is local-channel, so it can call it where a browser cannot). The Power screen adds Restart/Shutdown buttons (reusing the existing `restart_app`/`shutdown_app` wrappers). The RAID screen is rewritten to read status via the existing `raid_status()` wrapper and delete via `delete_array()` behind `ConfirmDialog`, eliminating its `get_context` hybrid + in-memory token dance.

**Tech Stack:** Python 3.11, Textual, httpx 0.27, pytest. Builds on Plans 1–4 (`BackendClient`, `api/system` `restart_app`/`shutdown_app`/`raid_status`). Spec: `docs/superpowers/specs/2026-06-07-tui-companion-rebuild-design.md`.

---

## Context for the implementer

- The TUI runs on the **local channel**, so it may call `require_local_admin` endpoints (`POST /api/system/raid/delete-array`) directly. The old `raid.py` used a `confirm/request`+`confirm/execute` token flow that exists only because the *web* UI is remote — the TUI does not need it.
- Verified backend endpoints:
  - `POST /api/system/raid/delete-array` — auth `require_local_admin`, body `{"array": str, "force": bool=false}`, returns `{"message": str}`. On a remote channel it returns 403 `{"detail": {"error": "local_channel_required", "message": "..."}}`.
  - `POST /api/system/restart` and `POST /api/system/shutdown` — auth `get_current_admin`, no body, return `{"message": str, ...}`. Already wrapped by `api.system.restart_app`/`shutdown_app` (Plan 1).
  - `GET /api/system/raid/status` — already wrapped by `api.system.raid_status` (Plan 3) → `list[dict]` with `name/level/status/devices[].name`.
- `api/system.py` already defines a `_Client` Protocol with `get`/`post` and imports `Any`/`Protocol`. `delete_array` reuses them.
- The TUI is admin-only (the login screen enforces the admin role), and every screen action is reached only when `current_user` is set, so the screens need no extra role gate — the server enforces `require_local_admin` regardless.
- Textual modal pattern: `self.app.push_screen(SomeModal(...), callback)` — `callback(result)` runs with whatever `self.dismiss(result)` passed. The existing user/log dialogs use exactly this.
- Tests use the inline `_Resp`/`_FakeClient` pattern. Run from `backend/`: `python -m pytest tests/tui/<file> -v --no-cov`.
- Shell is PowerShell: chain with `;` / `if ($?) { ... }`. Hook blocks grep/rg + the Grep tool — use Read/Glob. Worktree `D:\Programme (x86)\Baluhost\.claude\worktrees\feat+tui-companion-rebuild`; confirm `git branch --show-current` is `feat/tui-companion-rebuild` before each commit.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/baluhost_tui/widgets/__init__.py` | Create | package marker |
| `backend/baluhost_tui/widgets/confirm.py` | Create | `ConfirmDialog` modal + `confirm_matches()` pure helper |
| `backend/tests/tui/test_confirm.py` | Create | tests for `confirm_matches` |
| `backend/baluhost_tui/api/system.py` | Modify (append) | `delete_array(client, array, force=False) -> (ok, msg)` |
| `backend/tests/tui/test_api_system_delete_array.py` | Create | tests for `delete_array` |
| `backend/baluhost_tui/screens/power.py` | Modify | Restart/Shutdown buttons + ConfirmDialog wiring |
| `backend/baluhost_tui/screens/raid.py` | Rewrite | status via `raid_status`, delete via `delete_array` + ConfirmDialog; drop `get_context`/token flow |

Out of scope (later plans): users **bulk-delete** (needs multi-select UI) and RAID **create-array**/**format-disk** (need disk-selection forms) → next plan; removal of `context.py` (still imported by the CLI commands `commands/status.py` + `commands/users.py`, which are not ported here) → deferred until those CLI commands are addressed.

---

## Task 1: `ConfirmDialog` modal + `confirm_matches()` helper

**Files:**
- Create: `backend/baluhost_tui/widgets/__init__.py`
- Create: `backend/baluhost_tui/widgets/confirm.py`
- Test: `backend/tests/tui/test_confirm.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tui/test_confirm.py`:

```python
"""Tests for the type-to-confirm helper used by ConfirmDialog."""
from __future__ import annotations

from baluhost_tui.widgets.confirm import confirm_matches


def test_exact_match():
    assert confirm_matches("md0", "md0") is True


def test_trims_whitespace_around_typed():
    assert confirm_matches("md0", "  md0  ") is True


def test_mismatch():
    assert confirm_matches("md0", "md1") is False


def test_empty_typed_against_nonempty_expected():
    assert confirm_matches("md0", "") is False


def test_case_sensitive():
    assert confirm_matches("md0", "MD0") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend ; python -m pytest tests/tui/test_confirm.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'baluhost_tui.widgets'`.

- [ ] **Step 3: Implement**

Create `backend/baluhost_tui/widgets/__init__.py`:

```python
"""Reusable Textual widgets/modals for the TUI."""
```

Create `backend/baluhost_tui/widgets/confirm.py`:

```python
"""Reusable confirmation modal for destructive actions.

ConfirmDialog dismisses True on confirm, False on cancel. When require_text is
given, the Confirm button only proceeds if the user types that exact phrase
(type-to-confirm) — used for the most dangerous operations.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Label, Button, Input
from textual.binding import Binding


def confirm_matches(expected: str, typed: str) -> bool:
    """True when *typed* (trimmed) exactly equals *expected* (case-sensitive)."""
    return typed.strip() == expected


class ConfirmDialog(ModalScreen):
    """Yes/No confirmation modal. dismiss(True) on confirm, dismiss(False) otherwise."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    ConfirmDialog { align: center middle; }
    #confirm-box {
        width: 64;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    #confirm-title { text-style: bold; color: $error; margin-bottom: 1; }
    #confirm-message { margin-bottom: 1; }
    Input { width: 1fr; margin-bottom: 1; }
    .button-row { height: auto; align: center middle; }
    Button { margin: 0 1; }
    """

    def __init__(
        self,
        title: str,
        message: str,
        confirm_label: str = "Confirm",
        require_text: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_label = confirm_label
        self._require_text = require_text

    def compose(self) -> ComposeResult:
        with Container(id="confirm-box"):
            yield Label(self._title, id="confirm-title")
            yield Label(self._message, id="confirm-message")
            if self._require_text is not None:
                yield Label(f"Type [b]{self._require_text}[/b] to confirm:")
                yield Input(id="confirm-input")
            with Horizontal(classes="button-row"):
                yield Button(self._confirm_label, variant="error", id="confirm-yes")
                yield Button("Cancel", variant="default", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-no":
            self.dismiss(False)
        elif event.button.id == "confirm-yes":
            if self._require_text is not None:
                typed = self.query_one("#confirm-input", Input).value
                if not confirm_matches(self._require_text, typed):
                    self.notify("Confirmation text does not match", severity="error")
                    return
            self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend ; python -m pytest tests/tui/test_confirm.py -v --no-cov`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```
git add backend/baluhost_tui/widgets/__init__.py backend/baluhost_tui/widgets/confirm.py backend/tests/tui/test_confirm.py
git commit -m "feat(tui): ConfirmDialog modal + confirm_matches type-to-confirm helper"
```

---

## Task 2: `api/system.delete_array()`

**Files:**
- Modify (append): `backend/baluhost_tui/api/system.py`
- Test: `backend/tests/tui/test_api_system_delete_array.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tui/test_api_system_delete_array.py`:

```python
"""Tests for delete_array() in baluhost_tui.api.system."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.system import delete_array


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.responses: dict[str, _Resp] = {}

    def post(self, path: str, json: Any = None, **_: Any) -> _Resp:
        self.calls.append((path, json))
        return self.responses.get(path, _Resp(200, {"message": "Array deleted"}))


def test_delete_array_posts_correct_body_and_reports_ok():
    c = _Client()
    ok, msg = delete_array(c, "md0")
    assert ok is True
    assert c.calls == [("/api/system/raid/delete-array", {"array": "md0", "force": False})]
    assert "deleted" in msg.lower()


def test_delete_array_passes_force():
    c = _Client()
    delete_array(c, "md0", force=True)
    _, body = c.calls[0]
    assert body == {"array": "md0", "force": True}


def test_delete_array_reports_failure_with_detail():
    c = _Client()
    c.responses["/api/system/raid/delete-array"] = _Resp(409, {"detail": "array busy"})
    ok, msg = delete_array(c, "md0")
    assert ok is False
    assert "busy" in msg.lower() or "409" in msg


def test_delete_array_handles_local_channel_dict_detail():
    c = _Client()
    c.responses["/api/system/raid/delete-array"] = _Resp(
        403, {"detail": {"error": "local_channel_required", "message": "Companion app only"}}
    )
    ok, msg = delete_array(c, "md0")
    assert ok is False
    assert "companion" in msg.lower() or "local_channel" in msg.lower()


def test_delete_array_wraps_transport_error():
    class _Boom:
        def post(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    ok, msg = delete_array(_Boom(), "md0")
    assert ok is False
    assert "failed" in msg.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend ; python -m pytest tests/tui/test_api_system_delete_array.py -v --no-cov`
Expected: FAIL with `ImportError: cannot import name 'delete_array'`.

- [ ] **Step 3: Implement (append to `backend/baluhost_tui/api/system.py`)**

```python
def delete_array(client: _Client, array: str, force: bool = False) -> tuple[bool, str]:
    """POST /api/system/raid/delete-array (local-channel) -> (ok, message).

    On a remote channel the backend returns 403 with a dict detail
    {error, message}; that message is surfaced to the user.
    """
    try:
        resp = client.post(
            "/api/system/raid/delete-array", json={"array": array, "force": force}
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("error") or str(detail)
            msg = f"HTTP {resp.status_code}: {detail}".rstrip().rstrip(":").rstrip()
            return False, msg or f"HTTP {resp.status_code}"
        try:
            return True, resp.json().get("message", "Array deleted")
        except Exception:
            return True, "Array deleted"
    except Exception as exc:
        return False, f"request failed: {exc}"
```

Note: `api/system.py` already imports `Any`/`Protocol` and defines `_Client` with `post` — no new imports.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend ; python -m pytest tests/tui/test_api_system_delete_array.py -v --no-cov`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```
git add backend/baluhost_tui/api/system.py backend/tests/tui/test_api_system_delete_array.py
git commit -m "feat(tui): api.system.delete_array() (local-channel RAID delete)"
```

---

## Task 3: Power screen — Restart/Shutdown buttons behind ConfirmDialog

**Files:**
- Modify: `backend/baluhost_tui/screens/power.py`

- [ ] **Step 1: Add the imports**

In `backend/baluhost_tui/screens/power.py`, replace:

```python
from textual.binding import Binding


_ACTIONS: dict[str, str] = {
```

with:

```python
from textual.binding import Binding

from baluhost_tui.api import system as system_api
from baluhost_tui.widgets.confirm import ConfirmDialog


_ACTIONS: dict[str, str] = {
```

- [ ] **Step 2: Add the Restart/Shutdown button row to `compose`**

Replace:

```python
            with Horizontal(classes="power-row"):
                yield Button("Sleep", id="btn-soft", variant="primary")
                yield Button("Wake", id="btn-wake", variant="success")
                yield Button("Suspend", id="btn-suspend", variant="warning")
                yield Button("WoL", id="btn-wol", variant="default")
        yield Footer()
```

with:

```python
            with Horizontal(classes="power-row"):
                yield Button("Sleep", id="btn-soft", variant="primary")
                yield Button("Wake", id="btn-wake", variant="success")
                yield Button("Suspend", id="btn-suspend", variant="warning")
                yield Button("WoL", id="btn-wol", variant="default")
            with Horizontal(classes="power-row"):
                yield Button("Restart App", id="btn-restart-app", variant="warning")
                yield Button("Shutdown App", id="btn-shutdown-app", variant="error")
        yield Footer()
```

- [ ] **Step 3: Include the new buttons in the no-token disable loop**

Replace:

```python
            for btn_id in ("btn-soft", "btn-wake", "btn-suspend", "btn-wol"):
```

with:

```python
            for btn_id in ("btn-soft", "btn-wake", "btn-suspend", "btn-wol", "btn-restart-app", "btn-shutdown-app"):
```

- [ ] **Step 4: Handle the new buttons in `on_button_pressed` + add `_confirm_lifecycle`**

Replace the entire `on_button_pressed` method:

```python
    def on_button_pressed(self, event: Button.Pressed) -> None:
        action_map = {"btn-soft": "soft", "btn-wake": "wake", "btn-suspend": "suspend", "btn-wol": "wol"}
        action = action_map.get(event.button.id or "")
        if not action:
            return
        ok, msg = perform_action(self.app.client, action)
        self.notify(msg, severity="information" if ok else "error")
        if ok:
            self.refresh_status()
```

with:

```python
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "btn-restart-app":
            self._confirm_lifecycle(
                "Restart App",
                "Restart the BaluHost backend service? Active connections drop briefly.",
                system_api.restart_app,
            )
            return
        if bid == "btn-shutdown-app":
            self._confirm_lifecycle(
                "Shutdown App",
                "Stop the BaluHost backend service? The API goes offline until restarted.",
                system_api.shutdown_app,
            )
            return
        action_map = {"btn-soft": "soft", "btn-wake": "wake", "btn-suspend": "suspend", "btn-wol": "wol"}
        action = action_map.get(bid)
        if not action:
            return
        ok, msg = perform_action(self.app.client, action)
        self.notify(msg, severity="information" if ok else "error")
        if ok:
            self.refresh_status()

    def _confirm_lifecycle(self, title: str, message: str, fn) -> None:
        """Push a ConfirmDialog; on confirm call fn(client) and notify the result."""
        def _cb(confirmed):
            if not confirmed:
                return
            ok, msg = fn(self.app.client)
            self.notify(msg, severity="information" if ok else "error")

        self.app.push_screen(
            ConfirmDialog(title=title, message=message, confirm_label=title), _cb
        )
```

- [ ] **Step 5: Import-smoke + tests**

Run: `cd backend ; python -c "import baluhost_tui.screens.power; print('OK')" ; if ($?) { python -m pytest tests/tui/test_power_screen.py -v --no-cov }`
Expected: `OK` and the existing power tests still PASS (they cover `fetch_status`/`perform_action`, which are unchanged).

- [ ] **Step 6: Commit**

```
git add backend/baluhost_tui/screens/power.py
git commit -m "feat(tui): Power screen app-restart/shutdown behind ConfirmDialog"
```

---

## Task 4: Rewrite the RAID screen (status + local-channel delete)

**Files:**
- Rewrite: `backend/baluhost_tui/screens/raid.py`

The new screen reads status via `api.system.raid_status` and deletes via `api.system.delete_array` behind a type-to-confirm `ConfirmDialog`. It no longer imports `get_context` and drops the `confirm/request`+`execute` token flow (a remote-only workaround the local-channel TUI doesn't need). `app.py`'s `action_raid` already constructs `RaidControlScreen()` with no args — that stays valid.

- [ ] **Step 1: Replace `backend/baluhost_tui/screens/raid.py` entirely with:**

```python
"""RAID control screen — status + local-channel array deletion."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, DataTable, Label
from textual.binding import Binding

from baluhost_tui.api import system as system_api
from baluhost_tui.widgets.confirm import ConfirmDialog


class RaidControlScreen(Screen):
    """List RAID arrays; press 'd' to delete the selected array (local channel)."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("d", "delete_array", "Delete Array"),
    ]

    CSS = """
    #raid-container { padding: 1 2; }
    #raid-title { text-style: bold; color: $accent; margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="raid-container"):
            yield Label("🛡️  RAID Controls (d = delete array)", id="raid-title")
            yield DataTable(id="raid-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#raid-table", DataTable)
        table.add_columns("Name", "Level", "Status", "Devices")
        table.cursor_type = "row"
        self.load_status()

    def load_status(self) -> None:
        table = self.query_one("#raid-table", DataTable)
        table.clear()
        arrays = system_api.raid_status(self.app.client)
        if not arrays:
            table.add_row("(none)", "-", "-", "-", key="__empty__")
            return
        for a in arrays:
            devices = ", ".join(d.get("name", "?") for d in a.get("devices", []))
            name = str(a.get("name", "?"))
            table.add_row(
                name,
                str(a.get("level", "?")),
                str(a.get("status", "?")),
                devices,
                key=name,
            )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_status()

    def action_delete_array(self) -> None:
        table = self.query_one("#raid-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("Select an array first", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            array = str(row[0])
        except Exception:
            self.notify("Select an array first", severity="warning")
            return
        if array in ("(none)", "", "__empty__"):
            self.notify("No array selected", severity="warning")
            return

        def _cb(confirmed):
            if not confirmed:
                return
            ok, msg = system_api.delete_array(self.app.client, array)
            self.notify(f"{array}: {msg}", severity="information" if ok else "error")
            if ok:
                self.load_status()

        self.app.push_screen(
            ConfirmDialog(
                title="⚠️  Delete RAID Array",
                message=f"This permanently destroys array '{array}'. This cannot be undone.",
                confirm_label="Delete Array",
                require_text=array,
            ),
            _cb,
        )
```

- [ ] **Step 2: Import-smoke + confirm `get_context` is gone from raid.py**

Run: `cd backend ; python -c "import baluhost_tui.screens.raid, baluhost_tui.app; print('OK')"`
Expected: `OK`.

Read the file and confirm NO `get_context`, `baluhost_tui.context`, `time`, `import sys`, or `sys.path.insert` references remain.

- [ ] **Step 3: Run the full suite + commit**

Run: `cd backend ; python -m pytest tests/tui/ --no-cov -q`
Expected: all pass.

```
git add backend/baluhost_tui/screens/raid.py
git commit -m "refactor(tui): RAID screen — direct local-channel delete + ConfirmDialog (drop get_context/token)"
```

---

## Task 5: Full-suite verification

**Files:** none changed.

- [ ] **Step 1: Run the full TUI suite**

Run: `cd backend ; python -m pytest tests/tui/ -v --no-cov`
Expected: all pass. New: `test_confirm.py` (5), `test_api_system_delete_array.py` (5). Everything else unchanged and green.

- [ ] **Step 2: Import-smoke the whole package**

Run: `cd backend ; python -c "import baluhost_tui.app, baluhost_tui.main, baluhost_tui.screens.power, baluhost_tui.screens.raid; from baluhost_tui.widgets.confirm import ConfirmDialog, confirm_matches; from baluhost_tui.api.system import delete_array; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Confirm `get_context` no longer used by raid.py**

Run (PowerShell): `cd backend ; if (Select-String -Path baluhost_tui/screens/raid.py -Pattern "get_context|baluhost_tui.context" -Quiet) { Write-Output "STILL USES get_context" } else { Write-Output "clean" }`
Expected: `clean`. (Note: `context.py` itself stays — `commands/status.py` and `commands/users.py` still import it; their port is a separate future task.)

- [ ] **Step 4: Manual smoke (optional, dev)**

With `python start_dev.py` running, `cd backend ; python -m baluhost_tui dashboard`, log in as `admin`/`DevMode2024`. Open Power (`p`): the two new buttons (Restart App / Shutdown App) appear; clicking one shows a ConfirmDialog, Cancel does nothing. Open RAID (`R` from the app binding): arrays list (dev-mode mocks); press `d` on a selected array → ConfirmDialog requires typing the array name; a non-matching entry is rejected, the exact name deletes it (dev-storage sandbox) and the list refreshes. No commit.

---

## Self-Review

**1. Spec coverage (this plan's slice — destructive ops):**
- Spec "destructive-ops UX: ConfirmDialog, type-to-confirm for dangerous ops" → Task 1. ✓
- Spec "Power: app restart/shutdown" → Task 3 (reusing `restart_app`/`shutdown_app`). ✓
- Spec "RAID destructive: delete-array via local-channel" → Tasks 2 + 4. ✓
- Deferred (stated): RAID create-array/format-disk + users bulk-delete (form/multi-select UI) → next plan; `context.py` removal (blocked by CLI commands) → deferred.

**2. Placeholder scan:** No TBD/TODO; every code step shows complete content; every run step has exact command + expected output. ✓

**3. Type/consistency checks:**
- `ConfirmDialog(title, message, confirm_label, require_text=None)` dismisses `True`/`False`; both `power.py` (`_confirm_lifecycle` callback) and `raid.py` (`_cb`) consume that boolean. ✓
- `confirm_matches(expected, typed) -> bool` is used inside `ConfirmDialog.on_button_pressed` and tested directly. ✓
- `delete_array(client, array, force=False) -> (bool, str)` matches the raid `_cb` consumption; reuses the existing `_Client` Protocol (post). ✓
- `raid_status` (Plan 3) returns `list[dict]` — `load_status` iterates dicts with `name/level/status/devices[].name`. ✓
- `restart_app`/`shutdown_app` (Plan 1) take `client` → `(ok,msg)`; `_confirm_lifecycle` calls `fn(self.app.client)`. ✓
- `app.py action_raid` still does `RaidControlScreen()` no-arg; the rewrite has no `__init__` requiring args. ✓

**4. Behavioral notes:**
- RAID delete now uses type-to-confirm (must type the array name) — stronger than the old token flow's implicit confirmation.
- App restart/shutdown are `get_current_admin` (not local-channel-exclusive); a simple yes/no confirm (no type-to-confirm) is sufficient.
- `raid.py` no longer imports `get_context`; `context.py` persists only for the two CLI commands.

---

## Next plans (outline)

- **Plan 6 — Form-based destructive ops:** RAID **create-array** (name/level/device-selection form) + **format-disk** (disk + filesystem form); users **bulk-delete** (DataTable multi-select). All behind `ConfirmDialog`.
- **Plan 7 — New read screens + cleanup:** plugins (install/uninstall), vpn (read + sync-server-keys), network, settings; port the CLI `status`/`users` commands off `context.py` then delete `context.py`; `BaseScreen`; centralize `sys.path`; fix welcome version; update `TUI_FEATURE_AUDIT.md`.
