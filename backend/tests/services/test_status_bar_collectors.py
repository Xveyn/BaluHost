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
