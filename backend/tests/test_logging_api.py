"""Test logging API endpoints."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAS_MODE", "dev")

from app.main import create_app
from scripts.reset_dev_storage import reset_dev_storage


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client using the in-memory test DB session."""
    reset_dev_storage()
    app = create_app()

    # Override DB dependency to use test session
    from app.core.database import get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Ensure admin user exists in test DB
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    if not user_service.get_user_by_username("admin", db=db_session):
        user_service.create_user(UserCreate(username="admin", email="admin@example.com", password="changeme", role="admin"), db=db_session)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    reset_dev_storage()


@pytest.fixture
def auth_headers(client):
    """Get authentication headers."""
    # Login as admin (created by ensure_admin_user during app startup)
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "changeme"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestLoggingAPI:
    """Test logging API endpoints."""
    
    def test_get_disk_io_logs(self, client, auth_headers):
        """Test getting disk I/O logs."""
        response = client.get("/api/logging/disk-io", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "dev_mode" in data
        assert "disks" in data
        assert isinstance(data["disks"], dict)
        
        # In dev mode, should have mock data
        if data["dev_mode"]:
            assert len(data["disks"]) > 0
            for disk_name, samples in data["disks"].items():
                assert isinstance(samples, list)
                if len(samples) > 0:
                    sample = samples[0]
                    assert "timestamp" in sample
                    assert "readMbps" in sample
                    assert "writeMbps" in sample
                    assert "readIops" in sample
                    assert "writeIops" in sample
    
    def test_get_disk_io_logs_with_time_range(self, client, auth_headers):
        """Test getting disk I/O logs with custom time range."""
        response = client.get("/api/logging/disk-io?hours=6", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "disks" in data
    
    def test_get_file_access_logs(self, client, auth_headers):
        """Test getting file access logs."""
        response = client.get("/api/logging/file-access", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "dev_mode" in data
        assert "total" in data
        assert "logs" in data
        assert isinstance(data["logs"], list)
        
        # In dev mode, should have mock data
        if data["dev_mode"]:
            assert data["total"] > 0
            assert len(data["logs"]) > 0
            
            log = data["logs"][0]
            assert "timestamp" in log
            assert "event_type" in log
            assert "user" in log
            assert "action" in log
            assert "resource" in log
            assert "success" in log
    
    def test_get_file_access_logs_with_filters(self, client, auth_headers):
        """Test getting file access logs with filters."""
        response = client.get(
            "/api/logging/file-access?limit=50&days=2&action=read",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["logs"]) <= 50
        
        # Verify filter is applied
        for log in data["logs"]:
            if not data["dev_mode"]:  # Only check in non-dev mode
                assert log["action"] == "read"
    
    def test_get_logging_stats(self, client, auth_headers):
        """Test getting logging statistics."""
        response = client.get("/api/logging/stats", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "dev_mode" in data
        assert "period_days" in data
        assert "file_access" in data
        
        file_access = data["file_access"]
        assert "total_operations" in file_access
        assert "by_action" in file_access
        assert "by_user" in file_access
        assert "success_rate" in file_access
        
        # In dev mode, should have mock disk_io stats
        if data["dev_mode"]:
            assert "disk_io" in data
            disk_io = data["disk_io"]
            assert "avg_read_mbps" in disk_io
            assert "avg_write_mbps" in disk_io
    
    def test_get_logging_stats_with_custom_period(self, client, auth_headers):
        """Test getting logging statistics with custom period."""
        response = client.get("/api/logging/stats?days=14", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["period_days"] == 14
    
    def test_unauthorized_access(self, client):
        """Test that unauthenticated requests are rejected."""
        response = client.get("/api/logging/disk-io")
        assert response.status_code == 401
        
        response = client.get("/api/logging/file-access")
        assert response.status_code == 401
        
        response = client.get("/api/logging/stats")
        assert response.status_code == 401
