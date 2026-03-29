"""Tests for CloudExportJob model and CloudExportService."""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.cloud import CloudConnection
from app.models.cloud_export import CloudExportJob


def _create_connection(db: Session, user_id: int = 1) -> CloudConnection:
    """Helper to create a cloud connection."""
    conn = CloudConnection(
        user_id=user_id,
        provider="google_drive",
        display_name="Test Drive",
        encrypted_config="encrypted-data",
        is_active=True,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


class TestCloudExportJobModel:
    def test_create_export_job(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="Documents/report.pdf",
            is_directory=False,
            file_name="report.pdf",
            file_size_bytes=2_500_000,
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="pending",
            progress_bytes=0,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        assert job.id is not None
        assert job.status == "pending"
        assert job.share_link is None
        assert job.cloud_path is None

    def test_is_expired_with_no_expiry(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=0,
        )
        db_session.add(job)
        db_session.commit()
        assert job.is_expired() is False

    def test_is_expired_with_future_expiry(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=0,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(job)
        db_session.commit()
        assert job.is_expired() is False

    def test_is_expired_with_past_expiry(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=0,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(job)
        db_session.commit()
        assert job.is_expired() is True


from app.schemas.cloud_export import CloudExportRequest, CloudExportJobResponse, CloudExportStatistics


class TestCloudExportSchemas:
    def test_export_request_defaults(self):
        req = CloudExportRequest(connection_id=1, source_path="docs/report.pdf")
        assert req.cloud_folder == "BaluHost Shares/"
        assert req.link_type == "view"
        assert req.expires_at is None

    def test_export_request_custom_values(self):
        req = CloudExportRequest(
            connection_id=1,
            source_path="docs/report.pdf",
            cloud_folder="My Exports/",
            link_type="edit",
        )
        assert req.cloud_folder == "My Exports/"
        assert req.link_type == "edit"

    def test_export_request_rejects_invalid_link_type(self):
        with pytest.raises(Exception):
            CloudExportRequest(
                connection_id=1,
                source_path="test.txt",
                link_type="delete",  # type: ignore[arg-type]  # intentionally invalid
            )

    def test_job_response_from_model(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=1024,
            share_link="https://drive.google.com/file/d/abc123/view",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        resp = CloudExportJobResponse.model_validate(job, from_attributes=True)
        assert resp.id == job.id
        assert resp.status == "ready"
        assert resp.share_link == "https://drive.google.com/file/d/abc123/view"

    def test_statistics_schema(self):
        stats = CloudExportStatistics(
            total_exports=10,
            active_exports=5,
            failed_exports=2,
            total_upload_bytes=1_000_000,
        )
        assert stats.active_exports == 5


import asyncio
from pathlib import Path
import tempfile

from app.services.cloud.adapters.dev import DevCloudAdapter


class TestDevCloudAdapterUpload:
    def test_upload_file(self, tmp_path: Path):
        adapter = DevCloudAdapter(provider="google_drive")
        local_file = tmp_path / "test.txt"
        local_file.write_text("hello world")

        progress_values = []
        asyncio.run(
            adapter.upload_file(local_file, "/BaluHost Shares/test.txt", lambda b: progress_values.append(b))
        )
        assert len(progress_values) > 0
        assert progress_values[-1] > 0

    def test_upload_folder(self, tmp_path: Path):
        adapter = DevCloudAdapter(provider="google_drive")
        folder = tmp_path / "docs"
        folder.mkdir()
        (folder / "a.txt").write_text("aaa")
        (folder / "b.txt").write_text("bbb")

        result = asyncio.run(
            adapter.upload_folder(folder, "/BaluHost Shares/docs")
        )
        assert result.files_transferred == 2
        assert result.bytes_transferred > 0
        assert len(result.errors) == 0

    def test_create_share_link(self):
        adapter = DevCloudAdapter(provider="google_drive")
        link = asyncio.run(
            adapter.create_share_link("/BaluHost Shares/test.txt", link_type="view")
        )
        assert link.startswith("https://")
        assert "mock" in link.lower() or "baluhost" in link.lower() or "example" in link.lower()

    def test_create_share_link_onedrive(self):
        adapter = DevCloudAdapter(provider="onedrive")
        link = asyncio.run(
            adapter.create_share_link("/BaluHost Shares/test.txt", link_type="edit")
        )
        assert link.startswith("https://")


from unittest.mock import patch, AsyncMock, MagicMock

from app.services.cloud.export_service import CloudExportService


class TestCloudExportServiceStartExport:
    def test_start_export_creates_job(self, db_session: Session):
        conn = _create_connection(db_session)
        service = CloudExportService(db_session)

        job = service.start_export(
            connection_id=conn.id,
            user_id=1,
            source_path="Documents/report.pdf",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            expires_at=None,
        )

        assert job.id is not None
        assert job.status == "pending"
        assert job.file_name == "report.pdf"
        assert job.is_directory is False
        assert job.cloud_folder == "BaluHost Shares/"

    def test_start_export_directory(self, db_session: Session):
        conn = _create_connection(db_session)
        service = CloudExportService(db_session)

        job = service.start_export(
            connection_id=conn.id,
            user_id=1,
            source_path="Photos/Vacation/",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            expires_at=None,
        )

        assert job.file_name == "Vacation"
        assert job.is_directory is True

    def test_start_export_rejects_path_traversal(self, db_session: Session):
        conn = _create_connection(db_session)
        service = CloudExportService(db_session)

        with pytest.raises(ValueError, match="path traversal"):
            service.start_export(
                connection_id=conn.id,
                user_id=1,
                source_path="../etc/passwd",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )

    def test_start_export_invalid_connection(self, db_session: Session):
        service = CloudExportService(db_session)

        with pytest.raises(ValueError, match="not found"):
            service.start_export(
                connection_id=999,
                user_id=1,
                source_path="test.txt",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )


class TestCloudExportServiceQueries:
    def _create_job(self, db: Session, conn_id: int, user_id: int = 1, status: str = "ready") -> CloudExportJob:
        job = CloudExportJob(
            user_id=user_id,
            connection_id=conn_id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status=status,
            progress_bytes=1024,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def test_get_user_exports(self, db_session: Session):
        conn = _create_connection(db_session)
        self._create_job(db_session, conn.id)
        self._create_job(db_session, conn.id)

        service = CloudExportService(db_session)
        jobs = service.get_user_exports(user_id=1)
        assert len(jobs) == 2

    def test_get_user_exports_filters_by_user(self, db_session: Session):
        conn = _create_connection(db_session)
        self._create_job(db_session, conn.id, user_id=1)
        self._create_job(db_session, conn.id, user_id=2)

        service = CloudExportService(db_session)
        jobs = service.get_user_exports(user_id=1)
        assert len(jobs) == 1

    def test_get_export_status(self, db_session: Session):
        conn = _create_connection(db_session)
        job = self._create_job(db_session, conn.id)

        service = CloudExportService(db_session)
        result = service.get_export_status(job.id, user_id=1)
        assert result is not None
        assert result.id == job.id

    def test_get_export_status_wrong_user(self, db_session: Session):
        conn = _create_connection(db_session)
        job = self._create_job(db_session, conn.id, user_id=1)

        service = CloudExportService(db_session)
        result = service.get_export_status(job.id, user_id=999)
        assert result is None

    def test_get_export_statistics(self, db_session: Session):
        conn = _create_connection(db_session)
        self._create_job(db_session, conn.id, status="ready")
        self._create_job(db_session, conn.id, status="failed")
        self._create_job(db_session, conn.id, status="revoked")

        service = CloudExportService(db_session)
        stats = service.get_export_statistics(user_id=1)
        assert stats.total_exports == 3
        assert stats.active_exports == 1
        assert stats.failed_exports == 1

    def test_revoke_export(self, db_session: Session):
        conn = _create_connection(db_session)
        job = self._create_job(db_session, conn.id, status="ready")

        service = CloudExportService(db_session)
        with patch.object(service, '_delete_cloud_file', new_callable=AsyncMock):
            result = service.revoke_export(job.id, user_id=1)

        assert result is True
        db_session.refresh(job)
        assert job.status == "revoked"


from app.services.cloud.service import CloudService


class TestCloudServiceScopeCheck:
    def test_check_scope_readonly_google(self, db_session: Session):
        conn = CloudConnection(
            user_id=1,
            provider="google_drive",
            display_name="GDrive",
            encrypted_config="fake",
            rclone_remote_name="gdrive_test",
            is_active=True,
        )
        db_session.add(conn)
        db_session.commit()
        db_session.refresh(conn)

        service = CloudService(db_session)
        result = service.check_connection_scope(conn.id, 1)
        assert result["provider"] == "google_drive"
        # With fake config, default assumption is no export scope
        assert result["has_export_scope"] is False

    def test_check_scope_invalid_connection(self, db_session: Session):
        service = CloudService(db_session)
        with pytest.raises(ValueError):
            service.check_connection_scope(999, 1)


class TestCloudExportExecuteFlow:
    """Integration test for the full export flow using DevCloudAdapter."""

    async def test_execute_export_file(self, db_session: Session, tmp_path: Path):
        """Test full export: upload file + create link in dev mode."""
        # Setup: create connection and a local file
        conn = _create_connection(db_session)

        from app.core.config import settings
        original_storage = settings.nas_storage_path

        try:
            settings.nas_storage_path = str(tmp_path)
            test_file = tmp_path / "report.pdf"
            test_file.write_bytes(b"x" * 5000)

            service = CloudExportService(db_session)
            job = service.start_export(
                connection_id=conn.id,
                user_id=1,
                source_path="report.pdf",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )

            assert job.status == "pending"

            # Execute (uses DevCloudAdapter in dev mode)
            await service.execute_export(job.id)

            db_session.refresh(job)
            assert job.status == "ready"
            assert job.share_link is not None
            assert job.share_link.startswith("https://")
            assert job.cloud_path == "BaluHost Shares/report.pdf"
            assert job.completed_at is not None

        finally:
            settings.nas_storage_path = original_storage

    async def test_execute_export_missing_file(self, db_session: Session, tmp_path: Path):
        """Test export fails gracefully when source file doesn't exist."""
        conn = _create_connection(db_session)

        from app.core.config import settings
        original_storage = settings.nas_storage_path

        try:
            settings.nas_storage_path = str(tmp_path)
            # Don't create the file

            service = CloudExportService(db_session)
            job = service.start_export(
                connection_id=conn.id,
                user_id=1,
                source_path="nonexistent.txt",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )

            await service.execute_export(job.id)

            db_session.refresh(job)
            assert job.status == "failed"
            assert "does not exist" in (job.error_message or "")

        finally:
            settings.nas_storage_path = original_storage
