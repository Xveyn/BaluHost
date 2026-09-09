"""Respect logind block inhibitors held by other programs (issue #602).

BaluHost suspends with `sudo rtcwake -m mem` (`sleep_backend_linux.py`), which
writes straight to the kernel and never passes logind. Inhibitors other
programs hold are therefore NOT enforced against us — logind never sees the
suspend to refuse it. Proven on 2026-09-08: `steam-bpm-inhibit` held a
`block` on `sleep:idle` for the whole DiRT Rally session and BaluHost
suspended anyway, mid-game.

Since the OS cannot stop us, we ask ourselves. This module reads the inhibitor
list and the sleep loops treat a foreign block as a suspend suppressor, the
same way they treat presence or gaming.

Read over D-Bus via `busctl --json=short`, deliberately NOT by parsing
`systemd-inhibit --list`: that output is localised (a German box prints
"Bildschirmsperre" and German reasons) and truncated to terminal width.

Only `block` counts. `delay` merely postpones a suspend by a few seconds so a
daemon can prepare — treating it as a refusal would mean NetworkManager and
UPower keep the box awake forever.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_BUSCTL = "busctl"
_TIMEOUT_SECONDS = 5.0
# Long enough that a 5s status poll does not spawn a subprocess per request,
# short enough that a game starting is noticed within one loop tick.
_CACHE_TTL_SECONDS = 4.0

# Our own inhibitors, by the --who we pass in core_uptime_inhibitor.py and
# core_uptime_rtc_guard.py. Refusing to suspend because of our own lock would
# deadlock every automatic suspend.
_OWN_WHO = "BaluHost"

_cache: Optional[tuple[float, list["Inhibitor"]]] = None
_binary_missing_logged = False


@dataclass(frozen=True)
class Inhibitor:
    """One entry from org.freedesktop.login1.Manager.ListInhibitors."""

    what: str
    who: str
    why: str
    mode: str
    uid: int
    pid: int

    def covers(self, kind: str) -> bool:
        """Whether this inhibitor applies to *kind* (e.g. "sleep", "idle").

        `what` is a colon-separated list, so this compares whole segments:
        PowerDevil's "handle-power-key:handle-suspend-key" must not read as a
        sleep inhibitor just because "suspend" appears inside a segment.
        """
        return kind in self.what.split(":")


def reset_cache() -> None:
    """Drop the cached reading (tests, and after a state change)."""
    global _cache
    _cache = None


def parse_inhibitors(payload: str) -> list[Inhibitor]:
    """Parse `busctl --json=short` output. Returns [] on anything unexpected.

    Failing to an empty list means "nothing is holding us back", i.e. suspend
    stays allowed — the same fail-toward-energy-saving direction the presence
    and gaming checks use.
    """
    try:
        parsed = json.loads(payload)
        data = parsed["data"]
        rows = data[0] if data and isinstance(data[0], list) else []
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        logger.debug("Could not parse inhibitor list: %s", exc)
        return []

    out: list[Inhibitor] = []
    for row in rows:
        # A short or malformed row is skipped rather than discarding the whole
        # list — one odd entry must not blind us to a real inhibitor.
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            logger.debug("Skipping malformed inhibitor row: %r", row)
            continue
        try:
            out.append(
                Inhibitor(
                    what=str(row[0]),
                    who=str(row[1]),
                    why=str(row[2]),
                    mode=str(row[3]),
                    uid=int(row[4]),
                    pid=int(row[5]),
                )
            )
        except (TypeError, ValueError) as exc:
            logger.debug("Skipping unreadable inhibitor row %r: %s", row, exc)
    return out


def _run_busctl() -> str:
    """Ask logind for the inhibitor list. Raises on failure."""
    global _binary_missing_logged
    binary = shutil.which(_BUSCTL)
    if binary is None:
        if not _binary_missing_logged:
            logger.warning(
                "%s not found — third-party sleep inhibitors cannot be read and "
                "will NOT prevent automatic suspend.",
                _BUSCTL,
            )
            _binary_missing_logged = True
        raise FileNotFoundError(_BUSCTL)
    result = subprocess.run(
        [
            binary, "--json=short", "call",
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            "ListInhibitors",
        ],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=True,
    )
    return result.stdout


def list_foreign_blocks(
    runner: Optional[Callable[[], str]] = None,
    now: Callable[[], float] = time.monotonic,
) -> list[Inhibitor]:
    """Foreign `block`-mode inhibitors, cached for a few seconds."""
    global _cache
    timestamp = now()
    if _cache is not None and timestamp - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]

    try:
        payload = (runner or _run_busctl)()
    except Exception as exc:
        logger.debug("Could not read inhibitor list (allowing suspend): %s", exc)
        _cache = (timestamp, [])
        return []

    rows = [
        i for i in parse_inhibitors(payload)
        if i.mode == "block" and i.who != _OWN_WHO
    ]
    _cache = (timestamp, rows)
    return rows


def first_blocking(
    kind: str,
    runner: Optional[Callable[[], str]] = None,
    now: Callable[[], float] = time.monotonic,
) -> Optional[Inhibitor]:
    """The first foreign block inhibitor covering *kind*, or None.

    Returning the inhibitor rather than a bool so the caller can say WHO is
    keeping the box awake — "the box will not sleep" without a name is the
    kind of status that reads as a hang.
    """
    for inhibitor in list_foreign_blocks(runner=runner, now=now):
        if inhibitor.covers(kind):
            return inhibitor
    return None
