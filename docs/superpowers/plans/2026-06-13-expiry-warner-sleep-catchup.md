# Expiry-Warner Sleep Catch-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Device-Ablauf-Warnungen (7d/3d/1h) gehen nicht mehr verloren, wenn die NAS während des Warnfensters per True-Suspend schläft (Issue #229).

**Architecture:** Zwei unabhängige Teile. **Teil A** ersetzt das harte ±35-Min-Fenster in `_should_send_warning` durch eine „fällig-oder-überfällig, noch nicht gesendet, noch nicht abgelaufen"-Regel und kollabiert einen über Nacht aufgelaufenen Rückstand auf genau eine (die dringlichste) Notification. **Teil B** stößt einen Nachhol-Lauf direkt nach dem Aufwachen (`enter_true_suspend`) und einmalig beim Startup an, damit überfällige Warnungen sofort statt erst beim nächsten Scheduler-Tick rausgehen.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, APScheduler (Unified-Scheduler-Worker), pytest.

---

## Context: aktuelle Verdrahtung (vor der Implementierung lesen)

- Der periodische Check läuft **nicht** über die Standalone-`start_notification_scheduler()` in `backend/app/services/notifications/scheduler.py` — diese Funktion wird **nirgends aufgerufen** (toter Pfad, nur re-exportiert in `notifications/__init__.py`). Der **Live-Pfad** ist der Unified-Scheduler-Worker: `backend/app/services/scheduler/worker.py:356-359` dispatcht `notification_check` → `NotificationScheduler.run_periodic_check()`.
- Während `enter_true_suspend()` (`backend/app/services/power/sleep.py:986`) macht das Backend `rtcwake -m mem` — der **gesamte Prozess friert ein**. APScheduler-`interval`-Jobs holen Misfires per Default nicht nach → der verpasste Lauf ist weg, und das ±35-Min-Fenster in `_should_send_warning` verwirft die Warnung dann dauerhaft.
- `enter_true_suspend()` kehrt nach dem Wake in-process zurück und feuert dort bereits `emit_system_resume` (`sleep.py:1145-1155`, Primary-Worker). Das ist der Aufhängepunkt für Teil B.
- Die `WARNING_THRESHOLDS` (7d/3d/1h) und die `ExpirationNotification`-Dedup-Tabelle bleiben unverändert; die Kollaps-Logik nutzt die bestehende Dedup-Semantik (`success=True` → wird nicht erneut gesendet).
- **Bewusstes Non-Goal:** Warnungen werden NICHT in Kernbetriebszeit-Fenster umgeplant. Sie sollen beim ersten Wach-Moment raus. Die „Kopplung an Kernbetriebszeit" ist faktisch „geht im Sleep nicht verloren" — das liefert A+B.
- Der „expired/deauthorized"-Push beim tatsächlichen Ablauf gehört zu Issue #228 und ist hier **out of scope**; dieser Plan stellt nur sicher, dass nach Ablauf (`now >= expires_at`) keine sinnlose Lead-Warnung mehr feuert.

Test-Fixtures: `db_session`, `admin_user` existieren in `backend/tests/conftest.py` (siehe Nutzung in `backend/tests/services/test_firebase_push.py`). `MobileDevice` akzeptiert `user_id, device_name, device_type, push_token, is_active, expires_at`.

---

## Task 1: Teil A — `_should_send_warning` auf „fällig-oder-überfällig" umstellen

**Files:**
- Create: `backend/tests/services/test_notification_scheduler_catchup.py`
- Modify: `backend/app/services/notifications/scheduler.py:127-182` (`_should_send_warning`)

- [ ] **Step 1: Failing-Tests für `_should_send_warning` schreiben**

Create `backend/tests/services/test_notification_scheduler_catchup.py`:

```python
"""Tests for the device-expiration warning catch-up logic (#229).

Covers _should_send_warning's due/overdue rule and check_and_send_warnings'
backlog collapse + post-expiry skip.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.mobile import MobileDevice, ExpirationNotification
from app.models.user import User
from app.services.notifications.scheduler import NotificationScheduler


def _make_device(db: Session, user: User, expires_at: datetime) -> MobileDevice:
    device = MobileDevice(
        user_id=user.id,
        device_name="Catchup Phone",
        device_type="android",
        push_token="fake-fcm-token-catchup",
        is_active=True,
        expires_at=expires_at,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class TestShouldSendWarning:
    def test_not_yet_due(self, db_session: Session, admin_user: User):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(days=10))
        warning_time = now + timedelta(days=3)  # still in the future
        should_send, reason = NotificationScheduler._should_send_warning(
            db=db_session, device=device, warning_type="7_days",
            warning_time=warning_time, now=now,
        )
        assert should_send is False
        assert reason == "Not yet due"

    def test_overdue_unsent_sends(self, db_session: Session, admin_user: User):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(hours=2))
        warning_time = now - timedelta(hours=20)  # passed long ago (during sleep)
        should_send, reason = NotificationScheduler._should_send_warning(
            db=db_session, device=device, warning_type="7_days",
            warning_time=warning_time, now=now,
        )
        assert should_send is True

    def test_already_sent_skips(self, db_session: Session, admin_user: User):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(hours=2))
        db_session.add(ExpirationNotification(
            device_id=device.id, notification_type="7_days",
            sent_at=now, success=True, device_expires_at=device.expires_at,
        ))
        db_session.commit()
        warning_time = now - timedelta(hours=20)
        should_send, reason = NotificationScheduler._should_send_warning(
            db=db_session, device=device, warning_type="7_days",
            warning_time=warning_time, now=now,
        )
        assert should_send is False
        assert reason == "Warning already sent"
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/services/test_notification_scheduler_catchup.py::TestShouldSendWarning -v`
Expected: `test_not_yet_due` FAIL (aktuell liefert die Methode `"Not within warning window"` statt `"Not yet due"`, weil das ±35-Min-Fenster greift). Die anderen beiden können bereits passen.

- [ ] **Step 3: `_should_send_warning` neu schreiben**

Replace the body of `_should_send_warning` in `backend/app/services/notifications/scheduler.py` (lines 127-182, from the `"""` docstring close down to `return True, ""`) with:

```python
        # Not yet due — the warning time is still in the future.
        if now < warning_time:
            return False, "Not yet due"

        # Already handled for this exact expiry (sent or superseded)?
        existing_notification = db.query(ExpirationNotification).filter(
            ExpirationNotification.device_id == device.id,
            ExpirationNotification.notification_type == warning_type,
            ExpirationNotification.device_expires_at == device.expires_at
        ).first()

        if existing_notification:
            # Retry previously failed notifications (up to 3 attempts)
            if not existing_notification.success:
                fail_count = db.query(ExpirationNotification).filter(
                    ExpirationNotification.device_id == device.id,
                    ExpirationNotification.notification_type == warning_type,
                    ExpirationNotification.device_expires_at == device.expires_at,
                    ExpirationNotification.success == False
                ).count()
                if fail_count < 3:
                    # Delete failed record so _send_warning creates a fresh one
                    db.delete(existing_notification)
                    db.flush()
                    return True, ""
                return False, f"Max retries reached ({fail_count} failures)"
            return False, "Warning already sent"

        return True, ""
```

Also update the method's docstring `Returns` note if desired (optional, no behavior impact).

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `cd backend && python -m pytest tests/services/test_notification_scheduler_catchup.py::TestShouldSendWarning -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/scheduler.py backend/tests/services/test_notification_scheduler_catchup.py
git commit -m "fix(notifications): warner sends due/overdue warnings instead of dropping them (#229)"
```

---

## Task 2: Teil A — Backlog-Kollaps + Post-Expiry-Skip in `check_and_send_warnings`

**Files:**
- Modify: `backend/app/services/notifications/scheduler.py:30-125` (`check_and_send_warnings`), add `_record_superseded` classmethod
- Test: `backend/tests/services/test_notification_scheduler_catchup.py`

- [ ] **Step 1: Failing-Tests für das Verhalten schreiben**

Append to `backend/tests/services/test_notification_scheduler_catchup.py`:

