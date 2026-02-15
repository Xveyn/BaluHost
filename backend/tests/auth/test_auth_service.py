"""
Tests for authentication service.

Tests:
- authenticate_user: valid/invalid credentials, inactive users
- create_access_token: JWT creation, claims, expiry
- decode_token: token validation, expiry, manipulation protection
"""
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core import security
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import auth as auth_service
from app.services.auth import InvalidTokenError
from app.services import users as user_service


class TestAuthenticateUser:
    """Tests for authenticate_user function."""

    def test_authenticate_valid_credentials(self, db_session: Session, regular_user: User):
        """Test authentication with valid credentials."""
        user = auth_service.authenticate_user("testuser", "Testpass123!", db=db_session)

        assert user is not None
        assert user.username == "testuser"
        assert user.id == regular_user.id

    def test_authenticate_invalid_password(self, db_session: Session, regular_user: User):
        """Test authentication with invalid password."""
        user = auth_service.authenticate_user("testuser", "wrongpassword", db=db_session)

        assert user is None

    def test_authenticate_nonexistent_user(self, db_session: Session):
        """Test authentication with non-existent username."""
        user = auth_service.authenticate_user("nonexistent", "anypassword", db=db_session)

        assert user is None

    def test_authenticate_empty_password(self, db_session: Session, regular_user: User):
        """Test authentication with empty password."""
        user = auth_service.authenticate_user("testuser", "", db=db_session)

        assert user is None

    def test_authenticate_empty_username(self, db_session: Session):
        """Test authentication with empty username."""
        user = auth_service.authenticate_user("", "anypassword", db=db_session)

        assert user is None

    def test_authenticate_admin_user(self, db_session: Session, admin_user: User):
        """Test authentication with admin credentials."""
        user = auth_service.authenticate_user(
            settings.admin_username,
            settings.admin_password,
            db=db_session
        )

        assert user is not None
        assert user.role == "admin"

    def test_authenticate_case_sensitive_username(self, db_session: Session, regular_user: User):
        """Test that username is case-sensitive."""
        user = auth_service.authenticate_user("TESTUSER", "Testpass123!", db=db_session)

        # Depends on implementation - typically case-sensitive
        # If user is found, it would mean case-insensitive
        assert user is None or user.username == "TESTUSER"

    def test_authenticate_inactive_user(self, db_session: Session):
        """Test authentication with inactive user."""
        # Create an inactive user
        inactive_user = user_service.create_user(
            UserCreate(
                username="inactive_user",
                email="inactive@example.com",
                password="Inactive123!",
                role="user"
            ),
            db=db_session
        )
        inactive_user.is_active = False
        db_session.commit()

        # Authentication should succeed (auth_service doesn't check is_active)
        # The is_active check is done at the route level
        user = auth_service.authenticate_user("inactive_user", "Inactive123!", db=db_session)

        # authenticate_user should return the user regardless of active status
        # The caller (route) decides what to do with inactive users
        assert user is not None


class TestCreateAccessToken:
    """Tests for create_access_token function."""

    def test_create_token_basic(self, db_session: Session, regular_user: User):
        """Test basic token creation."""
        token = auth_service.create_access_token(regular_user)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_contains_required_claims(self, db_session: Session, regular_user: User):
        """Test that token contains required claims."""
        token = auth_service.create_access_token(regular_user)

        # Decode without verification to check claims
        payload = jwt.decode(token, options={"verify_signature": False})

        assert "sub" in payload
        assert "username" in payload
        assert "role" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert payload["sub"] == str(regular_user.id)
        assert payload["username"] == regular_user.username
        assert payload["role"] == regular_user.role

    def test_create_token_custom_expiry(self, db_session: Session, regular_user: User):
        """Test token with custom expiry time."""
        token = auth_service.create_access_token(regular_user, expires_minutes=5)

        payload = jwt.decode(token, options={"verify_signature": False})

        # Check expiry is approximately 5 minutes from now
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = exp_time - now

        # Allow 10 seconds tolerance
        assert 4.8 * 60 < diff.total_seconds() < 5.2 * 60

    def test_create_token_default_expiry(self, db_session: Session, regular_user: User):
        """Test token with default expiry time."""
        token = auth_service.create_access_token(regular_user)

        payload = jwt.decode(token, options={"verify_signature": False})

        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = exp_time - now

        # Default expiry should be settings.token_expire_minutes
        expected_seconds = settings.token_expire_minutes * 60
        # Allow 30 seconds tolerance
        assert expected_seconds - 30 < diff.total_seconds() < expected_seconds + 30

    def test_create_token_for_admin(self, db_session: Session, admin_user: User):
        """Test token creation for admin user."""
        token = auth_service.create_access_token(admin_user)

        payload = jwt.decode(token, options={"verify_signature": False})

        assert payload["role"] == "admin"

    def test_create_token_signature_valid(self, db_session: Session, regular_user: User):
        """Test that token signature is valid."""
        token = auth_service.create_access_token(regular_user)

        # Should not raise if signature is valid
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

        assert payload["sub"] == str(regular_user.id)


