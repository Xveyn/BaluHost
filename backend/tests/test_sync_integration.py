"""
Integration Tests for Sync System
Tests complete sync workflows including login, device registration, and file operations.
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil
from httpx import AsyncClient
from fastapi import status
from app.main import app
from app.core.database import get_db, engine, Base
from app.models.user import User
from app.models.device import Device
from app.models.file_metadata import FileMetadata
from sqlalchemy.orm import Session
import hashlib
import time


@pytest.fixture(scope="function")
async def async_client():
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="function")
def temp_storage():
    """Create temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")
def test_user_credentials():
    """Test user credentials."""
    return {
        "username": "sync_test_user",
        "password": "sync_test_pass123",
        "email": "sync_test@example.com"
    }


class TestSyncIntegration:
    """Integration tests for complete sync workflows."""
    
    @pytest.mark.asyncio
    async def test_complete_sync_workflow(self, async_client: AsyncClient, test_user_credentials):
        """Test complete sync workflow: register -> login -> device -> upload -> download."""
        
        # 1. Register user
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": test_user_credentials["username"],
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        assert response.status_code == status.HTTP_201_CREATED
        
        # 2. Login
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": test_user_credentials["username"],
                "password": test_user_credentials["password"]
            }
        )
        assert response.status_code == status.HTTP_200_OK
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Register device
        response = await async_client.post(
            "/api/sync/devices",
            json={
                "name": "test_device",
                "device_type": "desktop"
            },
            headers=headers
        )
        assert response.status_code == status.HTTP_201_CREATED
        device_id = response.json()["device_id"]
        
        # 4. Upload file
        test_content = b"Test sync file content"
        test_hash = hashlib.sha256(test_content).hexdigest()
        
        response = await async_client.post(
            "/api/files/upload",
            files={
                "file": ("test_sync.txt", test_content, "text/plain")
            },
            data={
                "path": "/sync_test/test_sync.txt"
            },
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        
        # 5. Get sync state
        response = await async_client.get(
            "/api/sync/state",
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        sync_state = response.json()
        assert len(sync_state["files"]) > 0
        
        # 6. Download file
        response = await async_client.get(
            "/api/files/download/sync_test/test_sync.txt",
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.content == test_content
        
        # 7. Update file
        updated_content = b"Updated sync file content"
        response = await async_client.post(
            "/api/files/upload",
            files={
                "file": ("test_sync.txt", updated_content, "text/plain")
            },
            data={
                "path": "/sync_test/test_sync.txt"
            },
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        
        # 8. Verify update in sync state
        response = await async_client.get(
            "/api/sync/state",
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        sync_state = response.json()
        file_entry = next(f for f in sync_state["files"] if f["path"] == "/sync_test/test_sync.txt")
        assert file_entry["sha256"] != test_hash
        
        # 9. Delete file
        response = await async_client.delete(
            "/api/files/delete",
            json={"path": "/sync_test/test_sync.txt"},
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        
        # 10. Verify deletion
        response = await async_client.get(
            "/api/sync/state",
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        sync_state = response.json()
        file_exists = any(f["path"] == "/sync_test/test_sync.txt" for f in sync_state["files"])
        assert not file_exists
    
    @pytest.mark.asyncio
    async def test_multiple_device_sync(self, async_client: AsyncClient, test_user_credentials):
        """Test sync across multiple devices."""
        
        # Register and login
        await async_client.post("/api/auth/register", json={
            "username": test_user_credentials["username"],
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        })
        
        response = await async_client.post("/api/auth/login", json={
            "username": test_user_credentials["username"],
            "password": test_user_credentials["password"]
        })
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Register device 1 (desktop)
        response = await async_client.post(
            "/api/sync/devices",
            json={"name": "desktop", "device_type": "desktop"},
            headers=headers
        )
        device1_id = response.json()["device_id"]
        
        # Register device 2 (mobile)
        response = await async_client.post(
            "/api/sync/devices",
            json={"name": "mobile", "device_type": "mobile"},
            headers=headers
        )
        device2_id = response.json()["device_id"]
        
        # Upload from device 1
        test_content = b"Multi-device sync test"
        response = await async_client.post(
            "/api/files/upload",
            files={"file": ("device1_file.txt", test_content, "text/plain")},
            data={"path": "/multi_device/device1_file.txt"},
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Both devices should see the file in sync state
        response = await async_client.get("/api/sync/state", headers=headers)
        sync_state = response.json()
        assert any(f["path"] == "/multi_device/device1_file.txt" for f in sync_state["files"])
        
        # Verify device list
        response = await async_client.get("/api/sync/devices", headers=headers)
        devices = response.json()
        assert len(devices) == 2
        device_names = [d["name"] for d in devices]
        assert "desktop" in device_names
        assert "mobile" in device_names
    
    @pytest.mark.asyncio
    async def test_folder_sync(self, async_client: AsyncClient, test_user_credentials):
        """Test syncing entire folder structure."""
        
        # Setup user
        await async_client.post("/api/auth/register", json={
            "username": test_user_credentials["username"],
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        })
        
        response = await async_client.post("/api/auth/login", json={
            "username": test_user_credentials["username"],
            "password": test_user_credentials["password"]
        })
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        await async_client.post(
            "/api/sync/devices",
            json={"name": "test_device", "device_type": "desktop"},
            headers=headers
        )
        
        # Create folder structure
        files_to_create = [
            "/folder_test/file1.txt",
            "/folder_test/subfolder/file2.txt",
            "/folder_test/subfolder/deep/file3.txt",
        ]
        
        for file_path in files_to_create:
            # Create directories first
            parts = file_path.split('/')[1:-1]  # Skip empty first and filename
            for i in range(1, len(parts) + 1):
                dir_path = '/' + '/'.join(parts[:i])
                await async_client.post(
                    "/api/files/mkdir",
                    json={"path": dir_path},
                    headers=headers
                )
            
            # Upload file
            response = await async_client.post(
                "/api/files/upload",
                files={"file": (Path(file_path).name, b"test content", "text/plain")},
                data={"path": file_path},
                headers=headers
            )
            assert response.status_code == status.HTTP_200_OK
        
        # Verify all files in sync state
        response = await async_client.get("/api/sync/state", headers=headers)
        sync_state = response.json()
        
        for file_path in files_to_create:
            assert any(f["path"] == file_path for f in sync_state["files"]), \
                f"File {file_path} not found in sync state"
    
    @pytest.mark.asyncio
    async def test_conflict_detection(self, async_client: AsyncClient, test_user_credentials):
        """Test conflict detection when file is modified on multiple devices."""
        
        # Setup
        await async_client.post("/api/auth/register", json={
            "username": test_user_credentials["username"],
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        })
        
        response = await async_client.post("/api/auth/login", json={
            "username": test_user_credentials["username"],
            "password": test_user_credentials["password"]
        })
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        await async_client.post(
            "/api/sync/devices",
            json={"name": "test_device", "device_type": "desktop"},
            headers=headers
        )
        
        # Upload initial file
        initial_content = b"Initial version"
        response = await async_client.post(
            "/api/files/upload",
            files={"file": ("conflict_test.txt", initial_content, "text/plain")},
            data={"path": "/conflict/conflict_test.txt"},
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Get initial state
        response = await async_client.get("/api/sync/state", headers=headers)
        initial_state = response.json()
        initial_file = next(f for f in initial_state["files"] if f["path"] == "/conflict/conflict_test.txt")
        initial_hash = initial_file["sha256"]
        initial_modified = initial_file["modified_at"]
        
        # Simulate waiting a bit
        await asyncio.sleep(0.1)
        
        # Upload modified version
        modified_content = b"Modified version"
        response = await async_client.post(
            "/api/files/upload",
            files={"file": ("conflict_test.txt", modified_content, "text/plain")},
            data={"path": "/conflict/conflict_test.txt"},
            headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Verify modification was detected
        response = await async_client.get("/api/sync/state", headers=headers)
        updated_state = response.json()
        updated_file = next(f for f in updated_state["files"] if f["path"] == "/conflict/conflict_test.txt")
        
        assert updated_file["sha256"] != initial_hash
        assert updated_file["modified_at"] != initial_modified
    
    @pytest.mark.asyncio
    async def test_sync_with_deletes(self, async_client: AsyncClient, test_user_credentials):
        """Test sync handles file deletions correctly."""
        
        # Setup
        await async_client.post("/api/auth/register", json={
            "username": test_user_credentials["username"],
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        })
        
        response = await async_client.post("/api/auth/login", json={
            "username": test_user_credentials["username"],
            "password": test_user_credentials["password"]
        })
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        await async_client.post(
            "/api/sync/devices",
            json={"name": "test_device", "device_type": "desktop"},
            headers=headers
        )
        
        # Create multiple files
        files = [f"/delete_test/file{i}.txt" for i in range(5)]
        for file_path in files:
            response = await async_client.post(
                "/api/files/upload",
                files={"file": (Path(file_path).name, b"test", "text/plain")},
                data={"path": file_path},
                headers=headers
            )
            assert response.status_code == status.HTTP_200_OK
        
        # Verify all files exist
        response = await async_client.get("/api/sync/state", headers=headers)
        sync_state = response.json()
        assert len([f for f in sync_state["files"] if f["path"].startswith("/delete_test")]) == 5
        
        # Delete some files
        for file_path in files[:3]:
            response = await async_client.delete(
                "/api/files/delete",
                json={"path": file_path},
                headers=headers
            )
            assert response.status_code == status.HTTP_200_OK
        
        # Verify deletions in sync state
        response = await async_client.get("/api/sync/state", headers=headers)
        sync_state = response.json()
        remaining_files = [f for f in sync_state["files"] if f["path"].startswith("/delete_test")]
        assert len(remaining_files) == 2
        
        remaining_paths = [f["path"] for f in remaining_files]
        assert "/delete_test/file3.txt" in remaining_paths
        assert "/delete_test/file4.txt" in remaining_paths


class TestSyncPerformance:
    """Performance tests for sync operations."""
    
    @pytest.mark.asyncio
    async def test_sync_state_performance(self, async_client: AsyncClient, test_user_credentials):
        """Test sync state retrieval performance with many files."""
        
        # Setup
        await async_client.post("/api/auth/register", json={
            "username": test_user_credentials["username"],
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        })
        
        response = await async_client.post("/api/auth/login", json={
            "username": test_user_credentials["username"],
            "password": test_user_credentials["password"]
        })
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        await async_client.post(
            "/api/sync/devices",
            json={"name": "test_device", "device_type": "desktop"},
            headers=headers
        )
        
        # Create many files
        num_files = 50
        for i in range(num_files):
            await async_client.post(
                "/api/files/upload",
                files={"file": (f"file{i}.txt", b"test content", "text/plain")},
                data={"path": f"/perf_test/file{i}.txt"},
                headers=headers
            )
        
        # Measure sync state retrieval time
        start_time = time.time()
        response = await async_client.get("/api/sync/state", headers=headers)
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        sync_state = response.json()
        assert len([f for f in sync_state["files"] if f["path"].startswith("/perf_test")]) == num_files
        
        # Should complete within reasonable time (< 2 seconds for 50 files)
        elapsed = end_time - start_time
        assert elapsed < 2.0, f"Sync state retrieval took {elapsed:.2f}s, expected < 2.0s"
    
    @pytest.mark.asyncio
    async def test_batch_upload_performance(self, async_client: AsyncClient, test_user_credentials):
        """Test performance of uploading multiple files."""
        
        # Setup
        await async_client.post("/api/auth/register", json={
            "username": test_user_credentials["username"],
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        })
        
        response = await async_client.post("/api/auth/login", json={
            "username": test_user_credentials["username"],
            "password": test_user_credentials["password"]
        })
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Measure batch upload time
        num_files = 20
        start_time = time.time()
        
        for i in range(num_files):
            response = await async_client.post(
                "/api/files/upload",
                files={"file": (f"batch{i}.txt", b"batch test content", "text/plain")},
                data={"path": f"/batch_test/batch{i}.txt"},
                headers=headers
            )
            assert response.status_code == status.HTTP_200_OK
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Should average less than 200ms per file
        avg_per_file = elapsed / num_files
        assert avg_per_file < 0.2, f"Average upload time {avg_per_file:.3f}s per file, expected < 0.2s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
