# Steam-Start über `systemd-run --user` (#640) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der `steam_gaming`-Launcher startet `steam://`-URLs über `systemd-run --user` statt als Kindprozess des Backends, sodass ein kalt gestartetes Steam weder Backend-Secrets erbt noch in der Backend-cgroup hängt.

**Architecture:** Nur `launcher._dispatch` ändert sich: `subprocess.run(["systemd-run", "--user", "--collect", "--quiet", "steam", url])` mit einer Umgebungs-Allowlist und 10-s-Timeout. Die transiente Unit läuft im User-Manager von `sven` und bekommt dessen (von KDE importierte) Umgebung. `services/power/session_env.py` bleibt funktional unverändert.

**Tech Stack:** Python 3.11+, `subprocess`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-steam-game-launch-design.md` — Abschnitt „PR A".

## Global Constraints

- Branch: von aktuellem `main` abzweigen (`git fetch origin ; git checkout main ; git merge --ff-only origin/main ; git checkout -b fix/steam-launch-systemd-run`). **Nicht** auf `feat/steam-game-launch` bauen. Diese Plan-Datei und die Spec liegen nur auf `feat/steam-game-launch` — vor dem Abzweigen lesen oder mit `git show feat/steam-game-launch:docs/superpowers/plans/2026-09-14-steam-launch-systemd-run.md` bzw. `git show feat/steam-game-launch:docs/superpowers/specs/2026-09-14-steam-game-launch-design.md` aufrufen; nicht in den Fix-Branch committen.
- argv exakt: `["systemd-run", "--user", "--collect", "--quiet", "steam", url]` — Listen-Argumente, nie `shell=True`.
- Umgebungs-Allowlist exakt: `HOME`, `USER`, `LOGNAME`, `PATH`, `LANG`, `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`; fehlt `XDG_RUNTIME_DIR`, wird `/run/user/<os.getuid()>` gesetzt.
- Timeout: `_STEAM_RUN_TIMEOUT_SECONDS = 10`.
- Dev-Modus (`settings.is_dev_mode`): kein Prozess, `(True, "<what> requested (dev)")`.
- Rückgabe-`detail` enthält nie `stderr` — das geht nur ins Log (gekürzt auf 300 Zeichen).
- Windows-Dev-Rechner: `os.getuid` existiert nicht; Tests setzen `XDG_RUNTIME_DIR` bzw. monkeypatchen `os.getuid` mit `raising=False`.
- Nur die relevanten Tests lokal laufen lassen; die volle Backend-Suite gehört der CI (hängt auf Windows).
- Befehle für PowerShell 5.1: nie `&&`, Verkettung mit `;`.
- Commits enden mit:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` und
  `Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC`

---

### Task 1: Launcher über `systemd-run --user`

**Files:**
- Modify: `backend/app/plugins/installed/steam_gaming/launcher.py` (ganze Datei)
- Modify: `backend/tests/plugins/test_steam_gaming_launcher.py` (ganze Datei)
- Modify: `backend/app/services/power/session_env.py:1-10` (Docstring)
- Modify: `backend/app/plugins/installed/steam_gaming/CLAUDE.md` (Layout-Zeile `launcher.py`)

**Interfaces:**
- Consumes: `app.core.config.settings.is_dev_mode`
- Produces (unverändert öffentlich): `BIG_PICTURE_URL`, `CLOSE_BIG_PICTURE_URL`, `open_big_picture() -> tuple[bool, str]`, `close_big_picture() -> tuple[bool, str]`; neu intern `_dispatch(url: str, what: str) -> tuple[bool, str]`, `_user_manager_env() -> dict[str, str]`, `_STEAM_RUN_TIMEOUT_SECONDS`, `_ENV_ALLOWLIST`. Plan B (`2026-09-14-steam-game-launch.md`) ergänzt später `launch_game(app_id)` über `_dispatch`.

- [ ] **Step 1: Tests ersetzen (fehlschlagend)**

`backend/tests/plugins/test_steam_gaming_launcher.py` komplett ersetzen:

