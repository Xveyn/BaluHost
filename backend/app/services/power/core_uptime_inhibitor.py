"""
Logind sleep inhibitor for Core Operating Hours.

While inside an active core-uptime window, BaluHost holds a `systemd-inhibit`
block lock on `sleep` so that ANY suspend attempt — kernel, logind idle,
desktop session daemons (mate-screensaver, gnome-power-manager, KDE), or a
direct `systemctl suspend` invocation — is refused by logind.

Implementation: spawns `/usr/bin/systemd-inhibit --what=sleep --mode=block
--who=BaluHost --why=<reason> sleep infinity` as a long-lived subprocess. The
inhibitor is released as soon as the subprocess exits, so we just kill it on
window end.

Notes:
- `--mode=block` requires the polkit action
  `org.freedesktop.login1.inhibit-block-sleep`. Default Debian 13 polkit
  policy allows this for any local active session and (via implicit-active)
  for system services that present a valid PID — i.e. the BaluHost systemd
  unit. If polkit denies, acquire() logs a warning and returns False; window
  protection then degrades to BaluHost's own per-loop guards (which catch
  BaluHost-initiated suspends but not third-party desktop daemons).
- Dev mode / Windows / missing binary → no-op (returns False, logs once).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEMD_INHIBIT = "systemd-inhibit"


class CoreUptimeInhibitor:
    """Holds a logind block-sleep inhibitor while a core-uptime window is active."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._binary_missing_logged = False

    def is_held(self) -> bool:
        """True iff the inhibitor subprocess is currently alive."""
        return self._proc is not None and self._proc.poll() is None

    def acquire(self, reason: str) -> bool:
        """Acquire the block-sleep inhibitor. Idempotent — no-op if already held.

        Returns True on success (or already held), False if acquisition failed
        (binary missing, polkit denied, etc.). Failures are logged but do not
        raise so the caller can degrade gracefully.
        """
        if self.is_held():
            return True

        # Drop a dead subprocess handle so we re-spawn cleanly.
        if self._proc is not None and self._proc.poll() is not None:
            logger.info(
                "Core uptime inhibitor subprocess exited unexpectedly (rc=%s) — re-acquiring",
                self._proc.returncode,
            )
            self._proc = None

        binary = shutil.which(_SYSTEMD_INHIBIT)
        if binary is None:
            if not self._binary_missing_logged:
                logger.warning(
                    "%s not found — core uptime inhibitor disabled. "
                    "Third-party suspend (desktop daemons, manual systemctl) "
                    "will NOT be blocked during core uptime windows.",
                    _SYSTEMD_INHIBIT,
                )
                self._binary_missing_logged = True
            return False

        try:
            self._proc = subprocess.Popen(
                [
                    binary,
                    "--what=sleep",
                    "--mode=block",
                    "--who=BaluHost",
                    f"--why={reason}",
                    "sleep", "infinity",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            logger.warning("Failed to spawn %s: %s", _SYSTEMD_INHIBIT, exc)
            return False

        # Brief settle window — if polkit denies (e.g. missing rules.d entry
        # for a system service without an active session), systemd-inhibit
        # exits immediately. Detect that here so the caller knows acquisition
        # actually failed instead of silently looping every loop tick.
        time.sleep(0.2)
        if self._proc.poll() is not None:
            stderr_output = ""
            if self._proc.stderr is not None:
                try:
                    stderr_output = self._proc.stderr.read().decode("utf-8", errors="replace").strip()
                except Exception:
                    pass
            logger.warning(
                "%s exited immediately (rc=%s) — likely polkit denial. "
                "Install /etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules. stderr=%r",
                _SYSTEMD_INHIBIT, self._proc.returncode, stderr_output,
            )
            self._proc = None
            return False

        logger.info(
            "Core uptime sleep inhibitor acquired (pid=%s, reason=%s)",
            self._proc.pid, reason,
        )
        return True

    def release(self) -> None:
        """Release the inhibitor by terminating the subprocess. Idempotent."""
        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Core uptime inhibitor pid=%s did not terminate in 3s — killing",
                        self._proc.pid,
                    )
                    self._proc.kill()
                    self._proc.wait(timeout=1.0)
            except OSError as exc:
                logger.warning("Error releasing core uptime inhibitor: %s", exc)
        logger.info("Core uptime sleep inhibitor released")
        self._proc = None
