# TUI Companion Rebuild — Users Screen CRUD Port (Plan 4 of N) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the User Management screen off direct database access onto the `BackendClient` — list/create/update/reset-password/delete users via the HTTP API — removing the last large direct-DB screen.

**Architecture:** Extend `api/users.py` with `create_user/update_user/set_password/delete_user` (each returning `(ok, message)`), then rewire `UserManagementScreen`'s five data operations to call them via `self.app.client`. The four modal dialogs (Create/Edit/PasswordReset/DeleteConfirm) are pure UI and stay unchanged; only the screen's data layer changes.

**Tech Stack:** Python 3.11, Textual, httpx 0.27, pytest. Builds on Plans 1–3 (`BackendClient`, `api/users.list_users`). Spec: `docs/superpowers/specs/2026-06-07-tui-companion-rebuild-design.md`.

---

## Context for the implementer

- Plan 3 shipped `backend/baluhost_tui/api/users.py` with `list_users(client) -> dict` (`{users, total, active, inactive, admins}`, fail-safe empty skeleton). This plan APPENDS the write operations to that file.
- The four modal dialogs in `screens/users.py` (`CreateUserDialog`, `EditUserDialog`, `PasswordResetDialog`, `DeleteConfirmDialog`) are pure Textual UI that `dismiss(...)` a result dict/value. They do NOT touch the DB and stay byte-for-byte unchanged.
- Backend endpoints (verified, all `get_current_admin`, all under `/api`):
  - `GET /api/users/` → `{users:[{id,username,email,role,is_active,created_at}], total, active, inactive, admins}` (already wrapped by `list_users`).
  - `POST /api/users/` body `{username, password, email?, role?}` → `UserPublic`, **201** on success, 409 if username exists.
  - `PUT /api/users/{id}` body any of `{email?, role?, is_active?, password?}` → `UserPublic`, **200**. Setting `password` here IS the admin password-reset (no old password needed).
  - `DELETE /api/users/{id}` → **204** No Content (empty body).
