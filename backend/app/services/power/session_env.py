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
