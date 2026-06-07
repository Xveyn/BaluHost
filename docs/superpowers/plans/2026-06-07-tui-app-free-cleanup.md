# TUI `app.*`-free Cleanup (Plan A of standalone-.deb) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `baluhost_tui` package fully independent of the backend (`app.*`) code so it can later be PyInstaller-bundled into a standalone `.deb` — by porting the `status`/`users` CLI to the API, moving `reset-password` to a backend-only script, and deleting `context.py`.

**Architecture:** The `status`/`users` CLI commands stop using the hybrid `get_context` (direct-DB/API) and instead build a `BackendClient` and call the already-tested `api.*` wrappers (so they need a token, resolved from flag/env/saved file). `reset-password` (inherently direct-DB, a backend-side rescue tool) moves to `backend/scripts/reset_password.py` and leaves the TUI. `context.py` and `commands/emergency.py` are deleted. The legacy `--mode` option is removed (nothing uses it anymore).

**Tech Stack:** Python 3.11, Click, Rich, httpx, pytest. Builds on Plans 1–5 (`BackendClient`, `api.users.list_users`, `api.system.storage`/`get_channel_status`, `config.save_token`/`load_token`). Spec: `docs/superpowers/specs/2026-06-07-tui-standalone-deb-artifact-design.md`.

---

## Context for the implementer

- `import baluhost_tui.app` (interactive TUI) is already `app.*`-free. The ONLY `app.*` imports left in the package are: `commands/emergency.py` (reset-password), `commands/status.py`, `commands/users.py`, and `context.py`. `commands/files.py` is already `app.*`-free (uses httpx directly) — leave it.
- The `api.*` wrappers used here already exist and are unit-tested:
  - `api.users.list_users(client) -> {"users":[{id,username,email,role,is_active,...}], "total","active","inactive","admins"}` (empty skeleton on failure).
  - `api.system.storage(client) -> dict|None` (`{total,used,use_percent,...}`).
  - `api.system.get_channel_status(client) -> "local"|"remote"` (fail-safe "remote").
- `config.py` (in `baluhost_tui/`) already has `save_token(token)`, `load_token() -> str|None`, `clear_token()`, and `TOKEN_FILE = ~/.baluhost/token`.
- `BackendClient(socket_path=None, server=None, token=None)` auto-detects transport (UDS prod / TCP `127.0.0.1:8000` dev) and injects the bearer token.
- The ported CLI commands need a token (the endpoints require auth). Token precedence used everywhere here: `--token` flag → global `--token` → `BALUHOST_TOKEN` env → `config.load_token()` (saved by the interactive login). On no token / 401 the wrappers fail safe (empty/None) and the command prints a clear "not authenticated" hint.
- Tests use the inline `_Resp`/`_FakeClient` pattern; Rich output is captured with `Console(file=io.StringIO())`. Run from `backend/`: `python -m pytest tests/tui/<file> -v --no-cov`.
- Shell is PowerShell: chain with `;` / `if ($?) {...}`. Hook blocks grep/rg + the Grep tool — use Read/Glob. Worktree `D:\Programme (x86)\Baluhost\.claude\worktrees\feat+tui-companion-rebuild`; confirm `git branch --show-current` is `feat/tui-companion-rebuild` before each commit. `backend/scripts/` already exists.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/baluhost_tui/commands/users.py` | Rewrite | `render_users(client, console=None)` via `api.users.list_users` |
| `backend/baluhost_tui/commands/status.py` | Rewrite | `show_status(client, console=None)` via `api.*` wrappers |
| `backend/baluhost_tui/screens/login.py` | Modify | persist token via `config.save_token` on successful login |
| `backend/baluhost_tui/main.py` | Modify | `status`/`users` build `BackendClient`+token; drop `reset-password` cmd, `--mode`, emergency import |
| `backend/scripts/reset_password.py` | Create | backend-side offline password reset (moved from `commands/emergency.py`) |
| `backend/baluhost_tui/commands/emergency.py` | Delete | moved to backend script |
| `backend/baluhost_tui/context.py` | Delete | no importers left |
| tests under `backend/tests/tui/` | Create/modify | cover the ported CLI render functions |

Out of scope: PyInstaller / `.deb` / `tui-build.yml` (Plan B); any interactive-TUI behavior change.

---

## Task 1: Port `commands/users.py` to the API

**Files:**
- Rewrite: `backend/baluhost_tui/commands/users.py`
- Test: `backend/tests/tui/test_cli_users.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tui/test_cli_users.py`:

```python
"""Tests for the ported `users` CLI render function."""
from __future__ import annotations

import io
from typing import Any