```python
"""steam:// dispatch for the steam_gaming plugin - through the user's systemd.

Measured on BaluNode (2026-09-14, M5 in the design doc): with an EMPTY caller
environment, ``systemd-run --user --collect steam steam://rungameid/400``
cold-starts Steam and the game appears. The unit runs in sven's user manager,
so Steam inherits neither the backend's secrets nor its cgroup.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.plugins.installed.steam_gaming import launcher
from app.plugins.installed.steam_gaming.launcher import (
    BIG_PICTURE_URL,
    CLOSE_BIG_PICTURE_URL,
    close_big_picture,
    open_big_picture,
)

_SETTINGS = "app.plugins.installed.steam_gaming.launcher.settings"


def _completed(returncode: int = 0, stderr: bytes = b"") -> MagicMock:
    return MagicMock(returncode=returncode, stderr=stderr)


@pytest.fixture
def prod(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    with patch(_SETTINGS) as cfg:
        cfg.is_dev_mode = False
        yield cfg


class TestArgv:
    def test_open_goes_through_the_user_manager(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            ok, _detail = open_big_picture()

        assert ok is True
        assert run.call_args.args[0] == [
            "systemd-run", "--user", "--collect", "--quiet", "steam", BIG_PICTURE_URL,
        ]

    def test_close_goes_through_the_user_manager(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            ok, _detail = close_big_picture()

        assert ok is True
        assert run.call_args.args[0][-1] == CLOSE_BIG_PICTURE_URL
        assert run.call_args.args[0][:5] == ["systemd-run", "--user", "--collect", "--quiet", "steam"]

    def test_close_url_is_not_the_open_url(self):
        """A copy-paste slip here would make the exit action re-open Big
        Picture, and nothing downstream could tell the difference."""
        assert CLOSE_BIG_PICTURE_URL != BIG_PICTURE_URL

    def test_never_a_shell(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert "shell" not in run.call_args.kwargs

    def test_is_bounded_by_a_timeout(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert run.call_args.kwargs["timeout"] == launcher._STEAM_RUN_TIMEOUT_SECONDS == 10
        assert run.call_args.kwargs["stdin"] == subprocess.DEVNULL


class TestEnvironment:
    def test_backend_secrets_never_reach_the_call(self, prod, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "must-not-leak")
        monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        env = run.call_args.kwargs["env"]
        assert "SECRET_KEY" not in env
        assert "DATABASE_URL" not in env
        assert set(env) <= set(launcher._ENV_ALLOWLIST)

    def test_keeps_the_runtime_dir_it_was_given(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert run.call_args.kwargs["env"]["XDG_RUNTIME_DIR"] == "/run/user/1000"

    def test_derives_the_runtime_dir_from_the_uid_when_missing(self, prod, monkeypatch):
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setattr(launcher.os, "getuid", lambda: 1234, raising=False)
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert run.call_args.kwargs["env"]["XDG_RUNTIME_DIR"] == "/run/user/1234"


class TestFailures:
    def test_missing_systemd_run_is_reported_not_raised(self, prod):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, detail = open_big_picture()

        assert ok is False
        assert "steam" in detail.lower()

    def test_a_timeout_is_reported_not_raised(self, prod):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("systemd-run", 10)):
            ok, _detail = open_big_picture()

        assert ok is False

    def test_an_os_error_is_reported_not_raised(self, prod):
        with patch("subprocess.run", side_effect=OSError("fork failed")):
            ok, _detail = open_big_picture()

        assert ok is False

    def test_a_non_zero_exit_is_a_failure_without_leaking_stderr(self, prod):
        """No user manager (nobody logged in) makes systemd-run exit non-zero."""
        failed = _completed(1, b"Failed to connect to bus: /run/user/1000/secret-path")
        with patch("subprocess.run", return_value=failed):
            ok, detail = close_big_picture()

        assert ok is False
        assert "secret-path" not in detail


class TestDevMode:
    def test_dev_mode_does_not_spawn_anything(self):
        with patch(_SETTINGS) as cfg, patch("subprocess.run") as run:
            cfg.is_dev_mode = True
            ok_open, _ = open_big_picture()
            ok_close, _ = close_big_picture()

        assert ok_open is True and ok_close is True
        run.assert_not_called()
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_launcher.py -v --no-cov`
Expected: FAIL — u. a. `AttributeError: ... has no attribute '_STEAM_RUN_TIMEOUT_SECONDS'` und `run.call_args` ist `None` (der Launcher ruft noch `Popen`).

