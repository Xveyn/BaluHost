"""Event emitter service for BaluHost notifications.

Provides a centralized event system that other services can use to emit
events that trigger notifications.
"""

import logging
import time as _time
from typing import Optional, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Cooldown cache: maps "event_type:entity_id" -> last_emit_timestamp
_cooldown_cache: dict[str, float] = {}

# Cooldown durations in seconds per event type
_COOLDOWN_SECONDS: dict[str, int] = {
    "raid.degraded": 3600,       # 1h
    "raid.failed": 3600,         # 1h
    "smart.warning": 86400,      # 24h
    "smart.failure": 86400,      # 24h
    "smart.reallocated": 86400,  # 24h
    "system.disk_space_low": 3600,      # 1h
    "system.disk_space_critical": 3600, # 1h
    "system.temperature_high": 1800,    # 30min
    "system.temperature_critical": 1800, # 30min
    "system.storage_permission": 300,  # 5min per path
}


def _check_cooldown(event_type: str, entity_id: str = "") -> bool:
    """Check if an event is still in cooldown.

    Returns True if the event should be suppressed (still cooling down).
    """
    cooldown = _COOLDOWN_SECONDS.get(event_type)
    if cooldown is None:
        return False  # No cooldown configured, always emit

    key = f"{event_type}:{entity_id}"
    last_emit = _cooldown_cache.get(key)
    if last_emit is None:
        return False  # Never emitted before

    return (_time.monotonic() - last_emit) < cooldown


def _set_cooldown(event_type: str, entity_id: str = "") -> None:
    """Record that an event was emitted (for cooldown tracking)."""
    if event_type in _COOLDOWN_SECONDS:
        key = f"{event_type}:{entity_id}"
        _cooldown_cache[key] = _time.monotonic()


class EventType(str, Enum):
    """Notification event types."""

    # RAID events
    RAID_DEGRADED = "raid.degraded"
    RAID_REBUILT = "raid.rebuilt"
    RAID_FAILED = "raid.failed"
    RAID_SYNC_STARTED = "raid.sync_started"
    RAID_SYNC_COMPLETE = "raid.sync_complete"
    RAID_SCRUB_STARTED = "raid.scrub_started"
    RAID_SCRUB_COMPLETE = "raid.scrub_complete"

    # SMART events
    SMART_WARNING = "smart.warning"
    SMART_FAILURE = "smart.failure"
    SMART_REALLOCATED = "smart.reallocated"

    # Backup events
    BACKUP_STARTED = "backup.started"
    BACKUP_COMPLETED = "backup.completed"
    BACKUP_FAILED = "backup.failed"

    # Scheduler events
    SCHEDULER_FAILED = "scheduler.failed"
    SCHEDULER_COMPLETED = "scheduler.completed"

    # System events
    DISK_SPACE_LOW = "system.disk_space_low"
    DISK_SPACE_CRITICAL = "system.disk_space_critical"
    SERVICE_DOWN = "system.service_down"
    SERVICE_RESTORED = "system.service_restored"
    CPU_HIGH = "system.cpu_high"
    MEMORY_HIGH = "system.memory_high"
    TEMPERATURE_HIGH = "system.temperature_high"
    TEMPERATURE_CRITICAL = "system.temperature_critical"
    STORAGE_PERMISSION_ERROR = "system.storage_permission"

    # Security events
    LOGIN_FAILED = "security.login_failed"
    BRUTE_FORCE_DETECTED = "security.brute_force"
    UNAUTHORIZED_ACCESS = "security.unauthorized"
    DEVICE_EXPIRED = "security.device_expired"

    # Sync events
    SYNC_CONFLICT = "sync.conflict"
    SYNC_FAILED = "sync.failed"
    SYNC_COMPLETED = "sync.completed"

    # VPN events
    VPN_CLIENT_EXPIRED = "vpn.client_expired"
    VPN_CONNECTION_FAILED = "vpn.connection_failed"


@dataclass
class EventConfig:
    """Configuration for an event type."""
    priority: int  # 0=low, 1=medium, 2=high, 3=critical
    category: str
    notification_type: str  # info, warning, critical
    title_template: str
    message_template: str
    action_url: Optional[str] = None


