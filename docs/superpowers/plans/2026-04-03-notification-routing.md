# Notification Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admins to configure which non-admin users receive system notification categories (RAID, SMART, etc.) via push and in-app channels.

**Architecture:** New `user_notification_routing` table (one boolean per category, one row per user) following the Power Permissions pattern. Routing logic in `events.py` and `service.py` extended to include routed non-admin users alongside admins. Frontend adds toggle section in user edit dialog and read-only display in user's notification settings.

**Tech Stack:** SQLAlchemy 2.0, FastAPI, Pydantic v2, React, TypeScript, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-04-03-notification-routing-design.md`

---

## File Map

**Create:**
- `backend/app/models/notification_routing.py` — ORM model
- `backend/app/schemas/notification_routing.py` — Pydantic schemas
- `backend/app/services/notification_routing.py` — service layer
- `client/src/api/notificationRouting.ts` — frontend API module
- `client/src/components/user-management/NotificationRoutingSection.tsx` — admin toggle UI
- `backend/tests/test_notification_routing.py` — tests

**Modify:**
- `backend/app/models/__init__.py` — register new model
- `backend/app/api/routes/users.py` — add admin GET/PUT endpoints
- `backend/app/api/routes/notifications.py` — add user GET my-routing endpoint
- `backend/app/services/notifications/events.py` — extend `_send_push_sync()` for routed users
- `backend/app/services/notifications/service.py` — extend `dispatch()`, `_send_push_to_admins()`, `_broadcast_to_admins()`
- `client/src/components/user-management/UserFormModal.tsx` — add NotificationRoutingSection
- `client/src/pages/NotificationPreferencesPage.tsx` — add read-only routing display

---

### Task 1: Model

**Files:**
- Create: `backend/app/models/notification_routing.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the model file**

```python
# backend/app/models/notification_routing.py
"""Database model for user notification routing."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class UserNotificationRouting(Base):
    """Per-user notification category routing, granted by an admin."""

    __tablename__ = "user_notification_routing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    receive_raid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_smart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_backup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_scheduler: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_security: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    receive_vpn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    granted_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    granted_by_user = relationship("User", foreign_keys=[granted_by])
```

- [ ] **Step 2: Register model in `__init__.py`**

Add import after line 85 (`from app.models.power_permissions import UserPowerPermission`):
```python
from app.models.notification_routing import UserNotificationRouting
```

Add to `__all__` list after `"UserPowerPermission"` (line 173):
```python
    "UserNotificationRouting",
```

- [ ] **Step 3: Create Alembic migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add user_notification_routing table"
```

- [ ] **Step 4: Apply migration**

Run:
```bash
cd backend && alembic upgrade head
```
Expected: migration applies, `user_notification_routing` table created.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/notification_routing.py backend/app/models/__init__.py backend/alembic/versions/
git commit -m "feat(notifications): add UserNotificationRouting model"
```

---

### Task 2: Schemas

**Files:**
- Create: `backend/app/schemas/notification_routing.py`

- [ ] **Step 1: Create the schemas file**

```python
# backend/app/schemas/notification_routing.py
"""Pydantic schemas for user notification routing."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationRoutingResponse(BaseModel):
    """Response schema for notification routing (admin view)."""

    user_id: int
    receive_raid: bool = False
    receive_smart: bool = False
    receive_backup: bool = False
    receive_scheduler: bool = False
    receive_system: bool = False
    receive_security: bool = False
    receive_sync: bool = False
    receive_vpn: bool = False
    granted_by: Optional[int] = None
    granted_by_username: Optional[str] = None
    granted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationRoutingUpdate(BaseModel):
    """Request schema for updating notification routing."""

    receive_raid: Optional[bool] = Field(default=None, description="Receive RAID notifications")
    receive_smart: Optional[bool] = Field(default=None, description="Receive SMART notifications")
    receive_backup: Optional[bool] = Field(default=None, description="Receive Backup notifications")
    receive_scheduler: Optional[bool] = Field(default=None, description="Receive Scheduler notifications")
    receive_system: Optional[bool] = Field(default=None, description="Receive System notifications")
    receive_security: Optional[bool] = Field(default=None, description="Receive Security notifications")
    receive_sync: Optional[bool] = Field(default=None, description="Receive Sync notifications")
    receive_vpn: Optional[bool] = Field(default=None, description="Receive VPN notifications")


class MyNotificationRoutingResponse(BaseModel):
    """Response for the user's own routing (read-only, no admin metadata)."""

    receive_raid: bool = False
    receive_smart: bool = False
    receive_backup: bool = False
    receive_scheduler: bool = False
    receive_system: bool = False
    receive_security: bool = False
    receive_sync: bool = False
    receive_vpn: bool = False
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/notification_routing.py
git commit -m "feat(notifications): add notification routing schemas"
```