- `BackendClient` exposes `get/post/put/delete(path, **kwargs) -> httpx.Response` (Plan 1). Screens read it via `self.app.client` and use `self.app.token` only as a login marker (the user screen is reached only when logged in as admin, so no per-screen token guard is needed — the app's `action_users` already gates on `current_user`).
- Tests use the inline `_Resp`/`_FakeClient` pattern. Run from `backend/`: `python -m pytest tests/tui/<file> -v --no-cov`.
- Shell is PowerShell: chain with `;` / `if ($?) { ... }`. Hook blocks grep/rg and the Grep tool — use Read/Glob. Worktree `D:\Programme (x86)\Baluhost\.claude\worktrees\feat+tui-companion-rebuild`; confirm `git branch --show-current` is `feat/tui-companion-rebuild` before each commit.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/baluhost_tui/api/users.py` | Modify (append) | `create_user/update_user/set_password/delete_user(client, ...) -> (ok, msg)` |
| `backend/tests/tui/test_api_users.py` | Modify (append) | cover the four write ops |
| `backend/baluhost_tui/screens/users.py` | Modify | screen data ops use `api.users` via `self.app.client`; drop direct DB/passlib |

Out of scope (later plans): destructive ops + `ConfirmDialog` + RAID local-channel + `context.py` removal (Plan 5); new screens + `BaseScreen` + cleanup (Plan 6). Note: the per-user `DELETE /api/users/{id}` is admin-only (any channel) — it is the existing single-delete the screen already offers, NOT the local-channel-gated `bulk-delete` (that's Plan 5).

---

## Task 1: Extend `api/users.py` with write operations

**Files:**
- Modify (append): `backend/baluhost_tui/api/users.py`
- Modify (append): `backend/tests/tui/test_api_users.py`

- [ ] **Step 1: Write the failing tests (append to `backend/tests/tui/test_api_users.py`)**

```python
class _WResp:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> Any:
        return self._payload


class _WClient:
    """Records write calls and returns a queued response per (method, path)."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.responses: dict[tuple[str, str], _WResp] = {}

    def post(self, path: str, json: Any = None, **_: Any) -> _WResp:
        self.calls.append(("POST", path, json))
        return self.responses.get(("POST", path), _WResp(201, {"id": 9}))

    def put(self, path: str, json: Any = None, **_: Any) -> _WResp:
        self.calls.append(("PUT", path, json))
        return self.responses.get(("PUT", path), _WResp(200, {"id": 9}))

    def delete(self, path: str, **_: Any) -> _WResp:
        self.calls.append(("DELETE", path, None))
        return self.responses.get(("DELETE", path), _WResp(204))


def test_create_user_posts_and_reports_ok():
    from baluhost_tui.api.users import create_user
    c = _WClient()
    ok, msg = create_user(c, username="bob", password="Secret123", email="b@x.io", role="user")
    assert ok is True
    assert c.calls == [("POST", "/api/users/", {"username": "bob", "password": "Secret123", "role": "user", "email": "b@x.io"})]
    assert "bob" in msg


def test_create_user_omits_empty_email():
    from baluhost_tui.api.users import create_user
    c = _WClient()
    create_user(c, username="bob", password="Secret123", email=None)
    _, _, body = c.calls[0]
    assert "email" not in body
    assert body["role"] == "user"


def test_create_user_reports_failure_with_detail():
    from baluhost_tui.api.users import create_user
    c = _WClient()
    c.responses[("POST", "/api/users/")] = _WResp(409, {"detail": "username exists"})
    ok, msg = create_user(c, username="bob", password="Secret123")
    assert ok is False
    assert "exists" in msg.lower() or "409" in msg


def test_update_user_sends_only_provided_fields():
    from baluhost_tui.api.users import update_user
    c = _WClient()
    ok, msg = update_user(c, 5, email="new@x.io", role="admin", is_active=False)
    assert ok is True
    assert c.calls == [("PUT", "/api/users/5", {"email": "new@x.io", "role": "admin", "is_active": False})]


def test_update_user_omits_none_fields():
    from baluhost_tui.api.users import update_user
    c = _WClient()
    update_user(c, 5, role="admin")
    _, _, body = c.calls[0]
    assert body == {"role": "admin"}


def test_set_password_puts_password_only():
    from baluhost_tui.api.users import set_password
    c = _WClient()
    ok, msg = set_password(c, 7, "NewPass123")
    assert ok is True
    assert c.calls == [("PUT", "/api/users/7", {"password": "NewPass123"})]


def test_delete_user_deletes_and_reports_ok():
    from baluhost_tui.api.users import delete_user
    c = _WClient()
    ok, msg = delete_user(c, 3)
    assert ok is True
    assert c.calls == [("DELETE", "/api/users/3", None)]


def test_delete_user_reports_failure():
    from baluhost_tui.api.users import delete_user
    c = _WClient()
    c.responses[("DELETE", "/api/users/3")] = _WResp(403, {"detail": "cannot delete last admin"})
    ok, msg = delete_user(c, 3)
    assert ok is False
    assert "admin" in msg.lower() or "403" in msg


def test_write_ops_wrap_transport_errors():
    from baluhost_tui.api.users import create_user, update_user, delete_user, set_password

    class _Boom:
        def post(self, *_: Any, **__: Any): raise RuntimeError("offline")
        def put(self, *_: Any, **__: Any): raise RuntimeError("offline")
        def delete(self, *_: Any, **__: Any): raise RuntimeError("offline")

    assert create_user(_Boom(), "a", "Secret123")[0] is False
    assert update_user(_Boom(), 1, role="user")[0] is False
    assert set_password(_Boom(), 1, "Secret123")[0] is False
    assert delete_user(_Boom(), 1)[0] is False
```

Note: `Any` is already imported at the top of `test_api_users.py` from Plan 3.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend ; python -m pytest tests/tui/test_api_users.py -v --no-cov`
Expected: FAIL with `ImportError: cannot import name 'create_user'`.

- [ ] **Step 3: Implement (append to `backend/baluhost_tui/api/users.py`)**

First, the existing `_Client` Protocol in that file only declares `get`. Replace the existing Protocol definition:

```python
class _Client(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...
```

with the extended version (adds the write verbs):

```python
class _Client(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...
    def post(self, path: str, **kwargs: Any) -> Any: ...
    def put(self, path: str, **kwargs: Any) -> Any: ...
    def delete(self, path: str, **kwargs: Any) -> Any: ...
```

Then append at the end of the file:

```python
def _detail(resp: Any) -> str:
    """Best-effort '(HTTP <code>: <detail>)' message from an error response."""
    try:
        detail = resp.json().get("detail", "")
    except Exception:
        detail = ""
    return f"HTTP {resp.status_code}: {detail}".strip().rstrip(":").strip() or f"HTTP {resp.status_code}"


def create_user(
    client: _Client,
    username: str,
    password: str,
    email: str | None = None,
    role: str = "user",
) -> tuple[bool, str]:
    """POST /api/users/ -> (ok, message). email omitted from the body when empty."""
    body: dict[str, Any] = {"username": username, "password": password, "role": role}
    if email:
        body["email"] = email
    try:
        resp = client.post("/api/users/", json=body)
        if resp.status_code in (200, 201):
            return True, f"User '{username}' created"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"


def update_user(
    client: _Client,
    user_id: int,
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> tuple[bool, str]:
    """PUT /api/users/{id} with only the provided fields -> (ok, message)."""
    body: dict[str, Any] = {}
    if email is not None:
        body["email"] = email
    if role is not None:
        body["role"] = role
    if is_active is not None:
        body["is_active"] = is_active
    try:
        resp = client.put(f"/api/users/{user_id}", json=body)
        if resp.status_code == 200:
            return True, "User updated"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"


def set_password(client: _Client, user_id: int, password: str) -> tuple[bool, str]:
    """PUT /api/users/{id} with {password} (admin password reset) -> (ok, message)."""
    try:
        resp = client.put(f"/api/users/{user_id}", json={"password": password})
        if resp.status_code == 200:
            return True, "Password updated"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"


def delete_user(client: _Client, user_id: int) -> tuple[bool, str]:
    """DELETE /api/users/{id} -> (ok, message). Backend returns 204 on success."""
    try:
        resp = client.delete(f"/api/users/{user_id}")
        if resp.status_code in (200, 204):
            return True, "User deleted"
        return False, _detail(resp)
    except Exception as exc:
        return False, f"request failed: {exc}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend ; python -m pytest tests/tui/test_api_users.py -v --no-cov`
Expected: PASS (3 prior + 9 new = 12 passed).

- [ ] **Step 5: Commit**

```
git add backend/baluhost_tui/api/users.py backend/tests/tui/test_api_users.py
git commit -m "feat(tui): api.users create/update/set_password/delete write ops"
```

---

## Task 2: Port `UserManagementScreen` to `api.users`

**Files:**
- Modify: `backend/baluhost_tui/screens/users.py`

The four modal dialog classes stay unchanged. Only the import block and the `UserManagementScreen` data methods change.

- [ ] **Step 1: Replace the import region**

Replace the top of `backend/baluhost_tui/screens/users.py`. The exact old_string (verbatim — lines 1–20, the module docstring through the `pwd_context = ...` line; do NOT include the trailing blank lines before `class CreateUserDialog`) is:

```python
"""User Management screen for BaluHost TUI."""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Container, Vertical, Horizontal, Grid
from textual.widgets import Header, Footer, Static, Label, DataTable, Button, Input, Select
from textual.binding import Binding
from rich.text import Text

from app.services.users import list_users, create_user, update_user, delete_user, get_user
from app.core.database import SessionLocal
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

Replace it with:

```python
"""User Management screen for BaluHost TUI (over the BackendClient)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, Label, DataTable, Button, Input, Select
from textual.binding import Binding
from rich.text import Text

from baluhost_tui.api import users as users_api
```

(Removed: `sys`/`Path`/`datetime`, the `sys.path.insert`, `Vertical`/`Grid` (the dialogs use only `Container`/`Horizontal`), `app.services.users`, `app.core.database.SessionLocal`, `passlib`/`CryptContext`, and the module-level `pwd_context`. Keep `Select` — used by Create/Edit dialogs.)

Important: read the dialogs to confirm they only use `Container` and `Horizontal` from `textual.containers` (they do — `CreateUserDialog`/`EditUserDialog`/`PasswordResetDialog`/`DeleteConfirmDialog` each use `with Container(...)` and `with Horizontal(...)`). If any uses `Vertical`/`Grid`, add it back to the import.

- [ ] **Step 2: Add `__init__` to `UserManagementScreen` (track loaded users)**

Find the `class UserManagementScreen(Screen):` line and its docstring `"""User management screen with CRUD operations."""`. Immediately after that docstring, before the `CSS = """` block, insert:

```python

    def __init__(self) -> None:
        super().__init__()
        self._users_by_id: dict[int, dict] = {}
```

- [ ] **Step 3: Replace `load_users`**

Replace the entire `load_users` method with:

```python
    def load_users(self) -> None:
        """Load users from the backend API."""
        try:
            table = self.query_one("#users-table", DataTable)
            table.clear()

            data = users_api.list_users(self.app.client)
            users = data.get("users", [])
            self._users_by_id = {}
            for user in users:
                uid = user.get("id")
                if uid is not None:
                    self._users_by_id[int(uid)] = user

                is_active = bool(user.get("is_active"))
                status_color = "green" if is_active else "red"
                status_text = Text("✓", style=status_color) if is_active else Text("✗", style=status_color)

                role = user.get("role", "user")
                role_color = "yellow" if role == "admin" else "white"
                role_text = Text(str(role), style=role_color)

                created = str(user.get("created_at") or "")
                created_str = created[:10] if created else "N/A"

                table.add_row(
                    str(user.get("id", "")),
                    user.get("username", ""),
                    user.get("email") or "",
                    role_text,
                    status_text,
                    created_str,
                    key=str(user.get("id", "")),
                )

            self.notify(f"Loaded {len(users)} users", severity="information")
        except Exception as e:
            self.notify(f"Error loading users: {str(e)}", severity="error")
```

- [ ] **Step 4: Replace `action_new_user`**

Replace the entire `action_new_user` method with:

```python
    def action_new_user(self) -> None:
        """Create a new user via the API."""
        def handle_result(data):
            if not data:
                return
            ok, msg = users_api.create_user(
                self.app.client,
                username=data["username"],
                password=data["password"],
                email=data.get("email") or None,
                role=data.get("role", "user"),
            )
            self.notify(msg, severity="information" if ok else "error")
            if ok:
                self.load_users()

        self.app.push_screen(CreateUserDialog(), handle_result)
```

- [ ] **Step 5: Replace `action_edit_user`**

Replace the entire `action_edit_user` method with (it reads the cached user dict from the last load instead of querying the DB):

```python
    def action_edit_user(self) -> None:
        """Edit the selected user via the API."""
        table = self.query_one("#users-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No user selected", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
        except Exception:
            self.notify("No user selected", severity="warning")
            return

        user = self._users_by_id.get(user_id)
        if not user:
            self.notify("User not found — refresh and retry", severity="error")
            return

        user_data = {
            "id": user.get("id"),
            "username": user.get("username", ""),
            "email": user.get("email") or "",
            "role": user.get("role", "user"),
            "is_active": bool(user.get("is_active")),
        }

        def handle_result(data):
            if not data:
                return
            ok, msg = users_api.update_user(
                self.app.client,
                user_id,
                email=data.get("email") or None,
                role=data.get("role"),
                is_active=data.get("is_active"),
            )
            self.notify(msg, severity="information" if ok else "error")
            if ok:
                self.load_users()

        self.app.push_screen(EditUserDialog(user_data), handle_result)
```

- [ ] **Step 6: Replace `action_reset_password`**

Replace the entire `action_reset_password` method with:

```python
    def action_reset_password(self) -> None:
        """Reset the selected user's password via the API."""
        table = self.query_one("#users-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No user selected", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
            username = str(row[1])
        except Exception:
            self.notify("No user selected", severity="warning")
            return

        def handle_result(new_password):
            if not new_password:
                return
            ok, msg = users_api.set_password(self.app.client, user_id, new_password)
            self.notify(f"{username}: {msg}", severity="information" if ok else "error")

        self.app.push_screen(PasswordResetDialog(username), handle_result)
```

- [ ] **Step 7: Replace `action_delete_user`**

Replace the entire `action_delete_user` method with (it derives admin-ness from the cached user dict rather than parsing the row's Text object):

```python
    def action_delete_user(self) -> None:
        """Delete the selected user via the API."""
        table = self.query_one("#users-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No user selected", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
            username = str(row[1])
        except Exception:
            self.notify("No user selected", severity="warning")
            return

        cached = self._users_by_id.get(user_id, {})
        is_admin = str(cached.get("role", "")).lower() == "admin"

        def handle_result(confirmed):
            if not confirmed:
                return
            ok, msg = users_api.delete_user(self.app.client, user_id)
            self.notify(f"{username}: {msg}", severity="information" if ok else "error")
            if ok:
                self.load_users()

        self.app.push_screen(DeleteConfirmDialog(username, is_admin), handle_result)
```

- [ ] **Step 8: Import-smoke + confirm direct-DB gone**

Run: `cd backend ; python -c "import baluhost_tui.screens.users, baluhost_tui.app; print('OK')"`
Expected: `OK`.

Read the file and confirm NO `SessionLocal`, `app.services`, `app.schemas`, `app.core`, `passlib`, `CryptContext`, `pwd_context`, `import sys`, `sys.path.insert`, or `datetime` references remain anywhere (the dialogs don't use any of them).

- [ ] **Step 9: Run the full suite + commit**

Run: `cd backend ; python -m pytest tests/tui/ --no-cov -q`
Expected: all pass.

```
git add backend/baluhost_tui/screens/users.py
git commit -m "refactor(tui): UserManagementScreen CRUD via api.users (drop direct DB)"
```

---

## Task 3: Full-suite verification

**Files:** none changed.

- [ ] **Step 1: Run the full TUI suite**

Run: `cd backend ; python -m pytest tests/tui/ -v --no-cov`
Expected: all pass (`test_api_users.py` now 12; everything else unchanged and green).

- [ ] **Step 2: Import-smoke the whole package**

Run: `cd backend ; python -c "import baluhost_tui.app, baluhost_tui.main, baluhost_tui.screens.users, baluhost_tui.screens.dashboard, baluhost_tui.screens.logs; from baluhost_tui.api import users; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Confirm direct-DB is gone from the users screen**

Run (PowerShell): `cd backend ; if (Select-String -Path baluhost_tui/screens/users.py -Pattern "SessionLocal|app\.services|app\.schemas|passlib|CryptContext" -Quiet) { Write-Output "STILL HAS DIRECT-DB" } else { Write-Output "clean" }`
Expected: `clean`. (PowerShell `Select-String` is allowed — the hook blocks only the Grep tool and shell `grep`/`rg`.)

- [ ] **Step 4: Manual smoke (optional, dev)**

With `python start_dev.py` running, `cd backend ; python -m baluhost_tui dashboard`, log in as `admin`/`DevMode2024`, press `u` for Users. The table lists users; `n` creates (e.g. `tester`/`Testpass123`), `e` edits the selected user, `p` resets password, `d` deletes — each shows a success/error toast and the list refreshes. No commit.

---

## Self-Review

**1. Spec coverage (this plan's slice — users CRUD port):**
- Spec "User-Management: volles CRUD (Create/Edit/Reset-PW/Delete)" over the API → Task 1 (`create_user/update_user/set_password/delete_user`) + Task 2 (the five screen ops). ✓
- Spec "remove direct-DB" → Task 2 drops `SessionLocal`/`app.services`/`passlib`. ✓
- Deferred (stated): bulk-delete (local-channel) → Plan 5; `BaseScreen`/cleanup → Plan 6.

**2. Placeholder scan:** No TBD/TODO; every code step shows complete content; every run step has exact command + expected output. ✓

**3. Type/consistency checks:**
- `api/users.py` `_Client` Protocol extended with `post/put/delete` (Task 1 Step 3) — `list_users` still uses `get`, the write ops use post/put/delete; the screen passes `self.app.client` (a `BackendClient` with all four verbs). ✓
- Write ops return `tuple[bool, str]`; the screen handlers consume `(ok, msg)` consistently. ✓
- `create_user(username, password, email=None, role="user")` matches the dialog result keys `{username,email,password,role}`. `update_user(user_id, email, role, is_active)` matches `EditUserDialog`'s `{email, role, is_active}`. `set_password(user_id, password)` matches `PasswordResetDialog` (returns the password string). `delete_user(user_id)` matches `DeleteConfirmDialog` (returns bool). ✓
- `_users_by_id` keyed by `int(id)`; `action_edit_user`/`action_delete_user` look up `int(row[0])`. ✓
- `created_at` is an ISO string from `UserPublic`; `created[:10]` yields `YYYY-MM-DD`. ✓

**4. Behavioral notes (intentional):**
- Emptying the email in the Edit dialog sends no `email` field (treated as "leave unchanged") rather than clearing it — a minor, acceptable difference from a hypothetical "set null" semantics; the original code's behavior here was ambiguous too.
- After this plan, `users.py` no longer touches the DB; the Dashboard "U → Users" shortcut and `app.action_users()` now open a fully API-backed screen (resolving the transitional gap noted in Plan 3).

---

## Next plans (outline)

- **Plan 5 — Destructive ops:** `ConfirmDialog` widget; RAID create/delete/format via local-channel API (replace hybrid `raid.py`); users **bulk-delete** (local-channel); power app-restart/shutdown actions; remove `context.py`.
- **Plan 6 — New screens + cleanup:** plugins (install/uninstall), vpn (read + sync-server-keys), network, settings; `BaseScreen`; centralize `sys.path`; fix welcome version; update `TUI_FEATURE_AUDIT.md`.
