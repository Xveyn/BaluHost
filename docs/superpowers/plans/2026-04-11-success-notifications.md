# Success Notifications & Category Settings Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins opt-in to success notifications per category and redesign the Category Settings table to separate *what* (Fehler/Erfolg) from *where* (Mobile App/Desktop Client).

**Architecture:** Extend the existing `category_preferences` JSON field with new keys (`error`, `success`, `mobile`, `desktop`), add gate logic in `emit_sync()` to check these flags before creating notifications, emit missing success events from the scheduler worker, and redesign the frontend table in `NotificationPreferencesPage.tsx`.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), SQLAlchemy JSON column (no migration), i18next

---

## Task 1: Backend — Update CategoryPreference Schema

**Files:**
- Modify: `backend/app/schemas/notification.py:154-158`

- [ ] **Step 1: Update CategoryPreference schema**

In `backend/app/schemas/notification.py`, replace the `CategoryPreference` class (lines 154-158):

```python
class CategoryPreference(BaseModel):
    """Preferences for a single notification category."""

    push: bool = True
    in_app: bool = True
```

with:

```python
class CategoryPreference(BaseModel):
    """Preferences for a single notification category.

    Controls what events generate notifications and where they are delivered.
    Supports old format (push/in_app) for backwards compatibility on read.
    """

    error: bool = True
    success: bool = False
    mobile: bool = True
    desktop: bool = False
```

- [ ] **Step 2: Verify schema imports still work**

Run:
```bash
cd backend && python -c "from app.schemas.notification import CategoryPreference; p = CategoryPreference(); print(p.model_dump())"
```
Expected: `{'error': True, 'success': False, 'mobile': True, 'desktop': False}`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/notification.py
git commit -m "feat(notifications): update CategoryPreference schema to error/success/mobile/desktop"
```

---

## Task 2: Backend — Add _get_category_pref Helper with Backwards Compatibility

**Files:**
- Modify: `backend/app/services/notifications/service.py:340-358`
- Test: `backend/tests/services/test_notification_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/test_notification_service.py`:

```python
class TestGetCategoryPref:
    """Tests for _get_category_pref helper with backwards compatibility."""

    def test_no_prefs_returns_defaults(self):
        from app.services.notifications.service import NotificationService
        svc = NotificationService()
        result = svc._get_category_pref(None, "raid")
        assert result == {"error": True, "success": False, "mobile": True, "desktop": False}

    def test_no_prefs_backup_defaults_success_true(self):
        from app.services.notifications.service import NotificationService
        svc = NotificationService()
        result = svc._get_category_pref(None, "backup")
        assert result["success"] is True

    def test_old_format_migrated(self):
        """Old push/in_app format is auto-mapped to new fields."""
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"push": True, "in_app": False}}
        result = svc._get_category_pref(prefs, "raid")
        assert result == {"error": False, "success": False, "mobile": True, "desktop": False}

    def test_new_format_used_directly(self):
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"error": True, "success": True, "mobile": False, "desktop": True}}
        result = svc._get_category_pref(prefs, "raid")
        assert result == {"error": True, "success": True, "mobile": False, "desktop": True}

    def test_missing_category_returns_defaults(self):
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"error": True, "success": False, "mobile": True, "desktop": False}}
        result = svc._get_category_pref(prefs, "smart")
        assert result == {"error": True, "success": False, "mobile": True, "desktop": False}

    def test_partial_new_format_fills_defaults(self):
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"error": True, "success": True}}
        result = svc._get_category_pref(prefs, "raid")
        assert result == {"error": True, "success": True, "mobile": True, "desktop": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestGetCategoryPref -v`
Expected: FAIL — `AttributeError: 'NotificationService' object has no attribute '_get_category_pref'`

- [ ] **Step 3: Implement _get_category_pref**

In `backend/app/services/notifications/service.py`, add after the `_should_send_to_channel` method (after line 358):

```python
    def _get_category_pref(self, prefs, category: str) -> dict:
        """Get category preference with backwards compatibility.

        Handles migration from old format (push/in_app) to new format
        (error/success/mobile/desktop). Returns a dict with all four keys.

        Args:
            prefs: NotificationPreferences or None
            category: Notification category name

        Returns:
            Dict with keys: error, success, mobile, desktop
        """
        defaults = {
            "error": True,
            "success": category == "backup",
            "mobile": True,
            "desktop": False,
        }

        if not prefs or not prefs.category_preferences:
            return defaults

        cat = prefs.category_preferences.get(category, {})
        if not cat:
            return defaults

        # Old format detection: has "push" but no "error"
        if "push" in cat and "error" not in cat:
            return {
                "error": cat.get("in_app", True),
                "success": False,
                "mobile": cat.get("push", True),
                "desktop": False,
            }

        return {**defaults, **cat}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestGetCategoryPref -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): add _get_category_pref helper with backwards compat"
