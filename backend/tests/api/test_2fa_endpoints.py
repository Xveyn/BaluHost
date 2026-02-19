"""Tests for 2FA API endpoints."""

import pytest
import pyotp

from app.core.config import settings
from app.services import totp_service
from app.models.user import User
from tests.conftest import get_auth_headers


class TestLoginWith2FA:
    """Test login flow when 2FA is enabled."""

    def _enable_2fa_for_admin(self, db_session) -> str:
        """Enable 2FA for the admin user, returning the TOTP secret."""
        user = db_session.query(User).filter(User.username == settings.admin_username).first()
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        totp_service.verify_and_enable(db_session, user.id, secret, totp.now())
        return secret

    def test_login_returns_2fa_required(self, client, db_session, admin_user):
        """Login with valid creds + 2FA enabled returns requires_2fa response."""
        secret = self._enable_2fa_for_admin(db_session)

        response = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["requires_2fa"] is True
        assert "pending_token" in data
        assert data["token_type"] == "2fa_pending"
        # Should NOT contain access_token
        assert "access_token" not in data

    def test_login_without_2fa_returns_access_token(self, client, admin_user):
        """Login without 2FA enabled returns normal access token."""
        response = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "requires_2fa" not in data

    def test_verify_2fa_valid_code(self, client, db_session, admin_user):
        """Verify 2FA with valid TOTP code returns access token."""
        secret = self._enable_2fa_for_admin(db_session)

        # Step 1: Login
        login_resp = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        pending_token = login_resp.json()["pending_token"]

        # Step 2: Verify 2FA
        totp = pyotp.TOTP(secret)
        verify_resp = client.post(
            f"{settings.api_prefix}/auth/verify-2fa",
            json={"pending_token": pending_token, "code": totp.now()},
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert "access_token" in data
        assert data["user"]["username"] == settings.admin_username

    def test_verify_2fa_invalid_code(self, client, db_session, admin_user):
        """Verify 2FA with invalid code returns 401."""
        self._enable_2fa_for_admin(db_session)

        login_resp = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        pending_token = login_resp.json()["pending_token"]

        verify_resp = client.post(
            f"{settings.api_prefix}/auth/verify-2fa",
            json={"pending_token": pending_token, "code": "000000"},
        )
        assert verify_resp.status_code == 401

    def test_verify_2fa_invalid_token(self, client, admin_user):
        """Verify 2FA with garbage token returns 401."""
        verify_resp = client.post(
            f"{settings.api_prefix}/auth/verify-2fa",
            json={"pending_token": "invalid.token.here", "code": "123456"},
        )
        assert verify_resp.status_code == 401

    def test_verify_2fa_with_backup_code(self, client, db_session, admin_user):
        """Verify 2FA with a valid backup code returns access token."""
        user = db_session.query(User).filter(User.username == settings.admin_username).first()
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        backup_codes = totp_service.verify_and_enable(db_session, user.id, secret, totp.now())

        login_resp = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        pending_token = login_resp.json()["pending_token"]

        verify_resp = client.post(
            f"{settings.api_prefix}/auth/verify-2fa",
            json={"pending_token": pending_token, "code": backup_codes[0]},
        )
        assert verify_resp.status_code == 200
        assert "access_token" in verify_resp.json()


class TestSetupEndpoints:
    """Test 2FA setup and management endpoints."""

    def test_setup_admin_only(self, client, user_headers):
        """Non-admin users cannot access 2FA setup."""
        response = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_setup_returns_qr_and_secret(self, client, admin_headers):
        """Setup endpoint returns QR code and secret."""
        response = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "qr_code" in data
        assert "secret" in data
        assert "provisioning_uri" in data
        assert data["qr_code"].startswith("data:image/png;base64,")

    def test_verify_setup_enables_2fa(self, client, admin_headers, db_session):
        """verify-setup with valid code enables 2FA and returns backup codes."""
        # Step 1: Get setup data
        setup_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=admin_headers,
        )
        secret = setup_resp.json()["secret"]

        # Step 2: Verify with valid code
        totp = pyotp.TOTP(secret)
        verify_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/verify-setup",
            json={"secret": secret, "code": totp.now()},
            headers=admin_headers,
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10

    def test_verify_setup_invalid_code(self, client, admin_headers):
        """verify-setup with invalid code returns 400."""
        setup_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=admin_headers,
        )
        secret = setup_resp.json()["secret"]

        verify_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/verify-setup",
            json={"secret": secret, "code": "000000"},
            headers=admin_headers,
        )
        assert verify_resp.status_code == 400

    def test_status_endpoint(self, client, admin_headers):
        """Status endpoint returns 2FA status."""
        response = client.get(
            f"{settings.api_prefix}/auth/2fa/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)

    def test_status_user_accessible(self, client, user_headers):
        """Regular users can check their own 2FA status."""
        response = client.get(
            f"{settings.api_prefix}/auth/2fa/status",
            headers=user_headers,
        )
        assert response.status_code == 200

    def test_disable_requires_password_and_code(self, client, admin_headers, db_session, admin_user):
        """Disable 2FA requires both password and valid TOTP code."""
        # Enable 2FA first
        setup_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=admin_headers,
        )
        secret = setup_resp.json()["secret"]
        totp = pyotp.TOTP(secret)
        client.post(
            f"{settings.api_prefix}/auth/2fa/verify-setup",
            json={"secret": secret, "code": totp.now()},
            headers=admin_headers,
        )

        # Try to disable with wrong password
        disable_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/disable",
            json={"password": "wrongpassword", "code": totp.now()},
            headers=admin_headers,
        )
        assert disable_resp.status_code == 401

        # Disable with correct password + code
        disable_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/disable",
            json={"password": settings.admin_password, "code": totp.now()},
            headers=admin_headers,
        )
        assert disable_resp.status_code == 200

        # Verify it's disabled
        status_resp = client.get(
            f"{settings.api_prefix}/auth/2fa/status",
            headers=admin_headers,
        )
        assert status_resp.json()["enabled"] is False

    def test_regenerate_backup_codes(self, client, admin_headers, db_session):
        """Regenerate backup codes returns new codes."""
        # Enable 2FA first
        setup_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=admin_headers,
        )
        secret = setup_resp.json()["secret"]
        totp = pyotp.TOTP(secret)
        client.post(
            f"{settings.api_prefix}/auth/2fa/verify-setup",
            json={"secret": secret, "code": totp.now()},
            headers=admin_headers,
        )

        # Regenerate
        regen_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/backup-codes",
            headers=admin_headers,
        )
        assert regen_resp.status_code == 200
        data = regen_resp.json()
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10

    def test_regenerate_non_admin_forbidden(self, client, user_headers):
        """Non-admin users cannot regenerate backup codes."""
        response = client.post(
            f"{settings.api_prefix}/auth/2fa/backup-codes",
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_setup_already_enabled_rejected(self, client, admin_headers, db_session):
        """Setup when 2FA is already enabled returns 400."""
        # Enable 2FA
        setup_resp = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=admin_headers,
        )
        secret = setup_resp.json()["secret"]
        totp = pyotp.TOTP(secret)
        client.post(
            f"{settings.api_prefix}/auth/2fa/verify-setup",
            json={"secret": secret, "code": totp.now()},
            headers=admin_headers,
        )

        # Try setup again
        resp = client.post(
            f"{settings.api_prefix}/auth/2fa/setup",
            headers=admin_headers,
        )
        assert resp.status_code == 400
