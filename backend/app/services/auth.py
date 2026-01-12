from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core import security  # ✅ Security Fix #3: Use consolidated security module
from app.models.user import User
from app.schemas.auth import TokenPayload
from app.services import users as user_service
import logging

logger = logging.getLogger(__name__)


class InvalidTokenError(Exception):
    """Raised when a token cannot be decoded or validated."""


def authenticate_user(username: str, password: str, db: Optional[Session] = None) -> Optional[User]:
    """Authenticate user with username and password."""
    user = user_service.get_user_by_username(username, db=db)
    if not user:
        return None
    if not user_service.verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(user: User, expires_minutes: Optional[int] = None) -> str:
    """
    Create JWT access token for user.

    ✅ Security Fix #3: This now delegates to app.core.security.create_access_token()
    which uses settings.SECRET_KEY instead of settings.token_secret.
    Both auth systems now use the same secret key.
    """
    expires_delta = timedelta(minutes=expires_minutes or settings.token_expire_minutes)
    # Delegate to security module (which uses settings.SECRET_KEY)
    return security.create_access_token(user, expires_delta=expires_delta)


def decode_token(token: str) -> TokenPayload:
    """
    Decode JWT token and return TokenPayload.

    ✅ Security Fix #3: This now delegates to app.core.security.decode_token()
    which uses settings.SECRET_KEY instead of settings.token_secret.
    """
    try:
        # Delegate to security module (which uses settings.SECRET_KEY)
        decoded = security.decode_token(token, token_type="access")

        # Log successful decode at debug level (non-sensitive fields only)
        logger.debug("Token decoded: sub=%s, role=%s", decoded.get("sub"), decoded.get("role"))
    except jwt.PyJWTError as exc:
        # Log the exception to help debugging token validation issues
        logger.exception("Failed to decode token: %s", exc)
        raise InvalidTokenError("Failed to decode token") from exc

    exp = decoded.get("exp")
    if isinstance(exp, (int, float)):
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    elif isinstance(exp, str):
        exp_dt = datetime.fromtimestamp(float(exp), tz=timezone.utc)
    elif isinstance(exp, datetime):
        exp_dt = exp
    else:
        exp_dt = datetime.now(tz=timezone.utc)

    return TokenPayload(
        sub=str(decoded.get("sub")),
        username=str(decoded.get("username")),
        role=str(decoded.get("role")),
        exp=exp_dt,
    )
