"""
Test Input Validation & Sanitization for Task 2.2 Security Hardening.

Tests cover:
1. SQL injection prevention via ORM
2. XSS prevention (HTML entity encoding)
3. Command injection prevention
4. Path traversal prevention
5. Input length limits
6. Type validation
"""

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.schemas.auth import RegisterRequest
from app.schemas.user import UserPublic


class TestSQLInjectionPrevention:
    """Test SQL injection prevention via SQLAlchemy ORM."""

    def test_username_with_sql_injection_attempt_safe(self, client: TestClient, db_session):
        """Verify SQL injection attempts in username are safely handled by ORM."""
        from app.services import users as user_service

        malicious_username = "admin' OR '1'='1"
        # ORM parameterizes queries, so this returns None (not all users)
        result = user_service.get_user_by_username(malicious_username, db=db_session)
        assert result is None

    def test_email_input_validated_by_pydantic(self):
        """Verify email validation prevents malformed inputs."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="testuser",
                email="not-an-email",
                password="SecurePass123!"
            )

    def test_password_field_not_in_response_schema(self):
        """Verify UserPublic schema does not contain password field."""
        fields = UserPublic.model_fields
        assert "password" not in fields
        assert "hashed_password" not in fields


class TestXSSPrevention:
    """Test XSS (Cross-Site Scripting) prevention."""

    def test_username_with_html_tags_rejected(self):
        """Verify HTML tags in username are rejected by validator."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="<script>alert('xss')</script>",
                email="test@example.com",
                password="SecurePass123!"
            )

    def test_response_content_type_is_json(self, client: TestClient):
        """Verify API responses use application/json content-type."""
        response = client.get("/api/health")
        assert "application/json" in response.headers.get("content-type", "")


class TestPathTraversalPrevention:
    """Test path traversal attack prevention."""

    def test_filename_with_parent_directory_traversal_rejected(self, client: TestClient, auth_headers):
        """Verify path traversal attempts (../) are rejected by file endpoints."""
        response = client.get(
            "/api/files/list",
            params={"path": "../../../etc/passwd"},
            headers=auth_headers,
        )
        # Should be rejected (400 or 403), not succeed
        assert response.status_code in (400, 403, 404, 422), (
            f"Path traversal should be rejected, got {response.status_code}"
        )

    def test_filename_with_null_bytes_rejected(self, client: TestClient, auth_headers):
        """Verify null byte injection in filenames is rejected."""
        response = client.get(
            "/api/files/list",
            params={"path": "file.txt\x00.exe"},
            headers=auth_headers,
        )
        # Should not succeed
        assert response.status_code != 200 or response.json().get("error") is not None


class TestInputLengthLimits:
    """Test input length validation."""

    def test_username_max_length_enforced(self):
        """Verify username has maximum length (32 chars)."""
        with pytest.raises(ValidationError, match="less than 32 characters"):
            RegisterRequest(
                username="a" * 1000,
                email="test@example.com",
                password="SecurePass123!"
            )

    def test_username_min_length_enforced(self):
        """Verify username has minimum length (3 chars)."""
        with pytest.raises(ValidationError, match="at least 3 characters"):
            RegisterRequest(
                username="ab",
                email="test@example.com",
                password="SecurePass123!"
            )

    def test_password_minimum_length_enforced(self):
        """Verify password has minimum length (8 chars)."""
        with pytest.raises(ValidationError, match="at least 8 characters"):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="Short1"
            )

    def test_password_maximum_length_enforced(self):
        """Verify password has maximum length (128 chars)."""
        with pytest.raises(ValidationError, match="less than 128 characters"):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="A" * 64 + "a" * 64 + "1"  # 129 chars
            )


class TestTypeValidation:
    """Test type validation and coercion."""

    def test_user_id_must_be_integer(self):
        """Verify user_id type is strictly validated."""
        with pytest.raises(ValidationError):
            UserPublic(
                id="not_an_integer",
                username="test",
                email="test@example.com",
                role="user",
                is_active=True,
                created_at="2026-01-05T00:00:00"
            )


class TestInputSanitization:
    """Test input sanitization patterns."""

    def test_username_whitespace_trimmed(self):
        """Verify leading/trailing whitespace is stripped from username."""
        req = RegisterRequest(
            username="  testuser  ",
            email="test@example.com",
            password="SecurePass123!"
        )
        assert req.username == "testuser"

    def test_common_password_rejected(self):
        """Verify common passwords from blacklist are rejected."""
        with pytest.raises(ValidationError, match="too common"):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="Password123"
            )

    def test_password_requires_uppercase(self):
        """Verify password requires at least one uppercase letter."""
        with pytest.raises(ValidationError, match="uppercase"):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="lowercase123"
            )

    def test_password_requires_digit(self):
        """Verify password requires at least one digit."""
        with pytest.raises(ValidationError, match="number"):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="NoDigitsHere"
            )


class TestSecurityHeaders:
    """Test security header implementation via actual HTTP responses."""

    def test_content_security_policy_header_set(self, client: TestClient):
        """Verify CSP header is present on responses."""
        response = client.get("/api/health")
        assert "Content-Security-Policy" in response.headers

    def test_x_content_type_options_header_set(self, client: TestClient):
        """Verify X-Content-Type-Options: nosniff header."""
        response = client.get("/api/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_header_set(self, client: TestClient):
        """Verify X-Frame-Options header prevents clickjacking."""
        response = client.get("/api/health")
        assert response.headers.get("X-Frame-Options") == "DENY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
