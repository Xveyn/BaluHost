# KDE-Session entsperren beim Displays-Einschalten — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /system/sleep/desktop/enable` entsperrt zusätzlich die grafische KDE-Session — aber nur für Berechtigte und nur aus LAN/VPN.

**Architecture:** Ein neues Modul `session_lock.py` kapselt den Mechanismus (`loginctl`, Session-Ermittlung, `LockedHint`-Polling) hinter einem Protocol mit Dev- und Linux-Backend, exakt wie `desktop_backend.py`. Die Policy — beide Gates plus Audit — steckt in **genau einer** Modulfunktion `unlock_if_permitted()`, die sowohl die Route als auch der Gaming-Modus aufruft.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, pytest (`asyncio_mode = "auto"`), React + TypeScript + Vitest.

**Spec:** `docs/superpowers/specs/2026-07-24-session-unlock-on-desktop-enable-design.md`
**Branch:** `feat/session-unlock-on-desktop-enable` (existiert, Spec ist dort committed)

## Global Constraints

- **Arbeitsverzeichnis Backend:** `backend/` — Testpfade relativ dazu. Frontend: `client/`.
- **Kein `&&` im PowerShell-Tool** (PowerShell 5.1); mit `;` trennen. Im Bash-Tool erlaubt.
- **Commit-Nachrichten ASCII-only**, einzeilig je `-m`, letzte Zeile `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Type Hints auf allen Funktionen**, Docstrings auf öffentlichen Funktionen/Klassen.
- **Migration setzt auf `down_revision = 'b661786568c1'`** — verifiziert der einzige Head (116 Revisionen, 2026-07-24). Niemals den Dev-DB-Head nehmen (#123 → #124).
- **Die Alembic-Kette läuft nicht von null durch (#471).** Migrationen werden isoliert geprüft: Schema stampen, dann `upgrade`/`downgrade`.
- **Grundregel, die keine Aufgabe verletzen darf:** Ein fehlgeschlagenes oder verweigertes Entsperren lässt `enable` weiterhin `success=true` liefern. Displays anschalten darf nie an der Sperre scheitern.
- **Konstanten wörtlich:** `_POLL_INTERVAL_SECONDS = 0.2`, `_POLL_TIMEOUT_SECONDS = 3.0`, `_COMMAND_TIMEOUT_SECONDS = 10`, Aktionsschlüssel `"unlock_session"`, Spalte `can_unlock_session`, Audit-Aktion `desktop_unlock_session`.
- **`unlock_message` ist ein englischer Debug-String** und wird nie wörtlich in der UI gerendert (#406).

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `app/services/power/session_lock.py` (neu) | Mechanismus (Protocol + Dev/Linux) **und** die eine Policy-Funktion |
| `app/models/power_permissions.py` (ändern) | Spalte `can_unlock_session` |
| `alembic/versions/<rev>_…` (neu) | Spalte anlegen/entfernen |
| `app/services/power_permissions.py` (ändern) | `_ACTION_FIELD_MAP`-Eintrag — **ohne ihn schlägt nichts fehl, es funktioniert nur nie** |
| `app/schemas/power_permissions.py` (ändern) | Feld in drei Schemas |
| `app/api/routes/desktop.py` (ändern) | `enable()` versucht den Unlock |
| `app/plugins/base.py` (ändern) | `run_menu_action`-Kontext |
| `app/api/routes/plugins.py` (ändern) | reicht `user` + `client_host` durch |
| `app/plugins/installed/steam_gaming/__init__.py` (ändern) | Gaming-Modus entsperrt zwischen Displays und Big Picture |
| `client/src/api/powerPermissions.ts` (ändern) | drei Interfaces |
| `client/src/api/desktop.ts` (ändern) | zwei Antwortfelder |
| `client/src/components/user-management/PowerPermissionsSection.tsx` (ändern) | Checkbox |
| `client/src/components/PowerMenu.tsx` (ändern) | übersetzter Hinweis statt Debug-String |
| `client/src/i18n/locales/{de,en}/admin.json` (ändern) | Label des neuen Rechts |
| `client/src/i18n/locales/{de,en}/common.json` (ändern) | Hinweis-Text |

---

## Task 1: Messung des Dienst-Kontexts (kein Code)

Die bisherige Messung lief aus einer **SSH-Session**, die selbst eine logind-Session ist. Das Backend ist ein session-loser Systemdienst. Diese Aufgabe klärt, ob der Unlock auch von dort geht — **bevor Code entsteht.**

**Files:** keine. Ergebnis wird berichtet.

- [ ] **Step 1: Grafische Session-ID ermitteln**

Auf BaluNode:

```bash
loginctl list-sessions
```

Gesucht: die Zeile mit `seat0` und Klasse `user` (bei der Vormessung `2`).

- [ ] **Step 2: Aus einem session-losen Dienst-Kontext sperren und entsperren**

```bash
loginctl show-session <ID> -p LockedHint
sudo systemd-run --uid=1000 --pipe --wait loginctl lock-session <ID>
sleep 2; loginctl show-session <ID> -p LockedHint
sudo systemd-run --uid=1000 --pipe --wait loginctl unlock-session <ID>
sleep 2; loginctl show-session <ID> -p LockedHint
```

Erwartet: `no` → `yes` → `no`.

- [ ] **Step 3: Session-Ermittlung prüfen**

```bash
loginctl show-user 1000 -p Display --value
```

Erwartet: dieselbe ID wie in Step 1. Kommt nichts, greift später der Fallback — auch das ist ein gültiges Ergebnis, es muss nur bekannt sein.

- [ ] **Step 4: Ergebnis melden — und bei Fehlschlag stoppen**

Bleibt `LockedHint` nach Step 2 auf `yes` oder kommt eine polkit-Fehlermeldung, ist die tragende Annahme des Designs widerlegt. **Dann nicht weiterbauen**, sondern melden: das Design bräuchte dann einen sudoers-Eintrag und ist neu abzuwägen.

---

## Task 2: `session_lock.py` — Mechanismus

**Files:**
- Create: `app/services/power/session_lock.py`
- Test: `tests/services/power/test_session_lock.py`

**Interfaces:**
- Produces: `SessionLockBackend` (Protocol, `unlock() -> Tuple[bool, str]`), `DevSessionLockBackend`, `LinuxSessionLockBackend(uid=None, runner=None, sleep=None, monotonic=None)`, `get_session_lock_backend()`.

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/services/power/test_session_lock.py`:

```python
"""Unlocking the graphical KDE session via logind."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import List

from app.services.power.session_lock import (
    DevSessionLockBackend,
    LinuxSessionLockBackend,
)

SHOW_USER = ["loginctl", "show-user", "1000", "-p", "Display", "--value"]
LIST_SESSIONS = ["loginctl", "list-sessions", "--no-legend"]

# Real output shape measured on the box (2026-07-24):
# SESSION UID USER SEAT LEADER CLASS TTY IDLE SINCE
LIST_OUTPUT = (
    "         1  993 ci-runner -     1975 manager-early -    no   -\n"
    "         2 1000 sven      seat0 2023 user          tty2 no   -\n"
    "        27 1000 sven      -    88823 user          -    no   -\n"
    "         3 1000 sven      -     2115 manager       -    no   -\n"
)


def _proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class FakeRunner:
    """Records commands and answers them from a table."""

    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: List[List[str]] = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        for key, value in self.responses.items():
            if list(key) == list(cmd):
                return value() if callable(value) else value
        # LockedHint reads are matched by prefix so tests can vary the session id
        if cmd[:2] == ["loginctl", "show-session"]:
            return self.responses.get("locked_hint", _proc(stdout="no\n"))
        return _proc(returncode=1, stderr="unexpected command")


def _backend(runner, monotonic_values=None):
    clock = iter(monotonic_values or [0.0] * 50)
    return LinuxSessionLockBackend(
        uid=1000,
        runner=runner,
        sleep=lambda _seconds: None,
        monotonic=lambda: next(clock),
    )


class TestSessionDiscovery:
    def test_uses_the_display_property_when_present(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
        })

        ok, detail = _backend(runner).unlock()

        assert ok is True
        assert "2" in detail
        assert LIST_SESSIONS not in runner.calls, "fallback must not run when Display works"

    def test_falls_back_to_list_sessions_when_display_is_empty(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="\n"),
            tuple(LIST_SESSIONS): _proc(stdout=LIST_OUTPUT),
            ("loginctl", "unlock-session", "2"): _proc(),
        })

        ok, _detail = _backend(runner).unlock()

        assert ok is True
        assert ["loginctl", "unlock-session", "2"] in runner.calls

    def test_fallback_skips_seatless_and_non_user_sessions(self):
        """Session 27 is the SSH login (no seat), 3 is the user manager,
        1 belongs to the CI runner - none of them may be picked."""
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="\n"),
            tuple(LIST_SESSIONS): _proc(stdout=LIST_OUTPUT),
            ("loginctl", "unlock-session", "2"): _proc(),
        })

        _backend(runner).unlock()

        unlocked = [c for c in runner.calls if c[:2] == ["loginctl", "unlock-session"]]
        assert unlocked == [["loginctl", "unlock-session", "2"]]

    def test_no_graphical_session_is_a_clean_failure(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="\n"),
            tuple(LIST_SESSIONS): _proc(stdout="         1  993 ci-runner - 1975 manager-early - no -\n"),
        })

        ok, detail = _backend(runner).unlock()

        assert ok is False
        assert "no graphical session" in detail


class TestUnlockVerification:
    def test_success_requires_locked_hint_to_flip(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
            "locked_hint": _proc(stdout="no\n"),
        })

        ok, _detail = _backend(runner).unlock()

        assert ok is True

    def test_a_locker_that_ignores_the_signal_is_reported_as_failure(self):
        """loginctl exits 0 as soon as the signal is SENT. Without reading the
        hint back the API would claim 'unlocked' over a locked screen."""
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
            "locked_hint": _proc(stdout="yes\n"),
        })

        ok, detail = _backend(runner, monotonic_values=[0.0, 0.0, 1.0, 2.0, 9.0]).unlock()

        assert ok is False
        assert "LockedHint" in detail

    def test_polls_until_the_hint_flips(self):
        """kscreenlocker needs a moment; a single immediate read would flap."""
        hints = iter([_proc(stdout="yes\n"), _proc(stdout="yes\n"), _proc(stdout="no\n")])
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
            "locked_hint": lambda: next(hints),
        })

        ok, _detail = _backend(runner).unlock()

        assert ok is True

    def test_nonzero_exit_is_reported(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(returncode=1, stderr="Access denied"),
        })

        ok, detail = _backend(runner).unlock()

        assert ok is False
        assert "Access denied" in detail

    def test_missing_loginctl_is_reported(self):
        def _raise(_cmd):
            raise FileNotFoundError()

        ok, detail = _backend(_raise).unlock()

        assert ok is False
        assert "loginctl not found" in detail

    def test_timeout_is_reported(self):
        def _raise(_cmd):
            raise subprocess.TimeoutExpired(cmd="loginctl", timeout=10)

        ok, detail = _backend(_raise).unlock()

        assert ok is False
        assert "timed out" in detail


class TestDevBackend:
    def test_dev_backend_reports_success_without_loginctl(self):
        ok, detail = DevSessionLockBackend().unlock()

        assert ok is True
        assert "dev" in detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/power/test_session_lock.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.power.session_lock'`

- [ ] **Step 3: Write the module**

Neue Datei `app/services/power/session_lock.py`:

```python
"""Unlock the graphical KDE session via systemd-logind.

`loginctl unlock-session` emits an Unlock signal that kscreenlocker obeys -
the same path fingerprint readers and smartcards use. Measured on the box: it
works as the session owner WITHOUT sudo, and the backend already runs as that
user, so this needs no sudoers rule and no new root path.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Callable, List, Optional, Protocol, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# kscreenlocker processes the Unlock signal asynchronously - the measurement on
# the box needed roughly two seconds. A single immediate read of LockedHint
# would sporadically still say "yes" and report a failure that never happened.
_POLL_INTERVAL_SECONDS = 0.2
_POLL_TIMEOUT_SECONDS = 3.0
_COMMAND_TIMEOUT_SECONDS = 10


class SessionLockBackend(Protocol):
    def unlock(self) -> Tuple[bool, str]: ...


class DevSessionLockBackend:
    """In-memory backend for dev mode / non-Linux hosts."""

    def __init__(self) -> None:
        self._locked = True

    def unlock(self) -> Tuple[bool, str]:
        self._locked = False
        return True, "session unlocked (dev)"


class LinuxSessionLockBackend:
    """Unlocks the user's graphical session through loginctl.

    Blocking - call via asyncio.to_thread. The runner/sleep/monotonic seams
    exist so tests never touch a real loginctl or a real clock.
    """

    def __init__(
        self,
        uid: Optional[int] = None,
        runner: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        monotonic: Optional[Callable[[], float]] = None,
    ) -> None:
        self._uid = uid if uid is not None else os.getuid()
        self._run = runner or self._default_runner
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic

    @staticmethod
    def _default_runner(cmd: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=_COMMAND_TIMEOUT_SECONDS
        )

    def _graphical_session_id(self) -> Optional[str]:
        """The user's graphical session, or None.

        Primary path is logind's own answer (`show-user -p Display`); the
        fallback scans the session list for a seated session of this user,
        which skips SSH logins (no seat) and the user manager (class != user).
        """
        result = self._run(
            ["loginctl", "show-user", str(self._uid), "-p", "Display", "--value"]
        )
        if result.returncode == 0:
            session_id = (result.stdout or "").strip()
            if session_id:
                return session_id

        result = self._run(["loginctl", "list-sessions", "--no-legend"])
        if result.returncode != 0:
            return None
        for line in (result.stdout or "").splitlines():
            parts = line.split()
            # SESSION UID USER SEAT LEADER CLASS TTY IDLE SINCE
            if len(parts) < 6:
                continue
            session_id, uid, _user, seat, _leader, session_class = parts[:6]
            if uid != str(self._uid) or seat == "-" or session_class != "user":
                continue
            return session_id
        return None

    def _locked_hint(self, session_id: str) -> Optional[bool]:
        result = self._run(
            ["loginctl", "show-session", session_id, "-p", "LockedHint", "--value"]
        )
        if result.returncode != 0:
            return None
        value = (result.stdout or "").strip().lower()
        if value in ("yes", "true"):
            return True
        if value in ("no", "false"):
            return False
        return None

    def unlock(self) -> Tuple[bool, str]:
        """Unlock the graphical session and VERIFY it actually unlocked.

        Returns (ok, detail). ok=True means LockedHint reads "no" afterwards -
        loginctl's exit code alone only says the signal was dispatched.
        """
        try:
            session_id = self._graphical_session_id()
            if not session_id:
                return False, "no graphical session found"

            result = self._run(["loginctl", "unlock-session", session_id])
            if result.returncode != 0:
                detail = (result.stderr or "").strip() or f"exit {result.returncode}"
                return False, detail

            deadline = self._monotonic() + _POLL_TIMEOUT_SECONDS
            while True:
                if self._locked_hint(session_id) is False:
                    return True, f"session {session_id} unlocked"
                if self._monotonic() >= deadline:
                    return False, (
                        f"session {session_id} still reports LockedHint=yes"
                    )
                self._sleep(_POLL_INTERVAL_SECONDS)
        except FileNotFoundError:
            return False, "loginctl not found"
        except subprocess.TimeoutExpired:
            return False, "loginctl timed out"


_backend: Optional[SessionLockBackend] = None


def get_session_lock_backend() -> SessionLockBackend:
    """Process-wide backend, chosen once by mode."""
    global _backend
    if _backend is None:
        _backend = (
            DevSessionLockBackend() if settings.is_dev_mode else LinuxSessionLockBackend()
        )
    return _backend
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/power/test_session_lock.py -v --no-cov`
Expected: PASS (11 passed)

- [ ] **Step 5: Verify the polling test is discriminating**

Setze `_POLL_TIMEOUT_SECONDS` testweise auf `0.0`, lass die Datei laufen: `test_polls_until_the_hint_flips` **muss rot werden**. Setze zurück, danach wieder 11 grün. Ergebnis im Report festhalten — ohne diesen Nachweis ist die Polling-Regel nicht belegt.

- [ ] **Step 6: Commit**

```bash
git add app/services/power/session_lock.py tests/services/power/test_session_lock.py
git commit -m "feat(power): logind-based session unlock with verified LockedHint" -m "loginctl exits 0 once the Unlock signal is dispatched, so the hint is polled back - otherwise the API would claim success over a still-locked screen." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Recht `can_unlock_session`

**Files:**
- Modify: `app/models/power_permissions.py`
- Modify: `app/services/power_permissions.py`
- Modify: `app/schemas/power_permissions.py`
- Create: `alembic/versions/<generiert>_add_can_unlock_session.py`
- Test: `tests/services/power/test_unlock_session_permission.py`

**Interfaces:**
- Produces: Spalte `UserPowerPermission.can_unlock_session`, Aktionsschlüssel `"unlock_session"` für `check_permission()`, Feld in `UserPowerPermissionsResponse`, `UserPowerPermissionsUpdate`, `MyPowerPermissionsResponse`.

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/services/power/test_unlock_session_permission.py`:

```python
"""The can_unlock_session permission and its action mapping."""
from __future__ import annotations

from app.models.power_permissions import UserPowerPermission
from app.services.power_permissions import _ACTION_FIELD_MAP, check_permission


class TestActionMapping:
    def test_unlock_session_is_mapped(self):
        """check_permission() returns False for unknown actions instead of
        raising, so a missing map entry is invisible: the feature would simply
        never work for delegated users, with no error anywhere."""
        assert _ACTION_FIELD_MAP["unlock_session"] == "can_unlock_session"


class TestCheckPermission:
    def test_granted_user_passes(self, db_session, regular_user):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_unlock_session=True)
        )
        db_session.commit()

        assert check_permission(db_session, regular_user.id, "unlock_session") is True

    def test_user_without_the_permission_is_rejected(self, db_session, regular_user):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_toggle_desktop=True)
        )
        db_session.commit()

        assert check_permission(db_session, regular_user.id, "unlock_session") is False

    def test_default_is_off(self, db_session, regular_user):
        """No row at all must not grant anything."""
        assert check_permission(db_session, regular_user.id, "unlock_session") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/power/test_unlock_session_permission.py -v --no-cov`
Expected: FAIL — `KeyError: 'unlock_session'` bzw. `TypeError: 'can_unlock_session' is an invalid keyword argument`

- [ ] **Step 3: Add the column**

In `app/models/power_permissions.py` nach der `can_toggle_desktop`-Zeile einfügen:

```python
    can_unlock_session: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
```

- [ ] **Step 4: Add the map entry**

In `app/services/power_permissions.py` `_ACTION_FIELD_MAP` erweitern:

```python
_ACTION_FIELD_MAP = {
    "soft_sleep": "can_soft_sleep",
    "wake": "can_wake",
    "suspend": "can_suspend",
    "wol": "can_wol",
    "toggle_desktop": "can_toggle_desktop",
    "unlock_session": "can_unlock_session",
}
```

- [ ] **Step 5: Add the schema fields**

In `app/schemas/power_permissions.py` drei Ergänzungen:

In `UserPowerPermissionsResponse` nach `can_toggle_desktop`:

```python
    can_unlock_session: bool = False
```

In `UserPowerPermissionsUpdate` nach `can_toggle_desktop`:

```python
    can_unlock_session: Optional[bool] = Field(default=None, description="Allow unlocking the desktop session from the web app")
```

In `MyPowerPermissionsResponse` nach `can_toggle_desktop`:

```python
    can_unlock_session: bool = False
```

- [ ] **Step 6: Generate the migration**

Run: `python -m alembic revision -m "add can_unlock_session permission"`

**Sofort prüfen:** `down_revision` muss `'b661786568c1'` sein. Steht dort etwas anderes, von Hand korrigieren.

`upgrade()`/`downgrade()` ersetzen durch:

```python
def upgrade() -> None:
    """Add can_unlock_session to user_power_permissions (defaults to off)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_unlock_session', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Drop can_unlock_session."""
    op.drop_column('user_power_permissions', 'can_unlock_session')
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/services/power/test_unlock_session_permission.py -v --no-cov`
Expected: PASS (4 passed)

- [ ] **Step 8: Verify the map entry is load-bearing**

Entferne die Zeile `"unlock_session": "can_unlock_session",` testweise, lass die Datei laufen: **drei** Tests müssen rot werden (der Mapping-Test und beide `check_permission`-Tests, die `True` erwarten bzw. das Mapping durchlaufen). Zurücksetzen. Ergebnis berichten.

- [ ] **Step 9: Commit**

```bash
git add app/models/power_permissions.py app/services/power_permissions.py app/schemas/power_permissions.py alembic/versions tests/services/power/test_unlock_session_permission.py
git commit -m "feat(power): separate can_unlock_session permission" -m "Keeps can_toggle_desktop a pure power permission instead of silently turning it into a desktop key. The _ACTION_FIELD_MAP entry is load-bearing: check_permission returns False for unknown actions, so forgetting it fails closed and invisibly." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Policy `unlock_if_permitted()` + Audit

**Files:**
- Modify: `app/services/power/session_lock.py`
- Test: `tests/services/power/test_session_unlock_policy.py`

**Interfaces:**
- Consumes: `get_session_lock_backend()` (Task 2), `check_permission(db, user_id, "unlock_session")` (Task 3), `is_private_or_local_ip()` aus `app/core/network_utils.py`.
- Produces: `async def unlock_if_permitted(*, user, client_host: Optional[str], db) -> Tuple[bool, str]` — die **einzige** Stelle, an der die Gates ausgewertet werden, und die Stelle, die den Audit-Eintrag schreibt.

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/services/power/test_session_unlock_policy.py`:

```python
"""Both gates for unlocking the desktop session, plus the audit trail."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.power_permissions import UserPowerPermission
from app.services.power import session_lock

LAN = "192.168.178.29"
VPN = "10.8.0.3"
PUBLIC = "203.0.113.7"


def _admin():
    return SimpleNamespace(id=1, username="admin", role="admin")


def _user(user_id: int):
    return SimpleNamespace(id=user_id, username="sven", role="user")


@pytest.fixture
def unlock_called():
    """Replaces the backend so no loginctl is ever invoked."""
    backend = MagicMock()
    backend.unlock.return_value = (True, "session 2 unlocked")
    with patch.object(session_lock, "get_session_lock_backend", return_value=backend):
        yield backend


@pytest.fixture(autouse=True)
def _silent_audit():
    with patch.object(session_lock, "get_audit_logger_db") as factory:
        factory.return_value = MagicMock()
        yield factory.return_value


class TestPermissionGate:
    async def test_admin_from_lan_unlocks(self, db_session, unlock_called):
        ok, _detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=LAN, db=db_session
        )

        assert ok is True
        unlock_called.unlock.assert_called_once()

    async def test_delegated_user_with_the_permission_unlocks(
        self, db_session, regular_user, unlock_called
    ):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_unlock_session=True)
        )
        db_session.commit()

        ok, _detail = await session_lock.unlock_if_permitted(
            user=_user(regular_user.id), client_host=LAN, db=db_session
        )

        assert ok is True

    async def test_user_without_the_permission_is_refused(
        self, db_session, regular_user, unlock_called
    ):
        ok, detail = await session_lock.unlock_if_permitted(
            user=_user(regular_user.id), client_host=LAN, db=db_session
        )

        assert ok is False
        assert "permission" in detail
        unlock_called.unlock.assert_not_called()


class TestNetworkGate:
    async def test_vpn_is_allowed(self, db_session, unlock_called):
        ok, _detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=VPN, db=db_session
        )

        assert ok is True

    async def test_public_address_is_refused_even_for_an_admin(
        self, db_session, unlock_called
    ):
        """The web app is reachable from the open internet via duckdns. This
        assertion is the one that fails if the IP gate ever breaks - testing
        only the allowed direction would stay green on a wide-open gate."""
        ok, detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=PUBLIC, db=db_session
        )

        assert ok is False
        assert "network" in detail
        unlock_called.unlock.assert_not_called()

    async def test_missing_client_host_is_refused(self, db_session, unlock_called):
        ok, _detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=None, db=db_session
        )

        assert ok is False
        unlock_called.unlock.assert_not_called()


class TestAuditTrail:
    async def test_successful_unlock_is_audited(
        self, db_session, unlock_called, _silent_audit
    ):
        await session_lock.unlock_if_permitted(
            user=_admin(), client_host=LAN, db=db_session
        )

        _silent_audit.log_event.assert_called_once()
        kwargs = _silent_audit.log_event.call_args.kwargs
        assert kwargs["action"] == "desktop_unlock_session"
        assert kwargs["event_type"] == "POWER"

    async def test_a_refused_unlock_writes_no_audit_noise(
        self, db_session, unlock_called, _silent_audit
    ):
        await session_lock.unlock_if_permitted(
            user=_admin(), client_host=PUBLIC, db=db_session
        )

        _silent_audit.log_event.assert_not_called()

    async def test_delegated_user_also_gets_a_security_event(
        self, db_session, regular_user, unlock_called, _silent_audit
    ):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_unlock_session=True)
        )
        db_session.commit()

        await session_lock.unlock_if_permitted(
            user=_user(regular_user.id), client_host=LAN, db=db_session
        )

        _silent_audit.log_security_event.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/power/test_session_unlock_policy.py -v --no-cov`
