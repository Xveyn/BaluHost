"""Tests for backup service."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.backup import Backup
from app.schemas.backup import BackupCreate
from app.services.backup import BackupService


@pytest.fixture
def backup_service(db_session: Session):
    """Create a backup service instance with test database."""
    return BackupService(db_session)


@pytest.fixture
def temp_backup_dir():
    """Create a temporary directory for backups."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


def test_create_backup_success(backup_service: BackupService, temp_backup_dir: Path, db_session: Session):
    """Test successful backup creation."""
    # Mock backup directory
    with patch.object(backup_service, 'backup_dir', temp_backup_dir):
        # Mock _get_database_path to return a temp file
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            tmp_db.write(b'test database content')
            tmp_db_path = Path(tmp_db.name)
        
        try:
            with patch.object(backup_service, '_get_database_path', return_value=tmp_db_path):
                # Mock storage path
                with tempfile.TemporaryDirectory() as tmp_storage:
                    storage_path = Path(tmp_storage)
                    test_file = storage_path / "test.txt"
                    test_file.write_text("test content")
                    
                    with patch('app.services.backup.settings') as mock_settings:
                        mock_settings.nas_storage_path = str(storage_path)
                        mock_settings.nas_backup_max_count = 10
                        mock_settings.nas_backup_retention_days = 30
                        
                        # Create backup
                        backup_data = BackupCreate(
                            backup_type="full",
                            includes_database=True,
                            includes_files=True,
                            includes_config=False
                        )
                        
                        backup = backup_service.create_backup(
                            backup_data=backup_data,
                            creator_id=1,
                            creator_username="test_user"
                        )
                        
                        # Assertions
                        assert backup.status == "completed"
                        assert backup.backup_type == "full"
                        assert backup.size_bytes > 0
                        assert backup.includes_database is True
                        assert backup.includes_files is True
                        assert backup.includes_config is False
                        assert backup.creator_id == 1
                        
                        # Check file exists
                        backup_file = Path(backup.filepath)
                        assert backup_file.exists()
                        assert backup_file.suffix == ".gz"
        finally:
            # Cleanup
            if tmp_db_path.exists():
                tmp_db_path.unlink()


def test_list_backups(backup_service: BackupService, db_session: Session):
    """Test listing backups."""
    # Create test backups directly in database
    backup1 = Backup(
        filename="backup_1.tar.gz",
        filepath="/tmp/backup_1.tar.gz",
        size_bytes=1000,
        backup_type="full",
        status="completed",
        creator_id=1,
        includes_database=True,
        includes_files=True,
        includes_config=False
    )
    backup2 = Backup(
        filename="backup_2.tar.gz",
        filepath="/tmp/backup_2.tar.gz",
        size_bytes=2000,
        backup_type="full",
        status="completed",
        creator_id=1,
        includes_database=True,
        includes_files=False,
        includes_config=False
    )
    
    db_session.add(backup1)
    db_session.add(backup2)
    db_session.commit()
    
    # List backups
    backups = backup_service.list_backups()
    
    assert len(backups) == 2
    assert backups[0].filename == "backup_2.tar.gz"  # Newest first
    assert backups[1].filename == "backup_1.tar.gz"


def test_get_backup_by_id(backup_service: BackupService, db_session: Session):
    """Test getting backup by ID."""
    # Create test backup
    backup = Backup(
        filename="backup_test.tar.gz",
        filepath="/tmp/backup_test.tar.gz",
        size_bytes=1000,
        backup_type="full",
        status="completed",
        creator_id=1,
        includes_database=True,
        includes_files=True,
        includes_config=False
    )
    db_session.add(backup)
    db_session.commit()
    db_session.refresh(backup)
    
    # Get backup
    found_backup = backup_service.get_backup_by_id(backup.id)
    
    assert found_backup is not None
    assert found_backup.id == backup.id
    assert found_backup.filename == "backup_test.tar.gz"
    
    # Test non-existent backup
    not_found = backup_service.get_backup_by_id(99999)
    assert not_found is None


