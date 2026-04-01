"""Tests for setup wizard token creation and verification."""

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_setup_token, decode_token


class TestCreateSetupToken:
    """Tests for the create_setup_token function."""

    def test_returns_jwt_string(self):
        """create_setup_token returns a non-empty JWT string."""
        token = create_setup_token(user_id=1, username="admin")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_has_setup_type_claim(self):
        """Setup token has type='setup' claim."""
        token = create_setup_token(user_id=1, username="admin")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["type"] == "setup"

    def test_has_sub_claim(self):
        """Setup token has 'sub' claim matching user_id."""
        token = create_setup_token(user_id=42, username="admin")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == "42"

    def test_has_username_claim(self):
        """Setup token has 'username' claim matching the provided username."""
        token = create_setup_token(user_id=1, username="myadmin")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["username"] == "myadmin"

    def test_has_admin_role_claim(self):
        """Setup token has role='admin' claim."""
        token = create_setup_token(user_id=1, username="admin")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["role"] == "admin"

    def test_has_expiry(self):
        """Setup token has an 'exp' claim."""
        token = create_setup_token(user_id=1, username="admin")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert "exp" in payload

    def test_has_iat(self):
        """Setup token has an 'iat' (issued-at) claim."""
        token = create_setup_token(user_id=1, username="admin")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert "iat" in payload

    def test_string_user_id(self):
        """create_setup_token accepts string user_id and stores it as string."""
        token = create_setup_token(user_id="99", username="admin")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == "99"


class TestSetupTokenDecoding:
    """Tests for decoding setup tokens via decode_token."""

    def test_decode_with_setup_type_succeeds(self):
        """decode_token succeeds when token_type='setup'."""
        token = create_setup_token(user_id=1, username="admin")
        payload = decode_token(token, token_type="setup")
        assert payload["type"] == "setup"
        assert payload["sub"] == "1"
        assert payload["username"] == "admin"
        assert payload["role"] == "admin"

    def test_rejected_when_decoded_as_access(self):
        """Setup token is rejected when decoded with token_type='access'."""
        token = create_setup_token(user_id=1, username="admin")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(token, token_type="access")

    def test_rejected_when_decoded_as_refresh(self):
        """Setup token is rejected when decoded with token_type='refresh'."""
        token = create_setup_token(user_id=1, username="admin")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(token, token_type="refresh")


class TestSetupConfigFields:
    """Tests for setup wizard config fields."""

    def test_skip_setup_exists_and_is_bool(self):
        """Config field skip_setup exists and is a bool (default False, overridable via env)."""
        assert hasattr(settings, "skip_setup")
        assert isinstance(settings.skip_setup, bool)

    def test_setup_secret_exists_and_defaults_empty(self):
        """Config field setup_secret exists and defaults to empty string."""
        assert hasattr(settings, "setup_secret")
        assert settings.setup_secret == ""