- [ ] **Step 3: Launcher implementieren**

`backend/app/plugins/installed/steam_gaming/launcher.py` komplett ersetzen:

```python
"""Hand steam:// URLs to Steam in the user's desktop session.

On the production box Steam runs permanently (app-steam@autostart.service), so
most calls just forward a URL to the running client, which then acts on it.

Every call goes through ``systemd-run --user`` rather than spawning ``steam``
from the backend. If Steam is NOT running, the invoked process becomes the
Steam client itself - and as a child of the backend it would

- inherit the backend environment, including the secrets systemd loads from
  ``.env.production``, and pass them on to every game it starts;
- live in the ``baluhost-backend.service`` cgroup, so every deploy restart
  would kill Steam together with the running game;
- see the unit's ``PrivateTmp``.

The transient unit instead runs in sven's user manager and gets that manager's
environment (DISPLAY is imported by KDE). Measured on BaluNode 2026-09-14 with
an empty caller environment: Steam cold-starts and the game appears.

``systemd-run`` returns as soon as the unit exists, so its exit code is
observable (e.g. no user manager because nobody is logged in). Whether Big
Picture or the game actually shows up stays unobservable from here.

The CLOSE direction still needs its caller to check that a Steam client is
running (see detection.steam_is_running): the URL would otherwise START Steam.
"""
from __future__ import annotations

import logging
import os
import subprocess

from app.core.config import settings

logger = logging.getLogger(__name__)

BIG_PICTURE_URL = "steam://open/bigpicture"
CLOSE_BIG_PICTURE_URL = "steam://close/bigpicture"

_STEAM_RUN_TIMEOUT_SECONDS = 10
_STDERR_LOG_LIMIT = 300

# What systemd-run itself needs to find the user manager - nothing more. The
# unit does not inherit this anyway (it gets the manager's environment), but
# there is no reason to hand even a short-lived helper the backend's secrets.
_ENV_ALLOWLIST = (
    "HOME",
    "USER",
    "LOGNAME",
    "PATH",
    "LANG",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
)


def _user_manager_env() -> dict[str, str]:
    """The allowlisted part of our environment, plus the runtime dir."""
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    return env


def _dispatch(url: str, what: str) -> tuple[bool, str]:
    """Hand *url* to Steam via the user manager. Blocking - call via asyncio.to_thread."""
    if settings.is_dev_mode:
        # No desktop session on a Windows dev box.
        return True, f"{what} requested (dev)"

    argv = ["systemd-run", "--user", "--collect", "--quiet", "steam", url]
    try:
        result = subprocess.run(  # fixed argv, no shell, no user input
            argv,
            env=_user_manager_env(),
            timeout=_STEAM_RUN_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return False, "systemd-run not found - cannot start steam"
    except subprocess.TimeoutExpired:
        logger.warning("systemd-run for %s timed out after %ss", url, _STEAM_RUN_TIMEOUT_SECONDS)
        return False, "steam could not be started"
    except OSError as exc:
        logger.warning("failed to dispatch %s: %s", url, exc)
        return False, "steam could not be started"

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", "replace").strip()
        logger.warning(
            "systemd-run for %s exited %s: %s", url, result.returncode, stderr[:_STDERR_LOG_LIMIT]
        )
        return False, "steam could not be started"

    return True, f"{what} requested"


def open_big_picture() -> tuple[bool, str]:
    """Ask Steam to show Big Picture. Blocking - call via asyncio.to_thread.

    Returns:
        (ok, detail). ok=True means the unit was started, not that Big Picture
        is on screen - that stays unobservable from here.
    """
    return _dispatch(BIG_PICTURE_URL, "big picture")


def close_big_picture() -> tuple[bool, str]:
    """Ask Steam to leave Big Picture. Blocking - call via asyncio.to_thread.

    Measured on BaluNode (2026-08-01): the running client drops back to the
    windowed UI and keeps running.

    Returns:
        (ok, detail). ok=True means the unit was started. Whether Big Picture
        is actually gone stays unobservable - the mode is not detectable from
        the outside at all (see the design doc from 2026-07-24).
    """
    return _dispatch(CLOSE_BIG_PICTURE_URL, "big picture close")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_launcher.py tests/plugins/test_steam_gaming_plugin.py -v --no-cov`
