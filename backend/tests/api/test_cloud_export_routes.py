"""Tests for cloud export API routes."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cloud import CloudConnection
from app.models.cloud_export import CloudExportJob


@pytest.fixture
def admin_token(client: TestClient) -> str:
    """Login as admin and return the raw access token."""
    resp = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _create_connection(db: Session, user_id: int = 1) -> CloudConnection:
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


def _create_export_job(
    db: Session, conn_id: int, user_id: int = 1, status: str = "ready"
) -> CloudExportJob:
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
        share_link="https://drive.google.com/mock" if status == "ready" else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


class TestCloudExportRoutes:
    def test_list_exports_empty(self, client: TestClient, admin_token: str):
        resp = client.get(
            "/api/cloud-export/jobs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_exports_with_jobs(
        self, client: TestClient, admin_token: str, db_session: Session
    ):
        conn = _create_connection(db_session, user_id=1)
        _create_export_job(db_session, conn.id, user_id=1)

        resp = client.get(
            "/api/cloud-export/jobs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["file_name"] == "test.txt"

    def test_get_export_status(
        self, client: TestClient, admin_token: str, db_session: Session
    ):
        conn = _create_connection(db_session, user_id=1)
        job = _create_export_job(db_session, conn.id)

        resp = client.get(
            f"/api/cloud-export/jobs/{job.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_get_export_status_not_found(self, client: TestClient, admin_token: str):
        resp = client.get(
            "/api/cloud-export/jobs/999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_get_statistics(self, client: TestClient, admin_token: str, db_session: Session):
        conn = _create_connection(db_session, user_id=1)
        _create_export_job(db_session, conn.id, status="ready")
        _create_export_job(db_session, conn.id, status="failed")

        resp = client.get(
            "/api/cloud-export/statistics",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_exports"] == 2
        assert stats["active_exports"] == 1
        assert stats["failed_exports"] == 1

    def test_revoke_export(self, client: TestClient, admin_token: str, db_session: Session):
        conn = _create_connection(db_session, user_id=1)
        job = _create_export_job(db_session, conn.id, status="ready")

        resp = client.post(
            f"/api/cloud-export/jobs/{job.id}/revoke",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_retry_export(self, client: TestClient, admin_token: str, db_session: Session):
        conn = _create_connection(db_session, user_id=1)
        job = _create_export_job(db_session, conn.id, status="failed")

        resp = client.post(
            f"/api/cloud-export/jobs/{job.id}/retry",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.get("/api/cloud-export/jobs")
        assert resp.status_code in (401, 403)