```python
class TestCheckAndSendWarnings:
    @pytest.fixture
    def fake_send(self, monkeypatch):
        """Patch FirebaseService.send_expiration_warning; record calls."""
        calls = []

        def _send(device_token, device_name, expires_at, warning_type, server_url):
            calls.append(warning_type)
            return {"success": True, "message_id": "mid-1", "error": None}

        monkeypatch.setattr(
            "app.services.notifications.firebase.FirebaseService.send_expiration_warning",
            staticmethod(_send),
        )
        return calls

    def _rows(self, db, device):
        return db.query(ExpirationNotification).filter(
            ExpirationNotification.device_id == device.id
        ).all()

    def test_backlog_collapses_to_most_urgent(self, db_session, admin_user, fake_send):
        # Expires in 30 min → all three thresholds are overdue.
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(minutes=30))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 1
        assert fake_send == ["1_hour"]  # only the most urgent goes out
        rows = self._rows(db_session, device)
        by_type = {r.notification_type: r for r in rows}
        assert by_type["1_hour"].success is True
        assert by_type["3_days"].error_message == "superseded_by_more_urgent"
        assert by_type["7_days"].error_message == "superseded_by_more_urgent"

    def test_normal_single_threshold(self, db_session, admin_user, fake_send):
        # Expires in 5 days → only 7_days is due.
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(days=5))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 1
        assert fake_send == ["7_days"]
        types = {r.notification_type for r in self._rows(db_session, device)}
        assert types == {"7_days"}  # 3_days / 1_hour neither sent nor superseded

    def test_skips_when_already_expired(self, db_session, admin_user, fake_send):
        now = datetime.now(timezone.utc)
        _make_device(db_session, admin_user, now - timedelta(minutes=10))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 0
        assert fake_send == []

    def test_no_resend_when_already_sent(self, db_session, admin_user, fake_send):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(minutes=30))
        db_session.add(ExpirationNotification(
            device_id=device.id, notification_type="1_hour",
            sent_at=now, success=True, device_expires_at=device.expires_at,
        ))
        db_session.commit()

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 0
        assert fake_send == []

    def test_failed_send_does_not_supersede(self, db_session, admin_user, monkeypatch):
        def _send_fail(device_token, device_name, expires_at, warning_type, server_url):
            return {"success": False, "message_id": None, "error": "boom"}

        monkeypatch.setattr(
            "app.services.notifications.firebase.FirebaseService.send_expiration_warning",
            staticmethod(_send_fail),
        )
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(minutes=30))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["failed"] == 1
        rows = {r.notification_type: r for r in db_session.query(ExpirationNotification).filter(
            ExpirationNotification.device_id == device.id).all()}
        assert rows["1_hour"].success is False
        # Less-urgent warnings must NOT be superseded — they retry next tick.
        assert "3_days" not in rows
        assert "7_days" not in rows
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/services/test_notification_scheduler_catchup.py::TestCheckAndSendWarnings -v`
Expected: mehrere FAIL — `_record_superseded` existiert nicht; aktuelles `check_and_send_warnings` sendet alle drei überfälligen Warnungen statt zu kollabieren und kennt den Post-Expiry-Skip nicht.

- [ ] **Step 3: `_record_superseded` ergänzen**

In `backend/app/services/notifications/scheduler.py`, immediately after the `_send_warning` classmethod (after its `return result`, before `run_periodic_check`), add:

```python
    @classmethod
    def _record_superseded(
        cls,
        db: Session,
        device: MobileDevice,
        warning_type: str
    ) -> None:
        """Mark a less-urgent warning as handled so it never fires later.

        Used when a more urgent warning for the same expiry is the one the user
        should see (e.g. a 7d + 3d + 1h backlog accumulated while the NAS was
        suspended). Idempotent: if any row already exists for this
        (device, warning_type, expiry) it leaves it untouched. Recorded with
        success=True so _should_send_warning treats it as done.
        """
        existing = db.query(ExpirationNotification).filter(
            ExpirationNotification.device_id == device.id,
            ExpirationNotification.notification_type == warning_type,
            ExpirationNotification.device_expires_at == device.expires_at,
        ).first()
        if existing:
            return

        notification = ExpirationNotification(
            device_id=device.id,
            notification_type=warning_type,
            sent_at=datetime.now(timezone.utc),
            success=True,
            fcm_message_id=None,
            error_message="superseded_by_more_urgent",
            device_expires_at=device.expires_at,
        )
        db.add(notification)
        db.commit()
```

- [ ] **Step 4: Den Geräte-Loop in `check_and_send_warnings` ersetzen**

In `backend/app/services/notifications/scheduler.py`, replace the device loop inside `check_and_send_warnings` — from `now = datetime.now(timezone.utc)` (currently line 64) down to the end of the `for device in devices:` block (the `except Exception as e:` that appends the per-device error, currently ending line 117) — with:

```python
            now = datetime.now(timezone.utc)

            # Most-urgent threshold first so a backlog (accumulated while the
            # NAS was suspended) collapses to a single, accurate message.
            ordered_thresholds = sorted(
                cls.WARNING_THRESHOLDS.items(), key=lambda kv: kv[1]
            )

            for device in devices:
                try:
                    if device.expires_at is None:
                        continue
                    # Ensure expires_at is timezone-aware (PostgreSQL may store naive)
                    expires_at = device.expires_at
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)

                    # Past expiry: lead-time warnings no longer apply. The
                    # "expired / deauthorized" push is handled separately (#228).
                    if now >= expires_at:
                        stats["skipped"] += 1
                        continue

                    # Thresholds whose warning time has arrived, most urgent first.
                    due = [
                        (warning_type, expires_at - threshold)
                        for warning_type, threshold in ordered_thresholds
                        if now >= (expires_at - threshold)
                    ]
                    if not due:
                        stats["skipped"] += 1
                        continue

                    # The single most-urgent due warning is the one the user
                    # should see; everything less urgent gets suppressed.
                    most_urgent_type, most_urgent_time = due[0]
                    less_urgent = due[1:]

                    should_send, reason = cls._should_send_warning(
                        db=db,
                        device=device,
                        warning_type=most_urgent_type,
                        warning_time=most_urgent_time,
                        now=now,
                    )

                    if should_send:
                        result = cls._send_warning(
                            db=db, device=device, warning_type=most_urgent_type
                        )
                        if result["success"]:
                            stats["sent"] += 1
                            logger.info(f"[NotificationScheduler] ✅ Sent {most_urgent_type} warning to {device.device_name}")
                            for lt, _ in less_urgent:
                                cls._record_superseded(db, device, lt)
                            stats["skipped"] += len(less_urgent)
                        else:
                            stats["failed"] += 1
                            stats["errors"].append({
                                "device": device.device_name,
                                "warning": most_urgent_type,
                                "error": result.get("error"),
                            })
                            logger.info(f"[NotificationScheduler] ❌ Failed to send {most_urgent_type} to {device.device_name}: {result.get('error')}")
                            # Don't supersede the less-urgent ones — the failed
                            # warning retries on the next run.
                    else:
                        # Most-urgent due warning already handled (sent earlier /
                        # superseded / max retries) → suppress the rest too.
                        stats["skipped"] += 1
                        if reason:
                            logger.info(f"[NotificationScheduler] ⏭️ Skipped {most_urgent_type} for {device.device_name}: {reason}")
                        for lt, _ in less_urgent:
                            cls._record_superseded(db, device, lt)
                        stats["skipped"] += len(less_urgent)

                except Exception as e:
                    stats["failed"] += 1
                    stats["errors"].append({
                        "device": device.device_name,
                        "error": str(e)
                    })
                    logger.info(f"[NotificationScheduler] ❌ Error processing device {device.device_name}: {e}")
```

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `cd backend && python -m pytest tests/services/test_notification_scheduler_catchup.py -v`
Expected: alle Tests passed (TestShouldSendWarning + TestCheckAndSendWarnings).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notifications/scheduler.py backend/tests/services/test_notification_scheduler_catchup.py
git commit -m "fix(notifications): collapse overdue-warning backlog to one message, skip post-expiry (#229)"
```

---

## Task 3: Teil B — Nachhol-Lauf nach dem Aufwachen aus True-Suspend

**Files:**
- Modify: `backend/app/services/power/sleep.py:1145-1159` (resume branch in `enter_true_suspend`)
- Test: `backend/tests/test_expiry_catchup_on_resume.py`

- [ ] **Step 1: Failing-Test schreiben**

Create `backend/tests/test_expiry_catchup_on_resume.py`:

```python
"""enter_true_suspend triggers a device-expiration catch-up after wake (#229)."""

import asyncio
from unittest.mock import patch, AsyncMock

from app.schemas.sleep import SleepTrigger


