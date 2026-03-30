"""Tests for services/samba_service.py — dev-mode stubs return True."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
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
class TestStorageGroupConfig:
    """Verify Samba uses settings.storage_group for force group."""

    async def test_regenerate_uses_storage_group(
        self, db_session: Session, admin_user: User, tmp_path, monkeypatch
    ):
        """In non-dev mode, force group should use storage_group setting."""
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings

        # Patch SessionLocal so samba_service uses the test DB
        test_engine = db_session.get_bind()
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        monkeypatch.setattr("app.services.samba_service.SessionLocal", TestSessionLocal)

        # Enable SMB for the admin user
        admin_user.smb_enabled = True
        db_session.commit()

        # Non-dev mode with custom storage group
        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(settings, "storage_group", "testgroup")

        # Write to temp file instead of /etc/samba/
        conf_path = str(tmp_path / "shares.conf")
        monkeypatch.setattr(samba_service, "_get_shares_conf_path", lambda: conf_path)

        result = await samba_service.regenerate_shares_config()
        assert result is True

        content = Path(conf_path).read_text()
        assert "force group = testgroup" in content
        assert "force group = sven" not in content


@pytest.mark.asyncio
class TestGetSambaStatus:
    async def test_dev_mode_returns_status_dict(self):
        status = await samba_service.get_samba_status()
        assert isinstance(status, dict)
        assert status["is_running"] is False
        assert status["version"] == "dev-mode"
        assert status["active_connections"] == []
        assert isinstance(status["smb_users_count"], int)
