"""Tests for services/cloud/scheduler.py — CloudSyncScheduler."""

from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.cloud import CloudConnection, CloudImportJob
from app.services.cloud.scheduler import CloudSyncScheduler


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


def _create_completed_sync_job(
    db: Session, connection_id: int, user_id: int = 1
) -> CloudImportJob:
    """Helper to create a completed sync job."""
    job = CloudImportJob(
        connection_id=connection_id,
        user_id=user_id,
        source_path="/Cloud/Documents",
        destination_path="/NAS/Documents",
        job_type="sync",
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


class TestRunSync:
    def test_no_sync_jobs_returns_zero(self, db_session: Session):
        result = CloudSyncScheduler.run_sync(db_session)
        assert result == {"synced": 0, "errors": 0}

    def test_no_completed_sync_jobs(self, db_session: Session):
        conn = _create_connection(db_session)
        # Create a pending job (not completed)
        job = CloudImportJob(
            connection_id=conn.id,
            user_id=1,
            source_path="/src",
            destination_path="/dst",
            job_type="sync",
            status="pending",
        )
        db_session.add(job)
        db_session.commit()

        result = CloudSyncScheduler.run_sync(db_session)
        assert result == {"synced": 0, "errors": 0}

    def test_ignores_import_jobs(self, db_session: Session):
        conn = _create_connection(db_session)
        # Create a completed import (not sync) job
        job = CloudImportJob(
            connection_id=conn.id,
            user_id=1,
            source_path="/src",
            destination_path="/dst",
            job_type="import",
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        db_session.commit()

        result = CloudSyncScheduler.run_sync(db_session)
        assert result == {"synced": 0, "errors": 0}

    @patch("app.services.cloud.import_job.CloudImportJobService")
    def test_resyncs_completed_jobs(self, mock_job_service_cls, db_session: Session):
        conn = _create_connection(db_session)
        _create_completed_sync_job(db_session, conn.id)

        # Mock the job service
        mock_service = MagicMock()
        mock_job_service_cls.return_value = mock_service

        # start_import returns a new job
        new_job = MagicMock()
        new_job.id = 999
        new_job.status = "completed"
        mock_service.start_import.return_value = new_job

        # execute_import is async, we need to mock the event loop
        mock_service.execute_import = AsyncMock()

        # db.refresh(new_job) would fail on a MagicMock, so patch it
        original_refresh = db_session.refresh

        def _safe_refresh(obj, *args, **kwargs):
            if isinstance(obj, MagicMock):
                return
            original_refresh(obj, *args, **kwargs)

        with patch.object(db_session, "refresh", side_effect=_safe_refresh):
            result = CloudSyncScheduler.run_sync(db_session)
        assert result["synced"] == 1
        assert result["errors"] == 0
        mock_service.start_import.assert_called_once()

    @patch("app.services.cloud.import_job.CloudImportJobService")
    def test_handles_sync_errors(self, mock_job_service_cls, db_session: Session):
        conn = _create_connection(db_session)
        _create_completed_sync_job(db_session, conn.id)

        mock_service = MagicMock()
        mock_job_service_cls.return_value = mock_service
        mock_service.start_import.side_effect = Exception("Cloud API error")

        result = CloudSyncScheduler.run_sync(db_session)
        assert result["synced"] == 0
        assert result["errors"] == 1

    def test_deduplicates_by_connection(self, db_session: Session):
        """Multiple completed sync jobs for same connection should only resync once."""
        conn = _create_connection(db_session)
        _create_completed_sync_job(db_session, conn.id)
        _create_completed_sync_job(db_session, conn.id)

        with patch("app.services.cloud.import_job.CloudImportJobService") as mock_cls:
            mock_service = MagicMock()
            mock_cls.return_value = mock_service
            new_job = MagicMock()
            new_job.id = 1
            new_job.status = "completed"
            mock_service.start_import.return_value = new_job
            mock_service.execute_import = AsyncMock()

            result = CloudSyncScheduler.run_sync(db_session)
            # Should only call start_import once despite two completed jobs
            assert mock_service.start_import.call_count == 1
