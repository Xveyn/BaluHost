"""Tests for services/nfs_service.py."""
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.nfs_export import NfsExport
from app.services import nfs_service


class TestValidateClients:
    def test_accepts_valid_specs(self):
        for spec in ["*", "192.168.1.5", "192.168.1.0/24", "host.local", "10.0.0.0/8"]:
            assert nfs_service.validate_clients(spec) == spec

    def test_rejects_bad_specs(self):
        for spec in ["", "300.1.1.1", "1.2.3.4/40", "bad spec!", "a b"]:
            with pytest.raises(ValueError):
                nfs_service.validate_clients(spec)


class TestValidateExportPath:
    def test_relative_path_within_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.nfs_service.settings.nas_storage_path", str(tmp_path))
        result = nfs_service.validate_export_path("Media")
        assert result.endswith("Media")

    def test_empty_path_is_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.nfs_service.settings.nas_storage_path", str(tmp_path))
        result = nfs_service.validate_export_path("")
        assert Path(result) == Path(str(tmp_path)).resolve()

    def test_traversal_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.nfs_service.settings.nas_storage_path", str(tmp_path))
        for bad in ["../etc", "Media/../../etc", "../../../etc/passwd"]:
            with pytest.raises(ValueError):
                nfs_service.validate_export_path(bad)


@pytest.mark.asyncio
class TestDevModeStubs:
    async def test_regenerate_returns_true(self):
        assert await nfs_service.regenerate_exports_config() is True

    async def test_apply_returns_true(self):
        assert await nfs_service.apply_exports() is True

    async def test_status_shape(self):
        status = await nfs_service.get_nfs_status()
        assert status["is_running"] is False
        assert status["version"] == "dev-mode"
        assert isinstance(status["exports_count"], int)


@pytest.mark.asyncio
class TestRegenerateExportsConfig:
    async def test_writes_correct_export_line(self, db_session: Session, tmp_path, monkeypatch):
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings

        test_engine = db_session.get_bind()
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        monkeypatch.setattr("app.services.nfs_service.SessionLocal", TestSessionLocal)

        exp = NfsExport(path="Media", clients="192.168.1.0/24", read_only=False, root_squash=True, enabled=True)
        db_session.add(exp)
        db_session.commit()
        db_session.refresh(exp)

        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(settings, "nas_storage_path", str(tmp_path))
        conf_path = str(tmp_path / "baluhost.exports")
        monkeypatch.setattr(nfs_service, "_get_exports_conf_path", lambda: conf_path)

        assert await nfs_service.regenerate_exports_config() is True

        content = Path(conf_path).read_text()
        assert "Media" in content
        assert f"192.168.1.0/24(rw,root_squash,sync,no_subtree_check,fsid={exp.id})" in content

    async def test_disabled_export_excluded(self, db_session: Session, tmp_path, monkeypatch):
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings

        test_engine = db_session.get_bind()
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        monkeypatch.setattr("app.services.nfs_service.SessionLocal", TestSessionLocal)

        db_session.add(NfsExport(path="Off", clients="*", enabled=False))
        db_session.commit()

        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(settings, "nas_storage_path", str(tmp_path))
        conf_path = str(tmp_path / "baluhost.exports")
        monkeypatch.setattr(nfs_service, "_get_exports_conf_path", lambda: conf_path)

        assert await nfs_service.regenerate_exports_config() is True
        assert "Off" not in Path(conf_path).read_text()