# Event configurations
EVENT_CONFIGS: dict[str, EventConfig] = {
    # RAID events
    EventType.RAID_DEGRADED: EventConfig(
        priority=3,
        category="raid",
        notification_type="critical",
        title_template="RAID Array {array_name} degradiert",
        message_template="Das RAID Array {array_name} ist im degradierten Zustand. {details}",
        action_url="/raid",
    ),
    EventType.RAID_REBUILT: EventConfig(
        priority=1,
        category="raid",
        notification_type="info",
        title_template="RAID Array {array_name} wiederhergestellt",
        message_template="Das RAID Array {array_name} wurde erfolgreich wiederhergestellt.",
        action_url="/raid",
    ),
    EventType.RAID_FAILED: EventConfig(
        priority=3,
        category="raid",
        notification_type="critical",
        title_template="RAID Array {array_name} ausgefallen!",
        message_template="KRITISCH: Das RAID Array {array_name} ist ausgefallen. Sofortige Aktion erforderlich! {details}",
        action_url="/raid",
    ),
    EventType.RAID_SCRUB_COMPLETE: EventConfig(
        priority=0,
        category="raid",
        notification_type="info",
        title_template="RAID Scrub abgeschlossen",
        message_template="Der RAID Scrub für {array_name} wurde abgeschlossen. {details}",
        action_url="/schedulers",
    ),
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

    # SMART events
    EventType.SMART_WARNING: EventConfig(
        priority=2,
        category="smart",
        notification_type="warning",
        title_template="Festplattenwarnung: {disk_name}",
        message_template="Die Festplatte {disk_name} zeigt Warnzeichen: {details}",
        action_url="/system",
    ),
    EventType.SMART_FAILURE: EventConfig(
        priority=3,
        category="smart",
        notification_type="critical",
        title_template="Festplattenfehler: {disk_name}",
        message_template="KRITISCH: Die Festplatte {disk_name} meldet einen Fehler. Daten sichern! {details}",
        action_url="/system",
    ),
    EventType.SMART_REALLOCATED: EventConfig(
        priority=2,
        category="smart",
        notification_type="warning",
        title_template="Reallocated Sectors: {disk_name}",
        message_template="Die Festplatte {disk_name} hat {count} reallocated Sektoren. Überwachung empfohlen.",
        action_url="/system",
    ),

    # Backup events
    EventType.BACKUP_COMPLETED: EventConfig(
        priority=0,
        category="backup",
        notification_type="info",
        title_template="Backup erfolgreich",
        message_template="Das {backup_type} Backup wurde erfolgreich erstellt. Größe: {size}",
        action_url="/admin/system-control?tab=backup",
    ),
    EventType.BACKUP_FAILED: EventConfig(
        priority=2,
        category="backup",
        notification_type="warning",
        title_template="Backup fehlgeschlagen",
        message_template="Das {backup_type} Backup ist fehlgeschlagen: {error}",
        action_url="/admin/system-control?tab=backup",
    ),

    # Scheduler events
    EventType.SCHEDULER_FAILED: EventConfig(
        priority=2,
        category="scheduler",
        notification_type="warning",
        title_template="Geplante Aufgabe fehlgeschlagen: {scheduler_name}",
        message_template="Die geplante Aufgabe '{scheduler_name}' ist fehlgeschlagen: {error}",
        action_url="/schedulers",
    ),
    EventType.SCHEDULER_COMPLETED: EventConfig(
        priority=0,
        category="scheduler",
        notification_type="info",
        title_template="Geplante Aufgabe abgeschlossen: {scheduler_name}",
        message_template="Die geplante Aufgabe '{scheduler_name}' wurde erfolgreich abgeschlossen.",
        action_url="/schedulers",
    ),

    # System events
    EventType.DISK_SPACE_LOW: EventConfig(
        priority=1,
        category="system",
        notification_type="warning",
        title_template="Speicherplatz niedrig",
        message_template="Der verfügbare Speicherplatz ist auf {percent}% gesunken ({free_space} frei).",
        action_url="/files",
    ),
    EventType.DISK_SPACE_CRITICAL: EventConfig(
        priority=3,
        category="system",
        notification_type="critical",
        title_template="Speicherplatz kritisch!",
        message_template="KRITISCH: Nur noch {percent}% Speicherplatz verfügbar ({free_space} frei).",
        action_url="/files",
    ),
    EventType.SERVICE_DOWN: EventConfig(
        priority=2,
        category="system",
        notification_type="warning",
        title_template="Dienst ausgefallen: {service_name}",
        message_template="Der Dienst '{service_name}' ist nicht mehr erreichbar.",
        action_url="/admin/health",
    ),
    EventType.SERVICE_RESTORED: EventConfig(
        priority=0,
        category="system",
        notification_type="info",
        title_template="Dienst wiederhergestellt: {service_name}",
        message_template="Der Dienst '{service_name}' ist wieder verfügbar.",
        action_url="/admin/health",
    ),
    EventType.TEMPERATURE_HIGH: EventConfig(
        priority=2,
        category="system",
        notification_type="warning",
        title_template="Temperatur erhöht: {component}",
        message_template="Die Temperatur von {component} hat {temperature}°C erreicht.",
        action_url="/fans",
    ),
    EventType.TEMPERATURE_CRITICAL: EventConfig(
        priority=3,
        category="system",
        notification_type="critical",
        title_template="Temperatur kritisch: {component}",
        message_template="KRITISCH: Die Temperatur von {component} hat {temperature}°C erreicht!",
        action_url="/fans",
    ),
    EventType.STORAGE_PERMISSION_ERROR: EventConfig(
        priority=2,
        category="system",
        notification_type="warning",
        title_template="Speicherzugriff verweigert: {operation}",
        message_template=(
            "Dateioperation '{operation}' fehlgeschlagen auf Pfad '{path}': "
            "Keine Berechtigung. Benutzer: {username}. "
            "Mögliche Ursache: Datei/Ordner gehört einem anderen Systemprozess."
        ),
        action_url="/files",
    ),

    # Security events
    EventType.LOGIN_FAILED: EventConfig(
        priority=1,
        category="security",
        notification_type="warning",
        title_template="Fehlgeschlagener Login",
        message_template="Fehlgeschlagener Login-Versuch für Benutzer '{username}' von IP {ip_address}.",
        action_url="/logging",
    ),
    EventType.BRUTE_FORCE_DETECTED: EventConfig(
        priority=3,
        category="security",
        notification_type="critical",
        title_template="Brute-Force Angriff erkannt",
        message_template="Mehrere fehlgeschlagene Login-Versuche von IP {ip_address}. Automatische Sperre aktiv.",
        action_url="/logging",
    ),
    EventType.DEVICE_EXPIRED: EventConfig(
        priority=1,
        category="security",
        notification_type="warning",
        title_template="Gerät abgelaufen: {device_name}",
        message_template="Die Autorisierung für das Gerät '{device_name}' ist abgelaufen.",
        action_url="/mobile-devices",
    ),

    # Sync events
    EventType.SYNC_CONFLICT: EventConfig(
        priority=1,
        category="sync",
        notification_type="warning",
        title_template="Sync-Konflikt erkannt",
        message_template="Ein Datei-Konflikt wurde bei '{file_path}' erkannt. Manuelle Lösung erforderlich.",
        action_url="/sync",
    ),
    EventType.SYNC_COMPLETED: EventConfig(
        priority=0,
        category="sync",
        notification_type="info",
        title_template="Synchronisation abgeschlossen: {folder_name}",
        message_template="Die Synchronisation für '{folder_name}' ({device_name}) wurde erfolgreich abgeschlossen.",
        action_url="/settings?tab=sync",
    ),
    EventType.SYNC_FAILED: EventConfig(
        priority=2,
        category="sync",
        notification_type="warning",
        title_template="Synchronisation fehlgeschlagen",
        message_template="Die Synchronisation für '{folder_name}' ist fehlgeschlagen: {error}",
        action_url="/sync",
    ),

    # VPN events
    EventType.VPN_CLIENT_EXPIRED: EventConfig(
        priority=1,
        category="vpn",
        notification_type="warning",
        title_template="VPN-Client abgelaufen: {client_name}",
        message_template="Die Konfiguration für VPN-Client '{client_name}' ist abgelaufen.",
        action_url="/vpn",
    ),
}