---

### Task 3: Service

**Files:**
- Create: `backend/app/services/notification_routing.py`

- [ ] **Step 1: Create the service file**

```python
# backend/app/services/notification_routing.py
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/notification_routing.py
git commit -m "feat(notifications): add notification routing service"
```

---

### Task 4: Admin API Routes

**Files:**
- Modify: `backend/app/api/routes/users.py` (after line 373)

- [ ] **Step 1: Add schema import and endpoints**

Add after line 373 (after the `update_user_power_permissions` function) in `users.py`:

```python

from app.schemas.notification_routing import NotificationRoutingResponse, NotificationRoutingUpdate


@router.get("/{user_id}/notification-routing", response_model=NotificationRoutingResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_user_notification_routing(
    request: Request,
    response: Response,
    user_id: int,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> NotificationRoutingResponse:
    """Get notification routing for a user (admin only)."""
    from app.services.notification_routing import get_routing

    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return get_routing(db, user_id)


@router.put("/{user_id}/notification-routing", response_model=NotificationRoutingResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_user_notification_routing(
    request: Request,
    response: Response,
    user_id: int,
    body: NotificationRoutingUpdate,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> NotificationRoutingResponse:
    """Update notification routing for a user (admin only)."""
    from app.services.notification_routing import update_routing

    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return update_routing(db, user_id, body, granted_by=current_admin.id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/users.py
git commit -m "feat(notifications): add admin notification routing endpoints"
```

---

### Task 5: User Read-Only API Route

**Files:**
- Modify: `backend/app/api/routes/notifications.py` (after the preferences endpoints, around line 281)

- [ ] **Step 1: Add my-routing endpoint**

Add after line 281 (after `update_notification_preferences`) in `notifications.py`:

```python


@router.get("/my-routing")
@user_limiter.limit(get_limit("admin_operations"))
async def get_my_notification_routing(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's notification routing (read-only)."""
    from app.services.notification_routing import get_routing
    from app.schemas.notification_routing import MyNotificationRoutingResponse

    routing = get_routing(db, current_user.id)
    return MyNotificationRoutingResponse(
        receive_raid=routing.receive_raid,
        receive_smart=routing.receive_smart,
        receive_backup=routing.receive_backup,
        receive_scheduler=routing.receive_scheduler,
        receive_system=routing.receive_system,
        receive_security=routing.receive_security,
        receive_sync=routing.receive_sync,
        receive_vpn=routing.receive_vpn,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/notifications.py
git commit -m "feat(notifications): add user my-routing read-only endpoint"
```

---

### Task 6: Extend Routing Logic

**Files:**
- Modify: `backend/app/services/notifications/service.py`
- Modify: `backend/app/services/notifications/events.py`

- [ ] **Step 1: Extend `_send_push_to_admins` in `service.py`**

Rename `_send_push_to_admins` to `_send_push_to_recipients` and extend to include routed users. Replace lines 167-224 in `service.py`:

```python
    async def _send_push_to_recipients(
        self, db: Session, notification: Notification
    ) -> None:
        """Send push notification to admin users and routed non-admin users.

        Args:
            db: Database session
            notification: Notification to send
        """
        from app.services.notifications.firebase import FirebaseService
        from app.models.mobile import MobileDevice

        if not FirebaseService.is_available():
            return

        try:
            # 1. Always include all admin users
            admin_ids = [
                uid for (uid,) in db.query(User.id).filter(
                    User.role == "admin",
                    User.is_active == True,
                ).all()
            ]

            # 2. Include non-admin users with routing for this category
            from app.services.notification_routing import get_routed_user_ids
            routed_ids = get_routed_user_ids(db, notification.category)

            all_recipient_ids = list(set(admin_ids + routed_ids))
            if not all_recipient_ids:
                return

            devices = db.query(MobileDevice).filter(
                MobileDevice.user_id.in_(all_recipient_ids),
                MobileDevice.is_active == True,
                MobileDevice.push_token.isnot(None),
            ).all()

            for device in devices:
                if not device.push_token:
                    continue

                # For routed non-admin users, check their preferences
                if device.user_id not in admin_ids:
                    prefs = self.get_user_preferences(db, device.user_id)
                    if prefs:
                        if self._is_quiet_hours(prefs) and notification.priority < 3:
                            continue
                        if not self._should_send_to_channel(prefs, notification.category, "push"):
                            continue

                result = FirebaseService.send_notification(
                    device_token=device.push_token,
                    title=notification.title,
                    body=notification.message,
                    category=notification.category,
                    priority=notification.priority,
                    notification_id=notification.id,
                    action_url=notification.action_url,
                    notification_type=notification.notification_type,
                )
                if result["success"]:
                    logger.debug(f"Push sent to device {device.id}")
                elif result["error"] == "unregistered":
                    logger.warning(
                        f"Device {device.id} token unregistered, clearing"
                    )
                    device.push_token = None
                    db.commit()
                else:
                    logger.error(
                        f"Push to device {device.id} failed: {result['error']}"
                    )
        except Exception as e:
            logger.error(f"Failed to send push notifications: {e}")
```

- [ ] **Step 2: Extend `_broadcast_to_admins` in `service.py`**

Rename `_broadcast_to_admins` to `_broadcast_to_recipients` and extend. Replace lines 155-165:

```python
    async def _broadcast_to_recipients(
        self, db: Session, notification: Notification
    ) -> None:
        """Broadcast notification to admin users and routed non-admin users via WebSocket.

        Args:
            db: Database session
            notification: Notification to broadcast
        """
        if not self._websocket_manager:
            return

        try:
            # Broadcast to all admins
            await self._websocket_manager.broadcast_to_admins(notification.to_dict())

            # Also broadcast to routed non-admin users
            from app.services.notification_routing import get_routed_user_ids
            routed_ids = get_routed_user_ids(db, notification.category)
            for uid in routed_ids:
                await self._websocket_manager.broadcast_to_user(uid, notification.to_dict())
        except Exception as e:
            logger.error(f"Failed to broadcast notification: {e}")
```

- [ ] **Step 3: Update `dispatch()` to use renamed methods**

In `service.py` `dispatch()` method (lines 125-128), replace:
```python
            await self._broadcast_to_admins(notification)
            await self._send_push_to_admins(db, notification)
```
with:
```python
            await self._broadcast_to_recipients(db, notification)
            await self._send_push_to_recipients(db, notification)
```

Note: `_broadcast_to_recipients` now takes `db` as first arg (needed for routing query).

- [ ] **Step 4: Extend `_send_push_sync` in `events.py`**

In `events.py`, modify `_send_push_sync` (lines 573-594) to also send to routed users. Replace the `if user_id is None:` branch (lines 574-588):

