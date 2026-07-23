"""Detect a running Steam game by scanning /proc for Steam's launch wrapper.

Steam launches every title — native or Proton — through
``reaper SteamLaunch AppId=<n> -- …``, so the AppID is right there in the
command line. Alternatives were measured and rejected: ``registry.vdf``'s
``RunningAppID`` is no longer maintained by Steam (always 0, upstream bug
ValveSoftware/steam-for-linux#9672), and Steam creates no per-game systemd
scope. See the design doc for the measurements.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator, Optional

DEFAULT_PROC_ROOT = Path("/proc")

_APPID_RE = re.compile(r"SteamLaunch\s+AppId=(\d+)")


def _iter_cmdlines(proc_root: Path) -> Iterator[tuple[int, str]]:
    """Yield ``(pid, cmdline)`` for every readable process directory."""
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return  # no /proc (Windows dev box) or not readable
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            raw = (proc_root / entry / "cmdline").read_bytes()
        except OSError:
            continue  # process vanished between listdir() and read()
        yield int(entry), raw.replace(b"\x00", b" ").decode("utf-8", "replace")


def detect_running_app_id(proc_root: Path = DEFAULT_PROC_ROOT) -> Optional[str]:
    """AppID of the running Steam game, or None.

    The design assumes at most one game at a time. Should two different
    AppIDs ever be present, the lowest PID wins — not because multiple games
    are supported, but so the answer cannot flip between polls based on
    directory order.
    """
    best_pid: Optional[int] = None
    best_app_id: Optional[str] = None
    for pid, cmdline in _iter_cmdlines(proc_root):
        match = _APPID_RE.search(cmdline)
        if match is None:
            continue
        if best_pid is None or pid < best_pid:
            best_pid, best_app_id = pid, match.group(1)
    return best_app_id