class EventEmitter:
    """Central event emitter for notification events."""

    def __init__(self):
        """Initialize the event emitter."""
        self._handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}
        self._db_session_factory = None

    def set_db_session_factory(self, factory: Callable) -> None:
        """Set the database session factory.

        Args:
            factory: Callable that returns a database session
        """
        self._db_session_factory = factory

    def on(
        self,
        event_type: str,
        handler: Callable[..., Awaitable[None]],
    ) -> None:
        """Register an event handler.

        Args:
            event_type: Event type to handle
            handler: Async function to call when event occurs
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Registered handler for event: {event_type}")

    def off(
        self,
        event_type: str,
        handler: Callable[..., Awaitable[None]],
    ) -> None:
        """Remove an event handler.

        Args:
            event_type: Event type
            handler: Handler to remove
        """
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)

    async def emit(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Emit an event.

        This creates a notification based on the event configuration and
        dispatches it to the appropriate channels.

        Args:
            event_type: Type of event
            user_id: Target user ID (None for admins/system)
            **kwargs: Event-specific data for template substitution
        """
        logger.info(f"Event emitted: {event_type}, user_id={user_id}, data={kwargs}")

        # Get event configuration
        config = EVENT_CONFIGS.get(event_type)
        if not config:
            logger.warning(f"Unknown event type: {event_type}")
            return

        # Format title and message with provided data
        try:
            title = config.title_template.format(**kwargs)
            message = config.message_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing event data for {event_type}: {e}")
            title = config.title_template
            message = config.message_template

        # Create notification
        from app.services.notifications.service import get_notification_service

        if self._db_session_factory:
            db = self._db_session_factory()
            try:
                service = get_notification_service()
                await service.create(
                    db=db,
                    user_id=user_id,
                    category=config.category,
                    notification_type=config.notification_type,
                    title=title,
                    message=message,
                    action_url=config.action_url,
                    metadata={"event_type": event_type, **kwargs},
                    priority=config.priority,
                )
            finally:
                db.close()

        # Call registered handlers
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    await handler(event_type=event_type, user_id=user_id, **kwargs)
                except Exception as e:
                    logger.error(f"Event handler error for {event_type}: {e}")

    def emit_sync(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        cooldown_entity: str = "",
        **kwargs: Any,
    ) -> None:
        """Synchronous event emit - creates notification directly via DB.

        For use in synchronous services (RAID, SMART, Backup, etc.)
        that cannot easily await async code.

        Args:
            event_type: Type of event
            user_id: Target user ID (None for admins/system)
            cooldown_entity: Entity identifier for cooldown (e.g. 'md0', 'sda')
            **kwargs: Event-specific data for template substitution
        """
        # Check cooldown
        if _check_cooldown(event_type, cooldown_entity):
            logger.debug(f"Event {event_type}:{cooldown_entity} suppressed by cooldown")
            return

        logger.info(f"Event emitted (sync): {event_type}, user_id={user_id}, data={kwargs}")

        config = EVENT_CONFIGS.get(event_type)
        if not config:
            logger.warning(f"Unknown event type: {event_type}")
            return

        try:
            title = config.title_template.format(**kwargs)
            message = config.message_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing event data for {event_type}: {e}")
            title = config.title_template
            message = config.message_template

        # Determine event classification for gate logic
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
                _set_cooldown(event_type, cooldown_entity)
                logger.info(f"Created notification (sync): id={notification.id}, type={event_type}")

                # Send push notifications to mobile devices
                self._send_push_sync(
                    db,
                    notification_id=notification.id,
                    user_id=user_id,
                    title=title,
                    message=message,
                    category=config.category,
                    notification_type=config.notification_type,
                    priority=config.priority,
                    action_url=config.action_url,
                )

                # Create per-user notification copies for routed non-admin users
                # so they appear in the user's notification list
                if user_id is None:
                    from app.services.notification_routing import get_routed_user_ids
                    from app.services.notifications.service import get_notification_service
                    svc = get_notification_service()
                    routed_ids = get_routed_user_ids(db, config.category)
                    for uid in routed_ids:
                        prefs = svc.get_user_preferences(db, uid)
                        if prefs:
                            if svc._is_quiet_hours(prefs) and config.priority < 3:
                                continue
                        user_copy = Notification(
                            user_id=uid,
                            category=config.category,
                            notification_type=config.notification_type,
                            title=title,
                            message=message,
                            action_url=config.action_url,
                            extra_data={"event_type": event_type, **kwargs},
                            priority=config.priority,
                        )
                        db.add(user_copy)
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create notification for {event_type}: {e}")
            finally:
                db.close()

    def emit_for_admins_sync(
        self,
        event_type: str,
        cooldown_entity: str = "",
        **kwargs: Any,
    ) -> None:
        """Synchronous emit for admin-targeted notifications.

        Args:
            event_type: Type of event
            cooldown_entity: Entity identifier for cooldown
            **kwargs: Event-specific data
        """
        self.emit_sync(event_type, user_id=None, cooldown_entity=cooldown_entity, **kwargs)

    def _send_push_sync(
        self,
        db,
        notification_id: int,
        user_id: Optional[int],
        title: str,
        message: str,
        category: str,
        notification_type: str,
        priority: int,
        action_url: Optional[str],
    ) -> None:
        """Send push notifications synchronously to mobile devices.

        For admin/system notifications (user_id=None), sends to all admin
        users' devices. For user-specific notifications, sends to that
        user's devices.

        Args:
            db: Database session
            notification_id: ID of the created notification
            user_id: Target user ID (None for admin broadcast)
            title: Notification title
            message: Notification body
            category: Notification category
            notification_type: info/warning/critical
            priority: Priority level 0-3
            action_url: Optional action URL
        """
        from app.services.notifications.firebase import FirebaseService

        if not FirebaseService.is_available():
            return

        from app.models.mobile import MobileDevice
        from app.models.user import User

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
                admin_ids = []
                devices = db.query(MobileDevice).filter(
                    MobileDevice.user_id == user_id,
                    MobileDevice.is_active == True,
                    MobileDevice.push_token.isnot(None),
                ).all()

            for device in devices:
                # Check mobile preference for admin users
                if user_id is None and device.user_id in admin_ids:
                    from app.services.notifications.service import get_notification_service
                    svc = get_notification_service()
                    device_prefs = svc.get_user_preferences(db, device.user_id)
                    cat_pref = svc._get_category_pref(device_prefs, category)
                    if not cat_pref.get("mobile", True):
                        continue

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
                    device_token=device.push_token,
                    title=title,
                    body=message,
                    category=category,
                    priority=priority,
                    notification_id=notification_id,
                    action_url=action_url,
                    notification_type=notification_type,
                )
                if result["success"]:
                    logger.debug(f"Push sent to device {device.id}")
                elif result["error"] == "unregistered":
                    logger.warning(f"Device {device.id} token unregistered, clearing")
                    device.push_token = None
                    db.commit()
                else:
                    logger.error(f"Push to device {device.id} failed: {result['error']}")
        except Exception as e:
            logger.error(f"Failed to send push notifications: {e}")

    async def emit_for_admins(
        self,
        event_type: str,
        **kwargs: Any,
    ) -> None:
        """Emit an event for all admin users.

        Args:
            event_type: Type of event
            **kwargs: Event-specific data
        """
        await self.emit(event_type, user_id=None, **kwargs)

    async def emit_for_all_users(
        self,
        event_type: str,
        db,
        **kwargs: Any,
    ) -> None:
        """Emit an event for all active users.

        Args:
            event_type: Type of event
            db: Database session
            **kwargs: Event-specific data
        """
        from app.models.user import User

        users = db.query(User).filter(User.is_active == True).all()
        for user in users:
            await self.emit(event_type, user_id=user.id, **kwargs)