```

---

## Task 3: Backend — Add Gate Logic in emit_sync

**Files:**
- Modify: `backend/app/services/notifications/events.py:453-552`
- Test: `backend/tests/services/test_notification_events.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_notification_events.py`:

```python
"""Tests for notification event gate logic (error/success preferences)."""
import pytest
from unittest.mock import MagicMock, patch

from app.services.notifications.events import (
    EventEmitter,
    EventType,
    _cooldown_cache,
)


class TestEmitSyncGateLogic:
    """Tests for error/success gate in emit_sync."""

    @pytest.fixture(autouse=True)
    def clear_cooldowns(self):
        _cooldown_cache.clear()
        yield
        _cooldown_cache.clear()

    def _make_emitter(self, db_session):
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)
        return emitter

    def test_success_event_skipped_when_no_admin_wants_it(self, db_session):
        """Success events (priority=0, type=info) are skipped if no admin has success=true."""
        from app.models.notification import Notification, NotificationPreferences
        from app.models.user import User

        # Create admin with success=false for scheduler (default)
        admin = db_session.query(User).filter(User.role == "admin").first()
        if not admin:
            pytest.skip("No admin user in test DB")

        prefs = NotificationPreferences(
            user_id=admin.id,
            category_preferences={"scheduler": {"error": True, "success": False, "mobile": True, "desktop": False}},
        )
        db_session.add(prefs)
        db_session.commit()

        emitter = self._make_emitter(db_session)
        emitter.emit_for_admins_sync(
            EventType.SCHEDULER_COMPLETED,
            scheduler_name="smart_check",
        )

        count = db_session.query(Notification).filter(
            Notification.category == "scheduler",
            Notification.notification_type == "info",
        ).count()
        assert count == 0

    def test_success_event_created_when_admin_wants_it(self, db_session):
        """Success events are created when at least one admin has success=true."""
        from app.models.notification import Notification, NotificationPreferences
        from app.models.user import User

        admin = db_session.query(User).filter(User.role == "admin").first()
        if not admin:
            pytest.skip("No admin user in test DB")

        prefs = NotificationPreferences(
            user_id=admin.id,
            category_preferences={"scheduler": {"error": True, "success": True, "mobile": True, "desktop": False}},
        )
        db_session.add(prefs)
        db_session.commit()

        emitter = self._make_emitter(db_session)
        emitter.emit_for_admins_sync(
            EventType.SCHEDULER_COMPLETED,
            scheduler_name="smart_check",
        )

        notification = db_session.query(Notification).filter(
            Notification.category == "scheduler",
            Notification.notification_type == "info",
        ).first()
        assert notification is not None
        assert "smart_check" in notification.title

    def test_error_event_skipped_when_admin_disables_it(self, db_session):
        """Error events are skipped if admin has error=false for this category."""
        from app.models.notification import Notification, NotificationPreferences
        from app.models.user import User

        admin = db_session.query(User).filter(User.role == "admin").first()
        if not admin:
            pytest.skip("No admin user in test DB")

        prefs = NotificationPreferences(
            user_id=admin.id,
            category_preferences={"scheduler": {"error": False, "success": False, "mobile": True, "desktop": False}},
        )
        db_session.add(prefs)
        db_session.commit()

        emitter = self._make_emitter(db_session)
        emitter.emit_for_admins_sync(
            EventType.SCHEDULER_FAILED,
            scheduler_name="backup",
            error="disk full",
        )

        count = db_session.query(Notification).filter(
            Notification.category == "scheduler",
        ).count()
        assert count == 0

    def test_error_event_created_by_default(self, db_session):
        """Error events are created when no preferences exist (defaults to error=true)."""
        from app.models.notification import Notification

        emitter = self._make_emitter(db_session)
        emitter.emit_for_admins_sync(
            EventType.SCHEDULER_FAILED,
            scheduler_name="backup",
            error="disk full",
        )

        notification = db_session.query(Notification).filter(
            Notification.category == "scheduler",
        ).first()
        assert notification is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_notification_events.py -v`
Expected: Tests pass for error (default behavior unchanged) but success gate test should pass since success events are created unconditionally today. We need to verify the current behavior first.

- [ ] **Step 3: Add gate logic to emit_sync**

In `backend/app/services/notifications/events.py`, modify `emit_sync` method. After the template formatting (line 489), before the `if self._db_session_factory:` block (line 491), add the gate check:

```python
        # Determine if this is a success or error event
        is_success_event = config.priority == 0 and config.notification_type == "info"
        is_error_event = config.notification_type in ("warning", "critical")

        if self._db_session_factory:
            db = self._db_session_factory()
            try:
                # Gate: check if any admin wants this event type
                if user_id is None:
                    from app.services.notifications.service import get_notification_service
                    svc = get_notification_service()
                    from app.models.user import User
                    from app.models.notification import NotificationPreferences

                    admin_ids = [
                        uid for (uid,) in db.query(User.id).filter(
                            User.role == "admin",
                            User.is_active == True,
                        ).all()
                    ]

                    any_admin_wants_it = False
                    for admin_id in admin_ids:
                        prefs = svc.get_user_preferences(db, admin_id)
                        cat_pref = svc._get_category_pref(prefs, config.category)
                        if is_success_event and cat_pref.get("success", False):
                            any_admin_wants_it = True
                            break
                        elif is_error_event and cat_pref.get("error", True):
                            any_admin_wants_it = True
                            break
                        elif not is_success_event and not is_error_event:
                            any_admin_wants_it = True
                            break

                    if not any_admin_wants_it:
                        logger.debug(
                            f"Event {event_type} suppressed: no admin wants "
                            f"{'success' if is_success_event else 'error'} for {config.category}"
                        )
                        return

                from app.models.notification import Notification
