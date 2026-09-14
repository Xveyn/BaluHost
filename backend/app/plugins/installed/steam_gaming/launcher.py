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