# Singleton instance
_event_emitter: Optional[EventEmitter] = None


def get_event_emitter() -> EventEmitter:
    """Get the event emitter singleton.

    Returns:
        EventEmitter instance
    """
    global _event_emitter
    if _event_emitter is None:
        _event_emitter = EventEmitter()
    return _event_emitter


def init_event_emitter(db_session_factory: Callable) -> EventEmitter:
    """Initialize the event emitter.

    Should be called during application startup.

    Args:
        db_session_factory: Callable that returns a database session

    Returns:
        EventEmitter instance
    """
    emitter = get_event_emitter()
    emitter.set_db_session_factory(db_session_factory)
    logger.info("Event emitter initialized")
    return emitter


# Convenience functions for common events
async def emit_raid_degraded(array_name: str, details: str = "") -> None:
    """Emit RAID degraded event."""
    await get_event_emitter().emit_for_admins(
        EventType.RAID_DEGRADED,
        array_name=array_name,
        details=details,
    )


async def emit_smart_warning(disk_name: str, details: str = "") -> None:
    """Emit SMART warning event."""
    await get_event_emitter().emit_for_admins(
        EventType.SMART_WARNING,
        disk_name=disk_name,
        details=details,
    )


async def emit_smart_failure(disk_name: str, details: str = "") -> None:
    """Emit SMART failure event."""
    await get_event_emitter().emit_for_admins(
        EventType.SMART_FAILURE,
        disk_name=disk_name,
        details=details,
    )


