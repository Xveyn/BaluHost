# Desktop-Disable Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Push-/In-App-Notification erzeugen, wenn der KDE-Desktop deaktiviert oder reaktiviert wird, pro Event durch Admins an-/abschaltbar (beide default an).

**Architecture:** Wiederverwendung der bestehenden `EventEmitter`-Pipeline. Zwei neue `EventType`-Werte in der `lifecycle`-Kategorie (priority=1/info, immer-an wie Suspend/Resume). Ein neuer „any-admin-wants-it"-Gate als `EventEmitter`-Methode liest pro-Event-Präferenzen aus `category_preferences["desktop_notifications"]` (JSON, keine Migration). Best-effort-Emit aus den Desktop-Routen nach erfolgreichem Toggle. Frontend bekommt eine Admin-only Toggle-Sektion.

**Tech Stack:** FastAPI / SQLAlchemy / Pytest (Backend), React + TypeScript + Vite / Vitest / i18next (Frontend).

Spec: `docs/superpowers/specs/2026-06-06-desktop-disable-notification-design.md`. i18n der Notification-**Inhalte** ist Non-Goal (siehe [#166](https://github.com/Xveyn/BaluHost/issues/166)).

---

## File Structure

| File | Verantwortung | Änderung |
|---|---|---|
| `backend/app/services/notifications/events.py` | Event-Definitionen, Cooldowns, Gate, Emit-Helfer | 2 EventTypes, 2 EVENT_CONFIGS, 2 Cooldowns, `EventEmitter.any_admin_wants_desktop_event`, 4 Emit-Helfer |
| `backend/app/api/routes/desktop.py` | HTTP-Routen Desktop-Toggle | best-effort Emit nach `ok==True` |
| `backend/tests/test_desktop_notifications.py` | Unit-Tests | NEU |
| `client/src/api/notifications.ts` | API-Typen | Typ `category_preferences` um Desktop-Shape erweitern |
| `client/src/pages/NotificationPreferencesPage.tsx` | Notification-Einstellungen | Admin-only Toggle-Sektion + State + Load/Merge |
| `client/src/i18n/locales/de/notifications.json` | DE-i18n | `desktopEvents.*` Keys |
| `client/src/i18n/locales/en/notifications.json` | EN-i18n | `desktopEvents.*` Keys |

---

## Task 1: EventTypes, EVENT_CONFIGS & Cooldowns

**Files:**
- Create: `backend/tests/test_desktop_notifications.py`
- Modify: `backend/app/services/notifications/events.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_desktop_notifications.py`:

```python
"""Tests for desktop disable/enable notifications."""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

import app.services.notifications.service as _notification_service_mod
from app.services.notifications.events import (
    EventEmitter,
    EVENT_CONFIGS,
    EventType,
    _COOLDOWN_SECONDS,
)


def test_desktop_event_configs_present():
    assert EventType.DESKTOP_DISABLED.value == "lifecycle.desktop_disabled"
    assert EventType.DESKTOP_ENABLED.value == "lifecycle.desktop_enabled"
    for et in (EventType.DESKTOP_DISABLED, EventType.DESKTOP_ENABLED):
        cfg = EVENT_CONFIGS[et]
        assert cfg.category == "lifecycle"
        assert cfg.priority == 1
        assert cfg.notification_type == "info"
        assert "{username}" in cfg.message_template
        assert cfg.action_url == "/admin/system-control?tab=sleep"


def test_desktop_event_cooldowns_present():
    assert _COOLDOWN_SECONDS["lifecycle.desktop_disabled"] == 30
    assert _COOLDOWN_SECONDS["lifecycle.desktop_enabled"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_desktop_notifications.py -v`
Expected: FAIL — `AttributeError: DESKTOP_DISABLED` (enum member missing).

- [ ] **Step 3: Add the two EventType values**

In `backend/app/services/notifications/events.py`, in the `EventType` enum, immediately after the line `SYSTEM_STARTUP = "lifecycle.startup"`:

```python
    # Desktop power events
    DESKTOP_DISABLED = "lifecycle.desktop_disabled"
    DESKTOP_ENABLED = "lifecycle.desktop_enabled"
```

- [ ] **Step 4: Add the two cooldown entries**

In `_COOLDOWN_SECONDS`, immediately after the line `"lifecycle.resume": 60,` and before the `# No cooldown for shutdown/startup` comment:

```python
    "lifecycle.desktop_disabled": 30,  # 30s — swallow accidental double-toggle
    "lifecycle.desktop_enabled": 30,
```

- [ ] **Step 5: Add the two EVENT_CONFIGS entries**

In `EVENT_CONFIGS`, immediately after the `EventType.SYSTEM_STARTUP: EventConfig(...)` block (the last entry, ending in `action_url="/",\n    ),`) and before the closing `}` of the dict:

```python
    EventType.DESKTOP_DISABLED: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="Desktop deaktiviert",
        message_template="Die Bildschirme wurden von {username} ausgeschaltet — die GPU kann in den Idle gehen.",
        action_url="/admin/system-control?tab=sleep",
    ),
    EventType.DESKTOP_ENABLED: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="Desktop reaktiviert",
        message_template="Die Bildschirme wurden von {username} wieder eingeschaltet.",
        action_url="/admin/system-control?tab=sleep",
    ),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_desktop_notifications.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/notifications/events.py backend/tests/test_desktop_notifications.py
git commit -m "feat(notifications): add desktop_disabled/enabled event types, configs, cooldowns"
```

---

## Task 2: Gate method & emit helpers

**Files:**
- Modify: `backend/app/services/notifications/events.py`
- Modify: `backend/tests/test_desktop_notifications.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_desktop_notifications.py`:

```python
# ---------------------------------------------------------------------------
# Gate: any_admin_wants_desktop_event
# ---------------------------------------------------------------------------

def _emitter_with_db(db: MagicMock) -> EventEmitter:
    emitter = EventEmitter()
    emitter.set_db_session_factory(lambda: db)
    return emitter


def _db_with_admins(*ids: int) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [(i,) for i in ids]
    return db


def _svc_with_prefs(category_preferences):
    svc = MagicMock()
    prefs = MagicMock()
    prefs.category_preferences = category_preferences
    svc.get_user_preferences.return_value = prefs
    return svc


def test_gate_default_true_when_no_pref():
    db = _db_with_admins(1)
    emitter = _emitter_with_db(db)
    svc = _svc_with_prefs(None)
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc):
        assert emitter.any_admin_wants_desktop_event("disabled") is True
        assert emitter.any_admin_wants_desktop_event("enabled") is True


def test_gate_per_event_independent():
    db = _db_with_admins(1)
    emitter = _emitter_with_db(db)
    svc = _svc_with_prefs({"desktop_notifications": {"disabled": False, "enabled": True}})
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc):
        assert emitter.any_admin_wants_desktop_event("disabled") is False
        assert emitter.any_admin_wants_desktop_event("enabled") is True


def test_gate_false_when_no_admins():
    db = _db_with_admins()  # no admins
    emitter = _emitter_with_db(db)
    svc = _svc_with_prefs({"desktop_notifications": {"disabled": True}})
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc):
        assert emitter.any_admin_wants_desktop_event("disabled") is False


def test_gate_true_when_factory_missing():
    """No DB factory configured (e.g. early startup) -> do not suppress."""
    emitter = EventEmitter()  # no set_db_session_factory
    assert emitter.any_admin_wants_desktop_event("disabled") is True


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------

def test_emit_desktop_disabled_calls_emit_when_wanted():
    from app.services.notifications.events import emit_desktop_disabled_sync, get_event_emitter
    emitter = get_event_emitter()
    with patch.object(emitter, "any_admin_wants_desktop_event", return_value=True), \
         patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_desktop_disabled_sync("alice")
    mock_emit.assert_called_once()
    args, kwargs = mock_emit.call_args
    assert args[0] == EventType.DESKTOP_DISABLED
    assert kwargs.get("username") == "alice"
    assert kwargs.get("cooldown_entity") == "desktop"


def test_emit_desktop_enabled_calls_emit_when_wanted():
    from app.services.notifications.events import emit_desktop_enabled_sync, get_event_emitter
    emitter = get_event_emitter()
    with patch.object(emitter, "any_admin_wants_desktop_event", return_value=True), \
         patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_desktop_enabled_sync("bob")
    mock_emit.assert_called_once()
    args, kwargs = mock_emit.call_args
    assert args[0] == EventType.DESKTOP_ENABLED
    assert kwargs.get("username") == "bob"


def test_emit_desktop_disabled_suppressed_when_not_wanted():
    from app.services.notifications.events import emit_desktop_disabled_sync, get_event_emitter
    emitter = get_event_emitter()
    with patch.object(emitter, "any_admin_wants_desktop_event", return_value=False), \
         patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_desktop_disabled_sync("alice")
    mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_suppresses_second_disable_within_window():
    from app.services.notifications.events import _cooldown_cache
    _cooldown_cache.clear()
    db = _db_with_admins(1)
    notif = MagicMock()
    notif.id = 1
    emitter = _emitter_with_db(db)
    svc = MagicMock()
    svc.get_user_preferences.return_value = None
    svc._get_category_pref.return_value = {"error": True, "success": False, "mobile": False, "desktop": False}
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc), \
         patch("app.services.notifications.events.EventEmitter._send_push_sync"), \
         patch("app.models.notification.Notification", return_value=notif), \
         patch("app.services.notification_routing.get_routed_user_ids", return_value=[]):
        emitter.emit_for_admins_sync(EventType.DESKTOP_DISABLED, cooldown_entity="desktop", username="admin")
        emitter.emit_for_admins_sync(EventType.DESKTOP_DISABLED, cooldown_entity="desktop", username="admin")
    db.add.assert_called_once()  # second suppressed by 30s cooldown
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_desktop_notifications.py -v`
Expected: FAIL — `AttributeError: 'EventEmitter' object has no attribute 'any_admin_wants_desktop_event'` and `ImportError: cannot import name 'emit_desktop_disabled_sync'`.

- [ ] **Step 3: Add the gate method to EventEmitter**

In `backend/app/services/notifications/events.py`, inside `class EventEmitter`, immediately after the `emit_for_admins_sync` method (after its final line `self.emit_sync(event_type, user_id=None, cooldown_entity=cooldown_entity, **kwargs)`) and before `_send_push_sync`:

```python
    def any_admin_wants_desktop_event(self, which: str) -> bool:
        """Return True if at least one active admin wants the desktop *which* event.

        *which* is "disabled" or "enabled". Reads each admin's
        category_preferences["desktop_notifications"][which]; default True.
        Returns True if no DB session factory is configured (e.g. very early
        startup) so notifications are never silently lost.
        """
        if not self._db_session_factory:
            return True
        db = self._db_session_factory()
        try:
            from app.services.notifications.service import get_notification_service
            from app.models.user import User

            svc = get_notification_service()
            admin_ids = [
                uid for (uid,) in db.query(User.id).filter(
                    User.role == "admin",
                    User.is_active == True,
                ).all()
            ]
            for admin_id in admin_ids:
                prefs = svc.get_user_preferences(db, admin_id)
                cat_prefs = (prefs.category_preferences or {}) if prefs else {}
                desktop_prefs = cat_prefs.get("desktop_notifications", {})
                if desktop_prefs.get(which, True):
                    return True
            return False
        finally:
            db.close()
```

- [ ] **Step 4: Add the emit helpers at the end of the file**

Append to the end of `backend/app/services/notifications/events.py` (after the `emit_system_startup` async helper):

```python
# ---------------------------------------------------------------------------
# Desktop power event helpers
# ---------------------------------------------------------------------------


def emit_desktop_disabled_sync(username: str) -> None:
    """Emit lifecycle.desktop_disabled (sync) — fired after a successful disable."""
    emitter = get_event_emitter()
    if not emitter.any_admin_wants_desktop_event("disabled"):
        logger.debug("Desktop-disabled event suppressed: no admin wants it")
        return
    emitter.emit_for_admins_sync(
        EventType.DESKTOP_DISABLED,
        cooldown_entity="desktop",
        username=username,
    )


def emit_desktop_enabled_sync(username: str) -> None:
    """Emit lifecycle.desktop_enabled (sync) — fired after a successful enable."""
    emitter = get_event_emitter()
    if not emitter.any_admin_wants_desktop_event("enabled"):
        logger.debug("Desktop-enabled event suppressed: no admin wants it")
        return
    emitter.emit_for_admins_sync(
        EventType.DESKTOP_ENABLED,
        cooldown_entity="desktop",
        username=username,
    )


async def emit_desktop_disabled(username: str) -> None:
    """Async wrapper — used in the desktop route handler."""
    emit_desktop_disabled_sync(username)


async def emit_desktop_enabled(username: str) -> None:
    """Async wrapper — used in the desktop route handler."""
    emit_desktop_enabled_sync(username)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_desktop_notifications.py -v`
Expected: PASS (all gate, emit-helper and cooldown tests green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notifications/events.py backend/tests/test_desktop_notifications.py
git commit -m "feat(notifications): add desktop event gate + emit helpers"
```

---

## Task 3: Wire emit into the desktop routes

**Files:**
- Modify: `backend/app/api/routes/desktop.py`
- Modify: `backend/tests/test_desktop_notifications.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_desktop_notifications.py`:

```python
# ---------------------------------------------------------------------------
# Route wiring (uses TestClient + admin auth)
# ---------------------------------------------------------------------------

from app.core.config import settings

_DISABLE_URL = f"{settings.api_prefix}/system/sleep/desktop/disable"
_ENABLE_URL = f"{settings.api_prefix}/system/sleep/desktop/enable"


def test_route_emits_on_disable_success(client, admin_headers):
    with patch("app.api.routes.desktop.emit_desktop_disabled", new=AsyncMock()) as m:
        r = client.post(_DISABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
    m.assert_awaited_once()
    assert m.await_args.args[0] == settings.admin_username


def test_route_emits_on_enable_success(client, admin_headers):
    with patch("app.api.routes.desktop.emit_desktop_enabled", new=AsyncMock()) as m:
        r = client.post(_ENABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
    m.assert_awaited_once()
    assert m.await_args.args[0] == settings.admin_username


def test_route_no_emit_on_disable_failure(client, admin_headers):
    svc = MagicMock()
    svc.disable = AsyncMock(return_value=(False, "boom"))
    with patch("app.api.routes.desktop.get_desktop_service", return_value=svc), \
         patch("app.api.routes.desktop.emit_desktop_disabled", new=AsyncMock()) as m:
        r = client.post(_DISABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is False
    m.assert_not_awaited()


def test_route_emit_failure_does_not_break_toggle(client, admin_headers):
    with patch("app.api.routes.desktop.emit_desktop_disabled",
               new=AsyncMock(side_effect=RuntimeError("push down"))):
        r = client.post(_DISABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_desktop_notifications.py -k route -v`
Expected: FAIL — `emit_desktop_disabled` not awaited (route does not emit yet) / `AttributeError` on the patch target (name not imported in `desktop.py`).

- [ ] **Step 3: Import the emit helpers in the route module**

In `backend/app/api/routes/desktop.py`, immediately after the line `from app.services.power.desktop import get_desktop_service`:

```python
from app.services.notifications.events import emit_desktop_disabled, emit_desktop_enabled
```

- [ ] **Step 4: Emit on success in `desktop_disable`**

In `backend/app/api/routes/desktop.py`, in `desktop_disable`, replace the final `return` block. Find:

```python
    if current_user.role != "admin":
        # Mirror the sleep routes: record that a delegated (non-admin) user
        # invoked a privileged power action, for the security-audit trail.
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="toggle_desktop",
            details={"action": "desktop_disable"},
            success=True,
        )
    return {"success": ok, "message": message}
```

Replace with (keep everything identical, add the `if ok:` block before `return`):

```python
    if current_user.role != "admin":
        # Mirror the sleep routes: record that a delegated (non-admin) user
        # invoked a privileged power action, for the security-audit trail.
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="toggle_desktop",
            details={"action": "desktop_disable"},
            success=True,
        )
    if ok:
        try:
            await emit_desktop_disabled(current_user.username)
        except Exception as exc:  # best-effort: never break the toggle
            logger.warning("Desktop-disabled notification failed: %s", exc)
    return {"success": ok, "message": message}
```

- [ ] **Step 5: Emit on success in `desktop_enable`**

In `desktop_enable`, find:

```python
    if current_user.role != "admin":
        # Mirror the sleep routes: record that a delegated (non-admin) user
        # invoked a privileged power action, for the security-audit trail.
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="toggle_desktop",
            details={"action": "desktop_enable"},
            success=True,
        )
    return {"success": ok, "message": message}
```

Replace with:

```python
    if current_user.role != "admin":
        # Mirror the sleep routes: record that a delegated (non-admin) user
        # invoked a privileged power action, for the security-audit trail.
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="toggle_desktop",
            details={"action": "desktop_enable"},
            success=True,
        )
    if ok:
        try:
            await emit_desktop_enabled(current_user.username)
        except Exception as exc:  # best-effort: never break the toggle
            logger.warning("Desktop-enabled notification failed: %s", exc)
    return {"success": ok, "message": message}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_desktop_notifications.py -v`
Expected: PASS (all tests, incl. route tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/desktop.py backend/tests/test_desktop_notifications.py
git commit -m "feat(desktop): emit desktop disabled/enabled notification on success"
```

---

## Task 4: Frontend API type

**Files:**
- Modify: `client/src/api/notifications.ts`

- [ ] **Step 1: Add the `DesktopEventsPref` interface**

In `client/src/api/notifications.ts`, immediately after the `CategoryPreference` interface (the block ending with `desktop: boolean;\n}`):

```typescript
export interface DesktopEventsPref {
  disabled: boolean;
  enabled: boolean;
}
```

- [ ] **Step 2: Widen the update type**

In the `NotificationPreferencesUpdate` interface, replace the line:

```typescript
  category_preferences?: Record<string, CategoryPreference>;
```

with:

```typescript
  category_preferences?: Record<string, CategoryPreference | DesktopEventsPref>;
```

- [ ] **Step 3: Verify the client still type-checks**

Run: `cd client && npx tsc --noEmit`
Expected: No new errors from `notifications.ts` (a pre-existing clean tree stays clean).

- [ ] **Step 4: Commit**

```bash
git add client/src/api/notifications.ts
git commit -m "feat(notifications): type desktop_notifications pref in update payload"
```

---

## Task 5: Frontend toggle section

**Files:**
- Modify: `client/src/pages/NotificationPreferencesPage.tsx`

- [ ] **Step 1: Add the `desktopEvents` state**

In `client/src/pages/NotificationPreferencesPage.tsx`, immediately after the line:

```typescript
  const [categoryPrefs, setCategoryPrefs] = useState<Record<string, CategoryPreference>>({});
```

add:

```typescript
  const [desktopEvents, setDesktopEvents] = useState<{ disabled: boolean; enabled: boolean }>({
    disabled: true,
    enabled: true,
  });
```

- [ ] **Step 2: Load `desktopEvents` in `loadPreferences`**

In `loadPreferences`, immediately after `setCategoryPrefs(migrated);`:

```typescript
      const de = (rawPrefs as any)?.desktop_notifications;
      setDesktopEvents({
        disabled: de?.disabled ?? true,
        enabled: de?.enabled ?? true,
      });
```

- [ ] **Step 3: Merge `desktopEvents` into the save payload**

In `handleSave`, replace the line:

```typescript
        category_preferences: categoryPrefs,
```

with:

```typescript
        category_preferences: {
          ...categoryPrefs,
          desktop_notifications: desktopEvents,
        },
```

- [ ] **Step 4: Add the Admin-only toggle section**

In the returned JSX, immediately after the Category Settings block — i.e. after the closing `)}` of the `{!isAdmin && visibleCategories.length === 0 ? (...) : (...)}` ternary and before the final `</div>` that closes the page wrapper — insert:

```tsx
      {/* Desktop power notifications (admin only) */}
      {isAdmin && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
          <div className="mb-4 flex items-center gap-3">
            <Monitor className="h-5 w-5 text-slate-400" />
            <div>
              <h2 className="text-lg font-semibold text-slate-100">{t('desktopEvents.title')}</h2>
              <p className="text-sm text-slate-400">{t('desktopEvents.description')}</p>
            </div>
          </div>
          <div className="space-y-3">
            <label className="flex items-center justify-between">
              <span className="text-sm text-slate-300">{t('desktopEvents.onDisable')}</span>
              <span className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  checked={desktopEvents.disabled}
                  onChange={(e) => setDesktopEvents((p) => ({ ...p, disabled: e.target.checked }))}
                  className="peer sr-only"
                />
                <span className="peer h-6 w-11 rounded-full bg-slate-700 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-slate-600 after:bg-slate-400 after:transition-all after:content-[''] peer-checked:bg-sky-500 peer-checked:after:translate-x-full peer-checked:after:border-white" />
              </span>
            </label>
            <label className="flex items-center justify-between">
              <span className="text-sm text-slate-300">{t('desktopEvents.onEnable')}</span>
              <span className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  checked={desktopEvents.enabled}
                  onChange={(e) => setDesktopEvents((p) => ({ ...p, enabled: e.target.checked }))}
                  className="peer sr-only"
                />
                <span className="peer h-6 w-11 rounded-full bg-slate-700 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-slate-600 after:bg-slate-400 after:transition-all after:content-[''] peer-checked:bg-sky-500 peer-checked:after:translate-x-full peer-checked:after:border-white" />
              </span>
            </label>
          </div>
        </div>
      )}
```

> `Monitor` is already imported from `lucide-react` at the top of this file — no new import needed.

- [ ] **Step 5: Verify the client type-checks**

Run: `cd client && npx tsc --noEmit`
Expected: No new errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/NotificationPreferencesPage.tsx
git commit -m "feat(notifications): admin toggles for desktop disable/enable notifications"
```

---

## Task 6: i18n keys (DE + EN)

**Files:**
- Modify: `client/src/i18n/locales/de/notifications.json`
- Modify: `client/src/i18n/locales/en/notifications.json`

- [ ] **Step 1: German keys**

In `client/src/i18n/locales/de/notifications.json`, immediately before the top-level `"buttons": {` object, insert:

```json
  "desktopEvents": {
    "title": "Desktop-Benachrichtigungen",
    "description": "Benachrichtigen, wenn der Desktop deaktiviert oder reaktiviert wird",
    "onDisable": "Bei Deaktivierung benachrichtigen",
    "onEnable": "Bei Reaktivierung benachrichtigen"
  },
```

- [ ] **Step 2: English keys**

In `client/src/i18n/locales/en/notifications.json`, immediately before the top-level `"buttons": {` object, insert:

```json
  "desktopEvents": {
    "title": "Desktop notifications",
    "description": "Notify when the desktop is disabled or re-enabled",
    "onDisable": "Notify on disable",
    "onEnable": "Notify on re-enable"
  },
```

- [ ] **Step 3: Verify both JSON files are valid**

Run:
```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/notifications.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/notifications.json','utf8')); console.log('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/notifications.json client/src/i18n/locales/en/notifications.json
git commit -m "i18n(notifications): desktopEvents toggle labels (de/en)"
```

---

## Task 7: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the new backend tests**

Run: `cd backend && python -m pytest tests/test_desktop_notifications.py -v`
Expected: PASS (all).

- [ ] **Step 2: Run the related notification suites (no regression)**

Run: `cd backend && python -m pytest tests/services/test_notification_events.py tests/test_lifecycle_notifications.py -q`
Expected: PASS (all previously-passing tests still pass).

- [ ] **Step 3: Run the frontend unit suite + build typecheck**

Run: `cd client && npx vitest run && npm run build`
Expected: Vitest green; production build (tsc + vite) succeeds.

- [ ] **Step 4: Manual smoke (dev mode)**

1. `python start_dev.py`, login as admin.
2. PowerMenu → „Desktop deaktivieren" → Glocke zeigt „Desktop deaktiviert … von admin".
3. System Control → Sleep → Desktop reaktivieren → „Desktop reaktiviert … von admin".
4. Notification-Einstellungen → „Bei Deaktivierung benachrichtigen" aus, speichern → erneut deaktivieren → **keine** Notification.
5. Zwei schnelle Deaktivierungen < 30 s → nur eine Notification (Cooldown).

- [ ] **Step 5: No commit** (verification only).

---

## Notes for the implementer

- **Dev mode:** `DevDesktopBackend.disable/enable` return `(True, ...)`, so the emit fires in dev — good for the manual smoke and route tests.
- **Single-admin reality:** the gate's „any admin wants it" is effectively a personal switch (BaluHost has one admin). With multiple admins, the shared system notification appears in every admin's bell; per-admin bell muting is out of scope (see spec).
- **No migration:** prefs live in the existing `category_preferences` JSON column under the reserved key `desktop_notifications`.
- **Notification text stays German** (backend templates), consistent with the whole system — see [#166](https://github.com/Xveyn/BaluHost/issues/166).
