"""
Pytest configuration and fixtures for tests.

This module provides shared test fixtures including:
- Database session with automatic rollback
- Test client with dependency overrides
- User authentication helpers
"""
import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables BEFORE importing app
os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))
# Prevent the application startup lifecycle from performing full DB init/seed during tests
# Tests create an in-memory DB and manage schema; skip app-level init to avoid touching production DB.
os.environ.setdefault("SKIP_APP_INIT", "1")
# Ensure tests write storage into a temporary directory (avoids protected program folders)
_tmp_storage = tempfile.mkdtemp(prefix="baluhost_test_storage_")
os.environ.setdefault("NAS_STORAGE_PATH", _tmp_storage)
os.environ.setdefault("NAS_TEMP_PATH", tempfile.mkdtemp(prefix="baluhost_test_tmp_"))
os.environ.setdefault("NAS_BACKUP_PATH", tempfile.mkdtemp(prefix="baluhost_test_backups_"))

from app.main import app
from app.core.config import settings
from app.core.database import get_db
from app.models.base import Base
from app.models.user import User
from app.models.file_metadata import FileMetadata
from app.schemas.user import UserCreate
from app.services import users as user_service
from app.models.vpn import VPNClient
from app.services.vpn import VPNService


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Create a new database session for a test with automatic rollback.
    
    This fixture:
    1. Creates an in-memory SQLite database
    2. Creates all tables
    3. Yields a session for the test
    4. Rolls back all changes after the test
    5. Drops all tables
    
    This ensures test isolation - each test gets a fresh database.
    """
    # Create in-memory SQLite database for testing
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        # Rollback any uncommitted changes
        session.rollback()
        session.close()
        
        # Drop all tables
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Create a test client with database session override.
    
    This fixture overrides the get_db dependency to use our test database
    session, ensuring all API calls use the test database.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session cleanup handled by db_session fixture
    
    app.dependency_overrides[get_db] = override_get_db
    # Ensure admin user exists in the test database so tests that perform
    # a login without the `admin_user` fixture still succeed.
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    from app.models.user import User as UserModel
    if not user_service.get_user_by_username(settings.admin_username, db=db_session):
        user_service.create_user(
            UserCreate(
                username=settings.admin_username,
                email=settings.admin_email,
                password=settings.admin_password,
                role=settings.admin_role,
            ),
            db=db_session,
        )
    # Initialize telemetry mock data so dev-mode endpoints return expected values
    try:
        from app.services import telemetry as telemetry_service
        import time
        # For deterministic tests, override uptime and telemetry values
        telemetry_service.get_server_uptime = lambda: 4 * 3600.0
        telemetry_service.get_latest_cpu_usage = lambda: 18.5
        try:
            from app.schemas.system import MemoryTelemetrySample
            import time as _time
            telemetry_service.get_latest_memory_sample = lambda: MemoryTelemetrySample(
                timestamp=int(_time.time() * 1000),
                used=3 * 1024 ** 3,
                total=8 * 1024 ** 3,
                percent=round((3 * 1024 ** 3) / (8 * 1024 ** 3) * 100, 2),
            )
        except Exception:
            pass
    except Exception:
        pass
    # Debug: list users present in the test DB
    try:
        users = db_session.query(UserModel).all()
        print("[TEST-DEBUG] users in db:", [u.username for u in users])
    except Exception:
        pass

    with TestClient(app) as test_client:
        yield test_client
    
    # Clean up dependency overrides
    app.dependency_overrides.clear()


# ============================================================================
# User Fixtures
# ============================================================================

@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create and return admin user for testing."""
    existing = user_service.get_user_by_username(settings.admin_username, db=db_session)
    if existing:
        return existing

    return user_service.create_user(
        UserCreate(
            username=settings.admin_username,
            email=settings.admin_email,
            password=settings.admin_password,
            role="admin"
        ),
        db=db_session
    )


@pytest.fixture
def regular_user(db_session: Session) -> User:
    """Create and return regular user for testing."""
    return user_service.create_user(
        UserCreate(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            role="user"
        ),
        db=db_session
    )


@pytest.fixture
def another_user(db_session: Session) -> User:
    """Create and return another regular user for testing."""
    return user_service.create_user(
        UserCreate(
            username="anotheruser",
            email="another@example.com",
            password="anotherpass123",
            role="user"
        ),
        db=db_session
    )


# ============================================================================
# Authentication Helpers
# ============================================================================

def get_auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    """
    Login and return authentication headers.
    
    Args:
        client: Test client
        username: Username to login with
        password: Password to login with
    
    Returns:
        Dictionary with Authorization header
    """
    response = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, f"Login failed: {response.json()}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def vpn_client_factory(db_session: Session):
    """Return a factory that creates a VPNClient owned by a given user id."""
    def _create(user_id: int | str, device_name: str = "TestPhone") -> int:
        # Use VPNService to create a client config (ensures model and keys)
        try:
            resp = VPNService.create_client_config(
                db=db_session,
                user_id=int(user_id),
                device_name=device_name,
                server_public_endpoint="127.0.0.1",
            )
            # resp.client_id maps to the created VPNClient.id
            return resp.client_id
        except Exception:
            # Fallback: create a simple VPNClient row
            client = VPNClient(
                user_id=int(user_id),
                device_name=device_name,
                public_key="",
                preshared_key="",
                assigned_ip="10.8.0.250",
                is_active=True
            )
            db_session.add(client)
            db_session.commit()
            db_session.refresh(client)
            return client.id

    return _create


@pytest.fixture
def admin_headers(client: TestClient, admin_user: User) -> dict[str, str]:
    """Get authentication headers for admin user."""
    return get_auth_headers(client, settings.admin_username, settings.admin_password)


@pytest.fixture
def user_headers(client: TestClient, regular_user: User) -> dict[str, str]:
    """Get authentication headers for regular user."""
    return get_auth_headers(client, "testuser", "testpass123")


@pytest.fixture
def another_user_headers(client: TestClient, another_user: User) -> dict[str, str]:
    """Get authentication headers for another user."""
    return get_auth_headers(client, "anotheruser", "anotherpass123")


# ============================================================================
# File Metadata Fixtures
# ============================================================================

@pytest.fixture
def sample_file_metadata(db_session: Session, regular_user: User) -> FileMetadata:
    """Create sample file metadata for testing."""
    metadata = FileMetadata(
        path="test_file.txt",
        name="test_file.txt",
        owner_id=regular_user.id,
        size_bytes=1024,
        is_directory=False,
        mime_type="text/plain"
    )
    db_session.add(metadata)
    db_session.commit()
    db_session.refresh(metadata)
    return metadata


@pytest.fixture
def sample_directory_metadata(db_session: Session, regular_user: User) -> FileMetadata:
    """Create sample directory metadata for testing."""
    metadata = FileMetadata(
        path="test_dir",
        name="test_dir",
        owner_id=regular_user.id,
        size_bytes=0,
        is_directory=True
    )
    db_session.add(metadata)
    db_session.commit()
    db_session.refresh(metadata)
    return metadata
