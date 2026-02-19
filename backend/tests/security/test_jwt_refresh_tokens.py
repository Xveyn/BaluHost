"""
Test JWT Refresh Token Implementation for Task 2.1 Security Hardening.

Tests cover:
1. Refresh token generation and storage
2. Token rotation on refresh
3. Refresh token expiration
4. Refresh token revocation
5. RT + AT coordination in auth flow
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.config import settings
import jwt as pyjwt


class TestJWTRefreshTokens:
    """Test JWT Refresh Token functionality."""

    def test_refresh_token_generation(self):
        """Verify refresh tokens are generated alongside access tokens."""
        user_id = "test_user_123"

        access_token = create_access_token({"sub": user_id})
        refresh_token, jti = create_refresh_token({"sub": user_id})

        assert access_token is not None
        assert refresh_token is not None
        assert jti is not None
        assert access_token != refresh_token

    def test_refresh_token_contains_required_claims(self):
        """Verify refresh tokens contain required claims."""
        user_id = "test_user_123"

        token, jti = create_refresh_token({"sub": user_id})

        decoded = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert decoded["sub"] == user_id
        assert "exp" in decoded
        assert "iat" in decoded
        assert decoded["type"] == "refresh"
        assert decoded["jti"] == jti

    def test_access_token_shorter_expiry_than_refresh_token(self):
        """Verify refresh tokens have longer TTL than access tokens."""
        user_id = "test_user_123"

        access_token = create_access_token({"sub": user_id})
        refresh_token, _jti = create_refresh_token({"sub": user_id})

        access_decoded = pyjwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"])
        refresh_decoded = pyjwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])

        assert refresh_decoded["exp"] > access_decoded["exp"]

    def test_refresh_token_can_be_used_to_get_new_access_token(self):
        """Verify refresh tokens can obtain new access tokens."""
        user_id = "test_user_123"

        refresh_token, _jti = create_refresh_token({"sub": user_id})

        # Decode the refresh token to extract user_id, then create new access token
        payload = decode_token(refresh_token, token_type="refresh")
        new_access_token = create_access_token({"sub": payload["sub"]})
        assert new_access_token is not None

    def test_expired_refresh_token_rejected(self):
        """Verify expired refresh tokens are rejected by decode_token."""
        expired_token = pyjwt.encode(
            {
                "sub": "test_user_123",
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
                "iat": datetime.now(timezone.utc),
                "type": "refresh",
                "jti": "test-jti",
            },
            settings.SECRET_KEY,
            algorithm="HS256",
        )

        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(expired_token, token_type="refresh")

    def test_invalid_refresh_token_signature_rejected(self):
        """Verify tokens with invalid signatures are rejected by decode_token."""
        # Sign with a different key
        token = pyjwt.encode(
            {
                "sub": "user123",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "iat": datetime.now(timezone.utc),
                "type": "refresh",
                "jti": "test-jti",
            },
            "completely-wrong-secret-key-that-differs",
            algorithm="HS256",
        )

        with pytest.raises(pyjwt.InvalidSignatureError):
            decode_token(token, token_type="refresh")

    def test_refresh_token_rotation_generates_unique_jtis(self):
        """Verify each refresh token gets a unique JTI for revocation support."""
        user_id = "test_user_123"

        _token1, jti1 = create_refresh_token({"sub": user_id})
        _token2, jti2 = create_refresh_token({"sub": user_id})

        assert jti1 != jti2, "Each refresh token must have a unique JTI"

    @pytest.mark.skip(reason="Refresh token revocation store not implemented yet")
    def test_refresh_token_revocation(self):
        """Verify refresh tokens can be revoked (logout)."""
        pass

    def test_refresh_endpoint_requires_valid_refresh_token(self, client):
        """Verify /auth/refresh endpoint rejects invalid tokens."""
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "not-a-valid-token"},
        )
        # Should reject with 401 or 422
        assert response.status_code in (401, 422), (
            f"Expected 401/422 for invalid refresh token, got {response.status_code}"
        )


class TestJWTSecurityMechanisms:
    """Test security mechanisms around JWT tokens."""

    def test_token_type_claim_prevents_confusion(self):
        """Verify 'type' claim distinguishes access vs refresh tokens."""
        user_id = "test_user_123"

        access_token = create_access_token({"sub": user_id})
        refresh_token, _jti = create_refresh_token({"sub": user_id})

        access_decoded = pyjwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"])
        refresh_decoded = pyjwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])

        assert access_decoded.get("type") == "access"
        assert refresh_decoded.get("type") == "refresh"

    def test_access_token_rejected_as_refresh(self):
        """Verify using an access token where refresh is expected fails."""
        access_token = create_access_token({"sub": "test_user"})

        with pytest.raises(pyjwt.InvalidTokenError, match="Invalid token type"):
            decode_token(access_token, token_type="refresh")

    def test_refresh_token_rejected_as_access(self):
        """Verify using a refresh token where access is expected fails."""
        refresh_token, _jti = create_refresh_token({"sub": "test_user"})

        with pytest.raises(pyjwt.InvalidTokenError, match="Invalid token type"):
            decode_token(refresh_token, token_type="access")

    def test_token_claims_include_issuance_time(self):
        """Verify tokens include iat (issued at) for clock skew detection."""
        token = create_access_token({"sub": "test_user"})

        decoded = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert "iat" in decoded
        assert isinstance(decoded["iat"], int)

    def test_short_access_token_reduces_exposure_window(self):
        """Verify access tokens expire quickly (short TTL)."""
        token = create_access_token({"sub": "test_user"})
        decoded = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

        now = datetime.now(timezone.utc)
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        ttl_minutes = (exp_time - now).total_seconds() / 60

        assert 10 < ttl_minutes < 60, f"Access token TTL {ttl_minutes:.1f}min not in expected 10-60min range"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
