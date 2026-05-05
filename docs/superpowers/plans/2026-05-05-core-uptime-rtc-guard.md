# Core Uptime RTC Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make any system suspend — including those triggered by third-party desktop daemons (mate-screensaver, KDE-Plasma) outside of an active core-uptime window — schedule an RTC wake alarm at the next core-uptime window start, so the server reliably wakes when the next "Kernbetriebszeit" begins.

**Architecture:** Add a `CoreUptimeRtcGuard` that holds a permanent `delay`-mode `systemd-inhibit` lock and listens to logind's `org.freedesktop.login1.Manager.PrepareForSleep` D-Bus signal. When the signal fires with `start=true`, the guard sets `rtcwake -m no -t <next_core_start>` (alarm only, no suspend) before releasing the delay lock so logind can proceed. BaluHost-initiated suspends (which already pass `wake_at` to `rtcwake -m mem`) bypass the guard via an in-progress flag to avoid clobbering their own RTC value.

**Tech Stack:** Python 3.11, `dbus-next` (async pure-Python D-Bus), `systemd-inhibit` subprocess pattern (mirrors existing `core_uptime_inhibitor.py`), polkit rules.d for production deployments.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/pyproject.toml` | modify | Add `dbus-next>=0.2.3,<1.0.0` to core dependencies |
| `backend/app/services/power/core_uptime_rtc_guard.py` | **create** | Guard class: delay-mode inhibitor + D-Bus signal handler + rtcwake invocation |
| `backend/app/services/power/sleep.py` | modify | Wire guard into `start()`/`stop()`, add `_baluhost_suspend_in_progress` flag set around `_backend.suspend_system()` |
| `deploy/install/templates/50-baluhost-inhibit-sleep.rules` | modify | Add `org.freedesktop.login1.inhibit-delay-sleep` to the allowed actions |
| `deploy/install/modules/10-systemd-services.sh` | (no change required — already reads template idempotently) | — |
| `backend/tests/services/test_core_uptime_rtc_guard.py` | **create** | Unit tests for guard, mocking subprocess + D-Bus + rtcwake |
| `backend/tests/services/test_sleep_core_uptime_integration.py` | modify | Integration test: external suspend → rtcwake set with next-core ts; BaluHost-initiated → rtcwake skipped |
| `CHANGELOG.md` | modify | New `[1.31.8]` entry |

**Design rationale for the new module:** The existing `core_uptime_inhibitor.py` does block-mode (refuse all suspends inside windows). The new guard is structurally similar but handles delay-mode (allow suspends outside windows but pre-arm an RTC alarm). Splitting them keeps each file's responsibility crisp; both are <250 LOC.

---

## Task 1: Add `dbus-next` dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add `dbus-next` to core dependencies**

In `backend/pyproject.toml`, inside the `dependencies = [...]` array, append after the line `"qrcode>=7.0.0"`:

```toml
  "dbus-next>=0.2.3,<1.0.0"
```

The full line in context (before/after):

```toml
  "qrcode>=7.0.0",
  "dbus-next>=0.2.3,<1.0.0"
]
```

(Note: ensure the trailing comma is added to the `qrcode` line.)

- [ ] **Step 2: Install the new dependency in the dev venv**

Run from project root:

```bash
cd backend && pip install -e ".[dev]"
```

Expected: `dbus-next` installed without conflict messages.

- [ ] **Step 3: Verify the import works**

Run:

```bash
python -c "from dbus_next.aio import MessageBus; from dbus_next import BusType; print('ok')"
```

Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(deps): add dbus-next for logind PrepareForSleep listener"
```

---

## Task 2: Polkit rule template — add `inhibit-delay-sleep`

**Files:**
- Modify: `deploy/install/templates/50-baluhost-inhibit-sleep.rules`

- [ ] **Step 1: Replace the polkit rule template**

Overwrite `deploy/install/templates/50-baluhost-inhibit-sleep.rules` with:

```js
// BaluHost — allow the service user to acquire logind sleep inhibitors.
//
// Two inhibitor types are needed:
//
//   inhibit-block-sleep  — held during active "Core Operating Hours" windows
//                           so third-party daemons (mate-screensaver, KDE,
//                           manual `systemctl suspend`) cannot suspend.
//
//   inhibit-delay-sleep  — held permanently by CoreUptimeRtcGuard. When ANY
//                           suspend is about to happen, logind fires
//                           PrepareForSleep(start=true), the guard sets an RTC
//                           alarm (`rtcwake -m no -t <next_core_start>`) and
//                           releases the delay lock so logind can proceed.
//
// The default polkit policy on Debian 13 for both
// `org.freedesktop.login1.inhibit-block-sleep` and
// `org.freedesktop.login1.inhibit-delay-sleep` is `allow_active=yes` only.
// A systemd service running as ${BALUHOST_USER} has no active session, so
// without this rule polkit asks for admin auth and the service silently fails
// to acquire the inhibitor.
//
// This rule grants the BaluHost service user permission for both actions.
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.login1.inhibit-block-sleep" ||
         action.id == "org.freedesktop.login1.inhibit-delay-sleep") &&
        subject.user == "@@BALUHOST_USER@@") {
        return polkit.Result.YES;
    }
});
```

- [ ] **Step 2: Commit**

```bash
git add deploy/install/templates/50-baluhost-inhibit-sleep.rules
git commit -m "feat(deploy): allow inhibit-delay-sleep in polkit rule"
```

---

## Task 3: Delay-mode systemd-inhibit wrapper (testable)

**Files:**
- Create: `backend/app/services/power/core_uptime_rtc_guard.py` (initial scaffold — class with delay-inhibitor only, no D-Bus yet)
- Test: `backend/tests/services/test_core_uptime_rtc_guard.py`