Expected: FAIL — `AttributeError: module 'app.services.power.session_lock' has no attribute 'unlock_if_permitted'`

- [ ] **Step 3: Add the policy function**

In `app/services/power/session_lock.py` die Importe ergänzen:

```python
import asyncio

from app.core.network_utils import is_private_or_local_ip
from app.services.audit.logger_db import get_audit_logger_db
from app.services.power_permissions import check_permission
```

und am Dateiende anfügen:

```python
def _may_unlock(user, db) -> bool:
    """Admins pass by role, like every other power permission."""
    if getattr(user, "role", None) == "admin":
        return True
    return check_permission(db, user.id, "unlock_session")


async def unlock_if_permitted(*, user, client_host: Optional[str], db) -> Tuple[bool, str]:
    """Unlock the desktop session if BOTH gates allow it.

    This is the only place the gates are evaluated and the only place the audit
    entry is written - so no caller can unlock without leaving a trace, not
    even a plugin.

    Args:
        user: The authenticated caller (needs .id, .username, .role).
        client_host: The request's client IP, or None.
        db: SQLAlchemy session.

    Returns:
        (unlocked, detail). ``unlocked`` describes the state afterwards; on a
        refused gate loginctl is never called and the real lock state is
        unknown, so it is False with the reason in ``detail``.
    """
    if not _may_unlock(user, db):
        return False, "permission required: power:unlock_session"
    if not is_private_or_local_ip(client_host):
        return False, "not permitted from this network"

    ok, detail = await asyncio.to_thread(get_session_lock_backend().unlock)
    if not ok:
        logger.warning("session unlock failed for %s: %s", user.username, detail)
        return False, detail

    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action="desktop_unlock_session",
        user=user.username,
        resource="desktop",
        success=True,
        details={"message": detail},
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="unlock_session",
            details={"action": "desktop_unlock_session"},
            success=True,
        )
    return True, detail
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/power/test_session_unlock_policy.py -v --no-cov`
Expected: PASS (9 passed)

- [ ] **Step 5: Verify the network gate is discriminating**

Ersetze `is_private_or_local_ip(client_host)` testweise durch `True`, lass die Datei laufen: `test_public_address_is_refused_even_for_an_admin` und `test_missing_client_host_is_refused` **müssen rot werden**. Zurücksetzen. Ergebnis berichten.

- [ ] **Step 6: Commit**

```bash
git add app/services/power/session_lock.py tests/services/power/test_session_unlock_policy.py
git commit -m "feat(power): single policy gate for the session unlock" -m "Permission plus LAN/VPN check plus audit entry in one function, so route and plugin cannot drift apart and no path can unlock without a trace." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Route-Anbindung

**Files:**
- Modify: `app/api/routes/desktop.py`
- Test: `tests/api/test_desktop_unlock.py`

**Interfaces:**
- Consumes: `unlock_if_permitted()` (Task 4).
- Produces: `POST /api/system/sleep/desktop/enable` liefert zusätzlich `session_unlocked: bool` und `unlock_message: str`.

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/api/test_desktop_unlock.py`:

```python
"""The enable route unlocks the session - but never fails because of it."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def desktop_enabled():
    service = MagicMock()
    service.enable = AsyncMock(return_value=(True, "ok"))
    with patch("app.api.routes.desktop.get_desktop_service", return_value=service):
        yield service


class TestEnableUnlocksTheSession:
    def test_response_reports_a_successful_unlock(
        self, client, admin_headers, desktop_enabled
    ):
        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(return_value=(True, "session 2 unlocked")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/enable", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["session_unlocked"] is True

    def test_a_failed_unlock_does_not_fail_the_enable(
        self, client, admin_headers, desktop_enabled
    ):
        """Turning the displays on is the primary action. If it started failing
        because a lock screen would not budge, the feature would be a
        regression rather than a convenience."""
        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(return_value=(False, "not permitted from this network")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/enable", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["session_unlocked"] is False
        assert body["unlock_message"] == "not permitted from this network"

    def test_the_client_ip_is_passed_to_the_gate(
        self, client, admin_headers, desktop_enabled
    ):
        gate = AsyncMock(return_value=(True, "unlocked"))
        with patch("app.api.routes.desktop.unlock_if_permitted", gate):
            client.post("/api/system/sleep/desktop/enable", headers=admin_headers)

        assert gate.await_args.kwargs["client_host"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_desktop_unlock.py -v --no-cov`
Expected: FAIL — `KeyError: 'session_unlocked'` bzw. `AttributeError: … has no attribute 'unlock_if_permitted'`

- [ ] **Step 3: Wire the route**

In `app/api/routes/desktop.py` die Importe ergänzen:

```python
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.power.session_lock import unlock_if_permitted
```

`desktop_enable` bekommt eine DB-Session und den Unlock-Versuch:

```python
@router.post("/enable")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_enable(
    request: Request,
    response: Response,
    current_user=Depends(require_power_toggle_desktop),
    db: Session = Depends(get_db),
) -> dict:
    """Turn the desktop displays back on (DPMS) and unlock the session.

    Admin or a delegated user with the can_toggle_desktop permission. The
    unlock is an ADD-ON: it needs its own permission plus a request from
    LAN/VPN, and failing it never fails the call - the displays are on either
    way.
    """
    ok, message = await get_desktop_service().enable()
```

Der bestehende Audit- und Notification-Block bleibt unverändert. Vor dem `return` einfügen und das `return` ersetzen:

```python
    session_unlocked, unlock_message = await unlock_if_permitted(
        user=current_user,
        client_host=request.client.host if request.client else None,
        db=db,
    )
    return {
        "success": ok,
        "message": message,
        "session_unlocked": session_unlocked,
        "unlock_message": unlock_message,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_desktop_unlock.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 5: Check for regressions in the existing desktop tests**

Run: `python -m pytest tests/ -k desktop -v --no-cov`
Expected: PASS — bestehende Tests der Enable/Disable-Routen bleiben grün (die zwei neuen Felder sind additiv)

- [ ] **Step 6: Commit**

```bash
git add app/api/routes/desktop.py tests/api/test_desktop_unlock.py
git commit -m "feat(desktop): enable route unlocks the session when allowed" -m "The unlock is additive: a refused or failed unlock still returns success=true with the displays on." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Extension-Point + Gaming-Modus