```

This replaces the existing lines 491-494. The rest of `emit_sync` (notification creation, push, routing) stays the same.

The full modified section (lines 489-510) should now read:

```python
        # Determine if this is a success or error event
        is_success_event = config.priority == 0 and config.notification_type == "info"
        is_error_event = config.notification_type in ("warning", "critical")

        if self._db_session_factory:
            db = self._db_session_factory()
            try:
                # Gate: check if any admin wants this event type
                if user_id is None:
                    from app.services.notifications.service import get_notification_service
                    svc = get_notification_service()
                    from app.models.user import User

                    admin_ids = [
                        uid for (uid,) in db.query(User.id).filter(
                            User.role == "admin",
                            User.is_active == True,
                        ).all()
                    ]

                    any_admin_wants_it = False
                    for admin_id in admin_ids:
                        prefs = svc.get_user_preferences(db, admin_id)
                        cat_pref = svc._get_category_pref(prefs, config.category)
                        if is_success_event and cat_pref.get("success", False):
                            any_admin_wants_it = True
                            break
                        elif is_error_event and cat_pref.get("error", True):
                            any_admin_wants_it = True
                            break
                        elif not is_success_event and not is_error_event:
                            any_admin_wants_it = True
                            break

                    if not any_admin_wants_it:
                        logger.debug(
                            f"Event {event_type} suppressed: no admin wants "
                            f"{'success' if is_success_event else 'error'} for {config.category}"
                        )
                        return

                from app.models.notification import Notification

                notification = Notification(
                    user_id=user_id,
                    category=config.category,
                    notification_type=config.notification_type,
                    title=title,
                    message=message,
                    action_url=config.action_url,
                    extra_data={"event_type": event_type, **kwargs},
                    priority=config.priority,
                )
                db.add(notification)
                db.commit()
```

The rest of `emit_sync` (from `_set_cooldown` onwards) remains unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_notification_events.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing notification tests to verify no regressions**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py tests/services/test_firebase_push.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notifications/events.py backend/tests/services/test_notification_events.py
git commit -m "feat(notifications): add error/success gate logic in emit_sync"
```

---

## Task 4: Backend — Add Mobile Gate in _send_push_sync

**Files:**
- Modify: `backend/app/services/notifications/events.py:561-660` (the `_send_push_sync` method)

- [ ] **Step 1: Add mobile preference check in _send_push_sync**

In the `_send_push_sync` method, after getting the devices list and before the `for device in devices:` loop, add a per-device mobile preference check. Find the existing loop (around line 630):