async def emit_backup_completed(backup_type: str, size: str) -> None:
    """Emit backup completed event."""
    await get_event_emitter().emit_for_admins(
        EventType.BACKUP_COMPLETED,
        backup_type=backup_type,
        size=size,
    )


async def emit_backup_failed(backup_type: str, error: str) -> None:
    """Emit backup failed event."""
    await get_event_emitter().emit_for_admins(
        EventType.BACKUP_FAILED,
        backup_type=backup_type,
        error=error,
    )


async def emit_scheduler_failed(scheduler_name: str, error: str) -> None:
    """Emit scheduler failed event."""
    await get_event_emitter().emit_for_admins(
        EventType.SCHEDULER_FAILED,
        scheduler_name=scheduler_name,
        error=error,
    )


async def emit_disk_space_low(percent: int, free_space: str) -> None:
    """Emit disk space low event."""
    await get_event_emitter().emit_for_admins(
        EventType.DISK_SPACE_LOW,
        percent=percent,
        free_space=free_space,
    )


async def emit_temperature_high(component: str, temperature: float) -> None:
    """Emit temperature high event."""
    await get_event_emitter().emit_for_admins(
        EventType.TEMPERATURE_HIGH,
        component=component,
        temperature=temperature,
    )


async def emit_temperature_critical(component: str, temperature: float) -> None:
    """Emit temperature critical event."""
    await get_event_emitter().emit_for_admins(
        EventType.TEMPERATURE_CRITICAL,
        component=component,
        temperature=temperature,
    )


