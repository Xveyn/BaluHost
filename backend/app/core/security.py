"""
JWT Security utilities for FastAPI authentication.

Handles:
- Access token generation (short TTL)
- Refresh token generation (long TTL)
- Token verification and decoding
- Token rotation
"""

from datetime import datetime, timedelta, timezone
import jwt
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
    else:
        user_id = user.id
        
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    
    payload = {
        "sub": str(user_id),
        "type": "access",  # Token type claim - prevents token confusion attacks
        "exp": expire,
        "iat": now,
    }
    
    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256"
    )
    
    return encoded_jwt


def create_refresh_token(user: User | dict, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT refresh token with long TTL (7 days default).
    
    Used to obtain new access tokens without re-authenticating.
    
    Args:
        user: User object or dict with user data (must have 'id' field)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    if isinstance(user, dict):
        user_id = user.get("id") or user.get("sub")
    else:
        user_id = user.id
        
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    
    payload = {
        "sub": str(user_id),
        "type": "refresh",  # Token type claim - prevents token confusion attacks
        "exp": expire,
        "iat": now,
    }
    
    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256"
    )
    
    return encoded_jwt


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
