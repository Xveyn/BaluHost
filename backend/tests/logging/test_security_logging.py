"""Tests for security event logging (unauthorized access attempts)."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services.audit_logger import AuditLogger


@pytest.fixture
def audit_logger(tmp_path: Path):
    """Create a test audit logger with temp directory."""
    logger = AuditLogger()
    logger._enabled = True
    logger._audit_log_dir = tmp_path / "audit"
    logger._setup_audit_log()
    return logger


def test_log_authentication_attempt_success(audit_logger: AuditLogger):
    """Test logging successful authentication."""
    audit_logger.log_authentication_attempt(
        username="testuser",
        success=True,
        ip_address="127.0.0.1",
        user_agent="TestAgent/1.0"
    )
    
    logs = audit_logger.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["event_type"] == "SECURITY"
    assert logs[0]["action"] == "login_attempt"
    assert logs[0]["user"] == "testuser"
    assert logs[0]["success"] is True
    assert logs[0]["details"]["ip_address"] == "127.0.0.1"
    assert logs[0]["details"]["user_agent"] == "TestAgent/1.0"


def test_log_authentication_attempt_failure(audit_logger: AuditLogger):
    """Test logging failed authentication."""
    audit_logger.log_authentication_attempt(
        username="baduser",
        success=False,
        ip_address="192.168.1.100",
        error_message="Invalid credentials"
    )
    
    logs = audit_logger.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["event_type"] == "SECURITY"
    assert logs[0]["action"] == "login_attempt"
    assert logs[0]["user"] == "baduser"
    assert logs[0]["success"] is False
    assert logs[0]["error"] == "Invalid credentials"
    assert logs[0]["details"]["ip_address"] == "192.168.1.100"


def test_log_authorization_failure(audit_logger: AuditLogger):
    """Test logging authorization failures (permission denied)."""
    audit_logger.log_authorization_failure(
        user="normaluser",
        action="delete_file",
        resource="/admin/secret.txt",
        required_permission="admin",
        ip_address="10.0.0.50"
    )
    
    logs = audit_logger.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["event_type"] == "SECURITY"
    assert logs[0]["action"] == "delete_file"
    assert logs[0]["user"] == "normaluser"
    assert logs[0]["resource"] == "/admin/secret.txt"
    assert logs[0]["success"] is False
    assert logs[0]["error"] == "Permission denied"
    assert logs[0]["details"]["required_permission"] == "admin"
    assert logs[0]["details"]["ip_address"] == "10.0.0.50"


def test_log_security_event_generic(audit_logger: AuditLogger):
    """Test logging generic security events."""
    audit_logger.log_security_event(
        action="invalid_token",
        user="unknown",
        details={"reason": "Token expired"},
        success=False,
        error_message="Token validation failed"
    )
    
    logs = audit_logger.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["event_type"] == "SECURITY"
    assert logs[0]["action"] == "invalid_token"
    assert logs[0]["user"] == "unknown"
    assert logs[0]["success"] is False
    assert logs[0]["error"] == "Token validation failed"


def test_log_registration_duplicate(audit_logger: AuditLogger):
    """Test logging duplicate registration attempts."""
    audit_logger.log_security_event(
        action="registration_duplicate",
        user="existinguser",
        details={"ip_address": "192.168.1.10"},
        success=False,
        error_message="Username already exists"
    )
    
    logs = audit_logger.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["event_type"] == "SECURITY"
    assert logs[0]["action"] == "registration_duplicate"
    assert logs[0]["success"] is False


def test_filter_security_logs(audit_logger: AuditLogger):
    """Test filtering logs by security event type."""
    # Log various events
    audit_logger.log_authentication_attempt("user1", True)
    audit_logger.log_authorization_failure("user2", "read_file", "/secret.txt")
    audit_logger.log_file_access("user3", "upload", "/public/file.txt", success=True)
    
    # Filter only security events
    security_logs = audit_logger.get_logs(limit=10, event_type="SECURITY")
    assert len(security_logs) == 2
    assert all(log["event_type"] == "SECURITY" for log in security_logs)
    
    # Filter file access events
    file_logs = audit_logger.get_logs(limit=10, event_type="FILE_ACCESS")
    assert len(file_logs) == 1
    assert file_logs[0]["event_type"] == "FILE_ACCESS"


def test_filter_by_user(audit_logger: AuditLogger):
    """Test filtering logs by user."""
    audit_logger.log_authentication_attempt("alice", True)
    audit_logger.log_authentication_attempt("bob", False)
    audit_logger.log_authorization_failure("alice", "delete_file", "/file.txt")
    
    # Filter alice's events
    alice_logs = audit_logger.get_logs(limit=10, user="alice")
    assert len(alice_logs) == 2
    assert all(log["user"] == "alice" for log in alice_logs)
    
    # Filter bob's events
    bob_logs = audit_logger.get_logs(limit=10, user="bob")
    assert len(bob_logs) == 1
    assert bob_logs[0]["user"] == "bob"


def test_multiple_failed_login_attempts(audit_logger: AuditLogger):
    """Test tracking multiple failed login attempts."""
    for i in range(5):
        audit_logger.log_authentication_attempt(
            username="attacker",
            success=False,
            ip_address="suspicious.ip.address",
            error_message="Invalid credentials"
        )
    
    logs = audit_logger.get_logs(limit=10, user="attacker")
    assert len(logs) == 5
    assert all(not log["success"] for log in logs)
    assert all(log["action"] == "login_attempt" for log in logs)


def test_admin_access_denied_logging(audit_logger: AuditLogger):
    """Test logging unauthorized admin access attempts."""
    audit_logger.log_authorization_failure(
        user="normaluser",
        action="admin_access_denied",
        required_permission="admin",
        ip_address="10.0.0.100"
    )
    
    logs = audit_logger.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["action"] == "admin_access_denied"
    assert logs[0]["details"]["required_permission"] == "admin"
    assert logs[0]["success"] is False