**Files:**
- Modify: `app/plugins/base.py`
- Modify: `app/api/routes/plugins.py`
- Modify: `app/plugins/installed/steam_gaming/__init__.py`
- Test: `tests/plugins/test_steam_gaming_plugin.py` (anhängen)

**Interfaces:**
- Consumes: `unlock_if_permitted()` (Task 4).
- Produces: `run_menu_action(self, action_id, db, *, user=None, client_host=None)`.

- [ ] **Step 1: Write the failing test**

An `tests/plugins/test_steam_gaming_plugin.py` anhängen:

```python
class TestGamingModeUnlocksTheSession:
    """Big Picture on a lock screen helps nobody - the gaming mode runs the
    same gates as the enable route, between displays-on and Big Picture."""

    async def test_unlock_runs_between_displays_and_big_picture(self):
        order: list[str] = []

        desktop_patch, service = _patch_desktop(True, "ok")
        service.enable = AsyncMock(side_effect=lambda: order.append("displays") or (True, "ok"))

        async def _unlock(**_kwargs):
            order.append("unlock")
            return True, "session 2 unlocked"

        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.unlock_if_permitted", _unlock
        ), patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            side_effect=lambda: order.append("bigpicture") or (True, "requested"),
        ):
            result = await SteamGamingPlugin().run_menu_action(
                _ACTION, db=None, user=MagicMock(role="admin"), client_host="192.168.178.29"
            )

        assert result.ok is True
        assert order == ["displays", "unlock", "bigpicture"]

    async def test_a_failed_unlock_does_not_stop_big_picture(self):
        desktop_patch, _service = _patch_desktop(True, "ok")

        async def _unlock(**_kwargs):
            return False, "not permitted from this network"

        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.unlock_if_permitted", _unlock
        ), patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            return_value=(True, "requested"),
        ) as launcher:
            result = await SteamGamingPlugin().run_menu_action(
                _ACTION, db=None, user=MagicMock(role="admin"), client_host="203.0.113.7"
            )

        launcher.assert_called_once()
        assert result.ok is True

    async def test_without_a_user_no_unlock_is_attempted(self):
        """Older callers pass neither user nor client_host - the action must
        still work, just without unlocking."""
        desktop_patch, _service = _patch_desktop(True, "ok")
        gate = AsyncMock(return_value=(True, "unlocked"))

        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.unlock_if_permitted", gate
        ), patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            return_value=(True, "requested"),
        ):
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        gate.assert_not_awaited()
        assert result.ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_plugin.py -k GamingModeUnlocks -v --no-cov`
Expected: FAIL — `TypeError: run_menu_action() got an unexpected keyword argument 'user'`

- [ ] **Step 3: Extend the extension point**

In `app/plugins/base.py` die Signatur von `run_menu_action` ersetzen:

```python
    async def run_menu_action(
        self,
        action_id: str,
        db: "Session",
        *,
        user: Optional[Any] = None,
        client_host: Optional[str] = None,
    ) -> Optional["MenuActionResult"]:
        """Execute a menu action this plugin declared.

        ``user`` and ``client_host`` describe the CALLER, so an action can ask
        the core for a privileged side effect under the core's own rules (see
        services/power/session_lock.unlock_if_permitted). Both are keyword-only
        with defaults: an older implementation keeps working, it just cannot
        request anything caller-dependent.
        """
        return None
```

- [ ] **Step 4: Pass the context through**

In `app/api/routes/plugins.py` den Aufruf ersetzen:

```python
        result = await asyncio.wait_for(
            plugin.run_menu_action(
                action_id,
                db,
                user=current_user,
                client_host=request.client.host if request.client else None,
            ),
            timeout=PLUGIN_MENU_ACTION_TIMEOUT_SECONDS,
        )
```

- [ ] **Step 5: Unlock in the gaming mode**

In `app/plugins/installed/steam_gaming/__init__.py` den Import ergänzen:

```python
from app.services.power.session_lock import unlock_if_permitted
```

und `run_menu_action` anpassen — Signatur und der neue Block zwischen Displays und Big Picture:

```python
    async def run_menu_action(
        self,
        action_id: str,
        db: Session,
        *,
        user=None,
        client_host: Optional[str] = None,
    ) -> Optional[MenuActionResult]:
        if action_id != _MENU_ACTION_ID:
            return None

        # Displays first: opening Big Picture onto dark screens helps nobody.
        # LinuxDesktopBackend.enable() runs kscreen-doctor in a thread, so the
        # core's wait_for stays effective.
        ok, detail = await get_desktop_service().enable()
        if not ok:
            # The user only ever sees the translated key, so without this line
            # the reason kscreen-doctor refused is lost for good.
            logger.warning("gaming mode: turning the displays on failed: %s", detail)
            return MenuActionResult(
                ok=False,
                message_key="menu_displays_failed",
                message_text=f"Displays could not be turned on: {detail}",
            )

        # Then the lock screen - Big Picture behind it would be just as useless
        # as behind a dark monitor. Same gates as the enable route; a refusal
        # is not a failure of the action.
        if user is not None:
            unlocked, unlock_detail = await unlock_if_permitted(
                user=user, client_host=client_host, db=db
            )
            if not unlocked:
                logger.info("gaming mode: session not unlocked: %s", unlock_detail)

        launched, detail = await asyncio.to_thread(open_big_picture)
```

Der Rest der Methode bleibt unverändert.

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_plugin.py -v --no-cov`
Expected: PASS — die drei neuen Tests plus alle bestehenden

- [ ] **Step 7: Check the whole plugin suite**

Run: `python -m pytest tests/plugins/ -v --no-cov`
Expected: PASS — insbesondere `test_plugin_menu_actions.py` (der Dispatch-Aufruf hat sich geändert)

- [ ] **Step 8: Commit**

```bash
git add app/plugins/base.py app/api/routes/plugins.py app/plugins/installed/steam_gaming/__init__.py tests/plugins/test_steam_gaming_plugin.py
git commit -m "feat(plugins): menu actions learn who called them, gaming mode unlocks" -m "run_menu_action gets keyword-only user and client_host so an action can ask the core for a privileged side effect under the core's rules, instead of relying on the implicit contract that the route already checked admin." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Frontend

