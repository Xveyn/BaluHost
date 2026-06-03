"""Unit tests for status-strip collectors. Each collector wraps a service;
we patch the service and assert the collector's mapping/silence behavior."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_collect_pihole_enabled_returns_success_tone():
    from app.services.status_bar import collectors
    fake_service = MagicMock()
    fake_service.get_status = AsyncMock(return_value={
        "blocking_enabled": True, "connected": True, "mode": "docker",
    })
    with patch.object(collectors, "get_pihole_service", return_value=fake_service):
        result = await collectors.collect_pihole(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["label_key"] == "pills.pihole.live"
    assert result["value_key"] == "pills.pihole.on"


@pytest.mark.asyncio
async def test_collect_pihole_disconnected_returns_none():
    from app.services.status_bar import collectors
    fake_service = MagicMock()
    fake_service.get_status = AsyncMock(return_value={
        "blocking_enabled": False, "connected": False, "mode": "disabled",
    })
    with patch.object(collectors, "get_pihole_service", return_value=fake_service):
        result = await collectors.collect_pihole(MagicMock(), "admin")
    assert result is None


@pytest.mark.asyncio
async def test_collect_raid_silent_when_optimal():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_raid_array_statuses", return_value=["optimal", "optimal"]):
        result = await collectors.collect_raid(MagicMock(), "admin")
    assert result is None


@pytest.mark.asyncio
async def test_collect_raid_warns_when_degraded():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_raid_array_statuses", return_value=["optimal", "degraded"]):
        result = await collectors.collect_raid(MagicMock(), "admin")
    assert result is not None
    assert result["tone"] in ("warning", "danger")
    assert result["label_key"] == "pills.raid.live"
    assert result["value_key"] == "pills.raid.status.degraded"
    assert result["value"] == "degraded"  # raw fallback for unknown statuses


@pytest.mark.asyncio
async def test_collector_never_raises_returns_none():
    from app.services.status_bar import collectors
    fake_service = MagicMock()
    fake_service.get_status = AsyncMock(side_effect=RuntimeError("backend down"))
    with patch.object(collectors, "get_pihole_service", return_value=fake_service):
        result = await collectors.collect_pihole(MagicMock(), "admin")
    assert result is None


@pytest.mark.asyncio
async def test_collect_sync_silent_without_conflicts():
    from app.services.status_bar import collectors
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.count.return_value = 0
    result = await collectors.collect_sync(fake_db, "admin")
    assert result is None


@pytest.mark.asyncio
async def test_collect_sync_warns_on_conflicts():
    from app.services.status_bar import collectors
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.count.return_value = 3
    result = await collectors.collect_sync(fake_db, "admin")
    assert result is not None
    assert result["tone"] == "warning"
    assert result["label_key"] == "pills.sync.live"
    assert result["value_key"] == "pills.sync.conflicts"
    assert result["value_params"] == {"n": 3}


@pytest.mark.asyncio
async def test_always_awake_silent_when_disabled():
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=False)
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        assert await collectors.collect_always_awake(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_always_awake_permanent_has_permanent_value():
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=True, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=False)
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result["value"] == "permanent"
    assert result["tone"] == "warning"
    assert result["label_key"] == "pills.alwaysAwake.live"


@pytest.mark.asyncio
async def test_always_awake_with_expiry_exposes_seconds():
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=True, until="2026-05-28T12:00:00Z", expires_in_seconds=3600.0)
    fake_status.core_uptime = MagicMock(active=False)
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result["extra"]["expires_in_seconds"] == 3600.0
    assert result["value"] == "01:00:00"


def _exec(name, status, started_at):
    m = MagicMock()
    m.scheduler_name = name
    m.status = status
    m.started_at = started_at
    return m


@pytest.mark.asyncio
async def test_scheduler_silent_when_no_active():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_active_executions", return_value=[]):
        assert await collectors.collect_scheduler(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_scheduler_counts_active_and_lists_names():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    rows = [
        _exec("backup", "running", datetime(2026, 5, 28, 10, tzinfo=timezone.utc)),
        _exec("smart_scan", "running", datetime(2026, 5, 28, 11, tzinfo=timezone.utc)),
        _exec("sync_check", "requested", datetime(2026, 5, 28, 12, tzinfo=timezone.utc)),
    ]
    with patch.object(collectors, "_active_executions", return_value=rows):
        result = await collectors.collect_scheduler(MagicMock(), "admin")
    assert result["value"] == "3"
    assert result["tone"] == "info"
    assert len(result["extra"]["jobs"]) == 3


@pytest.mark.asyncio
async def test_scheduler_caps_jobs_at_three_newest_first():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    rows = [_exec(f"job{i}", "running", datetime(2026, 5, 28, i, tzinfo=timezone.utc)) for i in range(5)]
    with patch.object(collectors, "_active_executions", return_value=rows):
        result = await collectors.collect_scheduler(MagicMock(), "admin")
    assert result["value"] == "5"
    assert len(result["extra"]["jobs"]) == 3


def _backup(status, created_at, completed_at=None):
    m = MagicMock()
    m.status = status
    m.created_at = created_at
    m.completed_at = completed_at
    return m


@pytest.mark.asyncio
async def test_backup_in_progress_shows_running_key():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    running = _backup("in_progress", datetime(2026, 5, 28, 10, tzinfo=timezone.utc))
    with patch.object(collectors, "_running_backup", return_value=running), \
         patch.object(collectors, "_last_finished_backup", return_value=None):
        result = await collectors.collect_backup(MagicMock(), "admin")
    assert result["tone"] == "info"
    assert result["label_key"] == "pills.backup.live"
    assert result["value_key"] == "pills.backup.running"


@pytest.mark.asyncio
async def test_backup_failed_within_24h_is_danger():
    from datetime import datetime, timezone, timedelta
    from app.services.status_bar import collectors
    finished = datetime.now(timezone.utc) - timedelta(hours=2)
    failed = _backup("failed", finished - timedelta(minutes=5), finished)
    with patch.object(collectors, "_running_backup", return_value=None), \
         patch.object(collectors, "_last_finished_backup", return_value=failed):
        result = await collectors.collect_backup(MagicMock(), "admin")
    assert result["tone"] == "danger"
    assert result["value_key"] == "pills.backup.failed"


@pytest.mark.asyncio
async def test_backup_failed_older_than_24h_is_silent():
    from datetime import datetime, timezone, timedelta
    from app.services.status_bar import collectors
    finished = datetime.now(timezone.utc) - timedelta(hours=25)
    failed = _backup("failed", finished - timedelta(minutes=5), finished)
    with patch.object(collectors, "_running_backup", return_value=None), \
         patch.object(collectors, "_last_finished_backup", return_value=failed):
        assert await collectors.collect_backup(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_backup_completed_is_silent():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    done = _backup("completed", datetime(2026, 5, 28, 9, tzinfo=timezone.utc),
                   datetime(2026, 5, 28, 10, tzinfo=timezone.utc))
    with patch.object(collectors, "_running_backup", return_value=None), \
         patch.object(collectors, "_last_finished_backup", return_value=done):
        assert await collectors.collect_backup(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_backup_running_beats_recent_failure():
    from datetime import datetime, timezone, timedelta
    from app.services.status_bar import collectors
    running = _backup("in_progress", datetime.now(timezone.utc))
    finished = datetime.now(timezone.utc) - timedelta(hours=1)
    failed = _backup("failed", finished, finished)
    with patch.object(collectors, "_running_backup", return_value=running), \
         patch.object(collectors, "_last_finished_backup", return_value=failed):
        result = await collectors.collect_backup(MagicMock(), "admin")
    assert result["value_key"] == "pills.backup.running"


@pytest.mark.asyncio
async def test_vpn_silent_without_active_clients():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_vpn_peer_counts", return_value=(0, 0)):
        assert await collectors.collect_vpn(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_vpn_neutral_when_configured_but_none_connected():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_vpn_peer_counts", return_value=(0, 4)):
        result = await collectors.collect_vpn(MagicMock(), "admin")
    assert result is not None
    assert result["tone"] == "neutral"
    assert result["label_key"] == "pills.vpn.live"
    assert result["value_key"] == "pills.vpn.connected"
    assert result["value_params"] == {"n": 0}


@pytest.mark.asyncio
async def test_vpn_success_when_peers_connected():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_vpn_peer_counts", return_value=(2, 4)):
        result = await collectors.collect_vpn(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["value_params"] == {"n": 2}
    assert result["label_key"] == "pills.vpn.live"
    assert "label" not in result


@pytest.mark.asyncio
async def test_collect_sleep_uses_label_key_and_raw_time():
    from app.services.status_bar import collectors
    status = MagicMock(schedule_enabled=True)
    config = MagicMock(schedule_sleep_time="23:30")
    mgr = MagicMock()
    mgr.get_status = MagicMock(return_value=status)
    mgr.get_config = MagicMock(return_value=config)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_sleep(MagicMock(), "admin")
    assert result["label_key"] == "pills.sleep.live"
    assert result["value"] == "23:30"


@pytest.mark.asyncio
async def test_collect_temp_uses_label_key_and_raw_celsius():
    from app.services.status_bar import collectors
    service = MagicMock()
    service.get_status = AsyncMock(return_value={"fans": [
        {"name": "cpu", "temperature_celsius": 95, "emergency_temp_celsius": 90},
    ]})
    with patch("app.services.power.fan_control.get_fan_control_service", return_value=service):
        result = await collectors.collect_temp(MagicMock(), "admin")
    assert result["label_key"] == "pills.temp.live"
    assert result["value"] == "95°C"


@pytest.mark.asyncio
async def test_collect_scheduler_uses_label_key():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    rows = [_exec("backup", "running", datetime(2026, 5, 28, 10, tzinfo=timezone.utc))]
    with patch.object(collectors, "_active_executions", return_value=rows):
        result = await collectors.collect_scheduler(MagicMock(), "admin")
    assert result["label_key"] == "pills.scheduler.live"
    assert result["value"] == "1"


def test_vpn_peer_counts_only_counts_recent_handshakes():
    from datetime import datetime, timezone, timedelta
    from app.services.status_bar import collectors

    def _client(handshake):
        m = MagicMock()
        m.last_handshake = handshake
        return m

    now = datetime.now(timezone.utc)
    clients = [
        _client(now - timedelta(seconds=30)),    # connected
        _client(now - timedelta(minutes=10)),    # stale
        _client(None),                            # never connected
    ]
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.all.return_value = clients
    connected, active_total = collectors._vpn_peer_counts(fake_db)
    assert connected == 1
    assert active_total == 3


def test_collectors_registry_covers_full_catalog():
    from app.services.status_bar.collectors import COLLECTORS
    from app.services.status_bar.catalog import CATALOG
    assert set(COLLECTORS.keys()) == {p.id for p in CATALOG}


@pytest.mark.asyncio
async def test_always_awake_falls_back_to_core_uptime():
    from datetime import datetime
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=True, current_window_ends_at=datetime(2026, 5, 29, 22, 0))
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result is not None
    assert result["icon"] == "Shield"
    assert result["tone"] == "success"
    assert result["label_key"] == "pills.alwaysAwake.coreUptimeLive"
    assert result["extra"]["variant"] == "core_uptime"
    assert result["extra"]["until"] == "22:00"
    assert "value" not in result


@pytest.mark.asyncio
async def test_always_awake_takes_precedence_over_core_uptime():
    from datetime import datetime
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=True, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(
        active=True, current_window_ends_at=datetime(2026, 5, 29, 22, 0))
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result["tone"] == "warning"
    assert result["extra"]["variant"] == "always_awake"
    assert result["value"] == "permanent"
    assert result["label_key"] == "pills.alwaysAwake.live"


@pytest.mark.asyncio
async def test_always_awake_and_core_uptime_both_off_silent():
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=False)
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        assert await collectors.collect_always_awake(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_collect_desktop_running_neutral():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="running")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result is not None
    assert result["tone"] == "neutral"
    assert result["label_key"] == "pills.desktop.live"
    assert result["value_key"] == "pills.desktop.on"
    assert result["icon"] == "Monitor"
    assert result["_state"] == "running"


@pytest.mark.asyncio
async def test_collect_desktop_stopped_success():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="stopped")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["value_key"] == "pills.desktop.off"
    assert result["_state"] == "stopped"


@pytest.mark.asyncio
async def test_collect_desktop_unknown_silent():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="unknown")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result is None


@pytest.mark.asyncio
async def test_collect_desktop_swallows_error():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(side_effect=RuntimeError("no sddm"))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result is None


def test_desktop_registered_in_collectors():
    from app.services.status_bar.collectors import COLLECTORS
    assert "desktop" in COLLECTORS


# ── power ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_power_pill_preset_and_level():
    from app.services.status_bar import collectors
    preset = MagicMock(); preset.name = "Balanced"
    status = MagicMock(dynamic_mode_enabled=False, current_profile=MagicMock(value="surge"), active_preset=preset)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.profile"
    assert result["label_params"] == {"preset": "Balanced", "level": "Surge"}
    assert result["icon"] == "Zap"
    assert "value" not in result and "label" not in result


@pytest.mark.asyncio
async def test_power_pill_no_preset_fallback():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=False, current_profile=MagicMock(value="surge"), active_preset=None)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.level"
    assert result["label_params"] == {"level": "Surge"}


@pytest.mark.asyncio
async def test_power_pill_silent_without_profile():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=False, current_profile=None)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        assert await collectors.collect_power(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_power_pill_dynamic_mode_with_governor():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=True, dynamic_mode_config=MagicMock(governor="schedutil"))
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.dynamic"
    assert result["label_params"] == {"governor": "schedutil"}


@pytest.mark.asyncio
async def test_power_pill_dynamic_mode_no_config():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=True, dynamic_mode_config=None)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.dynamicBare"
    assert "label_params" not in result


# ── uploads ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_collect_uploads_counts_active():
    from app.services.status_bar import collectors
    p1 = MagicMock(status="uploading"); p2 = MagicMock(status="done")
    mgr = MagicMock(); mgr._progress = {"a": p1, "b": p2}
    with patch("app.services.upload_progress.get_upload_progress_manager", return_value=mgr):
        result = await collectors.collect_uploads(MagicMock(), "admin")
    assert result["label_key"] == "pills.uploads.live"
    assert result["value"] == "1"


@pytest.mark.asyncio
async def test_no_collector_emits_legacy_label_key():
    """Every collector must emit `label_key`, never the legacy literal `label`."""
    from app.services.status_bar import collectors
    from app.services.status_bar.collectors import COLLECTORS
    from unittest.mock import AsyncMock, MagicMock, patch
    # Patch the underlying helpers so several collectors return a populated dict.
    patches = [
        patch.object(collectors, "_vpn_peer_counts", return_value=(1, 2)),
        patch.object(collectors, "_raid_array_statuses", return_value=["degraded"]),
        patch.object(collectors, "_active_executions",
                     return_value=[_exec("backup", "running", None)]),
        patch.object(collectors, "_running_backup", return_value=_backup("in_progress", None)),
        patch.object(collectors, "_last_finished_backup", return_value=None),
    ]
    for p in patches:
        p.start()
    try:
        for name, fn in COLLECTORS.items():
            result = await fn(MagicMock(), "admin")
            if result is None:
                continue
            assert "label" not in result, f"collector {name} still emits legacy 'label'"
            assert "label_key" in result, f"collector {name} missing 'label_key'"
    finally:
        for p in patches:
            p.stop()