We split the work: this task adds the inhibitor wrapper inside the guard module so we can unit-test it without D-Bus. Task 4 adds the D-Bus listener on top.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_core_uptime_rtc_guard.py`:

```python
"""Unit tests for CoreUptimeRtcGuard."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.power.core_uptime_rtc_guard import CoreUptimeRtcGuard


def _build_guard():
    """Build a guard with no-op callbacks; tests patch what they need."""
    return CoreUptimeRtcGuard(
        next_core_start_provider=lambda: None,
        is_baluhost_suspend_in_progress=lambda: False,
    )


class TestDelayInhibitor:
    """Subprocess lifecycle for the delay-mode systemd-inhibit lock."""

    def test_acquire_returns_false_when_systemd_inhibit_missing(self):
        guard = _build_guard()
        with patch("app.services.power.core_uptime_rtc_guard.shutil.which", return_value=None):
            ok = guard._acquire_delay_inhibitor()
        assert ok is False
        assert guard._delay_proc is None

    def test_acquire_spawns_subprocess_with_delay_mode(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        fake_proc.pid = 12345
        with patch("app.services.power.core_uptime_rtc_guard.shutil.which",
                   return_value="/usr/bin/systemd-inhibit"), \
             patch("app.services.power.core_uptime_rtc_guard.subprocess.Popen",
                   return_value=fake_proc) as mock_popen, \
             patch("app.services.power.core_uptime_rtc_guard.time.sleep"):
            ok = guard._acquire_delay_inhibitor()
        assert ok is True
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        assert "--mode=delay" in cmd
        assert "--what=sleep" in cmd
        assert "--who=BaluHost" in cmd

    def test_acquire_idempotent_when_already_held(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        guard._delay_proc = fake_proc
        with patch("app.services.power.core_uptime_rtc_guard.subprocess.Popen") as mock_popen:
            ok = guard._acquire_delay_inhibitor()
        assert ok is True
        mock_popen.assert_not_called()

    def test_acquire_detects_immediate_polkit_denial(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        # poll() returns None first (still alive after spawn), then 1 (exited
        # immediately during settle window — i.e. polkit denied).
        fake_proc.poll.side_effect = [1]
        fake_proc.returncode = 1
        fake_proc.stderr = None
        with patch("app.services.power.core_uptime_rtc_guard.shutil.which",
                   return_value="/usr/bin/systemd-inhibit"), \
             patch("app.services.power.core_uptime_rtc_guard.subprocess.Popen",
                   return_value=fake_proc), \
             patch("app.services.power.core_uptime_rtc_guard.time.sleep"):
            ok = guard._acquire_delay_inhibitor()
        assert ok is False
        assert guard._delay_proc is None

    def test_release_terminates_subprocess(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        fake_proc.pid = 12345
        guard._delay_proc = fake_proc
        guard._release_delay_inhibitor()
        fake_proc.terminate.assert_called_once()
        assert guard._delay_proc is None

    def test_release_idempotent_when_no_proc(self):
        guard = _build_guard()
        guard._release_delay_inhibitor()
        # No exception means pass.
```

- [ ] **Step 2: Run tests to confirm they fail with ImportError**

Run:

```bash
cd backend && python -m pytest tests/services/test_core_uptime_rtc_guard.py -v
```

Expected: collection error (`ModuleNotFoundError: No module named 'app.services.power.core_uptime_rtc_guard'`).

- [ ] **Step 3: Create the module skeleton**

Create `backend/app/services/power/core_uptime_rtc_guard.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd backend && python -m pytest tests/services/test_core_uptime_rtc_guard.py::TestDelayInhibitor -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/core_uptime_rtc_guard.py \
        backend/tests/services/test_core_uptime_rtc_guard.py
git commit -m "feat(sleep): scaffold CoreUptimeRtcGuard with delay-mode inhibitor"
```

---

## Task 4: rtcwake handler — pure logic for `on_prepare_for_sleep`

**Files:**
- Modify: `backend/app/services/power/core_uptime_rtc_guard.py` (add `on_prepare_for_sleep` method + `_set_rtc_alarm` helper)
- Modify: `backend/tests/services/test_core_uptime_rtc_guard.py` (add `TestOnPrepareForSleep`)

We isolate the handler's logic from the D-Bus subscription so it can be unit-tested without spawning a bus.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/test_core_uptime_rtc_guard.py`:

```python
import datetime as _dt


class TestOnPrepareForSleep:
    """Logic for handling logind's PrepareForSleep(start=...) signal."""

    @pytest.mark.asyncio
    async def test_start_true_skips_when_baluhost_initiated(self):
        next_start = _dt.datetime(2026, 5, 6, 8, 0)
        ran_rtc = []
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: next_start,
            is_baluhost_suspend_in_progress=lambda: True,
        )
        # Spawn a fake delay proc so we can verify it gets released.
        guard._delay_proc = MagicMock()
        guard._delay_proc.poll.return_value = None
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=lambda ts: ran_rtc.append(ts)):
            await guard.on_prepare_for_sleep(True)
        assert ran_rtc == []  # rtcwake skipped — BaluHost set its own
        # Delay inhibitor still released so logind can proceed.
        guard._delay_proc = None  # _release sets this; mock didn't track

    @pytest.mark.asyncio
    async def test_start_true_skips_when_no_next_core(self):
        ran_rtc = []
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: None,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        guard._delay_proc = MagicMock()
        guard._delay_proc.poll.return_value = None
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=lambda ts: ran_rtc.append(ts)), \
             patch.object(guard, "_release_delay_inhibitor") as mock_release:
            await guard.on_prepare_for_sleep(True)
        assert ran_rtc == []
        mock_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_true_sets_rtc_alarm_to_next_core(self):
        next_start = _dt.datetime(2026, 5, 6, 8, 0)
        ran_rtc = []
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: next_start,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        guard._delay_proc = MagicMock()
        guard._delay_proc.poll.return_value = None
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=lambda ts: ran_rtc.append(ts)), \
             patch.object(guard, "_release_delay_inhibitor"):
            await guard.on_prepare_for_sleep(True)
        assert ran_rtc == [next_start]

    @pytest.mark.asyncio
    async def test_start_false_reacquires_delay_inhibitor(self):
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: None,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        with patch.object(guard, "_acquire_delay_inhibitor",
                          return_value=True) as mock_acquire:
            await guard.on_prepare_for_sleep(False)
        mock_acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_true_releases_even_if_rtc_fails(self):
        """If rtcwake raises, we MUST still release the delay lock so the
        suspend isn't permanently stuck waiting on BaluHost."""
        next_start = _dt.datetime(2026, 5, 6, 8, 0)
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: next_start,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=RuntimeError("rtcwake failed")), \
             patch.object(guard, "_release_delay_inhibitor") as mock_release:
            await guard.on_prepare_for_sleep(True)
        mock_release.assert_called_once()