```python
        try:
            if user_id is None:
                # System/admin notification: send to all admin users' devices
                admin_ids = [
                    uid for (uid,) in db.query(User.id).filter(
                        User.role == "admin",
                        User.is_active == True,
                    ).all()
                ]

                # Also include non-admin users with routing for this category
                from app.services.notification_routing import get_routed_user_ids
                routed_ids = get_routed_user_ids(db, category)

                all_recipient_ids = list(set(admin_ids + routed_ids))
                if not all_recipient_ids:
                    return

                devices = db.query(MobileDevice).filter(
                    MobileDevice.user_id.in_(all_recipient_ids),
                    MobileDevice.is_active == True,
                    MobileDevice.push_token.isnot(None),
                ).all()
            else:
                devices = db.query(MobileDevice).filter(
                    MobileDevice.user_id == user_id,
                    MobileDevice.is_active == True,
                    MobileDevice.push_token.isnot(None),
                ).all()

            for device in devices:
                # For routed non-admin users, check their preferences
                if user_id is None and device.user_id not in admin_ids:
                    from app.services.notifications.service import get_notification_service
                    svc = get_notification_service()
                    prefs = svc.get_user_preferences(db, device.user_id)
                    if prefs:
                        if svc._is_quiet_hours(prefs) and priority < 3:
                            continue
                        if not svc._should_send_to_channel(prefs, category, "push"):
                            continue

                result = FirebaseService.send_notification(
```

The rest of the loop (lines 597-614) stays the same.

- [ ] **Step 5: Verify backend starts**

Run:
```bash
cd backend && python -c "from app.services.notifications.events import EventEmitter; from app.services.notifications.service import NotificationService; print('OK')"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notifications/service.py backend/app/services/notifications/events.py
git commit -m "feat(notifications): extend routing to include non-admin recipients"
```

---

### Task 7: Frontend API Module

**Files:**
- Create: `client/src/api/notificationRouting.ts`

- [ ] **Step 1: Create the API module**

```typescript
// client/src/api/notificationRouting.ts
/**
 * API client for user notification routing management.
 */

import { apiClient } from '../lib/api';

export interface UserNotificationRouting {
  user_id: number;
  receive_raid: boolean;
  receive_smart: boolean;
  receive_backup: boolean;
  receive_scheduler: boolean;
  receive_system: boolean;
  receive_security: boolean;
  receive_sync: boolean;
  receive_vpn: boolean;
  granted_by: number | null;
  granted_by_username: string | null;
  granted_at: string | null;
}

export interface UserNotificationRoutingUpdate {
  receive_raid?: boolean;
  receive_smart?: boolean;
  receive_backup?: boolean;
  receive_scheduler?: boolean;
  receive_system?: boolean;
  receive_security?: boolean;
  receive_sync?: boolean;
  receive_vpn?: boolean;
}

export interface MyNotificationRouting {
  receive_raid: boolean;
  receive_smart: boolean;
  receive_backup: boolean;
  receive_scheduler: boolean;
  receive_system: boolean;
  receive_security: boolean;
  receive_sync: boolean;
  receive_vpn: boolean;
}

/**
 * Get notification routing for a user (admin only).
 */
export async function getUserNotificationRouting(userId: number): Promise<UserNotificationRouting> {
  const { data } = await apiClient.get<UserNotificationRouting>(
    `/api/users/${userId}/notification-routing`,
  );
  return data;
}

/**
 * Update notification routing for a user (admin only).
 */
export async function updateUserNotificationRouting(
  userId: number,
  update: UserNotificationRoutingUpdate,
): Promise<UserNotificationRouting> {
  const { data } = await apiClient.put<UserNotificationRouting>(
    `/api/users/${userId}/notification-routing`,
    update,
  );
  return data;
}

/**
 * Get own notification routing (read-only).
 */
export async function getMyNotificationRouting(): Promise<MyNotificationRouting> {
  const { data } = await apiClient.get<MyNotificationRouting>(
    '/api/notifications/my-routing',
  );
  return data;
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/notificationRouting.ts
git commit -m "feat(notifications): add notification routing frontend API module"
```

---

### Task 8: NotificationRoutingSection Component

**Files:**
- Create: `client/src/components/user-management/NotificationRoutingSection.tsx`
- Modify: `client/src/components/user-management/UserFormModal.tsx`

- [ ] **Step 1: Create the component**

