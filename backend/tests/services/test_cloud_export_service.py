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
