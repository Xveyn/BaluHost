"""
JWT Security utilities for FastAPI authentication.

Handles:
- Access token generation (short TTL)
- Refresh token generation (long TTL)
- Token verification and decoding
- Token rotation

✅ Security Fix #6: Adds JTI (JWT ID) to refresh tokens for revocation support.
"""

from datetime import datetime, timedelta, timezone
import jwt
import uuid
from app.core.config import settings
from app.models.user import User


def create_access_token(user: User | dict, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT access token with short TTL (15 minutes default).

    Args:
        user: User object or dict with user data (must have 'id' field)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    if isinstance(user, dict):
        user_id = user.get("id") or user.get("sub")
        username = user.get("username")
        role = user.get("role")
    else:
        user_id = user.id
        username = user.username
        role = user.role

    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),
        "username": username,  # ✅ Security Fix #3: Add username to token
        "role": role,  # ✅ Security Fix #3: Add role to token
        "type": "access",  # Token type claim - prevents token confusion attacks
        "exp": expire,
        "iat": now,
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,  # ✅ Security Fix #3: Use single SECRET_KEY
        algorithm="HS256"
    )

    return encoded_jwt


def create_refresh_token(user: User | dict, expires_delta: timedelta | None = None, jti: str | None = None) -> tuple[str, str]:
    """
    Create a JWT refresh token with long TTL (7 days default).

    Used to obtain new access tokens without re-authenticating.

    ✅ Security Fix #6: Now includes JTI (JWT ID) for token revocation support.

    Args:
        user: User object or dict with user data (must have 'id' field)
        expires_delta: Optional custom expiration time
        jti: Optional JWT ID (generated if not provided)

    Returns:
        Tuple of (encoded JWT token string, JTI)
    """
    if isinstance(user, dict):
        user_id = user.get("id") or user.get("sub")
    else:
        user_id = user.id

    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # Generate unique JWT ID for revocation support
    if jti is None:
        jti = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),
        "jti": jti,  # ✅ Security Fix #6: Add JWT ID for revocation
        "type": "refresh",  # Token type claim - prevents token confusion attacks
        "exp": expire,
        "iat": now,
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256"
    )

    return encoded_jwt, jti


def create_sse_token(user_id: int | str, upload_id: str, expires_seconds: int = 60) -> str:
    """
    Create a short-lived, scoped token for SSE upload progress streaming.

    This token is intentionally minimal — it only grants access to a single
    SSE progress stream and expires quickly, so it is safe to pass as a
    query parameter (which gets logged by reverse proxies).

    Args:
        user_id: The authenticated user's ID.
        upload_id: The specific upload session this token grants access to.
        expires_seconds: Token lifetime in seconds (default 60).

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "upload_id": upload_id,
        "type": "sse",
        "exp": now + timedelta(seconds=expires_seconds),
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_2fa_pending_token(user_id: int | str, expires_seconds: int = 300) -> str:
    """
    Create a short-lived token indicating that password was verified but 2FA is pending.

    Args:
        user_id: The authenticated user's ID.
        expires_seconds: Token lifetime in seconds (default 5 minutes).

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "2fa_pending",
        "exp": now + timedelta(seconds=expires_seconds),
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str, token_type: str = "access") -> dict:
    """
    Decode and verify a JWT token.
    
    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")
        
    Returns:
        Decoded payload dict
        
    Raises:
        jwt.ExpiredSignatureError: If token has expired
        jwt.InvalidSignatureError: If signature is invalid
        jwt.InvalidTokenError: For other token validation errors
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        
        # Verify token type matches expectation
        if payload.get("type") != token_type:
            raise jwt.InvalidTokenError(
                f"Invalid token type. Expected '{token_type}', got '{payload.get('type')}'"
            )
        
        return payload
    except jwt.ExpiredSignatureError:
        raise
    except jwt.InvalidSignatureError:
        raise
    except jwt.InvalidTokenError:
        raise


def get_user_id_from_token(token: str, token_type: str = "access") -> str:
    """
    Extract user ID from token without raising on expiration.
    
    Useful for logging who initiated an expired request.
    
    Args:
        token: JWT token string
        token_type: Expected token type
        
    Returns:
        User ID from token
        
    Raises:
        jwt.InvalidTokenError: For signature or type validation errors
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": False}  # Don't fail on expiration
        )
        
        if payload.get("type") != token_type:
            raise jwt.InvalidTokenError(
                f"Invalid token type. Expected '{token_type}', got '{payload.get('type')}'"
            )
        
        return payload.get("sub")
    except jwt.InvalidSignatureError:
        raise
    except jwt.InvalidTokenError:
        raise