from rich.console import Console

from baluhost_tui.commands.users import render_users


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    def get(self, path: str, **_: Any) -> _Resp:
        assert path == "/api/users/"
        return self._resp


def _capture():
    return Console(file=io.StringIO(), width=120)


def test_render_users_lists_rows():
    client = _FakeClient(_Resp(200, {
        "users": [{"id": 1, "username": "admin", "email": "a@x.io", "role": "admin", "is_active": True}],
        "total": 1, "active": 1, "inactive": 0, "admins": 1,
    }))
    con = _capture()
    render_users(client, console=con)
    out = con.file.getvalue()
    assert "admin" in out
    assert "Total: 1" in out


def test_render_users_handles_empty():
    client = _FakeClient(_Resp(403, {"detail": "nope"}))
    con = _capture()
    render_users(client, console=con)
    out = con.file.getvalue()
    # empty skeleton -> 0 users; no crash
    assert "Total: 0" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend ; python -m pytest tests/tui/test_cli_users.py -v --no-cov`
Expected: FAIL — `render_users` does not exist (current `users.py` has `list_users(mode, server)`).

- [ ] **Step 3: Rewrite `backend/baluhost_tui/commands/users.py` entirely with:**

```python
"""`users` CLI — list users over the BackendClient (API)."""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from baluhost_tui.api import users as users_api

_console = Console()


def render_users(client: Any, console: Console | None = None) -> None:
    """Fetch users via the API and print a table."""
    console = console or _console
    data = users_api.list_users(client)
    users = data.get("users", [])

    table = Table(title="Users", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("Email", style="blue")
    table.add_column("Role", style="yellow")
    table.add_column("Active", style="magenta")

    for user in users:
        table.add_row(
            str(user.get("id", "")),
            user.get("username", ""),
            user.get("email") or "-",
            user.get("role", ""),
            "✓" if user.get("is_active") else "✗",
        )

    console.print(table)
    console.print(f"\nTotal: {data.get('total', 0)} users")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend ; python -m pytest tests/tui/test_cli_users.py -v --no-cov`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```
git add backend/baluhost_tui/commands/users.py backend/tests/tui/test_cli_users.py
git commit -m "refactor(tui): port users CLI to api.users (drop get_context/app.*)"
```

---

## Task 2: Port `commands/status.py` to the API

**Files:**
- Rewrite: `backend/baluhost_tui/commands/status.py`
- Test: `backend/tests/tui/test_cli_status.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tui/test_cli_status.py`:

```python
"""Tests for the ported `status` CLI render function."""
from __future__ import annotations

import io
from typing import Any

from rich.console import Console

from baluhost_tui.commands.status import show_status


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self) -> None:
        self.responses: dict[str, _Resp] = {}

    def get(self, path: str, **_: Any) -> _Resp:
        return self.responses.get(path, _Resp(200, {}))


def _capture():
    return Console(file=io.StringIO(), width=120)


def test_show_status_renders_channel_users_storage():
    c = _FakeClient()
    c.responses["/api/system/channel-status"] = _Resp(200, {"channel": "local"})
    c.responses["/api/users/"] = _Resp(200, {"users": [], "total": 3, "active": 2, "inactive": 1, "admins": 1})
    c.responses["/api/system/storage"] = _Resp(200, {"total": 100, "used": 40, "use_percent": "40%"})
    con = _capture()
    show_status(c, console=con)
    out = con.file.getvalue()
    assert "local" in out
    assert "3" in out          # total users
    assert "40%" in out        # storage use_percent


def test_show_status_survives_failures():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    con = _capture()
    show_status(_Boom(), console=con)  # must not raise
    out = con.file.getvalue()
    assert "remote" in out  # get_channel_status fail-safe default
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend ; python -m pytest tests/tui/test_cli_status.py -v --no-cov`
Expected: FAIL — `show_status` signature is `(mode, server)` (the old version).

- [ ] **Step 3: Rewrite `backend/baluhost_tui/commands/status.py` entirely with:**

```python
"""`status` CLI — quick system status over the BackendClient (API)."""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from baluhost_tui.api import users as users_api
from baluhost_tui.api import system as system_api

_console = Console()


