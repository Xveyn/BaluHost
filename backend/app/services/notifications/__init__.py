"""
Notifications services package.

Provides notification management with:
- Notification creation and delivery
- Event emission and handling
- Firebase push notifications
- Notification scheduling
"""

from app.services.notifications.service import (
    NotificationService,
    get_notification_service,
)
from app.services.notifications.scheduler import NotificationScheduler
from app.services.notifications.events import (
    EventType,
    EventConfig,
    EventEmitter,
    get_event_emitter,
    init_event_emitter,
    emit_raid_degraded,
    emit_smart_warning,
    emit_smart_failure,
    emit_backup_completed,
    emit_backup_failed,
    emit_scheduler_failed,
    emit_disk_space_low,
    emit_temperature_high,
)
from app.services.notifications.firebase import FirebaseService

__all__ = [
    # Service
    "NotificationService",
    "get_notification_service",
    # Scheduler
    "NotificationScheduler",
    # Events
    "EventType",
    "EventConfig",
    "EventEmitter",
    "get_event_emitter",
    "init_event_emitter",
    "emit_raid_degraded",
    "emit_smart_warning",
    "emit_smart_failure",
    "emit_backup_completed",
    "emit_backup_failed",
    "emit_scheduler_failed",
    "emit_disk_space_low",
    "emit_temperature_high",
    # Firebase
    "FirebaseService",
]
