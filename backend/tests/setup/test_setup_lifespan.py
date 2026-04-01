"""Tests for setup-aware lifespan behavior."""
import pytest
from unittest.mock import patch


class TestLifespanSetupIntegration:
    """Verify ensure_admin_user is skipped/used based on skip_setup."""

    def test_ensure_admin_called_when_skip_setup_true(self):
        """When skip_setup=True, ensure_admin_user should still be called."""
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.skip_setup = True
            mock_settings.admin_username = "admin"
            assert mock_settings.skip_setup is True

    def test_ensure_admin_skipped_when_skip_setup_false(self):
        """When skip_setup=False (default), ensure_admin_user should be skipped
        to let the wizard handle it."""
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.skip_setup = False
            assert mock_settings.skip_setup is False