async def emit_raid_failed(array_name: str, details: str = "") -> None:
    """Emit RAID failed event."""
    await get_event_emitter().emit_for_admins(
        EventType.RAID_FAILED,
        array_name=array_name,
        details=details,
    )


async def emit_raid_rebuilt(array_name: str) -> None:
    """Emit RAID rebuilt event."""
    await get_event_emitter().emit_for_admins(
        EventType.RAID_REBUILT,
        array_name=array_name,
    )


async def emit_raid_scrub_complete(array_name: str, details: str = "") -> None:
    """Emit RAID scrub complete event."""
    await get_event_emitter().emit_for_admins(
        EventType.RAID_SCRUB_COMPLETE,
        array_name=array_name,
        details=details,
    )


async def emit_disk_space_critical(percent: int, free_space: str) -> None:
    """Emit disk space critical event."""
    await get_event_emitter().emit_for_admins(
        EventType.DISK_SPACE_CRITICAL,
        percent=percent,
        free_space=free_space,
    )


async def emit_login_failed(username: str, ip_address: str) -> None:
    """Emit login failed event."""
    await get_event_emitter().emit_for_admins(
        EventType.LOGIN_FAILED,
        username=username,
        ip_address=ip_address,
    )


async def emit_brute_force_detected(ip_address: str) -> None:
    """Emit brute force detected event."""
    await get_event_emitter().emit_for_admins(
        EventType.BRUTE_FORCE_DETECTED,
        ip_address=ip_address,
    )


