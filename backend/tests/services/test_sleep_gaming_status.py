"""The sleep status and config must expose the gaming suppressor.

Without this the UI shows a box that refuses to sleep and no reason why, which
reads as a hang rather than as the feature working.
"""
from unittest.mock import patch

from app.models.sleep import SleepConfig
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.schemas.sleep import SleepConfigUpdate


def _build_service():
    SleepManagerService._instance = None
    return SleepManagerService(DevSleepBackend())


def _config(block_in_gaming_mode=True):
    return SleepConfig(
        id=1,
        auto_idle_enabled=False,
        idle_timeout_minutes=15,
        idle_cpu_threshold=8.0,
        idle_disk_io_threshold=1.0,
        idle_http_threshold=5.0,
        auto_escalation_enabled=False,
        escalation_after_minutes=60,
        schedule_enabled=False,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=False,
        core_uptime_suspend_on_exit=False,
        always_awake_enabled=False,
        always_awake_until=None,
        block_suspend_in_gaming_mode=block_in_gaming_mode,
        presence_enabled=False,
        presence_mode="active",
        presence_timeout_minutes=3,
    )


def test_status_reports_a_running_game_as_suppressing_suspend():
    svc = _build_service()
    with patch.object(svc, "_load_config", return_value=_config()), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.gaming_presence.game_is_running", return_value=True), \
         patch("app.services.power.gaming_presence.gaming_mode_on_screen", return_value=False):
        status = svc.get_status()

    assert status.gaming.game_running is True
    assert status.gaming.suppressing_suspend is True


def test_status_reports_big_picture_separately_from_a_game():
    svc = _build_service()
    with patch.object(svc, "_load_config", return_value=_config()), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.gaming_presence.game_is_running", return_value=False), \
         patch("app.services.power.gaming_presence.gaming_mode_on_screen", return_value=True):
        status = svc.get_status()

    assert status.gaming.game_running is False
    assert status.gaming.gaming_mode is True
    assert status.gaming.suppressing_suspend is True


def test_status_does_not_suppress_when_the_setting_is_off_and_no_game_runs():
    svc = _build_service()
    with patch.object(svc, "_load_config", return_value=_config(block_in_gaming_mode=False)), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.gaming_presence.game_is_running", return_value=False), \
         patch("app.services.power.gaming_presence.gaming_mode_on_screen", return_value=True):
        status = svc.get_status()

    assert status.gaming.gaming_mode is True
    assert status.gaming.suppressing_suspend is False


def test_config_response_exposes_the_setting():
    svc = _build_service()
    with patch.object(svc, "_load_config", return_value=_config(block_in_gaming_mode=False)):
        cfg = svc.get_config()

    assert cfg.block_suspend_in_gaming_mode is False


def test_config_update_accepts_the_setting():
    update = SleepConfigUpdate(block_suspend_in_gaming_mode=False)
    assert update.block_suspend_in_gaming_mode is False
