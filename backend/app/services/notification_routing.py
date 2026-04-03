"""Service for managing per-user notification routing."""

import logging

from sqlalchemy.orm import Session

from app.models.notification_routing import UserNotificationRouting
from app.schemas.notification_routing import (
    NotificationRoutingResponse,
    NotificationRoutingUpdate,
)
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

# Maps category string to model field name
_CATEGORY_FIELD_MAP = {
    "raid": "receive_raid",
    "smart": "receive_smart",
    "backup": "receive_backup",
    "scheduler": "receive_scheduler",
    "system": "receive_system",
    "security": "receive_security",
    "sync": "receive_sync",
    "vpn": "receive_vpn",
}


def get_routing(db: Session, user_id: int) -> NotificationRoutingResponse:
    """Get notification routing for a user. Returns defaults if no entry exists."""
    routing = db.query(UserNotificationRouting).filter(
        UserNotificationRouting.user_id == user_id
    ).first()

    if not routing:
        return NotificationRoutingResponse(user_id=user_id)

    granted_by_username = None
    if routing.granted_by:
        from app.models.user import User
        admin = db.query(User).filter(User.id == routing.granted_by).first()
        if admin:
            granted_by_username = admin.username

    return NotificationRoutingResponse(
        user_id=routing.user_id,
        receive_raid=routing.receive_raid,
        receive_smart=routing.receive_smart,
        receive_backup=routing.receive_backup,
        receive_scheduler=routing.receive_scheduler,
        receive_system=routing.receive_system,
        receive_security=routing.receive_security,
        receive_sync=routing.receive_sync,
        receive_vpn=routing.receive_vpn,
        granted_by=routing.granted_by,
        granted_by_username=granted_by_username,
        granted_at=routing.granted_at,
    )


def update_routing(
    db: Session,
    user_id: int,
    update: NotificationRoutingUpdate,
    granted_by: int,
) -> NotificationRoutingResponse:
    """Create or update notification routing for a user."""
    audit_logger = get_audit_logger_db()

    routing = db.query(UserNotificationRouting).filter(
        UserNotificationRouting.user_id == user_id
    ).first()

    if not routing:
        routing = UserNotificationRouting(user_id=user_id, granted_by=granted_by)
        db.add(routing)

    old_values = {field: getattr(routing, field) for field in _CATEGORY_FIELD_MAP.values()}

    for category, field in _CATEGORY_FIELD_MAP.items():
        value = getattr(update, field)
        if value is not None:
            setattr(routing, field, value)

    routing.granted_by = granted_by

    db.commit()
    db.refresh(routing)

    new_values = {field: getattr(routing, field) for field in _CATEGORY_FIELD_MAP.values()}

    # Audit log
    from app.models.user import User
    admin = db.query(User).filter(User.id == granted_by).first()
    target = db.query(User).filter(User.id == user_id).first()

    audit_logger.log_security_event(
        action="notification_routing_changed",
        user=admin.username if admin else str(granted_by),
        resource=f"user:{target.username if target else user_id}",
        details={"old": old_values, "new": new_values},
        success=True,
        db=db,
    )

    return get_routing(db, user_id)


def check_routing(db: Session, user_id: int, category: str) -> bool:
    """Check if a user has routing enabled for a specific category."""
    field = _CATEGORY_FIELD_MAP.get(category)
    if not field:
        return False

    routing = db.query(UserNotificationRouting).filter(
        UserNotificationRouting.user_id == user_id
    ).first()

    if not routing:
        return False

    return bool(getattr(routing, field, False))


def get_routed_user_ids(db: Session, category: str) -> list[int]:
    """Get all non-admin user IDs with routing enabled for a category.

    Args:
        db: Database session
        category: Notification category (raid, smart, etc.)

    Returns:
        List of user IDs with routing enabled for this category
    """
    field = _CATEGORY_FIELD_MAP.get(category)
    if not field:
        return []

    from app.models.user import User

    routing_rows = db.query(UserNotificationRouting.user_id).join(
        User, UserNotificationRouting.user_id == User.id
    ).filter(
        getattr(UserNotificationRouting, field) == True,
        User.role != "admin",
        User.is_active == True,
    ).all()

    return [uid for (uid,) in routing_rows]