**Files:**
- Modify: `client/src/api/powerPermissions.ts`
- Modify: `client/src/api/desktop.ts`
- Modify: `client/src/components/user-management/PowerPermissionsSection.tsx`
- Modify: `client/src/components/PowerMenu.tsx`
- Modify: `client/src/i18n/locales/de/admin.json`, `client/src/i18n/locales/en/admin.json`
- Modify: `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json`
- Test: `client/src/__tests__/components/PowerMenu.test.tsx` (anhängen)

**Interfaces:**
- Consumes: die zwei Antwortfelder aus Task 5, das Recht aus Task 3.

- [ ] **Step 1: Write the failing test**

An `client/src/__tests__/components/PowerMenu.test.tsx` anhängen (innerhalb der bestehenden Desktop-Beschreibung, am Dateiende als eigener Block):

```tsx
describe('PowerMenu session unlock hint', () => {
  it('shows an extra hint when the session could not be unlocked', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped',
    });
    (enableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      message: 'ok',
      session_unlocked: false,
      unlock_message: 'not permitted from this network',
    });

    render(<PowerMenu {...baseProps} />);
    const button = await screen.findByText('Enable desktop');
    fireEvent.click(button);

    await waitFor(() => expect(enableDesktop).toHaveBeenCalledTimes(1));
    // The raw English debug string must never reach the user (#406).
    await waitFor(() =>
      expect(
        screen.queryByText(/not permitted from this network/i),
      ).not.toBeInTheDocument(),
    );
  });

  it('shows no hint when the session was unlocked', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped',
    });
    (enableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      message: 'ok',
      session_unlocked: true,
      unlock_message: 'session 2 unlocked',
    });

    render(<PowerMenu {...baseProps} />);
    fireEvent.click(await screen.findByText('Enable desktop'));

    await waitFor(() => expect(enableDesktop).toHaveBeenCalledTimes(1));
  });
});
```

**Hinweis:** Die Datei hat **keinen** Render-Helfer — die bestehenden Tests rufen `render(<PowerMenu {...baseProps} />)` mit dem oben in der Datei definierten `baseProps`-Objekt. Genau dieses Muster verwenden; `render`, `screen`, `fireEvent` und `waitFor` sind dort bereits importiert.

- [ ] **Step 2: Run test to verify it fails**

Run (aus `client/`): `npx vitest run src/__tests__/components/PowerMenu.test.tsx`
Expected: FAIL — TypeScript kennt `session_unlocked` auf `DesktopActionResult` nicht

- [ ] **Step 3: Extend the API types**

In `client/src/api/desktop.ts` das Interface `DesktopActionResult` ersetzen — es hat heute genau zwei Felder, die beiden neuen sind optional, weil ein älteres Backend sie nicht sendet:

```ts
export interface DesktopActionResult {
  success: boolean;
  message: string;
  session_unlocked?: boolean;
  unlock_message?: string;
}
```

In `client/src/api/powerPermissions.ts` in **allen drei** Interfaces nach `can_toggle_desktop` ergänzen:

```ts
  can_unlock_session: boolean;
```

bzw. in `UserPowerPermissionsUpdate`:

```ts
  can_unlock_session?: boolean;
```

- [ ] **Step 4: Add the permission toggle**

In `client/src/components/user-management/PowerPermissionsSection.tsx`:

`FIELD_TO_I18N` erweitern:

```tsx
  can_toggle_desktop: 'toggleDesktop',
  can_unlock_session: 'unlockSession',
```

`PERMISSION_TOGGLES` erweitern (Import `LockOpen` aus `lucide-react` zu den bestehenden Icon-Importen ergänzen):

```tsx
  { key: 'can_toggle_desktop', icon: <MonitorOff className="h-4 w-4" /> },
  { key: 'can_unlock_session', icon: <LockOpen className="h-4 w-4" /> },
```

- [ ] **Step 5: Add the i18n entries**

In `client/src/i18n/locales/de/admin.json` unter `users.systemPermissions.items` nach `toggleDesktop`:

```json
      "unlockSession": {
        "label": "Session entsperren",
        "desc": "Beim Einschalten der Displays die Desktop-Sitzung mit entsperren (nur aus dem Heimnetz oder VPN)"
      }
```

In `client/src/i18n/locales/en/admin.json` an derselben Stelle:

```json
      "unlockSession": {
        "label": "Unlock session",
        "desc": "Also unlock the desktop session when turning the displays on (home network or VPN only)"
      }
```

In `client/src/i18n/locales/de/common.json` unter `powerMenu` nach `desktopEnabled`:

```json
    "desktopStillLocked": "Displays an - die Sitzung ist weiterhin gesperrt",
```

In `client/src/i18n/locales/en/common.json` an derselben Stelle:

```json
    "desktopStillLocked": "Displays on - the session is still locked",
```

- [ ] **Step 6: Show the hint**

In `client/src/components/PowerMenu.tsx` in `handleEnableDesktop` nach dem Erfolgs-Toast ergänzen:

```tsx
      if (result.success) {
        toast.success(t('powerMenu.desktopEnabled', 'Desktop enabled'));
        // unlock_message is an English debug string and stays out of the UI (#406).
        if (result.session_unlocked === false) {
          toast(t('powerMenu.desktopStillLocked', 'Displays on - the session is still locked'));
        }
      } else {
```

- [ ] **Step 7: Run test to verify it passes**

Run (aus `client/`): `npx vitest run src/__tests__/components/PowerMenu.test.tsx`
Expected: PASS

- [ ] **Step 8: Run the frontend gates**

Run (aus `client/`): `npx eslint .`
Expected: keine Fehler

Run (aus `client/`): `npm run build`
Expected: erfolgreich (`tsc -b` über App-, Node- und Test-Projekte)

- [ ] **Step 9: Commit**

