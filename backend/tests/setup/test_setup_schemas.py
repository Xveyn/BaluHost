"""Tests for setup wizard Pydantic schemas."""
import pytest
from pydantic import ValidationError

from app.schemas.setup import (
    SetupAdminRequest,
    SetupUserRequest,
    SetupFileAccessRequest,
    SambaConfig,
    WebdavConfig,
)


class TestSetupAdminRequest:
    """Tests for admin creation request schema."""

    def test_valid_admin_request(self):
        req = SetupAdminRequest(
            username="admin",
            password="StrongPass123!",
            email="admin@example.com",
        )
        assert req.username == "admin"

    def test_rejects_short_password(self):
        with pytest.raises(ValidationError):
            SetupAdminRequest(username="admin", password="short")

    def test_rejects_short_username(self):
        with pytest.raises(ValidationError):
            SetupAdminRequest(username="ab", password="StrongPass123!")

    def test_email_is_optional(self):
        req = SetupAdminRequest(username="admin", password="StrongPass123!")
        assert req.email is None

    def test_setup_secret_is_optional(self):
        req = SetupAdminRequest(username="admin", password="StrongPass123!")
        assert req.setup_secret is None

    def test_rejects_invalid_username_format(self):
        with pytest.raises(ValidationError):
            SetupAdminRequest(username="admin@host", password="StrongPass123!")


class TestSetupUserRequest:
    """Tests for regular user creation request schema."""

    def test_valid_user_request(self):
        req = SetupUserRequest(
            username="alice",
            password="StrongPass123!",
            email="alice@example.com",
        )
        assert req.username == "alice"

    def test_rejects_short_password(self):
        with pytest.raises(ValidationError):
            SetupUserRequest(username="alice", password="short")

    def test_rejects_invalid_username_format(self):
        with pytest.raises(ValidationError):
            SetupUserRequest(username="alice@host", password="StrongPass123!")

    def test_email_is_optional(self):
        req = SetupUserRequest(username="alice", password="StrongPass123!")
        assert req.email is None


class TestSetupFileAccessRequest:
    """Tests for file access configuration request."""

    def test_valid_samba_only(self):
        req = SetupFileAccessRequest(samba=SambaConfig(enabled=True))
        assert req.samba.enabled is True
        assert req.webdav is None

    def test_valid_webdav_only(self):
        req = SetupFileAccessRequest(webdav=WebdavConfig(enabled=True))
        assert req.webdav.enabled is True

    def test_valid_both_enabled(self):
        req = SetupFileAccessRequest(
            samba=SambaConfig(enabled=True),
            webdav=WebdavConfig(enabled=True, port=8443),
        )
        assert req.samba.enabled is True
        assert req.webdav.port == 8443

    def test_samba_defaults(self):
        config = SambaConfig(enabled=True)
        assert config.workgroup == "WORKGROUP"
        assert config.public_browsing is False

    def test_webdav_defaults(self):
        config = WebdavConfig(enabled=True)
        assert config.port == 8443
        assert config.ssl is False

    def test_webdav_rejects_invalid_port(self):
        with pytest.raises(ValidationError):
            WebdavConfig(enabled=True, port=0)
        with pytest.raises(ValidationError):
            WebdavConfig(enabled=True, port=65536)