def show_status(client: Any, console: Console | None = None) -> None:
    """Fetch a status summary via the API and print it."""
    console = console or _console

    channel = system_api.get_channel_status(client)
    users = users_api.list_users(client)
    storage = system_api.storage(client)

    table = Table(title="BaluHost System Status", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Channel", channel)
    table.add_row("Total Users", str(users.get("total", 0)))
    table.add_row("Active Users", str(users.get("active", 0)))
    table.add_row("Admin Users", str(users.get("admins", 0)))
    if storage and storage.get("total"):
        used = storage.get("used", 0)
        total = storage.get("total", 0)
        pct = storage.get("use_percent") or f"{round(used / total * 100, 1)}%"
        table.add_row("Storage", f"{pct} used ({used}/{total} bytes)")
    else:
        table.add_row("Storage", "[dim]unavailable[/dim]")

    console.print(table)
    ok = channel == "local"
    console.print(
        Panel(
            "[green]✓ Local channel[/green]" if ok else "[yellow]Remote channel[/yellow]",
            title="Status",
        )
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend ; python -m pytest tests/tui/test_cli_status.py -v --no-cov`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```
git add backend/baluhost_tui/commands/status.py backend/tests/tui/test_cli_status.py
git commit -m "refactor(tui): port status CLI to api.* (drop get_context/app.*)"
```

---

## Task 3: Move `reset-password` to a backend-only script

**Files:**
- Create: `backend/scripts/reset_password.py`
- Delete: `backend/baluhost_tui/commands/emergency.py`

The logic stays identical (direct DB); it just leaves the TUI package. It runs on the server where the backend is installed.

- [ ] **Step 1: Create `backend/scripts/reset_password.py`**

```python
"""Offline password reset (backend-side rescue tool).

Run on the server where the backend is installed, e.g. when login is broken:
    python scripts/reset_password.py <username>
Prompts for the new password. Requires direct database access.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Make the backend `app` package importable when run as a loose script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from passlib.context import CryptContext  # noqa: E402

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def reset_user_password(username: str, new_password: str) -> None:
    """Set *username*'s password hash directly in the DB. Raises ValueError if not found."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User '{username}' not found")
        user.hashed_password = pwd_context.hash(new_password)
        db.commit()
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="BaluHost offline password reset")
    parser.add_argument("username", help="Username to reset")
    args = parser.parse_args()

    new_password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if new_password != confirm:
        print("Error: passwords do not match", file=sys.stderr)
        return 1
    if not new_password:
        print("Error: password cannot be empty", file=sys.stderr)
        return 1
    try:
        reset_user_password(args.username, new_password)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ Password reset for user: {args.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Delete the old emergency command module**

Run: `git rm backend/baluhost_tui/commands/emergency.py`

- [ ] **Step 3: Smoke the script imports (won't reset anything without a DB)**

Run: `cd backend ; python -c "import ast; ast.parse(open('scripts/reset_password.py',encoding='utf-8').read()); print('parses OK')"`
Expected: `parses OK`. (We don't run it — it needs a live DB; this just confirms valid syntax.)

- [ ] **Step 4: Commit**

```
git add backend/scripts/reset_password.py
git rm backend/baluhost_tui/commands/emergency.py
git commit -m "refactor(tui): move reset-password to backend/scripts (out of TUI package)"
```

---

## Task 4: Persist the token on interactive login

**Files:**
- Modify: `backend/baluhost_tui/screens/login.py`

So the ported `status`/`users` CLI can reuse the token saved by `baluhost-tui dashboard`.

- [ ] **Step 1: Add the config import**

In `backend/baluhost_tui/screens/login.py`, replace:

```python
from baluhost_tui.api import auth as auth_api
```

with:

```python
from baluhost_tui.api import auth as auth_api
from baluhost_tui import config
```

- [ ] **Step 2: Persist the token on success**

In `attempt_login`, find:

```python
        self.app.token = token
        self.app.current_user = user
```

and replace with:

```python
        self.app.token = token
        self.app.current_user = user
        try:
            config.save_token(token)
        except Exception:
            pass  # token persistence is best-effort; login still succeeds
```

- [ ] **Step 3: Import-smoke**

Run: `cd backend ; python -c "import baluhost_tui.screens.login; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```
git add backend/baluhost_tui/screens/login.py
git commit -m "feat(tui): persist access token on login for CLI reuse"
```

---

## Task 5: Rewire `main.py` — port status/users, drop reset-password + --mode

**Files:**
- Modify: `backend/baluhost_tui/main.py`

- [ ] **Step 1: Remove `--mode` from the group + drop it from the context**

Replace:

```python
@click.group()
@click.option('--mode', type=click.Choice(['auto', 'local', 'remote']), default='auto',
              help='(Legacy) connection mode for the status/users CLI commands')
@click.option('--socket', 'socket_path', default=None,
              help='Unix socket path (prod local channel). Auto-detected when omitted.')
@click.option('--server', default=None,
              help='Server URL (dev TCP, e.g. http://127.0.0.1:8000). Auto-detected when omitted.')
@click.option('--token', default=None,
              help='Bearer token for API access')
@click.option('--debug/--no-debug', default=False,
              help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, mode: str, socket_path: str | None, server: str | None, token: str | None, debug: bool):
```

with:

```python
@click.group()
@click.option('--socket', 'socket_path', default=None,
              help='Unix socket path (prod local channel). Auto-detected when omitted.')
@click.option('--server', default=None,
              help='Server URL (dev TCP, e.g. http://127.0.0.1:8000). Auto-detected when omitted.')
@click.option('--token', default=None,
              help='Bearer token for API access')
@click.option('--debug/--no-debug', default=False,
              help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, socket_path: str | None, server: str | None, token: str | None, debug: bool):
```

Then replace the `cli()` body:

```python
    ctx.ensure_object(dict)
    ctx.obj['mode'] = mode
    ctx.obj['socket_path'] = socket_path
    ctx.obj['server'] = server
    ctx.obj['token'] = token
    ctx.obj['debug'] = debug
```

with:

```python
    ctx.ensure_object(dict)
    ctx.obj['socket_path'] = socket_path
    ctx.obj['server'] = server
    ctx.obj['token'] = token
    ctx.obj['debug'] = debug
```

- [ ] **Step 2: Delete the `reset_password` command**

Remove the entire command (the offline reset now lives in `backend/scripts/reset_password.py`):

```python
@cli.command()
@click.argument('username')
@click.option('--password', prompt=True, hide_input=True,
              confirmation_prompt=True,
              help='New password for user')
@click.pass_context
def reset_password(ctx: click.Context, username: str, password: str):
    """Emergency password reset (requires local access)."""
    from .commands.emergency import reset_user_password
    
    mode = ctx.obj['mode']
    
    if mode == 'remote':
        console.print("[red]Error: Password reset requires local access[/red]")
        console.print("Run this command on the server directly.")
        sys.exit(1)
    
    try:
        reset_user_password(username, password)
        console.print(f"[green]✓[/green] Password reset successfully for user: {username}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
```

- [ ] **Step 3: Replace the `status` command**

Replace:

```python
@cli.command()
@click.pass_context
def status(ctx: click.Context):
    """Quick system status check."""
    from .commands.status import show_status
    
    mode = ctx.obj['mode']
    server = ctx.obj['server'] or 'http://localhost:8000'

    show_status(mode=mode, server=server)
```

with:

```python
@cli.command()
@click.option('--token', 'token_opt', default=None, help='Auth token (overrides global)')
@click.pass_context
def status(ctx: click.Context, token_opt: str | None):
    """Quick system status check (over the API)."""
    from .commands.status import show_status
    from .client import BackendClient
    from . import config

    tok = token_opt or ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN') or config.load_token()
    client = BackendClient(socket_path=ctx.obj.get('socket_path'), server=ctx.obj.get('server'), token=tok)
    show_status(client)
```

- [ ] **Step 4: Replace the `users` command**

Replace:

```python
@cli.command()
@click.pass_context
def users(ctx: click.Context):
    """List all users."""
    from .commands.users import list_users
    
    mode = ctx.obj['mode']
    server = ctx.obj['server'] or 'http://localhost:8000'

    list_users(mode=mode, server=server)
```

with:

```python
@cli.command()
@click.option('--token', 'token_opt', default=None, help='Auth token (overrides global)')
@click.pass_context
def users(ctx: click.Context, token_opt: str | None):
    """List all users (over the API)."""
    from .commands.users import render_users
    from .client import BackendClient
    from . import config

    tok = token_opt or ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN') or config.load_token()
    client = BackendClient(socket_path=ctx.obj.get('socket_path'), server=ctx.obj.get('server'), token=tok)
    render_users(client)
```

Leave `dashboard`, `files-download`, `files-upload` unchanged (they don't use `--mode`; `files-*` already API-based).

- [ ] **Step 5: Verify CLI + help**

Run: `cd backend ; python -c "from baluhost_tui.main import cli; print('OK')"`
Expected: `OK`.

Run: `cd backend ; python -m baluhost_tui --help`
Expected: command list shows `dashboard, status, users, files-download, files-upload` and **no** `reset-password`; the group help no longer lists `--mode`.

- [ ] **Step 6: Commit**

```
git add backend/baluhost_tui/main.py
git commit -m "refactor(tui): main status/users over BackendClient; drop reset-password cmd + --mode"
```

---

## Task 6: Delete `context.py`

**Files:**
- Delete: `backend/baluhost_tui/context.py`

After Tasks 1–2 nothing imports it (raid dropped it in Plan 5; status/users now use the client).

- [ ] **Step 1: Confirm there are no importers**

Run (PowerShell): `cd backend ; if (Select-String -Path baluhost_tui/*.py,baluhost_tui/**/*.py -Pattern "baluhost_tui.context|from .context|import context|get_context" -Quiet) { Write-Output "STILL IMPORTED" } else { Write-Output "no importers" }`
Expected: `no importers`. (If any hit appears, fix that file before deleting.)

- [ ] **Step 2: Delete it**

Run: `git rm backend/baluhost_tui/context.py`

- [ ] **Step 3: Import-smoke the whole package**

Run: `cd backend ; python -c "import baluhost_tui.app, baluhost_tui.main, baluhost_tui.commands.status, baluhost_tui.commands.users, baluhost_tui.commands.files; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```
git rm backend/baluhost_tui/context.py
git commit -m "refactor(tui): delete context.py (no importers after CLI port)"
```

---

## Task 7: Verify the package is fully `app.*`-free

**Files:** none changed.

- [ ] **Step 1: Source scan for backend imports**

Run: `cd backend ; python - <<'PY'`
```python
import pathlib, re
hits = []
for f in sorted(pathlib.Path("baluhost_tui").rglob("*.py")):
    for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if re.match(r'^\s*(from|import)\s+app(\.|\s|$)', line):
            hits.append(f"{f.as_posix()}:{i}: {line.strip()}")
print("app.* imports in baluhost_tui:", hits or "NONE")
```
(close the heredoc with `PY`)
Expected: `NONE`.

- [ ] **Step 2: Runtime scan — importing the whole package loads no `app.*`**

Run: `cd backend ; python -c "import sys; import baluhost_tui.main, baluhost_tui.app, baluhost_tui.commands.status, baluhost_tui.commands.users, baluhost_tui.commands.files; mods=[m for m in sys.modules if m=='app' or m.startswith('app.')]; print('app.* loaded:', mods or 'NONE')"`
Expected: `app.* loaded: NONE`.

- [ ] **Step 3: Full TUI suite**

Run: `cd backend ; python -m pytest tests/tui/ -v --no-cov`
Expected: all pass — new `test_cli_users.py` (2), `test_cli_status.py` (2); removed coverage for the deleted emergency/context modules; everything else green.

- [ ] **Step 4: Commit (if any incidental fixes were needed; otherwise nothing to commit)**

If Steps 1–3 surfaced a stray importer that needed fixing, commit that fix; otherwise this task is verification-only.

---

## Self-Review

**1. Spec coverage (Phase A of the standalone-.deb spec):**
- A1 "port status/users to API" → Tasks 1 + 2 (+ token wiring in Task 5). ✓
- A2 "move reset-password to backend-only script" → Task 3 (+ command removal in Task 5). ✓
- A3 "delete context.py" → Task 6. ✓
- A4 "verify app.*-free" → Task 7. ✓
- Token-reuse design (login persists token) → Task 4. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete content; every run step has exact command + expected output. ✓

**3. Type/consistency checks:**
- `render_users(client, console=None)` / `show_status(client, console=None)` — `main.py` calls them with a single `client` arg (console defaults to the module console). ✓
- Both use already-existing wrappers: `users_api.list_users` (dict), `system_api.get_channel_status` (str), `system_api.storage` (dict|None). ✓
- `main.py` token chain `token_opt or ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN') or config.load_token()` — `config.load_token` returns `str|None`; `BackendClient(token=None)` is valid. ✓
- `--mode` removed: nothing references `ctx.obj['mode']` after Tasks 2–4 (reset_password — the only `ctx.obj['mode']` reader — is deleted in Task 5 Step 2; status/users rewritten in Steps 3–4). ✓
- `reset_user_password` moves verbatim to the backend script; the TUI no longer references it. ✓

**4. Behavioral notes:**
- `status`/`users` now require a token (flag/env/saved). The interactive login persists the token (Task 4) so `baluhost-tui status` works after a TUI login (within the access-token's 15-min lifetime; `--token`/env for scripting).
- `reset-password` is no longer a `baluhost-tui` subcommand; it's `python scripts/reset_password.py <user>` on the server.

---

## Next plan

**Plan B (packaging):** PyInstaller spec for `baluhost-tui` (`--collect-all textual`), `.deb` via `dpkg-deb` (binary → `/usr/bin/baluhost-tui`), `tui-build.yml` (ubuntu-latest, x86_64; push:main dev artifact + tag `v*` release attach), CODEOWNERS + ci-cd-security rule. Written after Plan A lands (so the binary builds against the verified `app.*`-free package).