```python
            for device in devices:
```

Replace the loop body to include mobile preference check for admin devices:

```python
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

                # Check mobile preference for admin users
                if user_id is None and device.user_id in admin_ids:
                    from app.services.notifications.service import get_notification_service
                    svc = get_notification_service()
                    prefs = svc.get_user_preferences(db, device.user_id)
                    cat_pref = svc._get_category_pref(prefs, category)
                    if not cat_pref.get("mobile", True):
                        continue
```

The existing Firebase send code after this remains unchanged.

- [ ] **Step 2: Run push notification tests**

Run: `cd backend && python -m pytest tests/services/test_firebase_push.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/notifications/events.py
git commit -m "feat(notifications): add per-admin mobile preference check in push delivery"
```

---

## Task 5: Backend — Add Missing EventConfigs and Convenience Functions

**Files:**
- Modify: `backend/app/services/notifications/events.py` (EVENT_CONFIGS section + convenience functions)
- Modify: `backend/app/services/notifications/__init__.py`

- [ ] **Step 1: Add missing EventConfigs**

In `backend/app/services/notifications/events.py`, add the following entries to `EVENT_CONFIGS` dict. Add after the `RAID_SCRUB_COMPLETE` entry (after line 155):

```python
    EventType.RAID_SYNC_STARTED: EventConfig(
        priority=0,
        category="raid",
        notification_type="info",
        title_template="RAID Synchronisation gestartet: {array_name}",
        message_template="Die RAID-Synchronisation für {array_name} wurde gestartet.",
        action_url="/admin/system-control?tab=raid",
    ),
    EventType.RAID_SYNC_COMPLETE: EventConfig(
        priority=0,
        category="raid",
        notification_type="info",
        title_template="RAID Synchronisation abgeschlossen: {array_name}",
        message_template="Die RAID-Synchronisation für {array_name} wurde erfolgreich abgeschlossen.",
        action_url="/admin/system-control?tab=raid",
    ),
```

Add after the `SERVICE_DOWN` entry (after line 243):

```python
    EventType.SERVICE_RESTORED: EventConfig(
        priority=0,
        category="system",
        notification_type="info",
        title_template="Dienst wiederhergestellt: {service_name}",
        message_template="Der Dienst '{service_name}' ist wieder verfügbar.",
        action_url="/admin/health",
    ),
```

Note: `SERVICE_RESTORED` EventConfig already exists at line 244-250 — verify before adding. If it already exists, skip this addition.

- [ ] **Step 2: Add sync convenience functions**

At the end of `events.py`, before the final closing, add:

```python
def emit_scheduler_completed_sync(scheduler_name: str) -> None:
    """Emit scheduler completed event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.SCHEDULER_COMPLETED,
        scheduler_name=scheduler_name,
    )


def emit_raid_sync_started_sync(array_name: str) -> None:
    """Emit RAID sync started event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.RAID_SYNC_STARTED,
        array_name=array_name,
    )


def emit_raid_sync_complete_sync(array_name: str) -> None:
    """Emit RAID sync complete event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.RAID_SYNC_COMPLETE,
        array_name=array_name,
    )


def emit_service_restored_sync(service_name: str) -> None:
    """Emit service restored event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.SERVICE_RESTORED,
        service_name=service_name,
    )
```

- [ ] **Step 3: Update __init__.py exports**

In `backend/app/services/notifications/__init__.py`, add to the imports from `events`:

```python
    emit_scheduler_completed_sync,
    emit_raid_sync_started_sync,
    emit_raid_sync_complete_sync,
    emit_service_restored_sync,
```

Add to `__all__`:

```python
    "emit_scheduler_completed_sync",
    "emit_raid_sync_started_sync",
    "emit_raid_sync_complete_sync",
    "emit_service_restored_sync",
```

- [ ] **Step 4: Verify imports work**

Run:
```bash
cd backend && python -c "from app.services.notifications import emit_scheduler_completed_sync, emit_raid_sync_started_sync, emit_raid_sync_complete_sync, emit_service_restored_sync; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/events.py backend/app/services/notifications/__init__.py
git commit -m "feat(notifications): add missing EventConfigs and convenience emit functions"
```

---

## Task 6: Backend — Wire Up Scheduler Completed Events

**Files:**
- Modify: `backend/app/services/scheduler/worker.py:274`

- [ ] **Step 1: Add success notification after scheduler job completes**