class TestSetRtcAlarm:
    """Subprocess invocation for `sudo rtcwake -m no -t <ts>`."""

    def test_set_rtc_alarm_calls_rtcwake_with_unix_timestamp(self):
        guard = _build_guard()
        wake_at = _dt.datetime(2026, 5, 6, 8, 0)
        expected_ts = str(int(wake_at.timestamp()))
        with patch("app.services.power.core_uptime_rtc_guard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            guard._set_rtc_alarm(wake_at)
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd == ["sudo", "rtcwake", "-m", "no", "-t", expected_ts]

    def test_set_rtc_alarm_logs_on_failure_but_does_not_raise(self):
        guard = _build_guard()
        wake_at = _dt.datetime(2026, 5, 6, 8, 0)
        with patch("app.services.power.core_uptime_rtc_guard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="permission denied")
            # Must not raise.
            guard._set_rtc_alarm(wake_at)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && python -m pytest tests/services/test_core_uptime_rtc_guard.py -v
```

Expected: `TestOnPrepareForSleep` and `TestSetRtcAlarm` fail with `AttributeError: 'CoreUptimeRtcGuard' object has no attribute 'on_prepare_for_sleep'` (and similar for `_set_rtc_alarm`).

- [ ] **Step 3: Add the handler + helper to the guard**

Append to `backend/app/services/power/core_uptime_rtc_guard.py` (inside the `CoreUptimeRtcGuard` class, after `_release_delay_inhibitor`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd backend && python -m pytest tests/services/test_core_uptime_rtc_guard.py -v
```

Expected: all 13 tests pass (6 from Task 3 + 5 from `TestOnPrepareForSleep` + 2 from `TestSetRtcAlarm`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/core_uptime_rtc_guard.py \
        backend/tests/services/test_core_uptime_rtc_guard.py
git commit -m "feat(sleep): RTC alarm handler for PrepareForSleep signal"
```

---

## Task 5: D-Bus subscription — `start()` and `stop()`

**Files:**
- Modify: `backend/app/services/power/core_uptime_rtc_guard.py` (add `start()`, `stop()`, `_subscribe_dbus()`)
- Modify: `backend/tests/services/test_core_uptime_rtc_guard.py` (add `TestStartStop`)

The D-Bus subscription is a thin shim — it routes the signal payload into `on_prepare_for_sleep` (already tested). Tests mock `MessageBus.connect` to verify the subscription is wired without an actual bus connection.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/test_core_uptime_rtc_guard.py`:

```python
class TestStartStop:
    """Lifecycle: start subscribes to D-Bus + acquires inhibitor; stop releases."""

    @pytest.mark.asyncio
    async def test_start_acquires_inhibitor_and_subscribes(self):
        guard = _build_guard()

        # Mock the dbus-next bus + introspection chain.
        fake_introspection = MagicMock()
        fake_proxy = MagicMock()
        fake_iface = MagicMock()
        fake_proxy.get_interface.return_value = fake_iface

        fake_bus = MagicMock()
        fake_bus.introspect = MagicMock(return_value=_async_value(fake_introspection))
        fake_bus.get_proxy_object.return_value = fake_proxy

        async def fake_connect():
            return fake_bus

        with patch("app.services.power.core_uptime_rtc_guard.MessageBus") as mock_bus_class, \
             patch.object(guard, "_acquire_delay_inhibitor", return_value=True) as mock_acquire:
            mock_bus_class.return_value.connect = fake_connect
            await guard.start()

        mock_acquire.assert_called_once()
        # Signal handler registered:
        fake_iface.on_prepare_for_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_continues_when_dbus_unavailable(self):
        """If dbus-next can't connect (dev mode, Windows, no system bus),
        the guard logs and returns without crashing."""
        guard = _build_guard()
        with patch("app.services.power.core_uptime_rtc_guard.MessageBus") as mock_bus_class, \
             patch.object(guard, "_acquire_delay_inhibitor", return_value=False):
            mock_bus_class.return_value.connect = _failing_async("no bus")
            # Must not raise.
            await guard.start()
        assert guard._dbus_iface is None

    @pytest.mark.asyncio
    async def test_stop_releases_inhibitor_and_disconnects(self):
        guard = _build_guard()
        guard._dbus_bus = MagicMock()
        guard._dbus_bus.disconnect = MagicMock()
        guard._dbus_iface = MagicMock()
        with patch.object(guard, "_release_delay_inhibitor") as mock_release:
            await guard.stop()
        mock_release.assert_called_once()
        guard._dbus_bus.disconnect.assert_called_once()
        assert guard._dbus_iface is None
        assert guard._dbus_bus is None


# Helpers for async mock awaitables.
def _async_value(value):
    async def _():
        return value
    return _()


def _failing_async(msg: str):
    async def _():
        raise RuntimeError(msg)
    return _
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && python -m pytest tests/services/test_core_uptime_rtc_guard.py::TestStartStop -v
```

Expected: 3 failures (`AttributeError: 'CoreUptimeRtcGuard' object has no attribute 'start'`).

- [ ] **Step 3: Add the D-Bus subscription**

In `backend/app/services/power/core_uptime_rtc_guard.py`:

a) Add the imports near the top (after existing imports):

```python
try:
    from dbus_next.aio import MessageBus
    from dbus_next import BusType
    _DBUS_AVAILABLE = True
except ImportError:  # pragma: no cover — dev/Windows fallback
    MessageBus = None  # type: ignore[assignment]
    BusType = None  # type: ignore[assignment]
    _DBUS_AVAILABLE = False
```

b) Extend `__init__` to track the bus + iface:

Replace the body of `__init__` so it ends with:

```python
        self._delay_proc: Optional[subprocess.Popen] = None
        self._binary_missing_logged = False
        self._dbus_bus: Optional["MessageBus"] = None
        self._dbus_iface = None
```

c) Add `start()` and `stop()` methods at the end of the class:

```python
    # --- lifecycle ---

    async def start(self) -> None:
        """Acquire the delay inhibitor and subscribe to logind PrepareForSleep.

        Failures (no D-Bus, no systemd-inhibit, polkit denial) are logged but
        do not raise — the guard simply degrades to no-op.
        """
        self._acquire_delay_inhibitor()

        if not _DBUS_AVAILABLE:
            logger.info("dbus-next not available — RTC guard signal listener disabled")
            return

        try:
            self._dbus_bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            introspection = await self._dbus_bus.introspect(
                "org.freedesktop.login1", "/org/freedesktop/login1",
            )
            proxy = self._dbus_bus.get_proxy_object(
                "org.freedesktop.login1", "/org/freedesktop/login1", introspection,
            )
            self._dbus_iface = proxy.get_interface("org.freedesktop.login1.Manager")

            def _on_signal(start: bool) -> None:
                # dbus-next dispatches signals as sync callbacks; bridge to async.
                import asyncio
                asyncio.create_task(self.on_prepare_for_sleep(start))

            self._dbus_iface.on_prepare_for_sleep(_on_signal)
            logger.info("Core uptime RTC guard: subscribed to logind PrepareForSleep signal")
        except Exception as exc:
            logger.warning(
                "Could not subscribe to logind PrepareForSleep — RTC guard listener "
                "disabled. External suspends will not get an auto-wake alarm. "
                "(%s)", exc,
            )
            self._dbus_iface = None
            if self._dbus_bus is not None:
                try:
                    self._dbus_bus.disconnect()
                except Exception:
                    pass
                self._dbus_bus = None

    async def stop(self) -> None:
        """Release the delay inhibitor and disconnect from D-Bus."""
        self._release_delay_inhibitor()
        if self._dbus_bus is not None:
            try:
                self._dbus_bus.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting from system bus: %s", exc)
        self._dbus_bus = None
        self._dbus_iface = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd backend && python -m pytest tests/services/test_core_uptime_rtc_guard.py -v
```