def test_resume_triggers_expiry_catchup():
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    # emit_system_suspend/resume are awaited inside enter_true_suspend, so they
    # MUST be AsyncMock (a plain MagicMock is not awaitable → asyncio.wait_for
    # would raise).
    with patch(
        "app.services.notifications.scheduler.NotificationScheduler.check_and_send_warnings",
        return_value={"checked": 0, "sent": 0, "skipped": 0, "failed": 0, "errors": []},
    ) as mock_check, patch(
        "app.services.notifications.events.emit_system_suspend", new=AsyncMock(),
    ), patch(
        "app.services.notifications.events.emit_system_resume", new=AsyncMock(),
    ):
        result = asyncio.run(svc.enter_true_suspend("test", SleepTrigger.MANUAL))

    assert result is True
    assert mock_check.call_count == 1
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/test_expiry_catchup_on_resume.py -v`
Expected: FAIL — `check_and_send_warnings` wird nie aufgerufen (`call_count == 0`).

- [ ] **Step 3: Resume-Hook einbauen**

In `backend/app/services/power/sleep.py`, locate the resume branch in `enter_true_suspend` (the `if ok:` block, around lines 1124-1155). Immediately after the line `await self._exit_soft_sleep("resume_from_suspend")` (line 1155), add:

```python

            # 5. Catch-up: send any device-expiration warnings whose window
            #    elapsed while the system was suspended (#229). Runs off the
            #    event loop so FCM I/O can't block; best-effort.
            try:
                from app.services.notifications.scheduler import NotificationScheduler

                def _expiry_catchup() -> None:
                    catch_db = SessionLocal()
                    try:
                        NotificationScheduler.check_and_send_warnings(catch_db)
                    finally:
                        catch_db.close()

                await asyncio.to_thread(_expiry_catchup)
            except Exception as exc:
                logger.warning("Expiration warning catch-up after resume failed: %s", exc)
```

(`asyncio`, `SessionLocal`, and `logger` are already imported at the top of `sleep.py`.)

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && python -m pytest tests/test_expiry_catchup_on_resume.py -v`
Expected: 1 passed.

- [ ] **Step 5: Sleep-Regression prüfen**

Run: `cd backend && python -m pytest tests/ -k "sleep or suspend or lifecycle" -v`
Expected: alle bisher grünen Sleep-/Lifecycle-Tests bleiben grün.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/test_expiry_catchup_on_resume.py
git commit -m "fix(sleep): run expiration-warning catch-up after resume from suspend (#229)"
```

---

## Task 4: Teil B — Einmaliger Nachhol-Lauf beim Startup

**Files:**
- Modify: `backend/app/core/lifespan.py` (neue Helper-Funktion auf Modulebene + Aufruf im Primary-Worker-Block bei ~Zeile 511)
- Test: `backend/tests/test_expiry_catchup_on_resume.py`

- [ ] **Step 1: Failing-Tests schreiben**

Append to `backend/tests/test_expiry_catchup_on_resume.py`:

```python
def test_startup_catchup_runs_when_firebase_available():
    from app.core import lifespan

    with patch(
        "app.services.notifications.firebase.FirebaseService.is_available",
        return_value=True,
    ), patch(
        "app.services.notifications.scheduler.NotificationScheduler.check_and_send_warnings",
        return_value={"checked": 0, "sent": 0, "skipped": 0, "failed": 0, "errors": []},
    ) as mock_check:
        asyncio.run(lifespan._expiry_warning_catchup_on_startup())

    assert mock_check.call_count == 1


