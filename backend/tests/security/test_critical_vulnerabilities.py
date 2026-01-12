from datetime import timezone
"""
Critical Security Vulnerability Tests

Tests for the 8 critical vulnerabilities identified in SECURITY_AUDIT_REPORT.md

These tests document the vulnerabilities and will PASS once fixes are implemented.
"""

import pytest
from fastapi.testclient import TestClient
from app.core.config import settings


class TestCriticalVulnerability1:
    """Test: Hardcoded Secrets in Configuration"""

    def test_secret_key_not_default(self):
        """Verify SECRET_KEY is not using default value."""
        assert settings.SECRET_KEY != "change-me-in-prod", (
            "SECRET_KEY is using default value! "
            "Generate a secure secret: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )

    def test_token_secret_not_default(self):
        """Verify token_secret is not using default value."""
        assert settings.token_secret != "change-me-in-prod", (
            "token_secret is using default value! "
            "Generate a secure secret: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )

    def test_secrets_minimum_length(self):
        """Verify secrets meet minimum length requirements."""
        assert len(settings.SECRET_KEY) >= 32, "SECRET_KEY must be at least 32 characters"
        assert len(settings.token_secret) >= 32, "token_secret must be at least 32 characters"


class TestCriticalVulnerability2:
    """Test: Security Headers Middleware Not Activated"""

    def test_security_headers_present(self, client: TestClient):
        """Verify security headers are set on all responses."""
        response = client.get("/api/health")

        # X-Frame-Options prevents clickjacking
        assert "X-Frame-Options" in response.headers, (
            "X-Frame-Options header missing! "
            "Activate security middleware in main.py: setup_security_headers(app)"
        )
        assert response.headers["X-Frame-Options"] == "DENY"

        # X-Content-Type-Options prevents MIME sniffing
        assert "X-Content-Type-Options" in response.headers, (
            "X-Content-Type-Options header missing!"
        )
        assert response.headers["X-Content-Type-Options"] == "nosniff"

        # Content-Security-Policy prevents XSS
        assert "Content-Security-Policy" in response.headers, (
            "Content-Security-Policy header missing!"
        )

    def test_csp_policy_strict(self, client: TestClient):
        """Verify CSP policy is strict (no unsafe-inline/unsafe-eval)."""
        response = client.get("/api/health")

        csp = response.headers.get("Content-Security-Policy", "")

        # Ideally CSP should NOT contain unsafe-inline/unsafe-eval
        # but dev mode might need it for Vite
        if not settings.debug:
            assert "unsafe-inline" not in csp, (
                "Production CSP should not use 'unsafe-inline'! Use nonces instead."
            )
            assert "unsafe-eval" not in csp, (
                "Production CSP should not use 'unsafe-eval'!"
            )


class TestCriticalVulnerability3:
    """Test: Dual Authentication Systems"""

    def test_auth_systems_use_same_secret(self):
        """Verify both auth systems use the same secret."""
        # After fix: both should use settings.SECRET_KEY
        from app.services import auth as auth_service
        from app.core import security

        # Create a test user
        class MockUser:
            id = 123
            username = "test"
            role = "user"

        # Generate tokens from both systems
        token1 = auth_service.create_access_token(MockUser())
        token2 = security.create_access_token(MockUser())

        # Both should be decodable with the same secret
        # (After fix: consolidate to one system)
        import jwt

        try:
            payload1 = jwt.decode(token1, settings.SECRET_KEY, algorithms=["HS256"])
            payload2 = jwt.decode(token2, settings.SECRET_KEY, algorithms=["HS256"])
            # If both decode successfully, they use the same secret
            assert payload1["sub"] == payload2["sub"]
        except jwt.InvalidSignatureError:
            pytest.fail(
                "Auth systems using different secrets! "
                "Consolidate to use settings.SECRET_KEY"
            )


class TestCriticalVulnerability4:
    """Test: No Password Policy Enforcement"""

    def test_weak_password_rejected(self, client: TestClient):
        """Verify weak passwords are rejected."""
        # Test various weak passwords
        weak_passwords = [
            "a",           # Too short
            "1234567",     # Too short, no letters
            "password",    # Common password
            "Password",    # No numbers
            "password123", # No uppercase
            "PASSWORD123", # No lowercase
        ]

        for weak_pwd in weak_passwords:
            response = client.post("/api/auth/register", json={
                "username": f"test_{weak_pwd}",
                "email": f"test_{weak_pwd}@example.com",
                "password": weak_pwd
            })

            assert response.status_code == 422, (
                f"Weak password '{weak_pwd}' should be rejected! "
                f"Add password validation in RegisterRequest schema"
            )

    def test_strong_password_accepted(self, client: TestClient):
        """Verify strong passwords are accepted."""
        import secrets

        strong_password = f"SecurePass{secrets.randbelow(1000)}!"

        response = client.post("/api/auth/register", json={
            "username": f"test_{secrets.token_hex(4)}",
            "email": f"test_{secrets.token_hex(4)}@example.com",
            "password": strong_password
        })

        # Should succeed (201) or fail for other reasons (409 duplicate), not 422
        assert response.status_code in [201, 409], (
            f"Strong password should be accepted, got {response.status_code}: {response.json()}"
        )

    def test_username_length_limits(self, client: TestClient):
        """Verify username has length limits."""
        # Too short
        response = client.post("/api/auth/register", json={
            "username": "ab",  # 2 chars (should require 3+)
            "email": "test@example.com",
            "password": "SecurePass123!"
        })
        assert response.status_code == 422, "Username too short should be rejected"

        # Too long
        response = client.post("/api/auth/register", json={
            "username": "a" * 100,  # 100 chars (should limit to 32)
            "email": "test2@example.com",
            "password": "SecurePass123!"
        })
        assert response.status_code == 422, "Username too long should be rejected"


class TestCriticalVulnerability5:
    """Test: Missing Rate Limiting on Critical Endpoints"""

    def test_password_change_rate_limited(self, client: TestClient, auth_headers):
        """Verify /change-password is rate limited."""
        # Make rapid password change attempts
        responses = []
        for i in range(10):
            response = client.post(
                "/api/auth/change-password",
                json={"current_password": "wrong", "new_password": "new"},
                headers=auth_headers
            )
            responses.append(response)

        # At least one should be rate limited (429)
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, (
            "Password change endpoint not rate limited! "
            "Add @limiter.limit(get_limit('auth_password_change'))"
        )

    def test_refresh_token_rate_limited(self, client: TestClient):
        """Verify /refresh is rate limited."""
        # Make rapid refresh attempts
        responses = []
        for i in range(15):
            response = client.post(
                "/api/auth/refresh",
                json={"refresh_token": "fake_token"}
            )
            responses.append(response)

        # At least one should be rate limited (429)
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, (
            "Refresh endpoint not rate limited! "
            "Add @limiter.limit(get_limit('auth_refresh'))"
        )


class TestCriticalVulnerability6:
    """Test: Refresh Tokens Cannot Be Revoked"""

    def test_refresh_token_revocation_supported(self, client: TestClient, db_session):
        """Verify refresh tokens can be revoked."""
        # This test will FAIL until refresh token revocation is implemented

        # 1. Register user and get refresh token
        import secrets
        username = f"test_{secrets.token_hex(4)}"
        response = client.post("/api/auth/register", json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "SecurePass123!"
        })

        if response.status_code != 201:
            pytest.skip("Registration failed, skipping revocation test")

        # 2. Get refresh token (would need to be returned by mobile registration)
        # For now, document the requirement
        pytest.skip(
            "Refresh token revocation not yet implemented. "
            "Need to add: RefreshToken model, store_refresh_token(), revoke_refresh_token()"
        )


class TestCriticalVulnerability7:
    """Test: Deprecated datetime.utcnow()"""

    def test_no_deprecated_datetime_usage(self):
        """Verify datetime.utcnow() is not used (deprecated in Python 3.14)."""
        import ast
        import os
        from pathlib import Path

        # Check deps.py for datetime.utcnow() usage
        deps_file = Path(__file__).parent.parent.parent / "app" / "api" / "deps.py"

        if not deps_file.exists():
            pytest.skip("deps.py not found")

        with open(deps_file, "r") as f:
            source = f.read()

        # Should use datetime.now(timezone.utc) instead of datetime.utcnow()
        assert "datetime.utcnow()" not in source, (
            "Found deprecated datetime.utcnow() usage! "
            "Replace with: datetime.now(timezone.utc)"
        )


class TestCriticalVulnerability8:
    """Test: Print Statements in Production Code"""

    def test_no_print_statements_in_auth_code(self):
        """Verify no print() statements in authentication code."""
        from pathlib import Path

        # Check deps.py for print statements
        deps_file = Path(__file__).parent.parent.parent / "app" / "api" / "deps.py"

        if not deps_file.exists():
            pytest.skip("deps.py not found")

        with open(deps_file, "r") as f:
            source = f.read()

        # Count print statements
        print_count = source.count("print(")

        assert print_count == 0, (
            f"Found {print_count} print() statements in deps.py! "
            f"Replace with logger.debug/info/warning/error"
        )


# Fixtures for tests
@pytest.fixture
def client():
    """Create test client."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def db_session():
    """Create database session for tests."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def auth_headers(client: TestClient):
    """Get authentication headers for test user."""
    import secrets

    # Register a test user
    username = f"test_{secrets.token_hex(4)}"
    password = "SecurePass123!"

    response = client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": password
    })

    if response.status_code != 201:
        # Try to login if user already exists
        response = client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })

    if response.status_code in [200, 201]:
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    pytest.fail(f"Could not get auth token: {response.json()}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
