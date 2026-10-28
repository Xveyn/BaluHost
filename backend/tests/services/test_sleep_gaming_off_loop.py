"""The /proc scan behind the gaming check must not run on the event loop.

`gaming_presence.blocks_suspend()` reads `/proc/<pid>/cmdline` for every
process (~600 on the production box, ~45 ms). `SleepManagerService` asks it
once per 60 s schedule tick and once per 30 s idle check, both on the loop —
py-spy on the primary worker (2026-10-28) showed it as the remaining ~50 ms
once-a-minute stall tracked in #797.
"""
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.sleep import SleepState
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend


def _build_service():
    SleepManagerService._instance = None  # reset singleton
    return SleepManagerService(DevSleepBackend())


def _recording_blocks_suspend(seen: list):
    def fake(_config):
        seen.append(threading.current_thread())
        return False

    return fake


@pytest.mark.asyncio
async def test_async_variant_scans_in_a_worker_thread():
    svc = _build_service()
    seen: list = []
    with patch("app.services.power.gaming_presence.blocks_suspend",
               side_effect=_recording_blocks_suspend(seen)):
        assert await svc._is_gaming_active_async(MagicMock()) is False

    assert len(seen) == 1
    assert seen[0] is not threading.main_thread()


@pytest.mark.asyncio
async def test_async_variant_fails_toward_energy_saving():
    svc = _build_service()
    with patch("app.services.power.gaming_presence.blocks_suspend",
               side_effect=RuntimeError("boom")):
        assert await svc._is_gaming_active_async(MagicMock()) is False


@pytest.mark.asyncio
async def test_schedule_tick_scans_once_off_loop_and_hands_result_to_reconcile():
    """One scan per tick, in a thread; reconcile reuses it instead of rescanning."""
    svc = _build_service()
    seen: list = []
    reconcile_kwargs: list = []
    svc._is_running = True
    svc._current_state = SleepState.AWAKE

    async def stop_after_first(*_a, **_k):
        if getattr(stop_after_first, "done", False):
            svc._is_running = False
        stop_after_first.done = True

    with patch.object(svc, "_load_config", return_value=MagicMock(
            always_awake_enabled=False, core_uptime_suspend_on_exit=False,
            schedule_enabled=False)), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_reconcile_sleep_inhibitor",
                      side_effect=lambda *a, **k: reconcile_kwargs.append(k)), \
         patch("app.services.power.gaming_presence.blocks_suspend",
               side_effect=_recording_blocks_suspend(seen)), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_first):
        await svc._schedule_check_loop()

    assert len(seen) == 1
    assert seen[0] is not threading.main_thread()
    assert reconcile_kwargs and reconcile_kwargs[0].get("gaming_active") is False


def test_reconcile_without_a_precomputed_result_still_scans_itself():
    """Sync callers (startup, post-clear) keep the old behaviour."""
    svc = _build_service()
    with patch.object(svc, "_is_gaming_active", return_value=False) as scan, \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False):
        svc._reconcile_sleep_inhibitor(MagicMock(), in_core=False)
    scan.assert_called_once()


def test_reconcile_uses_a_precomputed_result_without_scanning():
    svc = _build_service()
    with patch.object(svc, "_is_gaming_active") as scan, \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False):
        svc._reconcile_sleep_inhibitor(MagicMock(), in_core=False, gaming_active=False)
    scan.assert_not_called()
