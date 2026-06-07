# TUI Companion Rebuild — Transport Cutover (Plan 2 of N) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the TUI over to the `BackendClient` transport: the app builds one client (UDS in prod / TCP loopback in dev), login authenticates via JWT (no more direct DB), and the three already-API screens (services, smart, power) run through that client; the file-browser screen is removed.

**Architecture:** `main.py` builds a `BackendClient` and hands it to `BaluHostApp`, which holds it as `self.client`. `LoginScreen` calls `api.auth.login()` + `api.auth.me()` over that client, stores the token on it, and sets `self.app.current_user`. The three ported screens drop their `get_context()` usage and read `self.app.client` directly. Direct-DB screens (dashboard, users, logs) and the hybrid RAID screen stay AS-IS for now (later plans); they keep working because they use their own data paths and don't depend on the removed plumbing.

**Tech Stack:** Python 3.11, Textual, httpx 0.27, Click, pytest. Builds on Plan 1 (`backend/baluhost_tui/client.py`, `api/auth.py`, `api/system.py`). Spec: `docs/superpowers/specs/2026-06-07-tui-companion-rebuild-design.md`.

---

## Context for the implementer

- Plan 1 already shipped `BackendClient` (`backend/baluhost_tui/client.py`) with `get/post/put/delete` returning `httpx.Response`, plus `set_token()`/`clear_token()`, and `api/auth.py` (`login`, `LoginError`, `TwoFactorRequired`) and `api/system.py`.
- The three screens being ported currently share one pattern: `__init__(self, mode, server, token)`, then `with get_context(mode, server, token) as ctx: fn(ctx.get_api_client())`, and an `if not self.token:` guard. The port replaces all of that with `fn(self.app.client)` and an `if not self.app.token:` guard, and removes their custom `__init__`.
- `BaluHostApp` gates every screen action on `self.current_user` (and admin role for power/services/smart). Those guards stay. Tests in `backend/tests/tui/test_app_actions.py` construct the app via `__new__` and call the actions; they pass as long as the guards fire before any `push_screen` — they do.
- Tests run from `backend/`: `python -m pytest tests/tui/ -v --no-cov` (the repo's pytest config forces `--cov=app`, so `--no-cov` is required).
- Shell is PowerShell on Windows: chain with `;` / `if ($?) { ... }`, not `&&`. A hook blocks `grep`/`rg` and the Grep tool — use Read/Glob.
- Work in the worktree `D:\Programme (x86)\Baluhost\.claude\worktrees\feat+tui-companion-rebuild`; before each commit confirm `git branch --show-current` is `feat/tui-companion-rebuild`.

## File Structure

| File | Change | Responsibility after change |
|---|---|---|
| `backend/baluhost_tui/api/auth.py` | Modify (append `me()`) | also fetch the current user over the client |
| `backend/tests/tui/test_api_auth.py` | Modify (append tests) | cover `me()` |
| `backend/baluhost_tui/app.py` | Modify | hold `self.client`; no direct-DB; ported screens constructed no-arg; file-browser nav removed |
| `backend/baluhost_tui/main.py` | Modify | `--socket` option; `dashboard` command builds `BackendClient`; `files` TUI command removed |
| `backend/baluhost_tui/screens/login.py` | Rewrite | JWT-only login over the client; no direct DB |
| `backend/tests/tui/test_login_token.py` | Delete | obsolete (`_acquire_api_token` removed; covered by `test_api_auth`) |
| `backend/baluhost_tui/screens/services.py` | Modify | use `self.app.client` |
| `backend/baluhost_tui/screens/smart.py` | Modify | use `self.app.client` |
| `backend/baluhost_tui/screens/power.py` | Modify | use `self.app.client` |
| `backend/baluhost_tui/screens/files.py` | Delete | file-browser removed (per spec) |
| `backend/baluhost_tui/screens/dashboard.py` | Modify | drop the file-browser import + nav (stays direct-DB otherwise) |

Out of scope for Plan 2 (later plans): porting dashboard/users/logs off direct DB; porting RAID to the local-channel API; destructive ops (RAID create/delete/format, users bulk-delete); `ConfirmDialog`; `BaseScreen`; new screens (plugins/vpn/network/settings/live-logs); `sys.path` cleanup; welcome-version fix.

---

## Task 1: `api.auth.me()` — fetch the current user

**Files:**
- Modify: `backend/baluhost_tui/api/auth.py`
- Modify (append): `backend/tests/tui/test_api_auth.py`

- [ ] **Step 1: Write the failing test (append to `backend/tests/tui/test_api_auth.py`)**

```python
def test_me_returns_user_dict():
    class _C:
        def get(self, path: str, **_: Any):
            assert path == "/api/auth/me"
            return _Resp(200, {"id": 1, "username": "admin", "role": "admin"})

    from baluhost_tui.api.auth import me

    user = me(_C())
    assert user["username"] == "admin"
    assert user["role"] == "admin"


def test_me_raises_login_error_on_non_200():
    class _C:
        def get(self, path: str, **_: Any):
            return _Resp(401, {"detail": "Not authenticated"})

    from baluhost_tui.api.auth import me, LoginError

    with pytest.raises(LoginError):
        me(_C())
```

Note: `_Resp`, `Any`, and `pytest` are already imported at the top of this file from Plan 1.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend ; python -m pytest tests/tui/test_api_auth.py -v --no-cov`
Expected: FAIL with `ImportError: cannot import name 'me'`.

- [ ] **Step 3: Implement `me()` (append to `backend/baluhost_tui/api/auth.py`)**

```python
class _ClientGet(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...


def me(client: _ClientGet) -> dict:
    """GET /api/auth/me -> the current user dict (id, username, role, ...).

    Raises LoginError on a non-200 response or a non-dict body. Call only
    after the client has a token set (api.auth.login + client.set_token).
    """
    try:
        resp = client.get("/api/auth/me")
    except Exception as exc:
        raise LoginError(f"request failed: {exc}") from exc
    if resp.status_code != 200:
        raise LoginError(f"failed to fetch current user: HTTP {resp.status_code}")
    data = resp.json()
    if not isinstance(data, dict):
        raise LoginError("unexpected /me response")
    return data
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend ; python -m pytest tests/tui/test_api_auth.py -v --no-cov`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```
git add backend/baluhost_tui/api/auth.py backend/tests/tui/test_api_auth.py
git commit -m "feat(tui): api.auth.me() to fetch current user"
```

---

## Task 2: Rewrite `LoginScreen` for JWT-only login

**Files:**
- Rewrite: `backend/baluhost_tui/screens/login.py`
- Delete: `backend/tests/tui/test_login_token.py`

This screen no longer touches the database. It authenticates via `api.auth.login()` over `self.app.client`, fetches the user via `api.auth.me()`, enforces the admin-only rule (existing behavior), stores the token on the client and `self.app.token`, and sets `self.app.current_user`.

- [ ] **Step 1: Delete the obsolete token test**

The test targets `login._acquire_api_token`, which this rewrite removes. Its behavior is covered by `tests/tui/test_api_auth.py`.

Run: `git rm backend/tests/tui/test_login_token.py`

- [ ] **Step 2: Replace `backend/baluhost_tui/screens/login.py` entirely with:**

```python
"""Login screen for BaluHost TUI — JWT auth over the local-channel client."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, Label, Button, Input
from textual.binding import Binding

from baluhost_tui.api import auth as auth_api


class LoginScreen(Screen):
    """Admin login. Authenticates via the backend over the app's BackendClient."""

    def __init__(self) -> None:
        super().__init__()
        self.backend_available = False

    CSS = """
    LoginScreen {
        align: center middle;
        background: $surface;
    }

    #login-container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2 4;
    }

    #login-title {
        text-style: bold;
        color: $accent;
        text-align: center;
        margin-bottom: 1;
    }

    #backend-status {
        text-align: center;
        margin-bottom: 2;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .form-label {
        width: 12;
        content-align: left middle;
    }

    Input {
        width: 1fr;
    }

    .button-row {
        height: auto;
        margin-top: 2;
        align: center middle;
    }

    Button {
        margin: 0 1;
    }

    #error-message {
        color: $error;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="login-container"):
            yield Label("🔐 BaluHost TUI - Admin Login", id="login-title")
            yield Static("Checking backend status...", id="backend-status")

            with Horizontal(classes="form-row"):
                yield Label("Username:", classes="form-label")
                yield Input(placeholder="Enter username", id="input-username")

            with Horizontal(classes="form-row"):
                yield Label("Password:", classes="form-label")
                yield Input(placeholder="Enter password", password=True, id="input-password")

            with Horizontal(classes="button-row"):
                yield Button("Login", variant="primary", id="btn-login")
                yield Button("Quit", variant="default", id="btn-quit")

            yield Label("", id="error-message")
        yield Footer()

    def on_mount(self) -> None:
        self.check_backend_status()
        self.query_one("#input-username", Input).focus()

    def check_backend_status(self) -> None:
        """Probe the backend over the app's client; disable login if unreachable."""
        self.backend_available = False
        try:
            resp = self.app.client.get("/api/health")
            if resp.status_code == 200:
                self.query_one("#backend-status", Static).update(
                    "[green]✓ Backend erreichbar (local channel)[/green]"
                )
                self.backend_available = True
                return
            self.query_one("#backend-status", Static).update(
                f"[yellow]⚠ Backend-Status {resp.status_code}[/yellow]"
            )
        except Exception as exc:
            self.query_one("#backend-status", Static).update(
                f"[red]✗ Backend nicht erreichbar: {str(exc)[:60]}[/red]\n"
                "[yellow]Läuft baluhost-backend-local.service? (bzw. start_dev.py in Dev)[/yellow]"
            )
        try:
            self.query_one("#btn-login", Button).disabled = True
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-quit":
            self.app.exit()
        elif event.button.id == "btn-login":
            self.attempt_login()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "input-username":
            self.query_one("#input-password", Input).focus()
        elif event.input.id == "input-password":
            self.attempt_login()

    def attempt_login(self) -> None:
        if not self.backend_available:
            self.show_error("Backend nicht erreichbar. Login nicht möglich.")
            return

        username = self.query_one("#input-username", Input).value.strip()
        password = self.query_one("#input-password", Input).value
        if not username or not password:
            self.show_error("Benutzername und Passwort erforderlich")
            return

        client = self.app.client
        try:
            token = auth_api.login(client, username, password)
        except auth_api.TwoFactorRequired:
            self.show_error("2FA-Konten werden in der TUI noch nicht unterstützt.")
            return
        except auth_api.LoginError as exc:
            self.show_error(f"Login fehlgeschlagen: {exc}")
            return

        client.set_token(token)
        try:
            user = auth_api.me(client)
        except auth_api.LoginError as exc:
            client.clear_token()
            self.show_error(f"Konnte Benutzer nicht laden: {exc}")
            return

        if user.get("role") != "admin":
            client.clear_token()
            self.show_error("Zugriff verweigert. Admin-Rolle erforderlich.")
            return

        self.app.token = token
        self.app.current_user = user
        self.notify(f"Willkommen {user.get('username', username)}!", severity="information")

        from baluhost_tui.screens.dashboard import DashboardScreen
        self.app.switch_screen(DashboardScreen())

    def show_error(self, message: str) -> None:
        self.query_one("#error-message", Label).update(f"[red]{message}[/red]")
        self.notify(message, severity="error")
```

- [ ] **Step 3: Import-smoke the rewritten module**

Run: `cd backend ; python -c "import baluhost_tui.screens.login as m; print(hasattr(m, 'LoginScreen')); print(hasattr(m, '_acquire_api_token'))"`
Expected: `True` then `False` (the old helper is gone).

- [ ] **Step 4: Confirm the TUI suite still collects (no import errors from the deleted test)**

Run: `cd backend ; python -m pytest tests/tui/ --no-cov -q`
Expected: all pass (the deleted `test_login_token.py` is gone; remaining tests unaffected — `app.py` is patched in Task 3, so this step runs before that; if a collection error mentions `screens.login`, fix the import before continuing).

- [ ] **Step 5: Commit**

```
git add backend/baluhost_tui/screens/login.py
git rm backend/tests/tui/test_login_token.py
git commit -m "feat(tui): JWT-only LoginScreen over BackendClient (drop direct DB)"
```

---

## Task 3: Rewire `BaluHostApp` to hold the client; drop direct-DB + file-browser nav

**Files:**
- Modify: `backend/baluhost_tui/app.py`

- [ ] **Step 1: Replace the imports + `__init__` + `on_mount` region**

In `backend/baluhost_tui/app.py`, replace these top imports:

```python
from app.core.config import settings
from app.services.users import ensure_admin_user

from baluhost_tui.screens.login import LoginScreen
from baluhost_tui.screens.dashboard import DashboardScreen
from baluhost_tui.screens.users import UserManagementScreen
from baluhost_tui.screens.logs import AuditLogViewerScreen
from baluhost_tui.screens.files import FileBrowserScreen
from baluhost_tui.screens.raid import RaidControlScreen
from baluhost_tui.screens.power import PowerActionsScreen
from baluhost_tui.screens.services import ServiceHealthScreen
from baluhost_tui.screens.smart import SmartScreen
```

with (drop `app.core.config`, `ensure_admin_user`, and the `FileBrowserScreen` import; add the `BackendClient` import):

```python
from baluhost_tui.client import BackendClient
from baluhost_tui.screens.login import LoginScreen
from baluhost_tui.screens.dashboard import DashboardScreen
from baluhost_tui.screens.users import UserManagementScreen
from baluhost_tui.screens.logs import AuditLogViewerScreen
from baluhost_tui.screens.raid import RaidControlScreen
from baluhost_tui.screens.power import PowerActionsScreen
from baluhost_tui.screens.services import ServiceHealthScreen
from baluhost_tui.screens.smart import SmartScreen
```

- [ ] **Step 2: Replace `__init__`**

Replace the existing `__init__` method:

```python
    def __init__(self, mode: str = 'auto', server: str = 'http://localhost:8000', token: str | None = None):
        """Initialize app.

        Args:
            mode: Connection mode (auto, local, remote)
            server: Server URL for remote mode
        """
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token
        self.title = "BaluHost NAS TUI"
        self.sub_title = f"Mode: {mode}"
        self.current_user = None  # Will be set after login

        # Ensure admin user exists (same as backend does)
        try:
            ensure_admin_user(settings)
        except Exception as e:
            pass  # Will be handled by login screen
```

with:

```python
    def __init__(self, client: BackendClient | None = None, token: str | None = None):
        """Initialize app.

        Args:
            client: Pre-built BackendClient (UDS in prod / TCP loopback in dev).
                    Built with defaults (auto-detect transport) when omitted.
            token: Optional pre-supplied bearer token (set on the client).
        """
        super().__init__()
        self.client = client if client is not None else BackendClient()
        self.token = token
        if token:
            self.client.set_token(token)
        self.title = "BaluHost NAS TUI"
        self.sub_title = "Companion (local channel)"
        self.current_user = None  # Set after login
```

- [ ] **Step 3: Remove the Files binding and action; make ported screens no-arg**

In the `BINDINGS` list, remove this line:

```python
        Binding("f", "files", "Files"),
```

Remove the entire `action_files` method:

```python
    def action_files(self) -> None:
        """Show file browser."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        # start at storage root
        self.push_screen(FileBrowserScreen(start_path='/', mode=self.mode, server=self.server, token=self.token))
```

Change the three ported-screen actions to construct screens with no arguments. Replace:

```python
        self.push_screen(PowerActionsScreen(mode=self.mode, server=self.server, token=self.token))
```
with:
```python
        self.push_screen(PowerActionsScreen())
```

Replace:
```python
        self.push_screen(ServiceHealthScreen(mode=self.mode, server=self.server, token=self.token))
```
with:
```python
        self.push_screen(ServiceHealthScreen())
```

Replace:
```python
        self.push_screen(SmartScreen(mode=self.mode, server=self.server, token=self.token))
```
with:
```python
        self.push_screen(SmartScreen())
```

Leave `action_dashboard`, `action_users`, `action_raid`, `action_logs` unchanged.

- [ ] **Step 4: Import-smoke**

Run: `cd backend ; python -c "from baluhost_tui.app import BaluHostApp; print('OK')"`
Expected: `OK`.

- [ ] **Step 5: Run the app-action tests (must stay green)**

Run: `cd backend ; python -m pytest tests/tui/test_app_actions.py -v --no-cov`
Expected: PASS (all). The auth guards are unchanged and fire before any `push_screen`; the no-arg screen constructors are never reached in these tests.

- [ ] **Step 6: Commit**

```
git add backend/baluhost_tui/app.py
git commit -m "feat(tui): app holds BackendClient; drop direct-DB admin seeding + file-browser nav"
```

---

## Task 4: Port `ServiceHealthScreen` to `self.app.client`

**Files:**
- Modify: `backend/baluhost_tui/screens/services.py`

The module functions `fetch_services` / `restart_service` are unchanged (their tests stay green). Only the screen class changes.

- [ ] **Step 1: Remove the get_context import**

Delete this line:
```python
from baluhost_tui.context import get_context
```

- [ ] **Step 2: Remove the custom `__init__`**

Delete:
```python
    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token
```

- [ ] **Step 3: Update `on_mount` guard**

Replace:
```python
        if not self.token:
            self.notify("No API token — service actions unavailable", severity="warning")
            return
```
with:
```python
        if not self.app.token:
            self.notify("No API token — service actions unavailable", severity="warning")
            return
```

- [ ] **Step 4: Update `load_services`**

Replace:
```python
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            services = fetch_services(ctx.get_api_client())
```
with:
```python
        services = fetch_services(self.app.client)
```

- [ ] **Step 5: Update `on_data_table_row_selected`**

Replace:
```python
        if not self.token:
            self.notify("No API token", severity="error")
            return
```
with:
```python
        if not self.app.token:
            self.notify("No API token", severity="error")
            return
```

And replace:
```python
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            ok, msg = restart_service(ctx.get_api_client(), name)
```
with:
```python
        ok, msg = restart_service(self.app.client, name)
```

- [ ] **Step 6: Verify the screen's tests still pass + import-smoke**

Run: `cd backend ; python -m pytest tests/tui/test_services_screen.py -v --no-cov ; if ($?) { python -c "import baluhost_tui.screens.services; print('OK')" }`
Expected: tests PASS (module functions unchanged) and `OK`.

- [ ] **Step 7: Commit**

```
git add backend/baluhost_tui/screens/services.py
git commit -m "refactor(tui): ServiceHealthScreen uses app.client (drop get_context)"
```

---

## Task 5: Port `SmartScreen` to `self.app.client`

**Files:**
- Modify: `backend/baluhost_tui/screens/smart.py`

- [ ] **Step 1: Remove the get_context import**

Delete:
```python
from baluhost_tui.context import get_context
```

- [ ] **Step 2: Remove the custom `__init__`**

Delete:
```python
    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token
```

- [ ] **Step 3: Update `on_mount` guard**

Replace:
```python
        if not self.token:
            self.notify("No API token — SMART data unavailable", severity="warning")
            return
```
with:
```python
        if not self.app.token:
            self.notify("No API token — SMART data unavailable", severity="warning")
            return
```

- [ ] **Step 4: Update `load_smart`**

Replace:
```python
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            disks = fetch_smart(ctx.get_api_client())
```
with:
```python
        disks = fetch_smart(self.app.client)
```

- [ ] **Step 5: Verify + import-smoke**

Run: `cd backend ; python -m pytest tests/tui/test_smart_screen.py -v --no-cov ; if ($?) { python -c "import baluhost_tui.screens.smart; print('OK')" }`
Expected: tests PASS and `OK`.

- [ ] **Step 6: Commit**

```
git add backend/baluhost_tui/screens/smart.py
git commit -m "refactor(tui): SmartScreen uses app.client (drop get_context)"
```

---

## Task 6: Port `PowerActionsScreen` to `self.app.client`

**Files:**
- Modify: `backend/baluhost_tui/screens/power.py`

- [ ] **Step 1: Remove the get_context import**

Delete:
```python
from baluhost_tui.context import get_context
```

- [ ] **Step 2: Remove the custom `__init__`**

Delete:
```python
    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token
```

- [ ] **Step 3: Update `on_mount` guard**

The full `if not self.token:` block is 9 lines (it disables the buttons and returns). Replace the WHOLE block — only the first line changes (`self.token` → `self.app.token`); keep the button-disable loop and `return` exactly. Replace:
```python
        if not self.token:
            self.query_one("#power-status", Static).update(
                "[red]No API token — admin actions disabled. Login with backend online.[/red]"
            )
            for btn_id in ("btn-soft", "btn-wake", "btn-suspend", "btn-wol"):
                try:
                    self.query_one(f"#{btn_id}", Button).disabled = True
                except Exception:
                    pass
            return
```
with:
```python
        if not self.app.token:
            self.query_one("#power-status", Static).update(
                "[red]No API token — admin actions disabled. Login with backend online.[/red]"
            )
            for btn_id in ("btn-soft", "btn-wake", "btn-suspend", "btn-wol"):
                try:
                    self.query_one(f"#{btn_id}", Button).disabled = True
                except Exception:
                    pass
            return
```

- [ ] **Step 4: Update `refresh_status`**

Replace:
```python
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            status = fetch_status(ctx.get_api_client())
```
with:
```python
        status = fetch_status(self.app.client)
```

- [ ] **Step 5: Update `on_button_pressed`**

Replace:
```python
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            ok, msg = perform_action(ctx.get_api_client(), action)
```
with:
```python
        ok, msg = perform_action(self.app.client, action)
```

- [ ] **Step 6: Verify + import-smoke**

Run: `cd backend ; python -m pytest tests/tui/test_power_screen.py -v --no-cov ; if ($?) { python -c "import baluhost_tui.screens.power; print('OK')" }`
Expected: tests PASS and `OK`.

- [ ] **Step 7: Commit**

```
git add backend/baluhost_tui/screens/power.py
git commit -m "refactor(tui): PowerActionsScreen uses app.client (drop get_context)"
```

---

## Task 7: Remove the file-browser screen + dashboard nav to it

**Files:**
- Delete: `backend/baluhost_tui/screens/files.py`
- Modify: `backend/baluhost_tui/screens/dashboard.py`

The file-browser is out of scope per the spec. `app.py` already dropped its import/nav in Task 3. `dashboard.py` still imports and navigates to it — fix that here. (`dashboard.py` otherwise stays direct-DB; its full port is a later plan.)

- [ ] **Step 1: Delete the file-browser screen**

Run: `git rm backend/baluhost_tui/screens/files.py`

- [ ] **Step 2: Remove the import in `dashboard.py`**

In `backend/baluhost_tui/screens/dashboard.py`, delete this line:
```python
from baluhost_tui.screens.files import FileBrowserScreen
```

- [ ] **Step 3: Remove the Files binding in `dashboard.py`**

In the `DashboardScreen.BINDINGS` list, delete this line:
```python
        ("f", "files_screen", "Files"),
```

- [ ] **Step 4: Remove the `action_files_screen` method in `dashboard.py`**

Delete the whole method:
```python
    def action_files_screen(self) -> None:
        """Navigate to files screen."""
        try:
            # start at storage root
            self.app.push_screen(FileBrowserScreen(start_path='/', mode=self.app.mode, server=self.app.server, token=getattr(self.app, 'token', None)))
        except Exception as exc:
            self.notify(f"Failed to open File Browser: {exc}", severity="error")
```

- [ ] **Step 5: Import-smoke (this is the load-bearing check — `dashboard.py` must import without `files`)**

Run: `cd backend ; python -c "import baluhost_tui.screens.dashboard; import baluhost_tui.app; print('OK')"`
Expected: `OK` (no `ModuleNotFoundError: baluhost_tui.screens.files`).

- [ ] **Step 6: Confirm no other references to the deleted screen remain**

Run: `cd backend ; python -c "import baluhost_tui.main; print('OK')"`
Expected: `OK`. (If this fails because `main.py` still launches a `files` command that imports the app, that is fine — `main.py` is fixed in Task 8; this step only checks `main` still imports. If it errors on `screens.files`, search and remove that reference.)

- [ ] **Step 7: Commit**

```
git add backend/baluhost_tui/screens/dashboard.py
git rm backend/baluhost_tui/screens/files.py
git commit -m "feat(tui): remove file-browser screen + dashboard nav (out of scope per spec)"
```

---

## Task 8: Wire `main.py` to build the BackendClient; drop the `files` TUI command

**Files:**
- Modify: `backend/baluhost_tui/main.py`

The CLI group currently passes `mode`/`server`/`token` into `BaluHostApp(mode=..., server=..., token=...)`. After Task 3 the app takes `client=`/`token=`. Update the `dashboard` command to build a `BackendClient`, add a `--socket` option, and remove the now-dead `files` TUI command. The `status`/`users`/`reset-password`/`files-download`/`files-upload` commands are left working (the legacy `--server` default falls back inside each).

- [ ] **Step 1: Add `--socket` to the group and make `--server` default to None**

Replace the group decorator block:

```python
@click.group()
@click.option('--mode', type=click.Choice(['auto', 'local', 'remote']), default='auto',
              help='Connection mode: auto (detect), local (direct DB), remote (API)')
@click.option('--server', default='http://localhost:8000',
              help='Server URL for remote mode')
@click.option('--token', default=None,
              help='Bearer token for remote API access')
@click.option('--debug/--no-debug', default=False,
              help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, mode: str, server: str, token: str | None, debug: bool):
```

with:

```python
@click.group()
@click.option('--mode', type=click.Choice(['auto', 'local', 'remote']), default='auto',
              help='(Legacy) connection mode for the status/users CLI commands')
@click.option('--socket', 'socket_path', default=None,
              help='Unix socket path (prod local channel). Auto-detected when omitted.')
@click.option('--server', default=None,
              help='Server URL (dev TCP, e.g. http://127.0.0.1:3001). Auto-detected when omitted.')
@click.option('--token', default=None,
              help='Bearer token for API access')
@click.option('--debug/--no-debug', default=False,
              help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, mode: str, socket_path: str | None, server: str | None, token: str | None, debug: bool):
```

- [ ] **Step 2: Store the new options in the context**

Replace the body of `cli()`:

```python
    ctx.ensure_object(dict)
    ctx.obj['mode'] = mode
    ctx.obj['server'] = server
    ctx.obj['token'] = token
    ctx.obj['debug'] = debug
```

with:

```python
    ctx.ensure_object(dict)
    ctx.obj['mode'] = mode
    ctx.obj['socket_path'] = socket_path
    ctx.obj['server'] = server
    ctx.obj['token'] = token
    ctx.obj['debug'] = debug
```

- [ ] **Step 3: Rebuild the `dashboard` command to construct a BackendClient**

Replace the whole `dashboard` command:

```python
@cli.command()
@click.pass_context
def dashboard(ctx: click.Context):
    """Launch the interactive TUI dashboard."""
    from .app import BaluHostApp
    
    mode = ctx.obj['mode']
    server = ctx.obj['server']
    token = ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')
    
    console.print(f"[cyan]Starting BaluHost TUI[/cyan] (mode: {mode})")
    
    app = BaluHostApp(mode=mode, server=server, token=token)
    app.run()
```

with:

```python
@cli.command()
@click.pass_context
def dashboard(ctx: click.Context):
    """Launch the interactive TUI (UDS in prod, TCP loopback in dev)."""
    from .app import BaluHostApp
    from .client import BackendClient

    socket_path = ctx.obj.get('socket_path')
    server = ctx.obj.get('server')
    token = ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')

    client = BackendClient(socket_path=socket_path, server=server, token=token)
    console.print("[cyan]Starting BaluHost TUI[/cyan] (local channel)")

    app = BaluHostApp(client=client, token=token)
    app.run()
```

- [ ] **Step 4: Remove the dead `files` TUI command**

Delete the whole command (the interactive file browser it launched is gone; `files-download`/`files-upload` are separate commands and remain):

```python
@cli.command()
@click.pass_context
def files(ctx: click.Context):
    """Open file browser TUI."""
    from .app import BaluHostApp

    mode = ctx.obj['mode']
    server = ctx.obj['server']
    token = ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')

    console.print(f"[cyan]Starting BaluHost TUI - Files[/cyan] (mode: {mode})")
    app = BaluHostApp(mode=mode, server=server, token=token)
    app.run()
```

- [ ] **Step 5: Keep `status`/`users` working with the new `--server` default of None**

In the `status` command body, replace:
```python
    server = ctx.obj['server']

    show_status(mode=mode, server=server)
```
with:
```python
    server = ctx.obj['server'] or 'http://localhost:8000'

    show_status(mode=mode, server=server)
```

In the `users` command body, replace:
```python
    server = ctx.obj['server']

    list_users(mode=mode, server=server)
```
with:
```python
    server = ctx.obj['server'] or 'http://localhost:8000'

    list_users(mode=mode, server=server)
```

(The `files-download` / `files-upload` commands already use `server or ctx.obj.get('server')` with their own `--server` option default and need no change.)

- [ ] **Step 6: Verify the CLI imports and the help lists the expected commands**

Run: `cd backend ; python -c "from baluhost_tui.main import cli; print('OK')"`
Expected: `OK`.

Run: `cd backend ; python -m baluhost_tui --help`
Expected: help text shows `dashboard`, `status`, `users`, `reset-password`, `files-download`, `files-upload` and does NOT list a `files` command. (Running `python -m baluhost_tui` works because `__main__.py` calls `cli`.)

- [ ] **Step 7: Commit**

```
git add backend/baluhost_tui/main.py
git commit -m "feat(tui): main builds BackendClient (--socket/--server); drop files TUI command"
```

---

## Task 9: Full-suite verification

**Files:** none changed.

- [ ] **Step 1: Run the full TUI suite**

Run: `cd backend ; python -m pytest tests/tui/ -v --no-cov`
Expected: all pass. New: `test_api_auth.py` now 7. Removed: `test_login_token.py`. Unchanged and green: `test_client.py` (11), `test_api_system.py` (6), `test_services_screen.py`, `test_smart_screen.py`, `test_power_screen.py`, `test_app_actions.py`.

- [ ] **Step 2: Import-smoke the whole package**

Run: `cd backend ; python -c "import baluhost_tui.app, baluhost_tui.main, baluhost_tui.screens.login, baluhost_tui.screens.services, baluhost_tui.screens.smart, baluhost_tui.screens.power, baluhost_tui.screens.dashboard; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Confirm the file-browser is fully gone**

Run (PowerShell): `cd backend ; if (Test-Path baluhost_tui/screens/files.py) { Write-Output 'STILL PRESENT' } else { Write-Output 'removed' }`
Expected: `removed`.

- [ ] **Step 4: Manual smoke (optional, dev)**

With `python start_dev.py` running (backend on 3001, loopback fallback → channel=local), run `cd backend ; python -m baluhost_tui dashboard`. Expect the login screen to report the backend reachable, accept `admin` / `DevMode2024`, and land on the dashboard. Services/SMART/Power screens load over the client. (This step is manual; no commit.)

---

## Self-Review

**1. Spec coverage (this plan's slice — "transport cutover"):**
- "Transport: one client, two bindings" + "Auto-detection" → Task 8 builds `BackendClient(socket_path, server)`; app holds it (Task 3). ✓
- "Auth — JWT still required; direct-DB login removed" → Task 2 (`LoginScreen` via `api.auth.login`/`me`, admin-gate, no DB) + Task 1 (`me()`). ✓
- "Port services/smart/power onto BackendClient" → Tasks 4/5/6. ✓
- "Remove file-browser screen; keep `files-*` CLI" → Task 7 (+ Task 3/8 nav/command removal); `commands/files.py` untouched. ✓
- "Remove direct-DB" (from app startup) → Task 3 drops `ensure_admin_user`. ✓
- Deferred (explicitly out of scope, stated above): dashboard/users/logs ports, RAID local-channel port + destructive ops, `ConfirmDialog`, `BaseScreen`, new screens, `sys.path`/version cleanup.

**2. Placeholder scan:** No TBD/TODO; every code step shows complete old→new snippets or full file content; every run step has an exact command + expected output. ✓

**3. Type/consistency checks:**
- `BaluHostApp.__init__(client, token)` (Task 3) matches the `BaluHostApp(client=client, token=token)` call in Task 8. ✓
- Ported screens are constructed no-arg in Task 3 (`PowerActionsScreen()`, `ServiceHealthScreen()`, `SmartScreen()`) and have their `__init__` removed in Tasks 4/5/6 — consistent. ✓
- Screens read `self.app.client` (set in Task 3) and `self.app.token` (set on login in Task 2). `self.app.token` is initialized to `None`/`token` in `__init__` and assigned the JWT in `attempt_login`. ✓
- `api.auth.me()` (Task 1) returns a dict; `LoginScreen` reads `user.get("role")`/`user.get("username")` (Task 2). ✓
- Removed `self.mode`/`self.server` from the app: the only remaining consumers were `action_files`/`action_files_screen` (removed in Tasks 3/7) and the legacy `files` command (removed in Task 8). The RAID screen uses `get_context()` with no args (its own defaults) and does not read `self.app.mode/server`. ✓

**4. Known transitional warts (intentional, documented for later plans):**
- `dashboard.py`, `users.py`, `logs.py` still use direct DB/service calls — ported in a later plan.
- `raid.py` still uses `get_context()` (hybrid local/remote) — on the prod box it resolves to `local` and calls services directly rather than going through the local-channel API. The proper local-channel RAID port (with `require_local_admin` create/delete/format) is a later plan. No regression vs. today.
- `context.py` remains (still used by `raid.py`); removed in the plan that ports RAID.

---

## Next plans (outline — written after this one to avoid drift)

- **Plan 3 — Read-only screen ports:** dashboard, users (read/CRUD via API), logs (audit + live system logs) onto `BackendClient`; introduce `BaseScreen`; remove remaining direct-DB.
- **Plan 4 — Destructive ops:** `ConfirmDialog` widget; RAID create/delete/format via local-channel API (replace the hybrid `raid.py`); users bulk-delete; power app-restart/shutdown; remove `context.py`.
- **Plan 5 — New screens + cleanup:** plugins (install/uninstall), vpn (read + sync-server-keys), network, settings; centralize `sys.path`; fix welcome version; update `TUI_FEATURE_AUDIT.md`.
