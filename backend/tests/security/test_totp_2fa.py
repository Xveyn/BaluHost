"""Tests for TOTP 2FA service and token handling."""

import json
import pytest
import pyotp
from unittest.mock import patch

from app.core.security import create_2fa_pending_token, decode_token
from app.services import totp_service
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import users as user_service


# ============================================================================
# Token Tests
# ============================================================================

class TestTwoFactorPendingToken:
    """Tests for the 2fa_pending token type."""

    def test_create_and_decode(self):
        """Create a 2fa_pending token and decode it successfully."""
        token = create_2fa_pending_token(user_id=42)
        payload = decode_token(token, token_type="2fa_pending")
        assert payload["sub"] == "42"
        assert payload["type"] == "2fa_pending"

    def test_type_confusion_rejected(self):
        """A 2fa_pending token must not be accepted as an access token."""
        token = create_2fa_pending_token(user_id=42)
        with pytest.raises(Exception):
            decode_token(token, token_type="access")

    def test_access_token_not_accepted_as_2fa(self):
        """An access token must not be accepted as a 2fa_pending token."""
        from app.core.security import create_access_token
        token = create_access_token({"id": 42, "username": "admin", "role": "admin"})
        with pytest.raises(Exception):
            decode_token(token, token_type="2fa_pending")

    def test_expired_token_rejected(self):
        """An expired 2fa_pending token must be rejected."""
        import jwt as pyjwt
        token = create_2fa_pending_token(user_id=42, expires_seconds=-1)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(token, token_type="2fa_pending")


# ============================================================================
# TOTP Service Tests
# ============================================================================

class TestTOTPService:
    """Tests for the TOTP service functions."""

    def _create_admin(self, db) -> User:
        """Helper to create an admin user."""
        existing = user_service.get_user_by_username("totpadmin", db=db)
        if existing:
            return existing
        return user_service.create_user(
            UserCreate(
                username="totpadmin",
                email="totpadmin@example.com",
                password="AdminPass123!",
                role="admin",
            ),
            db=db,
        )

    def test_generate_setup(self, db_session):
        """generate_setup returns secret, QR code, and provisioning URI."""
        user = self._create_admin(db_session)
        result = totp_service.generate_setup(user)

        assert "secret" in result
        assert len(result["secret"]) == 32  # pyotp default
        assert result["qr_code"].startswith("data:image/png;base64,")
        assert "otpauth://totp/" in result["provisioning_uri"]
        assert "BaluHost" in result["provisioning_uri"]

    def test_verify_and_enable(self, db_session):
        """verify_and_enable with a valid code enables 2FA and returns backup codes."""
        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]

        # Generate a valid code
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        backup_codes = totp_service.verify_and_enable(db_session, user.id, secret, valid_code)

        assert len(backup_codes) == 10
        # Verify user is now enabled
        db_session.refresh(user)
        assert user.totp_enabled is True
        assert user.totp_secret_encrypted is not None
        assert user.totp_enabled_at is not None

    def test_verify_and_enable_invalid_code(self, db_session):
        """verify_and_enable with an invalid code raises ValueError."""
        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)

        with pytest.raises(ValueError, match="Invalid TOTP code"):
            totp_service.verify_and_enable(db_session, user.id, setup["secret"], "000000")

    def test_verify_code(self, db_session):
        """verify_code returns True for a valid TOTP code."""
        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        totp_service.verify_and_enable(db_session, user.id, secret, totp.now())

        # Now verify with a fresh code
        assert totp_service.verify_code(db_session, user.id, totp.now()) is True

    def test_verify_code_invalid(self, db_session):
        """verify_code returns False for an invalid code."""
        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        totp_service.verify_and_enable(db_session, user.id, secret, totp.now())

        assert totp_service.verify_code(db_session, user.id, "000000") is False

    def test_verify_backup_code(self, db_session):
        """A backup code can be used once and is then consumed."""
        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        backup_codes = totp_service.verify_and_enable(db_session, user.id, secret, totp.now())

        first_code = backup_codes[0]

        # First use should succeed
        assert totp_service.verify_backup_code(db_session, user.id, first_code) is True

        # Second use should fail (consumed)
        assert totp_service.verify_backup_code(db_session, user.id, first_code) is False

        # Remaining count should be 9
        assert totp_service.get_backup_codes_remaining(db_session, user.id) == 9

    def test_disable(self, db_session):
        """disable clears all 2FA data."""
        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        totp_service.verify_and_enable(db_session, user.id, secret, totp.now())

        totp_service.disable(db_session, user.id)

        db_session.refresh(user)
        assert user.totp_enabled is False
        assert user.totp_secret_encrypted is None
        assert user.totp_backup_codes_encrypted is None
        assert user.totp_enabled_at is None

    def test_regenerate_backup_codes(self, db_session):
        """Regenerating backup codes invalidates old ones."""
        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        old_codes = totp_service.verify_and_enable(db_session, user.id, secret, totp.now())

        new_codes = totp_service.regenerate_backup_codes(db_session, user.id)

        assert len(new_codes) == 10
        # Old codes should not work
        assert totp_service.verify_backup_code(db_session, user.id, old_codes[0]) is False
        # New codes should work
        assert totp_service.verify_backup_code(db_session, user.id, new_codes[0]) is True

    def test_encryption_roundtrip(self, db_session):
        """Secret is encrypted at rest and can be decrypted for verification."""
        from app.services.vpn.encryption import VPNEncryption

        user = self._create_admin(db_session)
        setup = totp_service.generate_setup(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        totp_service.verify_and_enable(db_session, user.id, secret, totp.now())

        db_session.refresh(user)
        # The stored value should be encrypted (not plain text)
        assert user.totp_secret_encrypted != secret
        # Decrypting should give back the original secret
        decrypted = VPNEncryption.decrypt_key(user.totp_secret_encrypted)
        assert decrypted == secret