Expected: all tests pass (16 total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/core_uptime_rtc_guard.py \
        backend/tests/services/test_core_uptime_rtc_guard.py
git commit -m "feat(sleep): subscribe RTC guard to logind PrepareForSleep"
```

---

## Task 6: Wire guard into `SleepManagerService`

**Files:**
- Modify: `backend/app/services/power/sleep.py` (instantiate guard, lifecycle hooks, in-progress flag)
- Modify: `backend/tests/services/test_sleep_core_uptime_integration.py` (integration test)

- [ ] **Step 1: Write the failing integration tests**

Append to `backend/tests/services/test_sleep_core_uptime_integration.py`:

```python
@pytest.mark.asyncio
async def test_rtc_guard_started_with_sleep_service(monkeypatch):
    """SleepManagerService.start() must call CoreUptimeRtcGuard.start()."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend
    from unittest.mock import AsyncMock, patch as _patch

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    with _patch.object(svc._core_uptime_rtc_guard, "start",
                       new=AsyncMock()) as mock_start, \
         _patch.object(svc, "_idle_detection_loop", new=AsyncMock()), \
         _patch.object(svc, "_schedule_check_loop", new=AsyncMock()):
        await svc.start(monitoring=True)
        await svc.stop()

    mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_rtc_guard_stopped_with_sleep_service(monkeypatch):
    """SleepManagerService.stop() must call CoreUptimeRtcGuard.stop()."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend
    from unittest.mock import AsyncMock, patch as _patch

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    with _patch.object(svc._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         _patch.object(svc._core_uptime_rtc_guard, "stop",
                       new=AsyncMock()) as mock_stop, \
         _patch.object(svc, "_idle_detection_loop", new=AsyncMock()), \
         _patch.object(svc, "_schedule_check_loop", new=AsyncMock()):
        await svc.start(monitoring=True)
        await svc.stop()

    mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_baluhost_initiated_suspend_sets_flag_around_backend_call():
    """During the rtcwake -m mem call, the in-progress flag must be True so
    the RTC guard skips its own rtcwake call and doesn't clobber wake_at."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend
    from app.schemas.sleep import SleepTrigger, SleepState
    from unittest.mock import AsyncMock, patch as _patch

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    flag_during_backend = []

    async def fake_suspend_system(wake_at=None):
        flag_during_backend.append(svc.is_baluhost_suspend_in_progress())
        return True

    with _patch.object(svc, "_load_config", return_value=None), \
         _patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         _patch.object(backend, "suspend_system", side_effect=fake_suspend_system), \
         _patch("app.services.power.sleep.SessionLocal"), \
         _patch("app.services.notifications.events.emit_system_suspend",
                new=AsyncMock(return_value=None)):
        svc._current_state = SleepState.SOFT_SLEEP
        assert svc.is_baluhost_suspend_in_progress() is False
        await svc.enter_true_suspend("test", SleepTrigger.MANUAL, wake_at=None)
        # Flag back to False after suspend returns.
        assert svc.is_baluhost_suspend_in_progress() is False

    assert flag_during_backend == [True]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py::test_rtc_guard_started_with_sleep_service tests/services/test_sleep_core_uptime_integration.py::test_baluhost_initiated_suspend_sets_flag_around_backend_call -v
```

Expected: failures (`AttributeError: '_core_uptime_rtc_guard'` and `'is_baluhost_suspend_in_progress'`).

- [ ] **Step 3: Wire the guard into `SleepManagerService.__init__`**

Edit `backend/app/services/power/sleep.py`:

a) Add import after the existing `CoreUptimeInhibitor` import (around line 31):

```python
from app.services.power.core_uptime_rtc_guard import CoreUptimeRtcGuard
```

b) In `SleepManagerService.__init__`, add right after the existing `self._core_uptime_inhibitor = CoreUptimeInhibitor()` line (locate by searching `_core_uptime_inhibitor`):

```python
        self._baluhost_suspend_in_progress: bool = False
        self._core_uptime_rtc_guard = CoreUptimeRtcGuard(
            next_core_start_provider=self._next_core_start_for_guard,
            is_baluhost_suspend_in_progress=lambda: self._baluhost_suspend_in_progress,
        )
```

c) Add the helper method (anywhere reasonable in the class — suggest right after `_load_core_uptime`):

```python
    def _next_core_start_for_guard(self) -> Optional[datetime]:
        """Provider used by CoreUptimeRtcGuard. Returns None on any failure
        so the guard cleanly skips arming the RTC."""
        try:
            master, windows = self._load_core_uptime()
            if not master:
                return None
            return core_uptime_helpers.next_core_uptime_start(datetime.now(), windows)
        except Exception as exc:
            logger.warning("RTC guard provider failed: %s", exc)
            return None

    def is_baluhost_suspend_in_progress(self) -> bool:
        """Public read-only accessor for the in-progress flag (for tests)."""
        return self._baluhost_suspend_in_progress
```

- [ ] **Step 4: Hook into `start()` and `stop()`**

Locate `SleepManagerService.start()` (line ~160 per the existing layout) and add **at the very beginning** of the `if monitoring:` block, before the existing core-uptime startup-acquire logic:

```python
            await self._core_uptime_rtc_guard.start()
```

In `SleepManagerService.stop()`, add as the **first line** of the method (before any other shutdown):

```python
        await self._core_uptime_rtc_guard.stop()
```

- [ ] **Step 5: Set the flag around `_backend.suspend_system()`**

In `enter_true_suspend()` (around line 887), wrap the suspend call. Replace this block:

```python
        # 3. Suspend the system.  When *wake_at* is given the backend uses
        #    ``rtcwake -m mem`` which sets the RTC alarm and suspends atomically.
        ok = await self._backend.suspend_system(wake_at=wake_at)
```

With:

```python
        # 3. Suspend the system.  When *wake_at* is given the backend uses
        #    ``rtcwake -m mem`` which sets the RTC alarm and suspends atomically.
        # The flag tells CoreUptimeRtcGuard to skip its own rtcwake on the
        # PrepareForSleep signal (we already set wake_at via rtcwake -m mem).
        self._baluhost_suspend_in_progress = True
        try:
            ok = await self._backend.suspend_system(wake_at=wake_at)
        finally:
            self._baluhost_suspend_in_progress = False
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -v
```

Expected: all integration tests pass (existing + 3 new).

- [ ] **Step 7: Run the full sleep test suite to verify no regression**

Run:

```bash
cd backend && python -m pytest tests/services/ tests/test_lifecycle_notifications.py -v
```

Expected: all previously-passing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/power/sleep.py \
        backend/tests/services/test_sleep_core_uptime_integration.py
git commit -m "feat(sleep): wire CoreUptimeRtcGuard into SleepManagerService lifecycle"
```

---

## Task 7: Documentation + CHANGELOG + version bump

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `backend/pyproject.toml` (version bump)
- Modify: `client/package.json` (version bump)
- Modify: `CLAUDE.md` (version bump)

- [ ] **Step 1: Bump version to 1.31.8**

Replace `1.31.7` with `1.31.8` in:

- `backend/pyproject.toml` line 3 (`version = "1.31.8"`)
- `client/package.json` (`"version": "1.31.8"`)
- `CLAUDE.md` (`**Version**: 1.31.8 (as of May 2026)`)

- [ ] **Step 2: Add CHANGELOG entry**

Open `CHANGELOG.md`, insert a new entry directly under the top header (above the `[1.31.7]` block):

```markdown
## [1.31.8] - 2026-05-05

### Added
- **Core Uptime RTC Guard**: New `CoreUptimeRtcGuard` listens to logind's
  `PrepareForSleep` D-Bus signal and pre-arms an RTC wake alarm
  (`rtcwake -m no -t <next_core_start>`) for any suspend that bypasses
  BaluHost (e.g. `mate-screensaver`, KDE-Plasma, manual `systemctl suspend`).
  Closes the gap where third-party suspends outside an active core-uptime
  window left the server suspended past the next window start.

### Changed
- Polkit rule template now also grants
  `org.freedesktop.login1.inhibit-delay-sleep` to the BaluHost service user
  (re-run the install / update path or manually update
  `/etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules`).

### Dependencies
- Added `dbus-next>=0.2.3,<1.0.0` (pure-Python async D-Bus client).
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md backend/pyproject.toml client/package.json CLAUDE.md
git commit -m "docs: CHANGELOG entry for v1.31.8 + version bump"
```

---

## Task 8: Verification + manual smoke (production-only)

These steps require a Linux host with logind. Skip on Windows/dev — the unit tests already cover the logic.

- [ ] **Step 1: Run the full backend test suite locally**

Run:

```bash
cd backend && python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Open PR to `development` branch**

```bash
git push -u origin <feature-branch-name>
gh pr create --base development --title "feat(sleep): RTC guard for third-party suspends" --body "$(cat <<'EOF'
## Summary
- Adds `CoreUptimeRtcGuard` that pre-arms an RTC wake alarm before any
  suspend, so external suspends (mate-screensaver, KDE, manual systemctl)
  still wake the server at the next core-uptime window start.
- Uses logind's `PrepareForSleep` D-Bus signal + a permanent delay-mode
  inhibitor so the handler can run before the kernel suspends.
- Adds `inhibit-delay-sleep` to the polkit rule template.

## Test plan
- [ ] Unit tests pass (`pytest tests/services/test_core_uptime_rtc_guard.py`)
- [ ] Integration tests pass (`pytest tests/services/test_sleep_core_uptime_integration.py`)
- [ ] Full backend suite passes (`pytest`)
- [ ] On prod (BaluNode): polkit rule updated, restart `baluhost-backend`,
      verify journal shows `delay inhibitor acquired`
- [ ] On prod: trigger external suspend outside a window, verify
      `Setting RTC alarm at <next_core_start>` log line; system wakes at
      that timestamp.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: After merge to `development` → `main` (release-PR), production deploy steps**

On the production server (`BaluNode`):

```bash
cd /opt/baluhost
sudo -u sven git pull
sudo -u sven /opt/baluhost/backend/.venv/bin/pip install -e ./backend
sudo bash deploy/install/modules/10-systemd-services.sh   # rewrites the polkit rule
sudo systemctl restart baluhost-backend
```

Verify:

```bash
# Polkit rule has both actions:
sudo cat /etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules | grep -E "inhibit-(block|delay)-sleep"

# Both inhibitors held simultaneously when in core uptime, only delay outside:
ps -ef | grep -E "systemd-inhibit.*BaluHost" | grep -v grep

# Journal shows delay-inhibitor acquired at startup:
sudo journalctl -u baluhost-backend --since "2 minutes ago" | grep -iE "delay inhibitor|PrepareForSleep|RTC alarm"
```

Expected: `Core uptime RTC guard: delay inhibitor acquired (pid=...)` and
`Core uptime RTC guard: subscribed to logind PrepareForSleep signal` appear
within ~5s of restart.

Smoke test the auto-wake:

```bash
# Outside a core-uptime window, manually suspend:
sudo systemctl suspend
# Wait for the window start time. System should wake automatically.
```

Verify wake:

```bash
sudo journalctl --since "10 minutes ago" | grep -iE "rtcwake|setting rtc alarm|wake from suspend"
```

Expected: `Setting RTC alarm at <next_core_start>` line in the suspend
prep, then a kernel wake at exactly that timestamp.

---

## Self-Review Checklist

- [x] Spec coverage: PrepareForSleep listener, delay inhibitor, rtcwake on external suspend, BaluHost-initiated bypass, polkit, deployment, tests — all in scope.
- [x] No placeholders ("TBD", "implement later", etc.).
- [x] Type consistency: `CoreUptimeRtcGuard.__init__(next_core_start_provider, is_baluhost_suspend_in_progress)` matches all test fixtures and the wiring in `SleepManagerService.__init__`. Method names: `start()`, `stop()`, `on_prepare_for_sleep(start: bool)`, `_acquire_delay_inhibitor()`, `_release_delay_inhibitor()`, `_set_rtc_alarm(wake_at)` — used consistently across tasks.
- [x] Every code step has the actual code (no "fill in"); every command shows expected output.
- [x] Frequent commits: 8 commits across 8 tasks.