def test_delete_backup(backup_service: BackupService, temp_backup_dir: Path, db_session: Session):
    """Test deleting a backup."""
    # Create a test backup file
    backup_file = temp_backup_dir / "backup_delete.tar.gz"
    backup_file.write_text("test backup content")
    
    # Create backup record
    backup = Backup(
        filename="backup_delete.tar.gz",
        filepath=str(backup_file),
        size_bytes=100,
        backup_type="full",
        status="completed",
        creator_id=1,
        includes_database=True,
        includes_files=True,
        includes_config=False
    )
    db_session.add(backup)
    db_session.commit()
    db_session.refresh(backup)
    
    # Delete backup
    success = backup_service.delete_backup(backup.id, "test_user")
    
    assert success is True
    assert not backup_file.exists()
    
    # Verify database record is deleted
    deleted_backup = db_session.query(Backup).filter(Backup.id == backup.id).first()
    assert deleted_backup is None


def test_delete_nonexistent_backup(backup_service: BackupService):
    """Test deleting a non-existent backup."""
    success = backup_service.delete_backup(99999, "test_user")
    assert success is False


def test_backup_cleanup_old_backups(backup_service: BackupService, temp_backup_dir: Path, db_session: Session):
    """Test cleanup of old backups based on retention policy."""
    from datetime import datetime, timedelta
    
    # Mock settings
    with patch('app.services.backup.settings') as mock_settings:
        mock_settings.nas_backup_max_count = 3
        mock_settings.nas_backup_retention_days = 7
        
        # Create 5 old backups
        for i in range(5):
            backup_file = temp_backup_dir / f"backup_{i}.tar.gz"
            backup_file.write_text(f"backup {i}")
            
            backup = Backup(
                filename=f"backup_{i}.tar.gz",
                filepath=str(backup_file),
                size_bytes=100,
                backup_type="full",
                status="completed",
                creator_id=1,
                includes_database=True,
                includes_files=True,
                includes_config=False
            )
            # Make some backups older
            if i < 2:
                backup.created_at = datetime.now() - timedelta(days=10)
            
            db_session.add(backup)
        
        db_session.commit()
        
        # Cleanup should be called automatically during backup creation
        with patch.object(backup_service, 'backup_dir', temp_backup_dir):
            backup_service._cleanup_old_backups()
        
        # Check that old backups were removed
        remaining_backups = db_session.query(Backup).all()
        assert len(remaining_backups) <= 3


def test_create_backup_handles_errors(backup_service: BackupService, temp_backup_dir: Path, db_session: Session):
    """Test that backup creation handles errors gracefully."""
    with patch.object(backup_service, 'backup_dir', temp_backup_dir):
        # Mock _get_database_path to raise an error
        with patch.object(backup_service, '_get_database_path', side_effect=ValueError("Test error")):
            backup_data = BackupCreate(
                backup_type="full",
                includes_database=True,
                includes_files=True,
                includes_config=False
            )
            
            with pytest.raises(ValueError):
                backup_service.create_backup(
                    backup_data=backup_data,
                    creator_id=1,
                    creator_username="test_user"
                )
            
            # Check that backup record was marked as failed
            failed_backup = db_session.query(Backup).filter(Backup.status == "failed").first()
            assert failed_backup is not None
            assert failed_backup.error_message == "Test error"


def test_download_backup(backup_service: BackupService, temp_backup_dir: Path, db_session: Session):
    """Test getting backup file path for download."""
    # Create backup file
    backup_file = temp_backup_dir / "backup_download.tar.gz"
    backup_file.write_text("test content")
    
    # Create backup record
    backup = Backup(
        filename="backup_download.tar.gz",
        filepath=str(backup_file),
        size_bytes=100,
        backup_type="full",
        status="completed",
        creator_id=1,
        includes_database=True,
        includes_files=True,
        includes_config=False
    )
    db_session.add(backup)
    db_session.commit()
    db_session.refresh(backup)
    
    # Get download path
    download_path = backup_service.download_backup(backup.id)
    
    assert download_path is not None
    assert download_path == backup_file
    assert download_path.exists()
    
    # Test non-existent backup
    no_path = backup_service.download_backup(99999)
    assert no_path is None
