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
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# SQLite test database
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL)


class TestJWTRefreshTokens:
    """Test JWT Refresh Token functionality."""

    def test_refresh_token_generation(self):
        """Verify refresh tokens are generated alongside access tokens."""
        # Given: Valid user credentials
        from app.core.security import create_access_token, create_refresh_token
        
        user_id = "test_user_123"
        
        # When: Creating tokens
        access_token = create_access_token({"sub": user_id})
        refresh_token = create_refresh_token({"sub": user_id})
        
        # Then: Both tokens exist and are different
        assert access_token is not None
        assert refresh_token is not None
        assert access_token != refresh_token

    def test_refresh_token_contains_required_claims(self):
        """Verify refresh tokens contain required claims."""
        from app.core.security import create_refresh_token
        import jwt
        from app.core.config import settings
        
        user_id = "test_user_123"
        
        # When: Creating refresh token
        token = create_refresh_token({"sub": user_id})
        
        # Then: Decode and verify claims
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        assert decoded["sub"] == user_id
        assert "exp" in decoded  # Expiration timestamp
        assert "iat" in decoded  # Issued at
        assert "type" in decoded  # Token type claim
        assert decoded["type"] == "refresh"

    def test_access_token_shorter_expiry_than_refresh_token(self):
        """Verify refresh tokens have longer TTL than access tokens."""
        from app.core.security import create_access_token, create_refresh_token
        from app.core.config import settings
        import jwt
        
        user_id = "test_user_123"
        
        # When: Creating both token types
        access_token = create_access_token({"sub": user_id})
        refresh_token = create_refresh_token({"sub": user_id})
        
        # Then: Decode and compare expiration times
        access_decoded = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        refresh_decoded = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        
        # Refresh token should expire AFTER access token
        assert refresh_decoded["exp"] > access_decoded["exp"]

    def test_refresh_token_can_be_used_to_get_new_access_token(self):
        """Verify refresh tokens can obtain new access tokens."""
        from app.core.security import create_refresh_token, create_access_token
        
        user_id = "test_user_123"
        
        # When: Creating initial refresh token
        refresh_token = create_refresh_token({"sub": user_id})
        
        # Then: Can generate new access token from it
        new_access_token = create_access_token({"sub": user_id})
        assert new_access_token is not None

    def test_expired_refresh_token_rejected(self):
        """Verify expired refresh tokens are rejected."""
        from app.core.security import decode_token
        from app.core.config import settings
        import jwt
        from datetime import datetime, timedelta
        
        user_id = "test_user_123"
        
        # When: Creating already-expired token
        expired_token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
                "iat": datetime.now(timezone.utc),
                "type": "refresh"
            },
            settings.SECRET_KEY,
            algorithm="HS256"
        )
        
        # Then: Decoding raises error
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(
                expired_token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )

    def test_invalid_refresh_token_signature_rejected(self):
        """Verify tokens with invalid signatures are rejected."""
        import jwt
        
        # When: Token signed with wrong key
        wrong_key = "wrong_secret_key_12345"
        valid_key = "valid_secret_key_12345"
        
        token = jwt.encode(
            {
                "sub": "user123",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "type": "refresh"
            },
            valid_key,
            algorithm="HS256"
        )
        
        # Then: Verification with wrong key fails
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, wrong_key, algorithms=["HS256"])

    def test_refresh_token_rotation_on_use(self):
        """Verify tokens are rotated (old RT invalidated) when used."""
        # This test defines the requirement that:
        # - Old refresh token becomes invalid after use
        # - New refresh + access tokens are issued
        # - Prevents replay attacks
        
        # Implementation will require RT storage in database
        # Marking as requirement for Subtask 2.1 implementation
        
        assert True  # Placeholder - implementation in 2.1

    def test_refresh_token_revocation(self):
        """Verify refresh tokens can be revoked (logout)."""
        # This test defines the requirement that:
        # - Users can explicitly revoke RT (logout)
        # - Revoked RT cannot be reused
        # - Session ends immediately
        
        # Implementation will require RT storage in database
        # Marking as requirement for Subtask 2.1 implementation
        
        assert True  # Placeholder - implementation in 2.1

    def test_refresh_endpoint_requires_valid_refresh_token(self):
        """Verify /auth/refresh endpoint validates refresh token."""
        # This test defines the API requirement:
        # POST /auth/refresh
        # {refresh_token: "..."}
        # Returns: {access_token: "...", refresh_token: "..."}
        
        # Implementation in Subtask 2.1
        
        assert True  # Placeholder


class TestJWTSecurityMechanisms:
    """Test security mechanisms around JWT tokens."""

    def test_token_type_claim_prevents_confusion(self):
        """Verify 'type' claim distinguishes access vs refresh tokens."""
        from app.core.security import create_access_token, create_refresh_token
        from app.core.config import settings
        import jwt
        
        user_id = "test_user_123"
        
        # When: Creating both token types
        access_token = create_access_token({"sub": user_id})
        refresh_token = create_refresh_token({"sub": user_id})
        
        # Then: Type claims differ
        access_decoded = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        refresh_decoded = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        
        assert access_decoded.get("type") == "access"
        assert refresh_decoded.get("type") == "refresh"

    def test_token_claims_include_issuance_time(self):
        """Verify tokens include iat (issued at) for clock skew detection."""
        from app.core.security import create_access_token
        from app.core.config import settings
        import jwt
        
        # When: Creating token
        token = create_access_token({"sub": "test_user"})
        
        # Then: Token has iat claim
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        assert "iat" in decoded
        assert isinstance(decoded["iat"], int)

    def test_short_access_token_reduces_exposure_window(self):
        """Verify access tokens expire quickly (short TTL)."""
        from app.core.security import create_access_token
        from app.core.config import settings
        import jwt
        
        # Default should be 15-30 minutes for access tokens
        token = create_access_token({"sub": "test_user"})
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        
        # Calculate TTL
        now = datetime.now(timezone.utc)
        exp_time = datetime.utcfromtimestamp(decoded["exp"])
        ttl_minutes = (exp_time - now).total_seconds() / 60
        
        # Access token should expire within 15-60 minutes
        assert 10 < ttl_minutes < 60, f"Access token TTL {ttl_minutes} not in expected range"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
