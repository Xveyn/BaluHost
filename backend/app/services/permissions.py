from __future__ import annotations

from app.core.config import settings
from app.schemas.user import UserPublic


def is_privileged(user: UserPublic) -> bool:
    return user.role in settings.privileged_roles


class PermissionDeniedError(Exception):
    """Raised when a user attempts an unauthorized file operation."""


def ensure_owner_or_privileged(user: UserPublic, owner_id: str | None) -> None:
    if owner_id is None:
        if is_privileged(user):
            return
        raise PermissionDeniedError("Operation not permitted")

    # Normalize owner_id to int when possible for reliable comparisons
    try:
        owner_int = int(owner_id)
    except Exception:
        owner_int = None

    if owner_int is not None and owner_int == user.id:
        return

    if is_privileged(user):
        return

    raise PermissionDeniedError("Operation not permitted")


def can_view(user: UserPublic, owner_id: str | None) -> bool:
    if owner_id is None:
        return True
    try:
        owner_int = int(owner_id)
    except Exception:
        owner_int = None

    if owner_int is not None and owner_int == user.id:
        return True
    return is_privileged(user)
