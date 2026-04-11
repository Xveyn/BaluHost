"""Tests for notification event gate logic (error/success preferences).

These tests verify that emit_sync correctly suppresses or allows notifications
based on admin category preferences for success/error event types.

The gate logic is inside emit_sync and uses a local import:
    from app.services.notifications.service import get_notification_service

So we patch `app.services.notifications.service.get_notification_service`
to intercept it.
"""
import pytest
from unittest.mock import MagicMock, patch

import app.services.notifications.service as _notification_service_mod
from app.services.notifications.events import (
    EventEmitter,
    EventConfig,
    EVENT_CONFIGS,
    EventType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_svc_mock(success: bool = False, error: bool = True) -> MagicMock:
    """Build a NotificationService mock that returns given category prefs."""
    svc = MagicMock()
    svc.get_user_preferences.return_value = None  # prefs object (not used directly)
    svc._get_category_pref.return_value = {
        "error": error,
        "success": success,
        "mobile": True,
        "desktop": False,
    }
    return svc


def _make_emitter_with_db(db_mock: MagicMock) -> EventEmitter:
    """Return an EventEmitter whose DB session factory returns db_mock."""
    emitter = EventEmitter()
    emitter.set_db_session_factory(lambda: db_mock)
    return emitter


def _db_with_one_admin() -> MagicMock:
    """Mock DB that returns one admin user id."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [(1,)]
    return db


def _db_with_no_admins() -> MagicMock:
    """Mock DB that returns no admin users."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmitSyncGateLogic:
    """Tests for the error/success gate in emit_sync."""

    # ------------------------------------------------------------------
    # Success events
    # ------------------------------------------------------------------

    def test_success_event_suppressed_when_no_admin_wants_it(self):
        """Success events (priority=0, type=info) are suppressed when no admin has success=True."""
        db = _db_with_one_admin()
        emitter = _make_emitter_with_db(db)
        svc = _make_svc_mock(success=False, error=True)

        original = _notification_service_mod.get_notification_service
        _notification_service_mod.get_notification_service = lambda: svc
        try:
            # SCHEDULER_COMPLETED: priority=0, type=info → success event
            emitter.emit_sync(
                EventType.SCHEDULER_COMPLETED,
                user_id=None,
                scheduler_name="TestJob",
            )
        finally:
            _notification_service_mod.get_notification_service = original

        # Notification should NOT be created
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_success_event_created_when_at_least_one_admin_wants_it(self):
        """Success events go through when at least one admin has success=True."""
        db = _db_with_one_admin()
        notification_obj = MagicMock()
        notification_obj.id = 42
        emitter = _make_emitter_with_db(db)
        svc = _make_svc_mock(success=True, error=True)

        original = _notification_service_mod.get_notification_service
        _notification_service_mod.get_notification_service = lambda: svc
        try:
            with patch(
                "app.services.notifications.events.EventEmitter._send_push_sync"
            ), patch(
                "app.models.notification.Notification",
                return_value=notification_obj,
            ):
                emitter.emit_sync(
                    EventType.SCHEDULER_COMPLETED,
                    user_id=None,
                    scheduler_name="TestJob",
                )
        finally:
            _notification_service_mod.get_notification_service = original

        # Notification should be added to the session
        db.add.assert_called_once()
        db.commit.assert_called()

    def test_success_event_suppressed_when_no_admins_exist(self):
        """Success events are suppressed when no admin users are found in the DB."""
        db = _db_with_no_admins()
        emitter = _make_emitter_with_db(db)
        svc = _make_svc_mock(success=True, error=True)

        original = _notification_service_mod.get_notification_service
        _notification_service_mod.get_notification_service = lambda: svc
        try:
            emitter.emit_sync(
                EventType.BACKUP_COMPLETED,
                user_id=None,
                backup_type="manual",
                size="1 GB",
            )
        finally:
            _notification_service_mod.get_notification_service = original

        db.add.assert_not_called()
        db.commit.assert_not_called()

    # ------------------------------------------------------------------
    # Error events
    # ------------------------------------------------------------------

    def test_error_event_created_by_default(self):
        """Error events (warning/critical) go through when admin prefs have error=True (default)."""
        db = _db_with_one_admin()
        notification_obj = MagicMock()
        notification_obj.id = 7
        emitter = _make_emitter_with_db(db)
        svc = _make_svc_mock(success=False, error=True)

        original = _notification_service_mod.get_notification_service
        _notification_service_mod.get_notification_service = lambda: svc
        try:
            with patch(
                "app.services.notifications.events.EventEmitter._send_push_sync"
            ), patch(
                "app.models.notification.Notification",
                return_value=notification_obj,
            ):
                emitter.emit_sync(
                    EventType.BACKUP_FAILED,
                    user_id=None,
                    backup_type="auto",
                    error="Disk full",
                )
        finally:
            _notification_service_mod.get_notification_service = original

        db.add.assert_called_once()
        db.commit.assert_called()

    def test_error_event_suppressed_when_admin_disables_errors(self):
        """Error events are suppressed when admin explicitly sets error=False."""
        db = _db_with_one_admin()
        emitter = _make_emitter_with_db(db)
        svc = _make_svc_mock(success=False, error=False)

        original = _notification_service_mod.get_notification_service
        _notification_service_mod.get_notification_service = lambda: svc
        try:
            emitter.emit_sync(
                EventType.BACKUP_FAILED,
                user_id=None,
                backup_type="auto",
                error="Disk full",
            )
        finally:
            _notification_service_mod.get_notification_service = original

        db.add.assert_not_called()
        db.commit.assert_not_called()

    # ------------------------------------------------------------------
    # User-targeted notifications bypass gate
    # ------------------------------------------------------------------

    def test_user_targeted_event_bypasses_gate(self):
        """Notifications with an explicit user_id skip the admin gate entirely."""
        db = MagicMock()
        notification_obj = MagicMock()
        notification_obj.id = 99
        emitter = _make_emitter_with_db(db)
        svc = MagicMock()

        original = _notification_service_mod.get_notification_service
        _notification_service_mod.get_notification_service = lambda: svc
        try:
            with patch(
                "app.services.notifications.events.EventEmitter._send_push_sync"
            ), patch(
                "app.models.notification.Notification",
                return_value=notification_obj,
            ):
                emitter.emit_sync(
                    EventType.SYNC_COMPLETED,
                    user_id=5,
                    folder_name="Photos",
                    device_name="MyPhone",
                )
        finally:
            _notification_service_mod.get_notification_service = original

        # Gate query should NOT have been called (user_id is not None)
        svc.get_user_preferences.assert_not_called()
        db.add.assert_called_once()

    # ------------------------------------------------------------------
    # Multiple admins: any-match semantics
    # ------------------------------------------------------------------

    def test_success_event_allowed_when_second_admin_wants_it(self):
        """Gate passes if at least one admin (out of many) wants the success event."""
        db = MagicMock()
        # Two admin users
        db.query.return_value.filter.return_value.all.return_value = [(1,), (2,)]

        notification_obj = MagicMock()
        notification_obj.id = 10
        emitter = _make_emitter_with_db(db)

        # First admin: success=False; second admin: success=True
        call_count = {"n": 0}

        def fake_get_category_pref(prefs, category):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"error": True, "success": False, "mobile": True, "desktop": False}
            return {"error": True, "success": True, "mobile": True, "desktop": False}

        svc = MagicMock()
        svc.get_user_preferences.return_value = None
        svc._get_category_pref.side_effect = fake_get_category_pref

        original = _notification_service_mod.get_notification_service
        _notification_service_mod.get_notification_service = lambda: svc
        try:
            with patch(
                "app.services.notifications.events.EventEmitter._send_push_sync"
            ), patch(
                "app.models.notification.Notification",
                return_value=notification_obj,
            ):
                emitter.emit_sync(
                    EventType.SCHEDULER_COMPLETED,
                    user_id=None,
                    scheduler_name="TestJob",
                )
        finally:
            _notification_service_mod.get_notification_service = original

        db.add.assert_called_once()
        db.commit.assert_called()

    # ------------------------------------------------------------------
    # Event classification (static checks, no DB needed)
    # ------------------------------------------------------------------

    def test_event_classification_success(self):
        """SCHEDULER_COMPLETED, BACKUP_COMPLETED etc. are classified as success events
        (priority=0 AND type=info).
        """
        success_event_types = [
            EventType.SCHEDULER_COMPLETED,
            EventType.BACKUP_COMPLETED,
            EventType.RAID_SCRUB_COMPLETE,
            EventType.SERVICE_RESTORED,
            EventType.SYNC_COMPLETED,
        ]
        for et in success_event_types:
            cfg = EVENT_CONFIGS.get(et)
            assert cfg is not None, f"No config for {et}"
            is_success = cfg.priority == 0 and cfg.notification_type == "info"
            assert is_success, (
                f"{et} expected to be a success event "
                f"(priority={cfg.priority}, type={cfg.notification_type})"
            )

    def test_event_classification_error(self):
        """BACKUP_FAILED, SMART_WARNING, RAID_DEGRADED etc. are classified as error events."""
        error_event_types = [
            EventType.BACKUP_FAILED,
            EventType.SCHEDULER_FAILED,
            EventType.SMART_WARNING,
            EventType.SMART_FAILURE,
            EventType.RAID_DEGRADED,
            EventType.RAID_FAILED,
            EventType.DISK_SPACE_LOW,
            EventType.DISK_SPACE_CRITICAL,
            EventType.TEMPERATURE_HIGH,
            EventType.TEMPERATURE_CRITICAL,
        ]
        for et in error_event_types:
            cfg = EVENT_CONFIGS.get(et)
            assert cfg is not None, f"No config for {et}"
            is_error = cfg.notification_type in ("warning", "critical")
            assert is_error, (
                f"{et} expected to be an error event (type={cfg.notification_type})"
            )
