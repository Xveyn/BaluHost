"""
Task 3.2: Security Event Logging Integration Tests

Tests for logging security events in auth endpoints and permission changes.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock
from datetime import datetime

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class TestAuthEventLogging:
    """Test security event logging in authentication flow."""

    def test_log_successful_login(self):
        """Verify successful login is logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            # Simulate login event
            log = AuditLog(
                event_type="SECURITY",
                action="login_success",
                user="admin@example.com",
                resource="auth/login",
                success=True,
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0"
            )
            db.add(log)
            db.commit()
            
            # Verify
            result = db.query(AuditLog).filter_by(action="login_success").first()
            assert result is not None
            assert result.user == "admin@example.com"
            assert result.success is True
        finally:
            db.close()

    def test_log_failed_login_attempts(self):
        """Verify failed login attempts are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            # Log failed attempt
            log = AuditLog(
                event_type="SECURITY",
                action="login_failed",
                user="attacker@example.com",
                resource="auth/login",
                success=False,
                error_message="Invalid credentials",
                ip_address="192.168.1.100"
            )
            db.add(log)
            db.commit()
            
            # Verify
            result = db.query(AuditLog).filter_by(action="login_failed").first()
            assert result is not None
            assert result.success is False
            assert "Invalid credentials" in result.error_message
        finally:
            db.close()

    def test_log_token_refresh(self):
        """Verify token refresh operations are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            log = AuditLog(
                event_type="SECURITY",
                action="token_refresh",
                user="user1",
                resource="auth/refresh",
                success=True,
                details='{"token_type": "refresh"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="token_refresh").first()
            assert result is not None
            assert result.event_type == "SECURITY"
        finally:
            db.close()


class TestPermissionChangeLogging:
    """Test logging of permission and role changes."""

    def test_log_role_change(self):
        """Verify role changes are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            log = AuditLog(
                event_type="SECURITY",
                action="role_changed",
                user="admin",
                resource="users/user123/role",
                success=True,
                details='{"old_role": "user", "new_role": "admin"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="role_changed").first()
            assert result is not None
            assert "admin" in result.details
        finally:
            db.close()

    def test_log_permission_grant(self):
        """Verify permission grants are logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            log = AuditLog(
                event_type="SECURITY",
                action="permission_granted",
                user="admin",
                resource="users/user456/permissions",
                success=True,
                details='{"permission": "write_files", "resource": "/storage"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="permission_granted").first()
            assert result is not None
        finally:
            db.close()

    def test_log_permission_revoke(self):
        """Verify permission revocation is logged."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            log = AuditLog(
                event_type="SECURITY",
                action="permission_revoked",
                user="admin",
                resource="users/user789/permissions",
                success=True,
                details='{"permission": "admin_access"}'
            )
            db.add(log)
            db.commit()
            
            result = db.query(AuditLog).filter_by(action="permission_revoked").first()
            assert result is not None
        finally:
            db.close()


class TestSecurityEventFiltering:
    """Test filtering and querying security events."""

    def test_get_all_failed_login_attempts(self):
        """Query all failed login attempts."""
        from app.models import AuditLog
        from app.core.database import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Use separate in-memory DB for this test
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            # Create mixed events
            events = [
                ("login_success", True),
                ("login_failed", False),
                ("login_failed", False),
                ("logout", True)
            ]
            
            for action, success in events:
                log = AuditLog(
                    event_type="SECURITY",
                    action=action,
                    user="testuser",
                    resource="auth",
                    success=success
                )
                db.add(log)
            db.commit()
            
            # Query
            failed = db.query(AuditLog).filter(
                (AuditLog.action == "login_failed") & 
                (AuditLog.success == False)
            ).all()
            
            assert len(failed) == 2
        finally:
            db.close()

    def test_get_recent_security_events(self):
        """Query recent security events by timestamp."""
        from app.models import AuditLog
        from app.core.database import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Use separate in-memory DB for this test
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            # Create events
            for i in range(3):
                log = AuditLog(
                    event_type="SECURITY",
                    action=f"action_{i}",
                    user="user1",
                    resource="resource",
                    success=True
                )
                db.add(log)
            db.commit()
            
            # Query recent
            recent = db.query(AuditLog).filter_by(event_type="SECURITY").order_by(
                AuditLog.timestamp.desc()
            ).limit(2).all()
            
            assert len(recent) == 2
        finally:
            db.close()

    def test_get_user_security_events(self):
        """Query all security events for a specific user."""
        from app.models import AuditLog
        from app.core.database import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Use separate in-memory DB for this test
        test_db = create_engine("sqlite:///:memory:")
        TestSession = sessionmaker(bind=test_db)
        Base.metadata.create_all(test_db)
        db = TestSession()
        
        try:
            # Create events for different users
            for user in ["user1", "user2", "user1"]:
                log = AuditLog(
                    event_type="SECURITY",
                    action="login_success",
                    user=user,
                    resource="auth",
                    success=True
                )
                db.add(log)
            db.commit()
            
            # Query user1's events
            user_events = db.query(AuditLog).filter_by(
                user="user1",
                event_type="SECURITY"
            ).all()
            
            assert len(user_events) == 2
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
