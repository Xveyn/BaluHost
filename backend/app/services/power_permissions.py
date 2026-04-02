"""Service for managing per-user power permissions."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.power_permissions import UserPowerPermission
from app.schemas.power_permissions import (
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

_ACTION_FIELD_MAP = {
    "soft_sleep": "can_soft_sleep",
    "wake": "can_wake",
    "suspend": "can_suspend",
    "wol": "can_wol",
}


def get_permissions(db: Session, user_id: int) -> UserPowerPermissionsResponse:
    """Get power permissions for a user. Returns defaults if no entry exists."""
    perm = db.query(UserPowerPermission).filter(
        UserPowerPermission.user_id == user_id
    ).first()

    if not perm:
        return UserPowerPermissionsResponse(user_id=user_id)

    granted_by_username = None
    if perm.granted_by:
        from app.models.user import User
        admin = db.query(User).filter(User.id == perm.granted_by).first()
        if admin:
            granted_by_username = admin.username

    return UserPowerPermissionsResponse(
        user_id=perm.user_id,
        can_soft_sleep=perm.can_soft_sleep,
        can_wake=perm.can_wake,
        can_suspend=perm.can_suspend,
        can_wol=perm.can_wol,
        granted_by=perm.granted_by,
        granted_by_username=granted_by_username,
        granted_at=perm.granted_at,
    )


def _apply_implications(
    can_soft_sleep: bool,
    can_wake: bool,
    can_suspend: bool,
    can_wol: bool,
    explicit_true: set[str] | None = None,
    explicit_false: set[str] | None = None,
) -> tuple[bool, bool, bool, bool]:
    """Apply implication rules to permissions.

    Forward: soft_sleep -> wake, suspend -> wol
    Reverse: !wake -> !soft_sleep, !wol -> !suspend

    Priority rules:
    - Forward implication only fires (and overrides a False prerequisite) when
      the dependent action was *explicitly* set True in this update call.
    - Reverse implication fires when a prerequisite is False, unless the
      dependent was explicitly set True in this same update call.
    - When a prerequisite is explicitly set False, reverse always applies
      (no forward can override it from DB-inherited True state).
    """
    if explicit_true is None:
        explicit_true = set()
    if explicit_false is None:
        explicit_false = set()

    # Forward: explicit grant of dependent forces its prerequisite True
    if "can_soft_sleep" in explicit_true:
        can_wake = True
    if "can_suspend" in explicit_true:
        can_wol = True

    # Reverse: False prerequisite clears dependent, unless dependent was
    # explicitly granted in this same update (forward wins in that case)
    if not can_wake and "can_soft_sleep" not in explicit_true:
        can_soft_sleep = False
    if not can_wol and "can_suspend" not in explicit_true:
        can_suspend = False

    return can_soft_sleep, can_wake, can_suspend, can_wol


def update_permissions(
    db: Session,
    user_id: int,
    update: UserPowerPermissionsUpdate,
    granted_by: int,
) -> UserPowerPermissionsResponse:
    """Create or update power permissions for a user."""
    audit_logger = get_audit_logger_db()

    perm = db.query(UserPowerPermission).filter(
        UserPowerPermission.user_id == user_id
    ).first()

    if not perm:
        perm = UserPowerPermission(user_id=user_id, granted_by=granted_by)
        db.add(perm)

    old_values = {
        "can_soft_sleep": perm.can_soft_sleep,
        "can_wake": perm.can_wake,
        "can_suspend": perm.can_suspend,
        "can_wol": perm.can_wol,
    }

    # Track which fields were explicitly set so implications can be applied
    # with the correct priority.
    explicit_true: set[str] = set()
    explicit_false: set[str] = set()

    # Apply explicit updates
    if update.can_soft_sleep is not None:
        perm.can_soft_sleep = update.can_soft_sleep
        if update.can_soft_sleep:
            explicit_true.add("can_soft_sleep")
        else:
            explicit_false.add("can_soft_sleep")
    if update.can_wake is not None:
        perm.can_wake = update.can_wake
        if not update.can_wake:
            explicit_false.add("can_wake")
    if update.can_suspend is not None:
        perm.can_suspend = update.can_suspend
        if update.can_suspend:
            explicit_true.add("can_suspend")
        else:
            explicit_false.add("can_suspend")
    if update.can_wol is not None:
        perm.can_wol = update.can_wol
        if not update.can_wol:
            explicit_false.add("can_wol")

    # Apply implication rules
    perm.can_soft_sleep, perm.can_wake, perm.can_suspend, perm.can_wol = (
        _apply_implications(
            perm.can_soft_sleep, perm.can_wake, perm.can_suspend, perm.can_wol,
            explicit_true=explicit_true,
            explicit_false=explicit_false,
        )
    )

    perm.granted_by = granted_by

    db.commit()
    db.refresh(perm)

    new_values = {
        "can_soft_sleep": perm.can_soft_sleep,
        "can_wake": perm.can_wake,
        "can_suspend": perm.can_suspend,
        "can_wol": perm.can_wol,
    }

    # Audit log
    from app.models.user import User
    admin = db.query(User).filter(User.id == granted_by).first()
    target = db.query(User).filter(User.id == user_id).first()

    audit_logger.log_security_event(
        action="power_permission_changed",
        user=admin.username if admin else str(granted_by),
        resource=f"user:{target.username if target else user_id}",
        details={"old": old_values, "new": new_values},
        success=True,
        db=db,
    )

    return get_permissions(db, user_id)


def check_permission(db: Session, user_id: int, action: str) -> bool:
    """Check if a user has a specific power permission.

    Args:
        db: Database session
        user_id: User ID to check
        action: One of 'soft_sleep', 'wake', 'suspend', 'wol'

    Returns:
        True if the user has the permission, False otherwise.
    """
    field = _ACTION_FIELD_MAP.get(action)
    if not field:
        return False

    perm = db.query(UserPowerPermission).filter(
        UserPowerPermission.user_id == user_id
    ).first()

    if not perm:
        return False

    return bool(getattr(perm, field, False))
