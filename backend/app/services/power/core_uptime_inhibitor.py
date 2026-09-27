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
- The `--why` text is fixed per subprocess. `update_reason()` swaps it
  make-before-break (#604): the new lock is taken and confirmed alive before
  the old one is dropped, so there is no instant without a block lock. For
  those few milliseconds `systemd-inhibit --list` shows two BaluHost lines.
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
        self._reason: Optional[str] = None
        self._binary_missing_logged = False

    def is_held(self) -> bool:
        """True iff the inhibitor subprocess is currently alive."""
        return self._proc is not None and self._proc.poll() is None

    @property
    def reason(self) -> Optional[str]:
        """The `--why` text of the lock currently held, or None."""
        return self._reason if self.is_held() else None

    def acquire(self, reason: str) -> bool:
        """Acquire the block-sleep inhibitor. Idempotent — no-op if already held.

        Returns True on success (or already held), False if acquisition failed
        (binary missing, polkit denied, etc.). Failures are logged but do not
        raise so the caller can degrade gracefully. Changing the text of a
        held lock is `update_reason()`'s job, not this method's.
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
            self._reason = None

        proc = self._spawn(reason)
        if proc is None:
            return False

        self._proc = proc
        self._reason = reason
        logger.info(
            "Core uptime sleep inhibitor acquired (pid=%s, reason=%s)",
            proc.pid, reason,
        )
        return True

    def update_reason(self, reason: str) -> bool:
        """Re-label the held lock so `systemd-inhibit --list` tells the truth.

        Make-before-break: the replacement lock is spawned and confirmed alive
        BEFORE the old subprocess is terminated. Swapping the other way round
        would leave a short window without any block lock, and a third-party
        suspend arriving in it would go through (#604).

        Returns True if the held lock now carries ``reason`` (including when it
        already did), False if nothing is held or the replacement could not be
        taken — in that case the old lock stays in place with its old text.
        """
        if not self.is_held():
            return False
        if reason == self._reason:
            return True

        new_proc = self._spawn(reason)
        if new_proc is None:
            logger.warning(
                "Could not re-label core uptime inhibitor to %r — keeping the "
                "held lock with its old reason %r",
                reason, self._reason,
            )
            return False

        old_proc, old_reason = self._proc, self._reason
        self._proc = new_proc
        self._reason = reason
        self._terminate(old_proc)
        logger.info(
            "Core uptime sleep inhibitor re-labelled (pid=%s, reason=%s, was %s)",
            new_proc.pid, reason, old_reason,
        )
        return True

    def release(self) -> None:
        """Release the inhibitor by terminating the subprocess. Idempotent."""
        if self._proc is None:
            return
        self._terminate(self._proc)
        logger.info("Core uptime sleep inhibitor released")
        self._proc = None
        self._reason = None

    def _spawn(self, reason: str) -> Optional[subprocess.Popen]:
        """Start a `systemd-inhibit` holder and confirm it survived startup.

        Returns the live subprocess, or None (binary missing, spawn error,
        polkit denial). Never touches ``self._proc`` — the callers decide what
        replaces what, which is what makes the make-before-break swap possible.
        """
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
            return None

        try:
            proc = subprocess.Popen(
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
            return None

        # Brief settle window — if polkit denies (e.g. missing rules.d entry
        # for a system service without an active session), systemd-inhibit
        # exits immediately. Detect that here so the caller knows acquisition
        # actually failed instead of silently looping every loop tick.
        time.sleep(0.2)
        if proc.poll() is not None:
            stderr_output = ""
            if proc.stderr is not None:
                try:
                    stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
                except Exception:
                    pass
            logger.warning(
                "%s exited immediately (rc=%s) — likely polkit denial. "
                "Install /etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules. stderr=%r",
                _SYSTEMD_INHIBIT, proc.returncode, stderr_output,
            )
            return None
        return proc

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        """Stop a holder subprocess; escalate to kill after 3s."""
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Core uptime inhibitor pid=%s did not terminate in 3s — killing",
                    proc.pid,
                )
                proc.kill()
                proc.wait(timeout=1.0)
        except OSError as exc:
            logger.warning("Error releasing core uptime inhibitor: %s", exc)
