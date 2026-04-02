"""Tests for sync schedule validation against sleep windows."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.sync.scheduler import SyncSchedulerService


class TestSyncScheduleSleepValidation:
    """Test that sync schedule creation/update rejects times in sleep windows."""

    def _mock_sleep_config(self, enabled=True, sleep_time="23:00", wake_time="06:00"):
        config = MagicMock()
        config.schedule_enabled = enabled
        config.schedule_sleep_time = sleep_time
        config.schedule_wake_time = wake_time
        return config

    def test_create_schedule_in_sleep_window_rejected(self, db_session):
        """Creating a schedule at 02:00 with sleep window 23:00-06:00 should raise ValueError."""
        service = SyncSchedulerService(db_session)
        config = self._mock_sleep_config()

        with patch.object(service, "_get_sleep_config", return_value=config):
            with pytest.raises(ValueError, match="sleep window"):
                service.create_schedule(
                    user_id=1,
                    device_id="test-device",
                    schedule_type="daily",
                    time_of_day="02:00",
                )

    def test_create_schedule_outside_sleep_window_allowed(self, db_session):
        """Creating a schedule at 12:00 with sleep window 23:00-06:00 should work."""
        service = SyncSchedulerService(db_session)
        config = self._mock_sleep_config()

        with patch.object(service, "_get_sleep_config", return_value=config):
            result = service.create_schedule(
                user_id=1,
                device_id="test-device",
                schedule_type="daily",
                time_of_day="12:00",
            )
        assert result is not None
        assert result["time_of_day"] == "12:00"

    def test_create_schedule_no_sleep_config_allowed(self, db_session):
        """When no sleep config exists, any time is allowed."""
        service = SyncSchedulerService(db_session)

        with patch.object(service, "_get_sleep_config", return_value=None):
            result = service.create_schedule(
                user_id=1,
                device_id="test-device",
                schedule_type="daily",
                time_of_day="02:00",
            )
        assert result is not None

    def test_create_schedule_sleep_disabled_allowed(self, db_session):
        """When sleep schedule is disabled, any time is allowed."""
        service = SyncSchedulerService(db_session)
        config = self._mock_sleep_config(enabled=False)

        with patch.object(service, "_get_sleep_config", return_value=config):
            result = service.create_schedule(
                user_id=1,
                device_id="test-device",
                schedule_type="daily",
                time_of_day="02:00",
            )
        assert result is not None