```tsx
// client/src/components/user-management/NotificationRoutingSection.tsx
import { useState, useEffect } from 'react';
import {
  HardDrive,
  Activity,
  Archive,
  Clock,
  Server,
  Shield,
  RefreshCw,
  Globe,
  Bell,
  Loader2,
} from 'lucide-react';
import {
  getUserNotificationRouting,
  updateUserNotificationRouting,
  type UserNotificationRouting,
  type UserNotificationRoutingUpdate,
} from '../../api/notificationRouting';
import { handleApiError } from '../../lib/errorHandling';
import toast from 'react-hot-toast';

interface NotificationRoutingSectionProps {
  userId: number;
  userRole: string;
}

interface RoutingToggle {
  key: keyof UserNotificationRoutingUpdate;
  label: string;
  description: string;
  icon: React.ReactNode;
}

const ROUTING_TOGGLES: RoutingToggle[] = [
  {
    key: 'receive_raid',
    label: 'RAID',
    description: 'RAID-Statusaenderungen und Warnungen',
    icon: <HardDrive className="h-4 w-4" />,
  },
  {
    key: 'receive_smart',
    label: 'SMART',
    description: 'Festplatten-Gesundheitswarnungen',
    icon: <Activity className="h-4 w-4" />,
  },
  {
    key: 'receive_backup',
    label: 'Backup',
    description: 'Backup-Erfolge und -Fehler',
    icon: <Archive className="h-4 w-4" />,
  },
  {
    key: 'receive_scheduler',
    label: 'Scheduler',
    description: 'Geplante Aufgaben Statusmeldungen',
    icon: <Clock className="h-4 w-4" />,
  },
  {
    key: 'receive_system',
    label: 'System',
    description: 'Speicherplatz, Temperatur, Services',
    icon: <Server className="h-4 w-4" />,
  },
  {
    key: 'receive_security',
    label: 'Sicherheit',
    description: 'Fehlgeschlagene Logins, Brute-Force',
    icon: <Shield className="h-4 w-4" />,
  },
  {
    key: 'receive_sync',
    label: 'Sync',
    description: 'Sync-Konflikte und -Fehler',
    icon: <RefreshCw className="h-4 w-4" />,
  },
  {
    key: 'receive_vpn',
    label: 'VPN',
    description: 'VPN-Client-Ablaufwarnungen',
    icon: <Globe className="h-4 w-4" />,
  },
];

export function NotificationRoutingSection({ userId, userRole }: NotificationRoutingSectionProps) {
  const [routing, setRouting] = useState<UserNotificationRouting | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (userRole === 'admin') return;
    setLoading(true);
    getUserNotificationRouting(userId)
      .then(setRouting)
      .catch(() => setRouting(null))
      .finally(() => setLoading(false));
  }, [userId, userRole]);

  if (userRole === 'admin') return null;

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Lade Benachrichtigungs-Routing...
      </div>
    );
  }

  const handleToggle = async (key: keyof UserNotificationRoutingUpdate, newValue: boolean) => {
    setSaving(true);
    try {
      const update: UserNotificationRoutingUpdate = { [key]: newValue };
      const result = await updateUserNotificationRouting(userId, update);
      setRouting(result);
      toast.success('Benachrichtigungs-Routing aktualisiert');
    } catch (error) {
      handleApiError(error, 'Fehler beim Speichern');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border-t border-slate-800 pt-3 mt-3">
      <div className="flex items-center gap-2 mb-1">
        <Bell className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-medium text-slate-300">System-Benachrichtigungen</h3>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Legt fest, welche System-Benachrichtigungen dieser User erhaelt.
      </p>

      <div className="space-y-2">
        {ROUTING_TOGGLES.map((toggle) => {
          const value = routing?.[toggle.key] ?? false;

          return (
            <div key={toggle.key} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-400">{toggle.icon}</span>
                <div>
                  <span className="text-sm text-slate-200">{toggle.label}</span>
                  <span className="text-xs text-slate-500 ml-2">{toggle.description}</span>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={value}
                disabled={saving}
                onClick={() => handleToggle(toggle.key, !value)}
                className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors
                  ${value ? 'bg-sky-500' : 'bg-slate-700'}
                  ${saving ? 'opacity-50' : 'cursor-pointer'}
                `}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
                    ${value ? 'translate-x-4' : 'translate-x-0.5'}
                  `}
                />
              </button>
            </div>
          );
        })}
      </div>

      {routing?.granted_by_username && (
        <p className="text-xs text-slate-500 mt-2">
          Zuletzt geaendert von {routing.granted_by_username}
          {routing.granted_at && ` am ${new Date(routing.granted_at).toLocaleDateString('de-DE')}`}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add to UserFormModal**

In `client/src/components/user-management/UserFormModal.tsx`, add import at top:
```tsx
import { NotificationRoutingSection } from './NotificationRoutingSection';
```

Add after the `PowerPermissionsSection` block (after line 131):
```tsx
        {editingUser && (
          <NotificationRoutingSection
            userId={editingUser.id}
            userRole={editingUser.role}
          />
        )}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/user-management/NotificationRoutingSection.tsx client/src/components/user-management/UserFormModal.tsx