```bash
git add client/src
git commit -m "feat(ui): unlock-session permission toggle and a translated lock hint" -m "The backend's unlock_message stays a debug string; the menu shows a translated generic hint instead." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Doku, Gates, Migrations-Handprobe

**Files:**
- Modify: `.claude/rules/security-agent.md`
- Modify: `backend/app/plugins/CLAUDE.md`

- [ ] **Step 1: Document the new permission**

In `.claude/rules/security-agent.md` im Abschnitt „Role Model" nach der `is_privileged`-Zeile ergänzen:

```markdown
- `can_unlock_session` (power permission) entsperrt die grafische Desktop-Session
  beim Einschalten der Displays. Doppelt gegated: Recht **und**
  `is_private_or_local_ip(request.client.host)` — die Web-App ist von außen
  erreichbar, und ein gestohlenes Web-Konto darf keinen physischen Desktop
  öffnen. Durchgesetzt ausschließlich in
  `services/power/session_lock.unlock_if_permitted()`, die auch den
  Audit-Eintrag schreibt.
```

- [ ] **Step 2: Document the extension-point change**

In `backend/app/plugins/CLAUDE.md` bei Punkt 7 (Menü-Contribution) ergänzen:

```markdown
   `run_menu_action()` bekommt zusätzlich `user` und `client_host` (keyword-only,
   Default `None`) — den authentifizierten Aufrufer und dessen IP. Damit kann
   eine Aktion einen privilegierten Seiteneffekt beim Core anfragen, der ihn
   nach **seinen** Regeln prüft (siehe
   `services/power/session_lock.unlock_if_permitted()`), statt sich auf den
   impliziten Vertrag „die Route hat Admin schon geprüft" zu verlassen.
```

- [ ] **Step 3: Run the backend gates**

Run (aus `backend/`): `python -m pytest tests/ -q --no-cov -k "power or desktop or plugin"`
Expected: PASS — tatsächliche Zahlen im Report festhalten

Run (aus `backend/`): `python -m ruff check .`
Expected: `All checks passed!`

**Hinweis:** `tests/auth/test_permissions.py::test_owner_can_delete_own_file` und `::test_admin_can_delete_any_file` sind bekannt flaky im großen Sammellauf (Windows-Isolation) und standalone grün. Falls sie auftauchen: standalone gegenprüfen, nicht reparieren.

- [ ] **Step 4: Migration isolation probe (SQLite)**

**Bash-Tool verwenden** — PowerShell kennt das `VAR=x cmd`-Präfix nicht.

```bash
DATABASE_URL="sqlite:///./migration_check.db" python -c "
from sqlalchemy import create_engine
from alembic.config import Config
from alembic import command
from app.models.base import Base
import app.models  # noqa: F401

engine = create_engine('sqlite:///./migration_check.db')
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
engine.dispose()
import sqlite3
con = sqlite3.connect('migration_check.db')
con.execute('ALTER TABLE user_power_permissions DROP COLUMN can_unlock_session')
con.commit(); con.close()
command.stamp(Config('alembic.ini'), 'b661786568c1')
"
```

Run: `DATABASE_URL="sqlite:///./migration_check.db" python -m alembic upgrade head`
Expected: `Running upgrade b661786568c1 -> <rev>, add can_unlock_session permission`

Run: `DATABASE_URL="sqlite:///./migration_check.db" python -m alembic downgrade -1`
Expected: sauberes `Running downgrade`

Run: `python -c "import os; os.remove('migration_check.db')"`
Expected: kein Output

- [ ] **Step 5: Migration probe against PostgreSQL**

Docker Desktop muss laufen. **Bash-Tool.**

```bash
docker run -d --name balu-pgprobe -e POSTGRES_PASSWORD=probe -e POSTGRES_DB=baluprobe -p 55432:5432 postgres:17
```

Dann dasselbe Schema-Stampen wie in Step 4, aber mit
`DATABASE_URL="postgresql://postgres:probe@127.0.0.1:55432/baluprobe"` und
`ALTER TABLE user_power_permissions DROP COLUMN can_unlock_session` über psql:

```bash
docker exec balu-pgprobe psql -U postgres -d baluprobe -c "ALTER TABLE user_power_permissions DROP COLUMN can_unlock_session;"
```

Danach `upgrade head`, `\d user_power_permissions` prüfen (Spalte `boolean not null default false`), `downgrade -1`, und aufräumen:

```bash
docker rm -f balu-pgprobe
```

- [ ] **Step 6: Commit**

```bash
git add .claude/rules/security-agent.md backend/app/plugins/CLAUDE.md
git commit -m "docs: document the unlock-session permission and the menu-action context" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7: Manueller Abschluss durch Xveyn (nicht dispatchen)**

Zwei Nachweise, die nur am Gerät zu führen sind und deshalb in die PR-Beschreibung gehören:

1. **Sperrbildschirm verschwindet wirklich.** Session sperren, dann in der Web-App „Displays an" — der Monitor muss ohne Passworteingabe nutzbar sein. `LockedHint` allein ist loginds Sicht, nicht die des Bildschirms.
2. **Das Ortsgate greift.** Dieselbe Aktion einmal über `baluhost.duckdns.org` von außerhalb (ohne VPN): Displays gehen an, die Sitzung bleibt gesperrt, und die UI zeigt den übersetzten Hinweis statt des englischen Debug-Strings.

---

## Abnahme

| Spec-Anforderung | Task |
|---|---|
| Messung des Dienst-Kontexts vor jedem Code | 1 |
| `loginctl`-Mechanismus, Session-Ermittlung mit Fallback | 2 |
| `LockedHint`-Polling statt Einzelread | 2 |
| Dev-Backend ohne `loginctl` | 2 |
| Recht `can_unlock_session` + Migration | 3 |
| `_ACTION_FIELD_MAP`-Eintrag (stille Falle) | 3 |
| Beide Gates in genau einer Funktion | 4 |
| Audit-Eintrag nur im Erfolgsfall, geschrieben von der Policy | 4 |
| Öffentliche IP wird abgelehnt (nicht nur private akzeptiert) | 4 |
| Enable bleibt erfolgreich bei fehlgeschlagenem Unlock | 5 |
| Antwortfelder `session_unlocked` / `unlock_message` | 5 |
| Extension-Point mit `user` + `client_host` | 6 |
| Gaming-Modus: Displays → Unlock → Big Picture | 6 |
| `unlock_message` nie in der UI | 7 |
| Checkbox + i18n de/en | 7 |
| Doku + Gates + Migrations-Handproben | 8 |

**Bewusst nicht im Plan** (Nicht-Ziele der Spec): Step-up-Auth vor dem Entsperren, Abschalten des KDE-Locks, ein „Session sperren"-Knopf, eine eigene Notification.
