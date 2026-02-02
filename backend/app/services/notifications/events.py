"""Event emitter service for BaluHost notifications.

Provides a centralized event system that other services can use to emit
events that trigger notifications.
"""

import logging
from typing import Optional, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


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
        action_url="/backups",
    ),
    EventType.BACKUP_FAILED: EventConfig(
        priority=2,
        category="backup",
        notification_type="warning",
        title_template="Backup fehlgeschlagen",
        message_template="Das {backup_type} Backup ist fehlgeschlagen: {error}",
        action_url="/backups",
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
