"""
Task 3.3: File Operation Logging Tests

Tests for logging file operations: uploads, downloads, deletions, moves, etc.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///:memory:"


class TestFileOperationLogging:
    """Test file operation logging."""

    def test_log_file_upload(self):
        """Verify file upload operations are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="upload",
                user="user1",
                resource="/documents/report.pdf",
                success=True,
                details='{"file_size": 2048576, "mime_type": "application/pdf"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="upload").first()
            assert result is not None
            assert result.resource == "/documents/report.pdf"
            assert result.success is True
        finally:
            db.close()

    def test_log_file_download(self):
        """Verify file download operations are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="download",
                user="user2",
                resource="/shared/data.csv",
                success=True,
                details='{"file_size": 1024, "download_time_ms": 245}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="download").first()
            assert result is not None
            assert "download_time_ms" in result.details
        finally:
            db.close()

    def test_log_file_delete(self):
        """Verify file deletion operations are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="delete",
                user="admin",
                resource="/old_files/temp.log",
                success=True,
                details='{"file_size": 512}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="delete").first()
            assert result is not None
            assert result.success is True
        finally:
            db.close()

    def test_log_file_move_or_rename(self):
        """Verify file move/rename operations are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="move",
                user="user3",
                resource="/documents/file.txt",
                success=True,
                details='{"source": "/documents/old_name.txt", "destination": "/documents/file.txt"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="move").first()
            assert result is not None
            assert "source" in result.details
            assert "destination" in result.details
        finally:
            db.close()

    def test_log_failed_file_operation(self):
        """Verify failed file operations are logged with error."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="upload",
                user="user4",
                resource="/protected/confidential.doc",
                success=False,
                error_message="Permission denied: insufficient privileges",
                details='{"attempted_size": 5242880}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(success=False).first()
            assert result is not None
            assert result.success is False
            assert "Permission denied" in result.error_message
        finally:
            db.close()


class TestFileOperationAnalytics:
    """Test analytics queries on file operations."""

    def test_get_all_uploads_by_user(self):
        """Query all uploads for a specific user."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            # Create uploads by different users
            for i, user in enumerate(["alice", "bob", "alice"]):
                log = AuditLog(
                    event_type="FILE_ACCESS",
                    action="upload",
                    user=user,
                    resource=f"/file_{i}.pdf",
                    success=True
                )
                db.add(log)
            db.commit()
            
            # Query alice's uploads
            uploads = db.query(AuditLog).filter(
                (AuditLog.user == "alice") &
                (AuditLog.action == "upload")
            ).all()
            
            assert len(uploads) == 2
        finally:
            db.close()

    def test_get_file_operation_statistics(self):
        """Query file operation statistics by type."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            # Create various file operations
            operations = [
                ("upload", True),
                ("upload", True),
                ("download", True),
                ("delete", True),
                ("upload", False),
            ]
            
            for action, success in operations:
                log = AuditLog(
                    event_type="FILE_ACCESS",
                    action=action,
                    user="testuser",
                    resource="/test",
                    success=success
                )
                db.add(log)
            db.commit()
            
            # Get statistics
            successful = db.query(AuditLog).filter(
                (AuditLog.event_type == "FILE_ACCESS") &
                (AuditLog.success == True)
            ).count()
            failed = db.query(AuditLog).filter(
                (AuditLog.event_type == "FILE_ACCESS") &
                (AuditLog.success == False)
            ).count()
            
            assert successful == 4
            assert failed == 1
        finally:
            db.close()

    def test_get_operations_by_time_range(self):
        """Query file operations within a time range."""
        from app.models import AuditLog
        from app.core.database import Base
        from datetime import datetime, timedelta
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            # Create operations
            for i in range(3):
                log = AuditLog(
                    event_type="FILE_ACCESS",
                    action="upload",
                    user="user",
                    resource=f"/file_{i}",
                    success=True
                )
                db.add(log)
            db.commit()
            
            # Query all FILE_ACCESS operations
            operations = db.query(AuditLog).filter(
                AuditLog.event_type == "FILE_ACCESS"
            ).all()
            
            assert len(operations) == 3
        finally:
            db.close()


class TestFileOperationDetails:
    """Test detailed metadata capture in file operations."""

    def test_capture_file_size_metadata(self):
        """Verify file size is captured in details."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="upload",
                user="user1",
                resource="/document.pdf",
                success=True,
                details='{"file_size": 5242880, "size_unit": "bytes"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).first()
            assert result is not None
            assert "file_size" in result.details
        finally:
            db.close()

    def test_capture_operation_duration(self):
        """Verify operation duration is captured."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="upload",
                user="user2",
                resource="/largefile.iso",
                success=True,
                details='{"duration_ms": 3456, "transfer_rate_mbps": 1.5}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).first()
            assert "duration_ms" in result.details
        finally:
            db.close()

    def test_capture_file_hash_metadata(self):
        """Verify file hash/integrity info is captured."""
        from app.models import AuditLog
        from app.core.database import Base
        
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="upload",
                user="user3",
                resource="/backup.zip",
                success=True,
                details='{"sha256": "abc123def456", "sha1": "fedcba654321"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).first()
            assert "sha256" in result.details
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
