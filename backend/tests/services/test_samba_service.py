"""Tests for services/samba_service.py — dev-mode stubs return True."""

import pytest

from app.services import samba_service


@pytest.mark.asyncio
class TestSyncSmbPassword:
    async def test_dev_mode_returns_true(self):
        result = await samba_service.sync_smb_password("testuser", "Password123")
        assert result is True


@pytest.mark.asyncio
class TestRemoveSmbUser:
    async def test_dev_mode_returns_true(self):
        result = await samba_service.remove_smb_user("testuser")
        assert result is True


@pytest.mark.asyncio
class TestEnableSmbUser:
    async def test_dev_mode_returns_true(self):
        result = await samba_service.enable_smb_user("testuser")
        assert result is True


@pytest.mark.asyncio
class TestDisableSmbUser:
    async def test_dev_mode_returns_true(self):
        result = await samba_service.disable_smb_user("testuser")
        assert result is True


@pytest.mark.asyncio
class TestRegenerateSharesConfig:
    async def test_dev_mode_returns_true(self):
        result = await samba_service.regenerate_shares_config()
        assert result is True


@pytest.mark.asyncio
class TestReloadSamba:
    async def test_dev_mode_returns_true(self):
        result = await samba_service.reload_samba()
        assert result is True


@pytest.mark.asyncio
class TestGetSambaStatus:
    async def test_dev_mode_returns_status_dict(self):
        status = await samba_service.get_samba_status()
        assert isinstance(status, dict)
        assert status["is_running"] is False
        assert status["version"] == "dev-mode"
        assert status["active_connections"] == []
        assert isinstance(status["smb_users_count"], int)