git commit -m "feat(notifications): add admin notification routing toggle UI"
```

---

### Task 9: User Read-Only Display

**Files:**
- Modify: `client/src/pages/NotificationPreferencesPage.tsx`

- [ ] **Step 1: Add routing display to preferences page**

Add import at top of `NotificationPreferencesPage.tsx`:
```tsx
import { getMyNotificationRouting, type MyNotificationRouting } from '../api/notificationRouting';
import { getCategoryName, getCategoryIcon } from '../api/notifications';
```

Add state after existing state declarations:
```tsx
const [routing, setRouting] = useState<MyNotificationRouting | null>(null);
```

Add fetch in the existing `useEffect` (or a new one alongside the preferences fetch):
```tsx
useEffect(() => {
  getMyNotificationRouting()
    .then(setRouting)
    .catch(() => setRouting(null));
}, []);
```

Add a section before the category matrix (before the Save button), only shown when at least one category is routed:

```tsx
{routing && Object.entries(routing).some(([_, v]) => v === true) && (
  <div className="border border-slate-700 rounded-lg p-4 mb-6">
    <h3 className="text-sm font-medium text-slate-300 mb-2">
      Zugewiesene System-Benachrichtigungen
    </h3>
    <p className="text-xs text-slate-500 mb-3">
      Diese Kategorien wurden dir von einem Administrator zugewiesen.
    </p>
    <div className="flex flex-wrap gap-2">
      {(Object.entries(routing) as [string, boolean][])
        .filter(([_, enabled]) => enabled)
        .map(([key]) => {
          const category = key.replace('receive_', '') as NotificationCategory;
          return (
            <span
              key={key}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20"
            >
              {getCategoryName(category)}
            </span>
          );
        })}
    </div>
  </div>
)}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/pages/NotificationPreferencesPage.tsx
git commit -m "feat(notifications): add read-only routing display in user preferences"
```

---

### Task 10: Tests

**Files:**
- Create: `backend/tests/test_notification_routing.py`

- [ ] **Step 1: Create tests**

```python
# backend/tests/test_notification_routing.py
"""Tests for notification routing feature."""

import pytest
from unittest.mock import patch, MagicMock

from app.models.notification_routing import UserNotificationRouting
from app.schemas.notification_routing import NotificationRoutingUpdate


