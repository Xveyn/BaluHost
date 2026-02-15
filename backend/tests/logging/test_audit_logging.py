"""Tests for audit logging functionality."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.audit_logger import AuditLogger, get_audit_logger


class TestAuditLogger:
    """Test audit logging functionality."""
    
    @pytest.fixture
    def temp_audit_dir(self):
        """Create temporary directory for audit logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def audit_logger_enabled(self, temp_audit_dir):
        """Create audit logger with logging enabled."""
        with patch('app.services.audit_logger.settings') as mock_settings:
            mock_settings.is_dev_mode = False
            mock_settings.nas_temp_path = str(temp_audit_dir)
            logger = AuditLogger()
            yield logger
    
    @pytest.fixture
    def audit_logger_disabled(self, temp_audit_dir):
        """Create audit logger with logging disabled (dev mode)."""
        with patch('app.services.audit_logger.settings') as mock_settings:
            mock_settings.is_dev_mode = True
            mock_settings.nas_temp_path = str(temp_audit_dir)
            logger = AuditLogger()
            yield logger
    
    def test_audit_logger_enabled_in_prod_mode(self, audit_logger_enabled):
        """Test that audit logging is enabled in production mode."""
        assert audit_logger_enabled.is_enabled() is True
    
    def test_audit_logger_disabled_in_dev_mode(self, audit_logger_disabled):
        """Test that audit logging is disabled in dev mode."""
        assert audit_logger_disabled.is_enabled() is False
    
    def test_log_file_access_creates_entry(self, audit_logger_enabled, temp_audit_dir):
        """Test that file access logging creates audit log entry."""
        audit_logger_enabled.log_file_access(
            user="test_user",
            action="upload",
            file_path="/test/file.txt",
            size_bytes=1024,
            success=True
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        assert audit_file.exists()
        
        with open(audit_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())
        
        assert log_entry["event_type"] == "FILE_ACCESS"
        assert log_entry["user"] == "test_user"
        assert log_entry["action"] == "upload"
        assert log_entry["resource"] == "/test/file.txt"
        assert log_entry["success"] is True
        assert log_entry["details"]["size_bytes"] == 1024
    
    def test_log_file_access_with_error(self, audit_logger_enabled, temp_audit_dir):
        """Test logging failed file access."""
        audit_logger_enabled.log_file_access(
            user="test_user",
            action="delete",
            file_path="/test/file.txt",
            success=False,
            error_message="Permission denied"
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        with open(audit_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())
        
        assert log_entry["success"] is False
        assert log_entry["error"] == "Permission denied"
    
    def test_log_disk_monitor_event(self, audit_logger_enabled, temp_audit_dir):
        """Test disk monitor event logging."""
        disk_stats = {
            "PhysicalDrive0": {
                "avg_read_mbps": 10.5,
                "avg_write_mbps": 5.2
            }
        }
        
        audit_logger_enabled.log_disk_monitor(
            action="periodic_summary",
            details={"disks": disk_stats, "interval_seconds": 60}
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        with open(audit_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())
        
        assert log_entry["event_type"] == "DISK_MONITOR"
        assert log_entry["user"] == "system"
        assert log_entry["action"] == "periodic_summary"
        assert log_entry["details"]["disks"]["PhysicalDrive0"]["avg_read_mbps"] == 10.5
    
    def test_log_disk_monitor_error(self, audit_logger_enabled, temp_audit_dir):
        """Test disk monitor error logging."""
        audit_logger_enabled.log_disk_monitor(
            action="monitor_error",
            disk_name="PhysicalDrive0",
            success=False,
            error_message="Failed to read disk stats"
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        with open(audit_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())
        
        assert log_entry["success"] is False
        assert log_entry["resource"] == "PhysicalDrive0"
        assert log_entry["error"] == "Failed to read disk stats"
    
    def test_log_system_event(self, audit_logger_enabled, temp_audit_dir):
        """Test system event logging."""
        audit_logger_enabled.log_system_event(
            action="startup",
            user="admin",
            details={"version": "1.0.0"}
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        with open(audit_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())
        
        assert log_entry["event_type"] == "SYSTEM"
        assert log_entry["action"] == "startup"
        assert log_entry["user"] == "admin"
        assert log_entry["details"]["version"] == "1.0.0"
    
    def test_no_logging_in_dev_mode(self, audit_logger_disabled, temp_audit_dir):
        """Test that no logs are created in dev mode."""
        audit_logger_disabled.log_file_access(
            user="test_user",
            action="upload",
            file_path="/test/file.txt"
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        assert not audit_file.exists()
    
    def test_multiple_log_entries(self, audit_logger_enabled, temp_audit_dir):
        """Test multiple log entries are appended correctly."""
        for i in range(5):
            audit_logger_enabled.log_file_access(
                user=f"user_{i}",
                action="read",
                file_path=f"/file_{i}.txt"
            )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        with open(audit_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        assert len(lines) == 5
        
        for i, line in enumerate(lines):
            entry = json.loads(line)
            assert entry["user"] == f"user_{i}"
            assert entry["resource"] == f"/file_{i}.txt"
    
    def test_get_logs(self, audit_logger_enabled, temp_audit_dir):
        """Test retrieving audit logs."""
        # Create some log entries
        for i in range(10):
            audit_logger_enabled.log_file_access(
                user=f"user_{i}",
                action="read",
                file_path=f"/file_{i}.txt"
            )
        
        # Get all logs
        logs = audit_logger_enabled.get_logs(limit=100)
        assert len(logs) == 10
        
        # Get limited logs
        logs = audit_logger_enabled.get_logs(limit=5)
        assert len(logs) == 5
    
    def test_get_logs_with_filters(self, audit_logger_enabled, temp_audit_dir):
        """Test retrieving audit logs with filters."""
        # Create mixed log entries
        audit_logger_enabled.log_file_access(
            user="alice",
            action="upload",
            file_path="/file1.txt"
        )
        audit_logger_enabled.log_file_access(
            user="bob",
            action="delete",
            file_path="/file2.txt"
        )
        audit_logger_enabled.log_disk_monitor(
            action="monitor_started"
        )
        
        # Filter by event type
        file_logs = audit_logger_enabled.get_logs(event_type="FILE_ACCESS")
        assert len(file_logs) == 2
        
        disk_logs = audit_logger_enabled.get_logs(event_type="DISK_MONITOR")
        assert len(disk_logs) == 1
        
        # Filter by user
        alice_logs = audit_logger_enabled.get_logs(user="alice")
        assert len(alice_logs) == 1
        assert alice_logs[0]["user"] == "alice"
    
    def test_get_logs_returns_empty_when_disabled(self, audit_logger_disabled):
        """Test that get_logs returns empty list when logging is disabled."""
        logs = audit_logger_disabled.get_logs()
        assert logs == []
    
    def test_get_audit_logger_singleton(self):
        """Test that get_audit_logger returns singleton instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2
    
    def test_log_file_operation_details(self, audit_logger_enabled, temp_audit_dir):
        """Test logging file operations with various details."""
        # Upload
        audit_logger_enabled.log_file_access(
            user="alice",
            action="upload",
            file_path="/documents/report.pdf",
            size_bytes=2048000,
            success=True
        )
        
        # Move
        audit_logger_enabled.log_file_access(
            user="bob",
            action="move",
            file_path="/old/path.txt",
            target_path="/new/path.txt",
            success=True
        )
        
        # Delete directory
        audit_logger_enabled.log_file_access(
            user="admin",
            action="delete",
            file_path="/temp/folder",
            is_directory=True,
            success=True
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        with open(audit_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        assert len(lines) == 3
        
        upload_entry = json.loads(lines[0])
        assert upload_entry["details"]["size_bytes"] == 2048000
        
        move_entry = json.loads(lines[1])
        assert move_entry["details"]["target_path"] == "/new/path.txt"
        
        delete_entry = json.loads(lines[2])
        assert delete_entry["details"]["is_directory"] is True
    
    def test_log_entry_has_timestamp(self, audit_logger_enabled, temp_audit_dir):
        """Test that all log entries have ISO format timestamps."""
        audit_logger_enabled.log_file_access(
            user="test",
            action="read",
            file_path="/test.txt"
        )
        
        audit_file = temp_audit_dir / "audit" / "audit.log"
        with open(audit_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())
        
        assert "timestamp" in log_entry
        # Verify it's a valid ISO format timestamp
        from datetime import datetime
        datetime.fromisoformat(log_entry["timestamp"])
    
    def test_audit_log_handles_write_errors(self, audit_logger_enabled, temp_audit_dir):
        """Test that audit logger handles file write errors gracefully."""
        # Make audit directory read-only
        audit_dir = temp_audit_dir / "audit"
        audit_dir.mkdir(exist_ok=True)
        audit_file = audit_dir / "audit.log"
        audit_file.touch()
        audit_file.chmod(0o444)  # Read-only
        
        # Should not raise exception
        try:
            audit_logger_enabled.log_file_access(
                user="test",
                action="read",
                file_path="/test.txt"
            )
        finally:
            # Restore permissions for cleanup
            audit_file.chmod(0o644)