class TestDecodeToken:
    """Tests for decode_token function."""

    def test_decode_valid_token(self, db_session: Session, regular_user: User):
        """Test decoding a valid token."""
        token = auth_service.create_access_token(regular_user)

        payload = auth_service.decode_token(token)

        assert payload.sub == str(regular_user.id)
        assert payload.username == regular_user.username
        assert payload.role == regular_user.role
        assert payload.exp is not None

    def test_decode_token_returns_token_payload(self, db_session: Session, regular_user: User):
        """Test that decode_token returns TokenPayload instance."""
        from app.schemas.auth import TokenPayload

        token = auth_service.create_access_token(regular_user)
        payload = auth_service.decode_token(token)

        assert isinstance(payload, TokenPayload)

    def test_decode_expired_token(self, db_session: Session, regular_user: User):
        """Test decoding an expired token."""
        # Create token that's already expired
        token = auth_service.create_access_token(regular_user, expires_minutes=-1)

        with pytest.raises(InvalidTokenError):
            auth_service.decode_token(token)

    def test_decode_invalid_signature(self, db_session: Session, regular_user: User):
        """Test decoding token with invalid signature."""
        token = auth_service.create_access_token(regular_user)

        # Tamper with the token
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".invalid_signature"

        with pytest.raises(InvalidTokenError):
            auth_service.decode_token(tampered)

    def test_decode_malformed_token(self, db_session: Session):
        """Test decoding malformed token."""
        with pytest.raises(InvalidTokenError):
            auth_service.decode_token("not.a.valid.token")

    def test_decode_empty_token(self, db_session: Session):
        """Test decoding empty token."""
        with pytest.raises(InvalidTokenError):
            auth_service.decode_token("")

    def test_decode_token_wrong_key(self, db_session: Session, regular_user: User):
        """Test decoding token signed with different key."""
        # Create a token with a different secret key
        payload = {
            "sub": str(regular_user.id),
            "username": regular_user.username,
            "role": regular_user.role,
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, "wrong_secret_key", algorithm="HS256")

        with pytest.raises(InvalidTokenError):
            auth_service.decode_token(token)


class TestSecurityModule:
    """Tests for core security module functions."""

    def test_create_refresh_token(self, db_session: Session, regular_user: User):
        """Test refresh token creation."""
        token, jti = security.create_refresh_token(regular_user)

        assert token is not None
        assert jti is not None
        assert isinstance(jti, str)

    def test_refresh_token_contains_jti(self, db_session: Session, regular_user: User):
        """Test that refresh token contains JTI."""
        token, jti = security.create_refresh_token(regular_user)

        payload = jwt.decode(token, options={"verify_signature": False})

        assert "jti" in payload
        assert payload["jti"] == jti

    def test_refresh_token_type_claim(self, db_session: Session, regular_user: User):
        """Test that refresh token has correct type claim."""
        token, _ = security.create_refresh_token(regular_user)

        payload = jwt.decode(token, options={"verify_signature": False})

        assert payload.get("type") == "refresh"

    def test_decode_access_token_rejects_refresh_token(self, db_session: Session, regular_user: User):
        """Test that access token decoder rejects refresh tokens."""
        refresh_token, _ = security.create_refresh_token(regular_user)

        with pytest.raises(jwt.InvalidTokenError):
            security.decode_token(refresh_token, token_type="access")

    def test_decode_refresh_token_rejects_access_token(self, db_session: Session, regular_user: User):
        """Test that refresh token decoder rejects access tokens."""
        access_token = security.create_access_token(regular_user)

        with pytest.raises(jwt.InvalidTokenError):
            security.decode_token(access_token, token_type="refresh")

    def test_get_user_id_from_token(self, db_session: Session, regular_user: User):
        """Test extracting user ID from token."""
        token = security.create_access_token(regular_user)

        user_id = security.get_user_id_from_token(token)

        assert user_id == str(regular_user.id)

    def test_get_user_id_from_expired_token(self, db_session: Session, regular_user: User):
        """Test extracting user ID from expired token."""
        # Create expired token
        expires_delta = timedelta(minutes=-1)
        token = security.create_access_token(regular_user, expires_delta=expires_delta)

        # Should still return user ID even if expired
        user_id = security.get_user_id_from_token(token)

        assert user_id == str(regular_user.id)