In `backend/app/services/scheduler/worker.py`, after line 274 (`logger.info("Scheduler job completed: %s", name)`), add:

```python
            # Emit notification for scheduler success
            try:
                from app.services.notifications.events import emit_scheduler_completed_sync
                emit_scheduler_completed_sync(name)
            except Exception:
                pass
```

This mirrors the existing failure notification pattern at lines 279-284.

- [ ] **Step 2: Verify no syntax errors**

Run:
```bash
cd backend && python -c "from app.services.scheduler.worker import SchedulerWorker; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/scheduler/worker.py
git commit -m "feat(notifications): emit scheduler completed notifications"
```

---

## Task 7: Backend — Add delivery-status Endpoint

**Files:**
- Modify: `backend/app/api/routes/notifications.py`
- Test: `backend/tests/services/test_notification_service.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_notification_service.py`:

```python
class TestDeliveryStatusEndpoint:
    """Tests for GET /api/notifications/delivery-status."""

    def test_returns_status_for_user(self, client, admin_headers):
        """Endpoint returns device availability."""
        from app.core.config import settings
        resp = client.get(
            f"{settings.api_prefix}/notifications/delivery-status",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "has_mobile_devices" in data
        assert "has_desktop_clients" in data
        assert isinstance(data["has_mobile_devices"], bool)
        assert isinstance(data["has_desktop_clients"], bool)

    def test_requires_authentication(self, client):
        """Endpoint requires auth."""
        from app.core.config import settings
        resp = client.get(f"{settings.api_prefix}/notifications/delivery-status")
        assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestDeliveryStatusEndpoint -v`
