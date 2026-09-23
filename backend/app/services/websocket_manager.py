"""WebSocket manager for real-time notification delivery.

Manages WebSocket connections and broadcasts notifications to connected clients.
"""

import asyncio
import logging
from typing import Optional, Any
from dataclasses import dataclass

from fastapi import WebSocket

from app.services.ws_bus import LocalWsBus, WsBus, WsEnvelope

logger = logging.getLogger(__name__)

# Max simultaneous WebSocket connections per user (DoS guard, Posten 5 #2).
# Covers a desktop client + phone + a couple of browser tabs.
MAX_CONNECTIONS_PER_USER = 5

# How long one socket may take a frame before it counts as dead. Delivery now
# runs through a single bus consumer task, so an unbounded send would let one
# client with a full TCP window freeze delivery for every user in this process.
SEND_TIMEOUT_SECONDS = 5.0


class ConnectionLimitExceeded(Exception):
    """Raised when a user exceeds MAX_CONNECTIONS_PER_USER active connections."""


@dataclass
class Connection:
    """Represents a WebSocket connection."""
    websocket: WebSocket
    user_id: int
    is_admin: bool = False


class WebSocketManager:
    """Manager for WebSocket connections and message broadcasting."""

    def __init__(self, bus: "WsBus | None" = None) -> None:
        """Initialize the WebSocket manager.

        Args:
            bus: Transport for broadcasts. Defaults to a LocalWsBus wired to
                this manager — the single-process behaviour, which is what dev
                mode and the tests want. Production replaces it via set_bus()
                with the Postgres bus, so a broadcast reaches the other five
                API processes too (#685).
        """
        # Map of user_id -> list of connections
        self._user_connections: dict[int, list[Connection]] = {}
        # Set of admin user_ids for admin broadcasts
        self._admin_users: set[int] = set()
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        self._bus: "WsBus" = bus or LocalWsBus(self.deliver_local)

    def set_bus(self, bus: "WsBus") -> None:
        """Replace the transport. Called once at startup, before any publish."""
        self._bus = bus

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        is_admin: bool = False,
    ) -> Connection:
        """Register a new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            user_id: ID of the connected user
            is_admin: Whether the user is an admin

        Returns:
            Connection object
        """
        connection = Connection(
            websocket=websocket,
            user_id=user_id,
            is_admin=is_admin,
        )

        async with self._lock:
            if len(self._user_connections.get(user_id, [])) >= MAX_CONNECTIONS_PER_USER:
                raise ConnectionLimitExceeded(
                    f"user {user_id} exceeded {MAX_CONNECTIONS_PER_USER} connections"
                )
            if user_id not in self._user_connections:
                self._user_connections[user_id] = []
            self._user_connections[user_id].append(connection)

            if is_admin:
                self._admin_users.add(user_id)

        logger.info(
            f"WebSocket connected: user_id={user_id}, "
            f"is_admin={is_admin}, "
            f"total_connections={self._count_connections()}"
        )
        return connection

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection.

        Args:
            websocket: The WebSocket connection to remove
        """
        async with self._lock:
            for user_id, connections in list(self._user_connections.items()):
                for conn in connections[:]:  # Iterate over copy
                    if conn.websocket is websocket:
                        connections.remove(conn)
                        logger.info(
                            f"WebSocket disconnected: user_id={user_id}, "
                            f"total_connections={self._count_connections()}"
                        )

                        # Clean up empty user entries
                        if not connections:
                            del self._user_connections[user_id]
                            self._admin_users.discard(user_id)
                        return

    def _count_connections(self) -> int:
        """Count total active connections."""
        return sum(len(conns) for conns in self._user_connections.values())

    async def broadcast_to_user(self, user_id: int, message: dict[str, Any]) -> None:
        """Publish a notification for one user's connections.

        Returns nothing on purpose: delivery happens in every process that
        holds a connection, so the publisher cannot count sockets. Use
        deliver_local()'s return value when you need the local number.
        """
        await self._bus.publish(
            WsEnvelope(kind="user", msg_type="notification", payload=message, user_id=user_id)
        )

    async def broadcast_to_admins(self, message: dict[str, Any]) -> None:
        """Publish a notification for every admin connection."""
        await self._bus.publish(
            WsEnvelope(kind="admins", msg_type="notification", payload=message)
        )

    async def broadcast_typed(
        self, msg_type: str, payload: Any, admins_only: bool = False
    ) -> None:
        """Publish a typed message to connected users.

        Sends {"type": msg_type, "payload": payload} — the caller names the
        type and it reaches the wire unchanged. This is the only all-users
        broadcast. There used to be a broadcast_to_all() next to it that
        force-set "type": "notification" and nested the caller's dict under
        it; a caller that had already typed its message got wrapped twice and
        no client could match on it (#511). Pass "notification" as msg_type if
        that is genuinely what you are sending.

        Args:
            msg_type: Message type string (e.g. "dashboard_panel_update").
            payload: Message payload — a dict for most message types, a list
                for the batch-shaped ones like "smart_device_update".
            admins_only: Skip non-admin connections. Needed for payloads that a
                REST route would gate behind is_privileged() - without it the
                gate would be decorative. "Admin" here means conn.is_admin,
                set at connect time from `role == "admin"` in
                api/routes/notifications.py - NOT is_privileged(). A
                PRIVILEGED_ROLES config extended beyond "admin" (e.g. adding
                "operator") widens REST visibility for admin_only panels
                without widening this broadcast, so the two enforcement
                points drift apart. That's fail-closed (no leak), just a trap
                for the next reader.
        """
        await self._bus.publish(
            WsEnvelope(
                kind="all", msg_type=msg_type, payload=payload, admins_only=admins_only
            )
        )

    async def send_unread_count(self, user_id: int, count: int) -> None:
        """Publish an updated unread count for one user's connections."""
        await self._bus.publish(
            WsEnvelope(
                kind="user",
                msg_type="unread_count",
                payload={"count": count},
                user_id=user_id,
            )
        )

    async def send_notification_state(
        self, user_id: int, ids: list[int], action: str
    ) -> None:
        """Tell a user's connections that notification state changed elsewhere.

        Counterpart to send_unread_count: that one carries the number, this
        one carries which notifications changed and how, so an open client can
        update its list.

        Args:
            user_id: Target user ID
            ids: Affected notification IDs; empty for the bulk actions, where
                "all" is exactly what the empty list means
            action: read | dismissed | snoozed | deleted | restored |
                read_all | dismissed_all | deleted_all
        """
        await self._bus.publish(
            WsEnvelope(
                kind="user",
                msg_type="notification_state",
                payload={"ids": ids, "action": action},
                user_id=user_id,
            )
        )

    async def deliver_local(self, env: WsEnvelope) -> int:
        """Write an envelope to this process's matching sockets.

        The only method that touches _user_connections for sending. Called
        from the bus consumer, never from publish() — see ws_bus for why there
        is exactly one delivery path.

        Returns:
            Number of connections in *this* process that got the frame.
        """
        frame = {"type": env.msg_type, "payload": env.payload}
        sent_count = 0

        async with self._lock:
            if env.kind == "user":
                if env.user_id is None:
                    logger.warning("deliver_local: kind=user without user_id, dropped")
                    return 0
                targets = [(env.user_id, self._user_connections.get(env.user_id, []))]
            elif env.kind == "admins":
                targets = [
                    (uid, self._user_connections.get(uid, []))
                    for uid in list(self._admin_users)
                ]
            elif env.kind == "all":
                targets = list(self._user_connections.items())
            else:
                # Never the permissive branch by accident: "all" is named
                # explicitly, and anything unrecognised is dropped rather than
                # broadcast to every socket.
                logger.warning("deliver_local: unknown kind %r, dropped", env.kind)
                return 0

            for user_id, connections in targets:
                disconnected = []
                for conn in connections:
                    if env.kind == "admins" and not conn.is_admin:
                        continue
                    if env.kind == "all" and env.admins_only and not conn.is_admin:
                        continue
                    try:
                        # Bounded on purpose. A client that stops reading (full
                        # TCP window) used to stall only its own caller; now it
                        # would stall the single bus consumer while holding
                        # self._lock, freezing delivery for every user in this
                        # process and silently overflowing the queue.
                        await asyncio.wait_for(
                            conn.websocket.send_json(frame), timeout=SEND_TIMEOUT_SECONDS
                        )
                        sent_count += 1
                    except (Exception, asyncio.TimeoutError) as e:
                        logger.warning(f"Failed to send to user {user_id}: {e}")
                        disconnected.append(conn)

                for conn in disconnected:
                    if conn in connections:
                        connections.remove(conn)

                if not connections and user_id in self._user_connections:
                    del self._user_connections[user_id]
                    self._admin_users.discard(user_id)

        return sent_count

    def get_connected_user_ids(self) -> list[int]:
        """Get list of all connected user IDs.

        Local only: knows the connections of *this* process. Six API processes
        hold connections, so a False here does not mean "nobody is listening".

        Returns:
            List of user IDs with active connections
        """
        return list(self._user_connections.keys())

    def get_connection_count(self, user_id: Optional[int] = None) -> int:
        """Get connection count.

        Local only: knows the connections of *this* process. Six API processes
        hold connections, so a False here does not mean "nobody is listening".

        Args:
            user_id: Optional user ID to filter by

        Returns:
            Number of connections
        """
        if user_id is not None:
            return len(self._user_connections.get(user_id, []))
        return self._count_connections()

    def is_user_connected(self, user_id: int) -> bool:
        """Check if a user has any active connections.

        Local only: knows the connections of *this* process. Six API processes
        hold connections, so a False here does not mean "nobody is listening".

        Args:
            user_id: User ID to check

        Returns:
            True if user has at least one connection
        """
        return user_id in self._user_connections and len(self._user_connections[user_id]) > 0


# Singleton instance
_websocket_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get the WebSocket manager singleton.

    Returns:
        WebSocketManager instance
    """
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
    return _websocket_manager


def init_websocket_manager() -> WebSocketManager:
    """Initialize the WebSocket manager.

    Should be called during application startup.

    Returns:
        WebSocketManager instance
    """
    manager = get_websocket_manager()

    # Connect to notification service
    from app.services.notifications import get_notification_service
    notification_service = get_notification_service()
    notification_service.set_websocket_manager(manager)

    logger.info("WebSocket manager initialized")
    return manager
