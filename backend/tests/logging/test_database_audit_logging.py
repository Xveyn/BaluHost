"""
Task 3.1: Database Audit Logging Tests

Simpler test suite validating AuditLog functionality
"""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class TestAuditLogSchema:
    """Test AuditLog database schema."""

    def test_audit_log_table_exists(self):
        """Verify audit_logs table exists."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        assert "audit_logs" in tables

    def test_audit_log_columns_exist(self):
        """Verify required columns exist."""
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("audit_logs")}
        
        required = {"id", "timestamp", "event_type", "action", "user", "resource", "success", "details"}
        assert required.issubset(columns)

    def test_indexes_configured(self):
        """Verify performance indexes exist."""
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        indexes = inspector.get_indexes("audit_logs")
        
        assert len(indexes) > 0


class TestAuditLogOperations:
    """Test AuditLog creation and querying."""

    def test_create_audit_log(self):
        """Verify audit logs can be created."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            log = AuditLog(
                event_type="FILE_ACCESS",
                action="upload",
                user="admin",
                resource="/test.pdf",
                success=True,
                details='{"size": 1024}'
            )
            db.add(log)
            db.commit()
            
            assert log.id is not None
            assert log.timestamp is not None
        finally:
            db.close()

    def test_query_by_event_type(self):
        """Verify logs can be filtered by event_type."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            # Create test logs
            for et in ["FILE_ACCESS", "SECURITY"]:
                log = AuditLog(event_type=et, action="test", user="u", resource="r", success=True, details='{}')
                db.add(log)
            db.commit()
            
            # Query
            results = db.query(AuditLog).filter_by(event_type="FILE_ACCESS").all()
            assert len(results) > 0
            assert all(log.event_type == "FILE_ACCESS" for log in results)
        finally:
            db.close()

    def test_query_by_success(self):
        """Verify logs can be filtered by success status."""
        from app.models import AuditLog
        from app.core.database import Base
        
        Base.metadata.create_all(engine)
        db = SessionLocal()
        
        try:
            # Create logs
            for success in [True, False]:
                log = AuditLog(event_type="TEST", action="test", user="u", resource="r", success=success, details='{}')
                db.add(log)
            db.commit()
            
            # Query
            failed = db.query(AuditLog).filter_by(success=False).all()
            assert len(failed) > 0
            assert all(not log.success for log in failed)
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
