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
    assert result is not None
    assert result["tone"] == "success"


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
    assert "3" in result["value"]


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
async def test_backup_in_progress_shows_laeuft():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    running = _backup("in_progress", datetime(2026, 5, 28, 10, tzinfo=timezone.utc))
    with patch.object(collectors, "_running_backup", return_value=running), \
         patch.object(collectors, "_last_finished_backup", return_value=None):
        result = await collectors.collect_backup(MagicMock(), "admin")
    assert result["tone"] == "info"
    assert result["value"] == "läuft"


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
    assert result["value"] == "läuft"


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
    assert result["value"] == "0 verbunden"


@pytest.mark.asyncio
async def test_vpn_success_when_peers_connected():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_vpn_peer_counts", return_value=(2, 4)):
        result = await collectors.collect_vpn(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["value"] == "2 verbunden"
    assert result["label"] == "VPN"


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
    fake_status.core_uptime = MagicMock(
        active=True, current_window_ends_at=datetime(2026, 5, 29, 22, 0))
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result is not None
    assert result["icon"] == "Shield"
    assert result["tone"] == "success"
    assert result["value"] == "bis 22:00"
    assert result["extra"]["variant"] == "core_uptime"
    assert result["extra"]["until"] == "22:00"


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


@pytest.mark.asyncio
async def test_always_awake_and_core_uptime_both_off_silent():
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=False)
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        assert await collectors.collect_always_awake(MagicMock(), "admin") is None
