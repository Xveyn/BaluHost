"""
RTC wake guard for Core Operating Hours.

While the sleep manager is running, this guard holds a permanent
`systemd-inhibit --mode=delay --what=sleep` lock and listens to logind's
`org.freedesktop.login1.Manager.PrepareForSleep` D-Bus signal. When ANY
suspend is about to happen (including those triggered by third-party desktop
daemons that bypass BaluHost), the guard:

    1. Receives `PrepareForSleep(start=true)`.
    2. If BaluHost itself initiated the suspend (it already passed `wake_at`
       to `rtcwake -m mem`), skips — clobbering the RTC value would lose
       the user's intent.
    3. Otherwise computes the next core-uptime window start and runs
       `sudo rtcwake -m no -t <ts>` to set the RTC alarm without suspending.
    4. Releases the delay-mode inhibitor so logind can proceed with suspend.

After resume, `PrepareForSleep(start=false)` fires and the guard re-acquires
the delay lock for the next round.

Polkit:
- `--mode=delay` requires `org.freedesktop.login1.inhibit-delay-sleep`.
- The deployment template grants this for the BaluHost service user; see
  `deploy/install/templates/50-baluhost-inhibit-sleep.rules`.

Dev mode / Windows / missing binaries → no-op (returns False, logs once).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_SYSTEMD_INHIBIT = "systemd-inhibit"


class CoreUptimeRtcGuard:
    """Pre-arm RTC alarms for any suspend so external suspends still wake at next window."""

    def __init__(
        self,
        next_core_start_provider: Callable[[], Optional[object]],
        is_baluhost_suspend_in_progress: Callable[[], bool],
    ) -> None:
        """
        Args:
            next_core_start_provider: returns next datetime when a core-uptime
                window starts, or None if none configured / master toggle off.
            is_baluhost_suspend_in_progress: returns True iff `enter_true_suspend`
                is currently between its rtcwake call and resume — used to skip
                clobbering a BaluHost-initiated RTC alarm.
        """
        self._next_core_start = next_core_start_provider
        self._baluhost_in_progress = is_baluhost_suspend_in_progress
        self._delay_proc: Optional[subprocess.Popen] = None
        self._binary_missing_logged = False

    # --- delay-mode inhibitor lifecycle ---

    def _acquire_delay_inhibitor(self) -> bool:
        """Acquire the delay-mode inhibitor. Idempotent.

        Returns True on success (or already held), False on failure.
        """
        if self._delay_proc is not None and self._delay_proc.poll() is None:
            return True

        # Drop a dead handle so we re-spawn cleanly.
        if self._delay_proc is not None and self._delay_proc.poll() is not None:
            logger.info(
                "Core uptime RTC guard: delay inhibitor exited unexpectedly (rc=%s) — re-acquiring",
                self._delay_proc.returncode,
            )
            self._delay_proc = None

        binary = shutil.which(_SYSTEMD_INHIBIT)
        if binary is None:
            if not self._binary_missing_logged:
                logger.warning(
                    "%s not found — RTC wake guard disabled. External suspends "
                    "will not get an automatic wake-on-window-start alarm.",
                    _SYSTEMD_INHIBIT,
                )
                self._binary_missing_logged = True
            return False

        try:
            self._delay_proc = subprocess.Popen(
                [
                    binary,
                    "--what=sleep",
                    "--mode=delay",
                    "--who=BaluHost",
                    "--why=Set RTC wake at next core uptime window start",
                    "sleep", "infinity",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            logger.warning("Failed to spawn %s for delay inhibitor: %s", _SYSTEMD_INHIBIT, exc)
            return False

        # Settle window — polkit denial exits the subprocess immediately.
        time.sleep(0.2)
        if self._delay_proc.poll() is not None:
            stderr_output = ""
            if self._delay_proc.stderr is not None:
                try:
                    stderr_output = self._delay_proc.stderr.read().decode("utf-8", errors="replace").strip()
                except Exception:
                    pass
            logger.warning(
                "%s --mode=delay exited immediately (rc=%s) — likely polkit denial. "
                "Update /etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules to also allow "
                "org.freedesktop.login1.inhibit-delay-sleep. stderr=%r",
                _SYSTEMD_INHIBIT, self._delay_proc.returncode, stderr_output,
            )
            self._delay_proc = None
            return False

        logger.info(
            "Core uptime RTC guard: delay inhibitor acquired (pid=%s)",
            self._delay_proc.pid,
        )
        return True

    def _release_delay_inhibitor(self) -> None:
        """Release the delay inhibitor. Idempotent."""
        if self._delay_proc is None:
            return
        if self._delay_proc.poll() is None:
            try:
                self._delay_proc.terminate()
                try:
                    self._delay_proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Core uptime RTC guard: delay inhibitor pid=%s did not terminate in 3s — killing",
                        self._delay_proc.pid,
                    )
                    self._delay_proc.kill()
                    self._delay_proc.wait(timeout=1.0)
            except OSError as exc:
                logger.warning("Error releasing core uptime RTC guard delay inhibitor: %s", exc)
        logger.info("Core uptime RTC guard: delay inhibitor released")
        self._delay_proc = None

    # --- signal handler ---

    async def on_prepare_for_sleep(self, start: bool) -> None:
        """Handle logind's PrepareForSleep signal.

        start=True  → system is about to suspend. Pre-arm RTC alarm if applicable,
                      then release the delay lock.
        start=False → system has just resumed. Re-acquire the delay lock.
        """
        if not start:
            self._acquire_delay_inhibitor()
            return

        # start=True: BaluHost-initiated suspends already wrote rtcwake themselves.
        # Skip to avoid clobbering their wake_at value.
        try:
            if self._baluhost_in_progress():
                logger.info(
                    "PrepareForSleep(start=true) — skipping RTC arm: BaluHost-initiated suspend",
                )
                return

            next_start = self._next_core_start()
            if next_start is None:
                logger.info(
                    "PrepareForSleep(start=true) — no upcoming core uptime window, "
                    "external suspend will not auto-wake",
                )
                return

            try:
                self._set_rtc_alarm(next_start)
            except Exception as exc:
                # Failure is non-fatal — system still suspends, but won't auto-wake.
                logger.warning(
                    "PrepareForSleep(start=true) — failed to set RTC alarm: %s", exc,
                )
        finally:
            # Always release the delay lock so logind doesn't time out on us.
            self._release_delay_inhibitor()

    # --- rtcwake invocation ---

    def _set_rtc_alarm(self, wake_at) -> None:
        """Run `sudo rtcwake -m no -t <unix_ts>` to set the RTC alarm without suspending."""
        timestamp = str(int(wake_at.timestamp()))
        cmd = ["sudo", "rtcwake", "-m", "no", "-t", timestamp]
        logger.info("Setting RTC alarm at %s (ts=%s) for next core uptime start",
                    wake_at.isoformat(), timestamp)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                "rtcwake failed (rc=%s): stdout=%r stderr=%r",
                result.returncode, result.stdout.strip(), result.stderr.strip(),
            )