# Synchronous convenience functions for use in sync services
def emit_raid_degraded_sync(array_name: str, details: str = "") -> None:
    """Emit RAID degraded event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.RAID_DEGRADED,
        cooldown_entity=array_name,
        array_name=array_name,
        details=details,
    )


def emit_raid_failed_sync(array_name: str, details: str = "") -> None:
    """Emit RAID failed event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.RAID_FAILED,
        cooldown_entity=array_name,
        array_name=array_name,
        details=details,
    )


def emit_raid_rebuilt_sync(array_name: str) -> None:
    """Emit RAID rebuilt event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.RAID_REBUILT,
        array_name=array_name,
    )


def emit_raid_scrub_complete_sync(array_name: str, details: str = "") -> None:
    """Emit RAID scrub complete event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.RAID_SCRUB_COMPLETE,
        array_name=array_name,
        details=details,
    )


def emit_smart_warning_sync(disk_name: str, details: str = "") -> None:
    """Emit SMART warning event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.SMART_WARNING,
        cooldown_entity=disk_name,
        disk_name=disk_name,
        details=details,
    )


def emit_smart_failure_sync(disk_name: str, details: str = "") -> None:
    """Emit SMART failure event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.SMART_FAILURE,
        cooldown_entity=disk_name,
        disk_name=disk_name,
        details=details,
    )


def emit_backup_completed_sync(backup_type: str, size: str) -> None:
    """Emit backup completed event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.BACKUP_COMPLETED,
        backup_type=backup_type,
        size=size,
    )


def emit_backup_failed_sync(backup_type: str, error: str) -> None:
    """Emit backup failed event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.BACKUP_FAILED,
        backup_type=backup_type,
        error=error,
    )


def emit_scheduler_failed_sync(scheduler_name: str, error: str) -> None:
    """Emit scheduler failed event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.SCHEDULER_FAILED,
        scheduler_name=scheduler_name,
        error=error,
    )


def emit_disk_space_low_sync(percent: int, free_space: str) -> None:
    """Emit disk space low event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.DISK_SPACE_LOW,
        cooldown_entity="storage",
        percent=percent,
        free_space=free_space,
    )


def emit_disk_space_critical_sync(percent: int, free_space: str) -> None:
    """Emit disk space critical event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.DISK_SPACE_CRITICAL,
        cooldown_entity="storage",
        percent=percent,
        free_space=free_space,
    )


def emit_temperature_high_sync(component: str, temperature: float) -> None:
    """Emit temperature high event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.TEMPERATURE_HIGH,
        cooldown_entity=component,
        component=component,
        temperature=temperature,
    )


def emit_temperature_critical_sync(component: str, temperature: float) -> None:
    """Emit temperature critical event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.TEMPERATURE_CRITICAL,
        cooldown_entity=component,
        component=component,
        temperature=temperature,
    )


def emit_login_failed_sync(username: str, ip_address: str) -> None:
    """Emit login failed event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.LOGIN_FAILED,
        username=username,
        ip_address=ip_address,
    )


def emit_brute_force_detected_sync(ip_address: str) -> None:
    """Emit brute force detected event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.BRUTE_FORCE_DETECTED,
        ip_address=ip_address,
    )


def emit_storage_permission_error_sync(operation: str, path: str, username: str) -> None:
    """Emit storage permission error event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.STORAGE_PERMISSION_ERROR,
        cooldown_entity=path,
        operation=operation,
        path=path,
        username=username,
    )


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
