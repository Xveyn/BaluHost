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
                link_type="delete",
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
