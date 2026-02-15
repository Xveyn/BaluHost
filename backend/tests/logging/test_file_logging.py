"""Tests for audit logging integration with file operations."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.user import UserPublic
from datetime import datetime, timezone
from app.services import files


@pytest.fixture
def mock_user():
    """Create a mock user."""
    return UserPublic(
        id=123,
        username="testuser",
        email="test@example.com",
        role="user",
        is_active=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def mock_admin():
    """Create a mock admin user."""
    return UserPublic(
        id=1,
        username="admin",
        email="admin@example.com",
        role="admin",
        is_active=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('app.services.files.ROOT_DIR', Path(tmpdir)):
            with patch('app.services.files.settings') as mock_settings:
                mock_settings.nas_storage_path = tmpdir
                mock_settings.nas_quota_bytes = None
                yield Path(tmpdir)


class TestFileOperationLogging:
    """Test audit logging for file operations."""
    
    @pytest.mark.asyncio
    async def test_upload_logs_audit_event(self, temp_storage, mock_user):
        """Test that file upload creates audit log entry."""
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Create mock upload file
            from fastapi import UploadFile
            from io import BytesIO
            
            test_data = b"test file content"
            mock_file = UploadFile(
                filename="test.txt",
                file=BytesIO(test_data)
            )
            
            # Perform upload
            await files.save_uploads("", [mock_file], mock_user)
            
            # Verify audit log was called
            mock_logger.log_file_access.assert_called_once()
            call_kwargs = mock_logger.log_file_access.call_args[1]
            
            assert call_kwargs["user"] == "testuser"
            assert call_kwargs["action"] == "upload"
            assert call_kwargs["file_path"] == "test.txt"
            assert call_kwargs["size_bytes"] == len(test_data)
            assert call_kwargs["success"] is True
    
    def test_delete_file_logs_audit_event(self, temp_storage, mock_user):
        """Test that file deletion creates audit log entry."""
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Create a test file
            test_file = temp_storage / "test.txt"
            test_file.write_text("test content")
            
            # Set up metadata
            with patch('app.services.files.get_owner', return_value=123):
                # Perform deletion
                files.delete_path("test.txt", mock_user)
            
            # Verify audit log was called
            mock_logger.log_file_access.assert_called_once()
            call_kwargs = mock_logger.log_file_access.call_args[1]
            
            assert call_kwargs["user"] == "testuser"
            assert call_kwargs["action"] == "delete"
            assert call_kwargs["file_path"] == "test.txt"
            assert call_kwargs["is_directory"] is False
            assert call_kwargs["success"] is True
    
    def test_delete_directory_logs_audit_event(self, temp_storage, mock_user):
        """Test that directory deletion creates audit log entry."""
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Create a test directory
            test_dir = temp_storage / "testdir"
            test_dir.mkdir()
            
            # Set up metadata
            with patch('app.services.files.get_owner', return_value=123):
                # Perform deletion
                files.delete_path("testdir", mock_user)
            
            # Verify audit log was called
            call_kwargs = mock_logger.log_file_access.call_args[1]
            assert call_kwargs["is_directory"] is True
    
    def test_create_folder_logs_audit_event(self, temp_storage, mock_user):
        """Test that folder creation creates audit log entry."""
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Create folder
            files.create_folder("", "newfolder", mock_user)
            
            # Verify audit log was called
            mock_logger.log_file_access.assert_called_once()
            call_kwargs = mock_logger.log_file_access.call_args[1]
            
            assert call_kwargs["user"] == "testuser"
            assert call_kwargs["action"] == "create_folder"
            assert call_kwargs["file_path"] == "newfolder"
            assert call_kwargs["success"] is True
    
    def test_move_path_logs_audit_event(self, temp_storage, mock_user):
        """Test that moving files/folders creates audit log entry."""
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Create source file
            source = temp_storage / "source.txt"
            source.write_text("test")
            
            # Set up metadata
            with patch('app.services.files.get_owner', return_value=123):
                # Perform move
                files.move_path("source.txt", "target.txt", mock_user)
            
            # Verify audit log was called
            mock_logger.log_file_access.assert_called_once()
            call_kwargs = mock_logger.log_file_access.call_args[1]
            
            assert call_kwargs["user"] == "testuser"
            assert call_kwargs["action"] == "move"
            assert call_kwargs["file_path"] == "source.txt"
            assert call_kwargs["target_path"] == "target.txt"
            assert call_kwargs["success"] is True
    
    def test_system_operations_log_as_system_user(self, temp_storage):
        """Test that operations without user log as system."""
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Create folder without user
            files.create_folder("", "systemfolder", owner=None)
            
            # Verify audit log was called with system user
            call_kwargs = mock_logger.log_file_access.call_args[1]
            assert call_kwargs["user"] == "system"
    
    @pytest.mark.asyncio
    async def test_multiple_uploads_log_multiple_entries(self, temp_storage, mock_user):
        """Test that multiple file uploads create multiple audit entries."""
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            from fastapi import UploadFile
            from io import BytesIO
            
            # Create multiple mock upload files
            files_to_upload = []
            for i in range(3):
                mock_file = UploadFile(
                    filename=f"test{i}.txt",
                    file=BytesIO(f"content {i}".encode())
                )
                files_to_upload.append(mock_file)
            
            # Perform upload
            await files.save_uploads("", files_to_upload, mock_user)
            
            # Verify audit log was called 3 times
            assert mock_logger.log_file_access.call_count == 3
    
    def test_audit_logging_disabled_in_dev_mode(self, temp_storage, mock_user):
        """Test that audit logging respects dev mode setting."""
        # In dev mode, audit logger should still be called but won't write to disk
        with patch('app.services.files.get_audit_logger_db') as mock_audit, \
             patch('app.services.file_metadata_db.create_metadata') as mock_create, \
             patch('app.services.file_metadata_db.update_metadata') as mock_update:
            mock_logger = MagicMock()
            mock_logger.is_enabled.return_value = False
            mock_audit.return_value = mock_logger
            
            # Create folder
            files.create_folder("", "testfolder", mock_user)
            
            # Audit logger should still be called
            mock_logger.log_file_access.assert_called_once()
