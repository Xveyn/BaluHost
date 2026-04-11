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
from app.services.notifications.scheduler import (
    NotificationScheduler,
    _notification_scheduler,
    start_notification_scheduler,
    stop_notification_scheduler,
)
from app.services.notifications.events import (
    EventType,
    EventConfig,
    EventEmitter,
    get_event_emitter,
    init_event_emitter,
    # Async convenience functions
    emit_raid_degraded,
    emit_raid_failed,
    emit_raid_rebuilt,
    emit_raid_scrub_complete,
    emit_smart_warning,
    emit_smart_failure,
    emit_backup_completed,
    emit_backup_failed,
    emit_scheduler_failed,
    emit_disk_space_low,
    emit_disk_space_critical,
    emit_temperature_high,
    emit_temperature_critical,
    emit_login_failed,
    emit_brute_force_detected,
    # Sync convenience functions
    emit_raid_degraded_sync,
    emit_raid_failed_sync,
    emit_raid_rebuilt_sync,
    emit_raid_scrub_complete_sync,
    emit_smart_warning_sync,
    emit_smart_failure_sync,
    emit_backup_completed_sync,
    emit_backup_failed_sync,
    emit_scheduler_failed_sync,
    emit_disk_space_low_sync,
    emit_temperature_high_sync,
    emit_temperature_critical_sync,
    emit_login_failed_sync,
    emit_brute_force_detected_sync,
    emit_scheduler_completed_sync,
    emit_raid_sync_started_sync,
    emit_raid_sync_complete_sync,
    emit_service_restored_sync,
)
from app.services.notifications.firebase import FirebaseService

__all__ = [
    # Service
    "NotificationService",
    "get_notification_service",
    # Scheduler
    "NotificationScheduler",
    "_notification_scheduler",
    "start_notification_scheduler",
    "stop_notification_scheduler",
    # Events
    "EventType",
    "EventConfig",
    "EventEmitter",
    "get_event_emitter",
    "init_event_emitter",
    # Async
    "emit_raid_degraded",
    "emit_raid_failed",
    "emit_raid_rebuilt",
    "emit_raid_scrub_complete",
    "emit_smart_warning",
    "emit_smart_failure",
    "emit_backup_completed",
    "emit_backup_failed",
    "emit_scheduler_failed",
    "emit_disk_space_low",
    "emit_disk_space_critical",
    "emit_temperature_high",
    "emit_temperature_critical",
    "emit_login_failed",
    "emit_brute_force_detected",
    # Sync
    "emit_raid_degraded_sync",
    "emit_raid_failed_sync",
    "emit_raid_rebuilt_sync",
    "emit_raid_scrub_complete_sync",
    "emit_smart_warning_sync",
    "emit_smart_failure_sync",
    "emit_backup_completed_sync",
    "emit_backup_failed_sync",
    "emit_scheduler_failed_sync",
    "emit_disk_space_low_sync",
    "emit_temperature_high_sync",
    "emit_temperature_critical_sync",
    "emit_login_failed_sync",
    "emit_brute_force_detected_sync",
    "emit_scheduler_completed_sync",
    "emit_raid_sync_started_sync",
    "emit_raid_sync_complete_sync",
    "emit_service_restored_sync",
    # Firebase
    "FirebaseService",
]