Expected: FAIL — 404 (endpoint not found)

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/routes/notifications.py`, add after the imports (around line 27):

```python
from app.models.mobile import MobileDevice
from app.models.sync_state import SyncState
```

Add the endpoint before the `create_notification` endpoint (before the `@router.post("")` line):

```python
@router.get("/delivery-status")
@user_limiter.limit(get_limit("read_operations"))
async def get_delivery_status(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Get device availability for notification delivery channels.

    Returns whether the current user has active mobile devices and desktop clients,
    used by the frontend to dim unavailable delivery columns.
    """
    has_mobile = db.query(MobileDevice.id).filter(
        MobileDevice.user_id == current_user.id,
        MobileDevice.is_active == True,
        MobileDevice.push_token.isnot(None),
    ).first() is not None

    has_desktop = db.query(SyncState.id).filter(
        SyncState.user_id == current_user.id,
    ).first() is not None

    return {
        "has_mobile_devices": has_mobile,
        "has_desktop_clients": has_desktop,
    }
```

**Important:** This endpoint must be placed BEFORE any endpoint with path parameters (like `/{notification_id}`) to avoid route conflicts. Place it right after the `get_notification_preferences` endpoint.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestDeliveryStatusEndpoint -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/notifications.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): add delivery-status endpoint for device availability"
```

---

## Task 8: Frontend — Update API Types and Add getDeliveryStatus

**Files:**
- Modify: `client/src/api/notifications.ts:45-70`

- [ ] **Step 1: Update CategoryPreference type**

In `client/src/api/notifications.ts`, replace the `CategoryPreference` interface (lines 45-48):

```typescript
export interface CategoryPreference {
  push: boolean;
  in_app: boolean;
}
```

with:

```typescript
export interface CategoryPreference {
  error: boolean;
  success: boolean;
  mobile: boolean;
  desktop: boolean;
}
```

- [ ] **Step 2: Add DeliveryStatus type and API function**

After the `NotificationPreferencesUpdate` interface (after line 70), add:

```typescript
export interface DeliveryStatus {
  has_mobile_devices: boolean;
  has_desktop_clients: boolean;
}

export async function getDeliveryStatus(): Promise<DeliveryStatus> {
  const response = await apiClient.get<DeliveryStatus>('/api/notifications/delivery-status');
  return response.data;
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/api/notifications.ts
git commit -m "feat(notifications): update CategoryPreference type and add getDeliveryStatus API"
```

---

## Task 9: Frontend — Update i18n Keys

**Files:**
- Modify: `client/src/i18n/locales/de/notifications.json`
- Modify: `client/src/i18n/locales/en/notifications.json`

- [ ] **Step 1: Update German translations**

Replace the `categories` section in `client/src/i18n/locales/de/notifications.json`:

```json
{
  "title": "Benachrichtigungen",
  "description": "Konfiguriere wie und wann du benachrichtigt wirst",
  "priority": {
    "title": "Prioritätsfilter",
    "description": "Wähle die minimale Priorität für Benachrichtigungen",
    "all": "Alle",
    "allDesc": "Alle Benachrichtigungen erhalten",
    "warnings": "Warnungen+",
    "warningsDesc": "Nur Warnungen und kritische Meldungen",
    "important": "Wichtig",
    "importantDesc": "Nur hohe Priorität und kritische Meldungen",
    "critical": "Nur kritisch",
    "criticalDesc": "Nur kritische Systemmeldungen"
  },
  "quietHours": {
    "title": "Ruhezeiten",
    "description": "Keine Benachrichtigungen während dieser Zeit",
    "from": "Von",
    "to": "Bis"
  },
  "categories": {
    "title": "Kategorie-Einstellungen",
    "description": "Konfiguriere Benachrichtigungen für einzelne Kategorien",
    "type": "Typ",
    "error": "Fehler",
    "errorDesc": "Bei Fehlern und Warnungen benachrichtigen",
    "success": "Erfolg",
    "successDesc": "Bei erfolgreichen Vorgängen benachrichtigen",
    "mobileApp": "Mobile App",
    "mobileAppDimmed": "Keine Mobile App verbunden",
    "desktopClient": "Desktop Client",
    "desktopClientDimmed": "Kein Desktop Client verbunden"
  },
  "buttons": {
    "save": "Speichern",
    "back": "Zurück"
  },
  "toast": {
    "saved": "Einstellungen gespeichert",
    "loadFailed": "Fehler beim Laden der Einstellungen",
    "saveFailed": "Fehler beim Speichern"
  },
  "noNotifications": "Keine Benachrichtigungen",
  "connected": "Verbunden",
  "markedAllRead": "Alle als gelesen markiert",
  "markError": "Fehler beim Markieren",
  "allRead": "Alle gelesen",
  "settings": "Einstellungen",
  "viewAll": "Alle anzeigen",
  "markAllRead": "Alle als gelesen markieren"
}
```

- [ ] **Step 2: Update English translations**

Replace the full content of `client/src/i18n/locales/en/notifications.json`:

```json
{
  "title": "Notifications",
  "description": "Configure how and when you get notified",
  "priority": {
    "title": "Priority Filter",
    "description": "Choose the minimum priority for notifications",
    "all": "All",
    "allDesc": "Receive all notifications",
    "warnings": "Warnings+",
    "warningsDesc": "Only warnings and critical messages",
    "important": "Important",
    "importantDesc": "Only high priority and critical messages",
    "critical": "Critical only",
    "criticalDesc": "Only critical system messages"
  },
  "quietHours": {
    "title": "Quiet Hours",
    "description": "No notifications during this time",
    "from": "From",
    "to": "To"
  },
  "categories": {
    "title": "Category Settings",
    "description": "Configure notifications for individual categories",
    "type": "Type",
    "error": "Error",
    "errorDesc": "Notify on errors and warnings",
    "success": "Success",
    "successDesc": "Notify on successful operations",
    "mobileApp": "Mobile App",
    "mobileAppDimmed": "No mobile app connected",
    "desktopClient": "Desktop Client",
    "desktopClientDimmed": "No desktop client connected"
  },
  "buttons": {
    "save": "Save",
    "back": "Back"
  },
  "toast": {
    "saved": "Settings saved",
    "loadFailed": "Failed to load settings",
    "saveFailed": "Failed to save"
  },
  "noNotifications": "No notifications",
  "connected": "Connected",
  "markedAllRead": "All marked as read",
  "markError": "Failed to mark as read",
  "allRead": "All read",
  "settings": "Settings",
  "viewAll": "View all",
  "markAllRead": "Mark all as read"
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/i18n/locales/de/notifications.json client/src/i18n/locales/en/notifications.json
git commit -m "feat(notifications): update i18n keys for category settings redesign"
```

---

## Task 10: Frontend — Redesign NotificationPreferencesPage

**Files:**
- Modify: `client/src/pages/NotificationPreferencesPage.tsx`

- [ ] **Step 1: Update imports and types**

In `client/src/pages/NotificationPreferencesPage.tsx`, replace the imports (lines 1-29):

```typescript
/**
 * Notification Preferences Page
 *
 * Allows users to configure their notification settings including
 * channel preferences, category filters, and quiet hours.
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Moon,
  ChevronLeft,
  Save,
  RefreshCw,
  AlertTriangle,
  CircleCheck,
  Smartphone,
  Monitor,
  Check,
  X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { Spinner } from '../components/ui/Spinner';
import {
  getPreferences,
  updatePreferences,
  getDeliveryStatus,
  getCategoryIcon,
  getCategoryName,
  type NotificationPreferences,
  type NotificationCategory,
  type CategoryPreference,
  type DeliveryStatus,
} from '../api/notifications';
import { getMyNotificationRouting, type MyNotificationRouting } from '../api/notificationRouting';
```

- [ ] **Step 2: Update component state and loading**

Replace the state declarations and `loadPreferences` function (lines 49-95) with:

```typescript
export default function NotificationPreferencesPage({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation(['notifications', 'common']);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [_preferences, setPreferences] = useState<NotificationPreferences | null>(null);

  // Local state for form
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietHoursStart, setQuietHoursStart] = useState('22:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('07:00');
  const [minPriority, setMinPriority] = useState(0);
  const [categoryPrefs, setCategoryPrefs] = useState<Record<string, CategoryPreference>>({});
  const [routing, setRouting] = useState<MyNotificationRouting | null>(null);
  const [deliveryStatus, setDeliveryStatus] = useState<DeliveryStatus>({ has_mobile_devices: false, has_desktop_clients: false });

  useEffect(() => {
    loadPreferences();
  }, []);

  useEffect(() => {
    getMyNotificationRouting()
      .then(setRouting)
      .catch(() => setRouting(null));
  }, []);

  useEffect(() => {
    getDeliveryStatus()
      .then(setDeliveryStatus)
      .catch(() => {});
  }, []);

  const loadPreferences = async () => {
    try {
      setLoading(true);
      const prefs = await getPreferences();
      setPreferences(prefs);

      // Populate form
      setQuietHoursEnabled(prefs.quiet_hours_enabled);
      setQuietHoursStart(prefs.quiet_hours_start || '22:00');
      setQuietHoursEnd(prefs.quiet_hours_end || '07:00');
      setMinPriority(prefs.min_priority);

      // Migrate old format category preferences
      const migrated: Record<string, CategoryPreference> = {};
      if (prefs.category_preferences) {
        for (const [cat, pref] of Object.entries(prefs.category_preferences)) {
          const p = pref as any;
          if ('push' in p && !('error' in p)) {
            // Old format: migrate
            migrated[cat] = {
              error: p.in_app ?? true,
              success: cat === 'backup',
              mobile: p.push ?? true,
              desktop: false,
            };
          } else {
            migrated[cat] = {
              error: p.error ?? true,
              success: p.success ?? (cat === 'backup'),
              mobile: p.mobile ?? true,
              desktop: p.desktop ?? false,
            };
          }
        }
      }
      setCategoryPrefs(migrated);
    } catch {
      toast.error(t('common:toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  };
```

- [ ] **Step 3: Update handleSave and helper functions**

Replace `handleSave` and `handleCategoryChange` and `getCategoryPref` (lines 97-136):

```typescript
  const handleSave = async () => {
    try {
      setSaving(true);
      await updatePreferences({
        quiet_hours_enabled: quietHoursEnabled,
        quiet_hours_start: quietHoursEnabled ? quietHoursStart : null,
        quiet_hours_end: quietHoursEnabled ? quietHoursEnd : null,
        min_priority: minPriority,
        category_preferences: categoryPrefs,
      });
      toast.success(t('common:toast.saved'));
    } catch {
      toast.error(t('common:toast.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleCategoryChange = (
    category: NotificationCategory,
    field: keyof CategoryPreference,
    value: boolean
  ) => {
    setCategoryPrefs((prev) => {
      const existing = prev[category] || {
        error: true,
        success: category === 'backup',
        mobile: true,
        desktop: false,
      };
      return {
        ...prev,
        [category]: {
          ...existing,
          [field]: value,
        },
      };
    });
  };

  const getCategoryPref = (category: NotificationCategory): CategoryPreference => {
    return categoryPrefs[category] || {
      error: true,
      success: category === 'backup',
      mobile: true,
      desktop: false,
    };
  };
```

- [ ] **Step 4: Replace the JSX — remove Global Channel Settings, redesign Category table**

Replace the entire JSX return (from the `{/* Global Channel Settings */}` section through the end of the Category Settings table, lines 200-411) with the following. Keep the header section (lines 146-198) and Priority Filter section and Quiet Hours section unchanged. Remove the `{/* Global Channel Settings */}` section entirely. Then replace the `{/* Category Settings */}` section:

```tsx
      {/* Category Settings */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">{t('categories.title')}</h2>
        <p className="mb-4 text-sm text-slate-400">
          {t('categories.description')}
        </p>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800 text-left text-sm text-slate-400">
                <th className="pb-3 pr-4">{t('categories.type')}</th>
                <th className="pb-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-1 text-amber-400">
                    <AlertTriangle className="h-4 w-4" />
                    <span>{t('categories.error')}</span>
                  </div>
                </th>
                <th className="pb-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-1 text-emerald-400">
                    <CircleCheck className="h-4 w-4" />
                    <span>{t('categories.success')}</span>
                  </div>
                </th>
                <th className={`pb-3 px-4 text-center ${!deliveryStatus.has_mobile_devices ? 'opacity-50' : ''}`}>
                  <div className="flex items-center justify-center gap-1">
                    <Smartphone className="h-4 w-4" />
                    <span>{t('categories.mobileApp')}</span>
                  </div>
                </th>
                <th className={`pb-3 pl-4 text-center ${!deliveryStatus.has_desktop_clients ? 'opacity-50' : ''}`}>
                  <div className="flex items-center justify-center gap-1">
                    <Monitor className="h-4 w-4" />
                    <span>{t('categories.desktopClient')}</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {ALL_CATEGORIES.map((category) => {
                const pref = getCategoryPref(category);
                const isActive = pref.error || pref.success;
                return (
                  <tr key={category} className="text-sm">
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{getCategoryIcon(category)}</span>
                        <span className="font-medium text-slate-100">
                          {getCategoryName(category)}
                        </span>
                        {isActive ? (
                          <Check className="h-4 w-4 text-emerald-400" />
                        ) : (
                          <X className="h-4 w-4 text-red-400" />
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <input
                        type="checkbox"
                        checked={pref.error}
                        onChange={(e) =>
                          handleCategoryChange(category, 'error', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                    <td className="py-3 px-4 text-center">
                      <input
                        type="checkbox"
                        checked={pref.success}
                        onChange={(e) =>
                          handleCategoryChange(category, 'success', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                    <td className={`py-3 px-4 text-center ${!deliveryStatus.has_mobile_devices ? 'opacity-50' : ''}`}>
                      <input
                        type="checkbox"
                        checked={pref.mobile}
                        onChange={(e) =>
                          handleCategoryChange(category, 'mobile', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                    <td className={`py-3 pl-4 text-center ${!deliveryStatus.has_desktop_clients ? 'opacity-50' : ''}`}>
                      <input
                        type="checkbox"
                        checked={pref.desktop}
                        onChange={(e) =>
                          handleCategoryChange(category, 'desktop', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
```

Also remove the unused imports `Smartphone` and `Monitor` from the old channel settings (they are now used in the table headers, so they stay in the import list). Remove unused state variables `pushEnabled`, `setPushEnabled`, `inAppEnabled`, `setInAppEnabled` since the global channel toggles are removed.

- [ ] **Step 5: Verify build compiles**

Run:
```bash
cd client && npx tsc --noEmit
```
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/NotificationPreferencesPage.tsx
git commit -m "feat(notifications): redesign category settings table with error/success/mobile/desktop"
```

---

## Task 11: Full Integration Test

**Files:** (no new files)

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py tests/services/test_notification_events.py tests/services/test_firebase_push.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run frontend type check**

Run: `cd client && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Start dev server and verify UI**

Run: `cd "D:/Programme (x86)/Baluhost" && python start_dev.py`

Open `http://localhost:5173/settings?tab=notifications` and verify:
- Global Channel Settings section is removed
- Category Settings table has 5 columns: Typ, Fehler, Erfolg, Mobile App, Desktop Client
- Each category row has a green check or red X indicator
- Mobile App / Desktop Client columns are dimmed if no devices connected
- Checkboxes are clickable and save correctly
- Priority Filter and Quiet Hours sections work as before

- [ ] **Step 4: Commit all remaining changes (if any)**

```bash
git add -A && git status
```

Only commit if there are unstaged fixes discovered during testing.