class TestNotificationRoutingModel:
    """Tests for the UserNotificationRouting model."""

    def test_create_routing(self, db):
        """New routing row has all categories disabled by default."""
        routing = UserNotificationRouting(user_id=999)
        db.add(routing)
        db.commit()
        db.refresh(routing)

        assert routing.receive_raid is False
        assert routing.receive_smart is False
        assert routing.receive_backup is False
        assert routing.receive_scheduler is False
        assert routing.receive_system is False
        assert routing.receive_security is False
        assert routing.receive_sync is False
        assert routing.receive_vpn is False

    def test_unique_user_id(self, db):
        """Only one routing row per user."""
        from sqlalchemy.exc import IntegrityError

        db.add(UserNotificationRouting(user_id=888))
        db.commit()
        db.add(UserNotificationRouting(user_id=888))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestNotificationRoutingService:
    """Tests for the notification routing service."""

    def test_get_routing_no_row(self, db):
        """Returns defaults when no row exists."""
        from app.services.notification_routing import get_routing

        result = get_routing(db, user_id=777)
        assert result.user_id == 777
        assert result.receive_raid is False
        assert result.granted_by is None

    def test_update_routing_creates_row(self, db, admin_user):
        """Update creates row if none exists."""
        from app.services.notification_routing import update_routing

        update = NotificationRoutingUpdate(receive_raid=True, receive_security=True)
        result = update_routing(db, user_id=admin_user.id, update=update, granted_by=admin_user.id)

        assert result.receive_raid is True
        assert result.receive_security is True
        assert result.receive_smart is False
        assert result.granted_by == admin_user.id

    def test_update_routing_partial(self, db, admin_user):
        """Partial update only changes specified fields."""
        from app.services.notification_routing import update_routing

        # Create with raid=True
        update1 = NotificationRoutingUpdate(receive_raid=True)
        update_routing(db, user_id=admin_user.id, update=update1, granted_by=admin_user.id)

        # Update only smart, raid should stay True
        update2 = NotificationRoutingUpdate(receive_smart=True)
        result = update_routing(db, user_id=admin_user.id, update=update2, granted_by=admin_user.id)

        assert result.receive_raid is True
        assert result.receive_smart is True

    def test_check_routing(self, db, admin_user):
        """check_routing returns correct boolean."""
        from app.services.notification_routing import check_routing, update_routing

        update = NotificationRoutingUpdate(receive_raid=True)
        update_routing(db, user_id=admin_user.id, update=update, granted_by=admin_user.id)

        assert check_routing(db, admin_user.id, "raid") is True
        assert check_routing(db, admin_user.id, "smart") is False
        assert check_routing(db, admin_user.id, "nonexistent") is False

    def test_get_routed_user_ids(self, db, admin_user, regular_user):
        """get_routed_user_ids returns only non-admin users with routing enabled."""
        from app.services.notification_routing import get_routed_user_ids, update_routing

        # Give regular user raid routing
        update = NotificationRoutingUpdate(receive_raid=True)
        update_routing(db, user_id=regular_user.id, update=update, granted_by=admin_user.id)

        routed = get_routed_user_ids(db, "raid")
        assert regular_user.id in routed
        # Admin should not appear even if they have a routing row
        assert admin_user.id not in routed

        # Different category should return empty
        assert get_routed_user_ids(db, "smart") == []


class TestNotificationRoutingAPI:
    """Tests for notification routing API endpoints."""

    def test_get_routing_requires_admin(self, client, user_token):
        """Non-admin cannot read other user's routing."""
        resp = client.get(
            "/api/users/1/notification-routing",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code in (401, 403)

    def test_get_routing_admin(self, client, admin_token):
        """Admin can read routing."""
        resp = client.get(
            "/api/users/2/notification-routing",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["receive_raid"] is False

    def test_update_routing_admin(self, client, admin_token):
        """Admin can update routing."""
        resp = client.put(
            "/api/users/2/notification-routing",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"receive_raid": True, "receive_system": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["receive_raid"] is True
        assert data["receive_system"] is True
        assert data["receive_smart"] is False

    def test_my_routing(self, client, user_token):
        """User can read own routing."""
        resp = client.get(
            "/api/notifications/my-routing",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "receive_raid" in data
        # Should not contain admin metadata
        assert "granted_by" not in data
```

- [ ] **Step 2: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_notification_routing.py -v
```
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_notification_routing.py
git commit -m "test(notifications): add notification routing tests"
```
