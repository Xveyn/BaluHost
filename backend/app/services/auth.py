from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.schemas.auth import TokenPayload
from app.services import users as user_service


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
    """Create JWT access token for user."""
    expire_delta = timedelta(minutes=expires_minutes or settings.token_expire_minutes)
    expire_at = datetime.now(tz=timezone.utc) + expire_delta
    payload = {
        "sub": str(user.id),  # Convert to string for consistency
        "username": user.username,
        "role": user.role,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.token_secret, algorithm=settings.token_algorithm)


def decode_token(token: str) -> TokenPayload:
    try:
        decoded = jwt.decode(
            token,
            settings.token_secret,
            algorithms=[settings.token_algorithm],
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - small wrapper
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