def test_startup_catchup_skipped_without_firebase():
    from app.core import lifespan

    with patch(
        "app.services.notifications.firebase.FirebaseService.is_available",
        return_value=False,
    ), patch(
        "app.services.notifications.scheduler.NotificationScheduler.check_and_send_warnings",
    ) as mock_check:
        asyncio.run(lifespan._expiry_warning_catchup_on_startup())

    assert mock_check.call_count == 0
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/test_expiry_catchup_on_resume.py -k startup -v`
Expected: FAIL — `lifespan._expiry_warning_catchup_on_startup` existiert noch nicht (`AttributeError`).

- [ ] **Step 3: Helper-Funktion ergänzen**

In `backend/app/core/lifespan.py`, add this module-level coroutine (place it just above `async def _startup(`):

```python
async def _expiry_warning_catchup_on_startup() -> None:
    """One-shot device-expiration catch-up after (re)start.

    Sends warnings whose window elapsed while the box was off/suspended, so
    they go out promptly instead of waiting for the next scheduler tick (#229).
    Best-effort; runs off the event loop so FCM I/O can't block startup.
    """
    try:
        from app.services.notifications.firebase import FirebaseService
        if not FirebaseService.is_available():
            return
        from app.services.notifications.scheduler import NotificationScheduler
        from app.core.database import SessionLocal

        def _run() -> None:
            db = SessionLocal()
            try:
                NotificationScheduler.check_and_send_warnings(db)
            finally:
                db.close()

        await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("Startup expiration-warning catch-up failed: %s", exc)
```

- [ ] **Step 4: Aufruf im Primary-Worker-Block einhängen**

In `backend/app/core/lifespan.py`, inside `_startup`, find the `if IS_PRIMARY_WORKER:` block that starts the background loops (currently around line 511, with `asyncio.create_task(_write_service_heartbeats())`). Immediately after `asyncio.create_task(_pihole_health_loop())`, add:

```python
        asyncio.create_task(_expiry_warning_catchup_on_startup())
```

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `cd backend && python -m pytest tests/test_expiry_catchup_on_resume.py -v`
Expected: 3 passed (resume + 2 startup tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/lifespan.py backend/tests/test_expiry_catchup_on_resume.py
git commit -m "fix(lifespan): one-shot expiration-warning catch-up on startup (#229)"
```

---

## Task 5: Verifikation — volle Suite + Smoke

**Files:** keine

- [ ] **Step 1: Betroffene Tests gebündelt laufen lassen**

Run: `cd backend && python -m pytest tests/services/test_notification_scheduler_catchup.py tests/test_expiry_catchup_on_resume.py -v`
Expected: alle passed.

- [ ] **Step 2: Notification-/Sleep-Regression**

Run: `cd backend && python -m pytest tests/ -k "notification or sleep or suspend or lifecycle or firebase" -v`
Expected: keine neuen Fehlschläge gegenüber `main`.

- [ ] **Step 3: Import-Smoke**

Run: `cd backend && python -c "from app.services.notifications.scheduler import NotificationScheduler; from app.core import lifespan; print('OK')"`
Expected: `OK`, kein Traceback.

- [ ] **Step 4: Dev-Smoke (optional, manuell)**

In `python start_dev.py` (dev mode, DevSleepBackend simuliert Suspend mit 2s Wake): ein `MobileDevice` mit `expires_at = now + 30min` und `push_token` anlegen, dann `POST /api/sleep/suspend` auslösen. Nach dem simulierten Wake im Log `[NotificationScheduler] ... Sent 1_hour warning` erwarten und genau eine `ExpirationNotification`-Zeile mit `success=True` plus zwei `superseded_by_more_urgent`-Zeilen. (FCM no-op ohne Credentials — Log/DB-Zeilen genügen als Nachweis.)

---

## Self-Review

**Spec coverage (Issue #229):**
- ±35-Min-Fenster entfernt / „verlieren statt nachholen" behoben → Task 1 (`_should_send_warning`).
- Backlog nach Sleep → genau eine (dringlichste) Notification, Rest superseded → Task 2.
- Post-Expiry kein Lead-Warning (Übergabe an #228) → Task 2 (`now >= expires_at`-Skip).
- Nachhol-Lauf direkt nach Wake → Task 3 (`enter_true_suspend`-Resume-Hook).
- Nachhol-Lauf nach Reboot/Off → Task 4 (Startup-Hook).
- Kernbetriebszeit-Umplanung bewusst NICHT umgesetzt (Non-Goal, im Context dokumentiert).
- Fehlgeschlagener Send der dringlichsten Warnung superseded die übrigen NICHT (kein `_record_superseded` im Fail-Zweig) und retryt über die `_should_send_warning`-Retry-Logik (bis 3 Fehlversuche).

**Placeholder-Scan:** keine TODO/TBD; alle Code-Schritte enthalten vollständigen Code, alle Commands haben erwartete Ausgabe.

**Typ-Konsistenz:** `_should_send_warning(db, device, warning_type, warning_time, now)`, `_send_warning(db, device, warning_type)`, neues `_record_superseded(db, device, warning_type)`, `check_and_send_warnings(db)`, `_expiry_warning_catchup_on_startup()` — Signaturen über alle Tasks und Tests hinweg identisch. `ExpirationNotification`-Felder (`device_id, notification_type, sent_at, success, fcm_message_id, error_message, device_expires_at`) stimmen mit `backend/app/models/mobile.py` überein.

## Execution Handoff

Wird nach Bestätigung des Plans angeboten.
