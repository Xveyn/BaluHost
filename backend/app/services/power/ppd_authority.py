"""Stand power-profiles-daemon down so BaluHost is the sole CPU authority.

All subprocess calls use explicit argument lists (no shell=True). The
matching scoped sudoers rules are provisioned in deploy/install/templates/.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Optional

from app.services.power import config_store

logger = logging.getLogger(__name__)

UNIT = "power-profiles-daemon"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=10)


def _systemctl_state(verb: str) -> bool:
    try:
        res = _run(["systemctl", verb, UNIT])
        out = (res.stdout or b"").decode(errors="ignore").strip()
        return out.startswith("active") or out.startswith("enabled")
    except Exception:
        return False


async def acquire() -> bool:
    """Stop and mask power-profiles-daemon so BaluHost is the sole CPU authority.

    Idempotent: success is judged by the END STATE (is the unit masked?), not by
    each command's return code. ``systemctl stop`` on an already-masked unit
    exits non-zero ("Unit is masked"), so checking per-command rc made a second
    activation fail spuriously. Returns True iff PPD is masked afterwards.
    """
    def _do() -> bool:
        # Only record the prior state the FIRST time (before we change anything).
        # On a re-acquire the unit is already masked — don't clobber the real
        # pre-feature state with the masked one.
        if not _is_masked():
            config_store.save_authority_config({
                "ppd_prev_active": _systemctl_state("is-active"),
                "ppd_prev_enabled": _systemctl_state("is-enabled"),
            })
        for verb in ("stop", "mask"):
            res = _run(["sudo", "-n", "systemctl", verb, UNIT])
            if res.returncode != 0:
                # Non-fatal: stop on a masked/inactive unit is expected to be non-zero.
                logger.warning(
                    "PPD %s returned rc=%s: %s",
                    verb,
                    res.returncode,
                    (res.stderr or b"").decode(errors="ignore").strip(),
                )
        masked = _is_masked()
        if not masked:
            logger.error("PPD did not end up masked after acquire (sudoers missing?)")
        return masked
    return await asyncio.get_running_loop().run_in_executor(None, _do)


async def release() -> bool:
    """Unmask power-profiles-daemon and optionally restart it if it was active."""
    def _do() -> bool:
        cfg = config_store.load_authority_config()
        ok = True
        res = _run(["sudo", "-n", "systemctl", "unmask", UNIT])
        if res.returncode != 0:
            ok = False
            logger.warning("PPD unmask failed (rc=%s): %s", res.returncode,
                           (res.stderr or b"").decode(errors="ignore").strip())
        if cfg.get("ppd_prev_active"):
            res = _run(["sudo", "-n", "systemctl", "start", UNIT])
            if res.returncode != 0:
                ok = False
                logger.warning("PPD start failed (rc=%s): %s", res.returncode,
                               (res.stderr or b"").decode(errors="ignore").strip())
        return ok
    return await asyncio.get_running_loop().run_in_executor(None, _do)


def status() -> dict:
    """Return current PPD daemon state."""
    return {
        "ppd_active": _systemctl_state("is-active"),
        "ppd_masked": _is_masked(),
    }


def _is_masked() -> bool:
    try:
        res = _run(["systemctl", "is-enabled", UNIT])
        return (res.stdout or b"").decode(errors="ignore").strip() == "masked"
    except Exception:
        return False