Expected: PASS. `test_steam_gaming_plugin.py` patcht `open_big_picture`/`close_big_picture` als Ganzes und bleibt unberührt grün.

- [ ] **Step 5: `session_env.py`-Docstring korrigieren**

In `backend/app/services/power/session_env.py` den Modul-Docstring (Zeilen 1-9) ersetzen durch:

```python
"""Environment for reaching the logged-in user's Wayland session.

The backend runs as the session user (uid match) but outside the graphical
session, so XDG_RUNTIME_DIR and WAYLAND_DISPLAY have to be supplied for
commands like kscreen-doctor or pactl to talk to it.

Callers: the desktop (DPMS) backend, desktop_windows (show desktop), the
audio_control plugin (pactl) and the display_output plugin (kscreen-doctor).
The steam_gaming launcher deliberately does NOT use it: it starts Steam through
``systemd-run --user`` so Steam gets the user manager's environment instead of
a copy of the backend's (see steam_gaming/launcher.py).
"""
```

Die Funktion bleibt unverändert.

- [ ] **Step 6: Plugin-Doku anpassen**

In `backend/app/plugins/installed/steam_gaming/CLAUDE.md` die Layout-Zeile

```
| `launcher.py` | Detached `steam steam://open|close/bigpicture` dispatch |
```

ersetzen durch:

```
| `launcher.py` | `steam://` dispatch through `systemd-run --user` — Steam runs in sven's user manager, never as a backend child (no inherited secrets, survives backend restarts; #640) |
```

- [ ] **Step 7: Lint und verwandte Tests**

Run: `cd backend ; python -m ruff check app/plugins/installed/steam_gaming app/services/power/session_env.py tests/plugins/test_steam_gaming_launcher.py ; python -m pytest tests/plugins/ tests/test_session_env.py -q --no-cov`
Expected: `All checks passed!`, alle Tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/plugins/installed/steam_gaming/launcher.py backend/tests/plugins/test_steam_gaming_launcher.py backend/app/services/power/session_env.py backend/app/plugins/installed/steam_gaming/CLAUDE.md
git commit -m "fix(steam-gaming): Steam über systemd-run --user starten (#640)" -m "Ein vom Backend kalt gestartetes Steam erbte die Backend-Umgebung samt Secrets, hing in der Backend-cgroup und scheiterte ohne X11. Die transiente Unit läuft im User-Manager und bekommt dessen Umgebung." -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC"
```

---

### Task 2: PR und Verifikation an der Box

**Files:** keine Codeänderung.

- [ ] **Step 1: PR öffnen**

PR-Body mit dem Write-Tool nach `<scratchpad>/pr-640.md` schreiben (Here-Strings brechen in beiden Shell-Tools), Inhalt: Problem (vier Punkte aus der Spec, Abschnitt PR A), Lösung, Messung M5, Testplan, `Closes #640`, Abschlusszeile `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Run: `git push -u origin fix/steam-launch-systemd-run ; gh pr create --base main --title "fix(steam-gaming): Steam über systemd-run --user starten (#640)" --body-file <scratchpad>/pr-640.md`
Expected: PR-URL.

- [ ] **Step 2: Nach Merge und Deploy — Verifikation mit beobachteter Wirkung (durch Sven an BaluNode)**

1. `steam -shutdown` ; `pgrep -c -x steam` → `0`.
2. Im Web-UI Power-Menü „Gaming Mode" klicken → Steam startet, Big Picture erscheint **auf dem Bildschirm**.
3. `sudo systemctl restart baluhost-backend` → `pgrep -c -x steam` bleibt > 0, Big Picture bleibt sichtbar.
4. `tr '\0' '\n' < /proc/$(pgrep -x steam | head -1)/environ` → **kein** `SECRET_KEY`, `DATABASE_URL`, `TOKEN_SECRET`.

Erst wenn 1–4 gelten, beginnt Plan B (`docs/superpowers/plans/2026-09-14-steam-game-launch.md`).
