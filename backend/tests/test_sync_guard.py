"""Tests for the sync sleep guard dependency."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient

from app.schemas.sleep import SleepState


def _make_app():
    """Create a minimal FastAPI app with the guard dependency."""
    from app.api.deps import require_sync_allowed

    test_app = FastAPI()

    @test_app.get("/test-guarded")
    async def guarded_endpoint(request: Request, _=Depends(require_sync_allowed)):
        return {"ok": True}

    return test_app


class TestRequireSyncAllowed:
    """Test the require_sync_allowed dependency."""

    def test_awake_allows_auto_sync(self):
        """Auto sync is allowed when NAS is awake."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.AWAKE

        with patch("app.services.power.sleep.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "auto"})
        assert resp.status_code == 200

    def test_soft_sleep_blocks_auto_sync(self):
        """Auto sync is blocked (503) when NAS is in soft sleep."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP
        mock_config = MagicMock()
        mock_config.schedule_enabled = True
        mock_config.schedule_wake_time = "06:00"
        mock_manager._load_config.return_value = mock_config

        with patch("app.services.power.sleep.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "auto"})
        assert resp.status_code == 503
        data = resp.json()
        assert data["detail"]["sleep_state"] == "soft_sleep"
        assert data["detail"]["next_wake_at"] is not None

    def test_soft_sleep_allows_manual_sync(self):
        """Manual sync is allowed even during soft sleep (auto-wake handles it)."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP

        with patch("app.services.power.sleep.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "manual"})
        assert resp.status_code == 200

    def test_no_header_treated_as_manual(self):
        """Missing X-Sync-Trigger header is treated as manual (backwards compat)."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP

        with patch("app.services.power.sleep.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded")
        assert resp.status_code == 200

    def test_scheduled_trigger_blocked(self):
        """Scheduled sync is blocked like auto sync."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP
        mock_manager._load_config.return_value = None

        with patch("app.services.power.sleep.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "scheduled"})
        assert resp.status_code == 503

    def test_no_sleep_manager_allows_all(self):
        """When sleep manager is not running, all syncs are allowed."""
        app = _make_app()

        with patch("app.services.power.sleep.get_sleep_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "auto"})
        assert resp.status_code == 200
