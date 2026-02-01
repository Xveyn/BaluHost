"""WebSocket manager for real-time notification delivery.

Manages WebSocket connections and broadcasts notifications to connected clients.
"""

import asyncio
import logging
from typing import Optional, Any
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    """Represents a WebSocket connection."""
    websocket: WebSocket
    user_id: int
    is_admin: bool = False


class WebSocketManager:
    """Manager for WebSocket connections and message broadcasting."""

    def __init__(self):
        """Initialize the WebSocket manager."""
        # Map of user_id -> list of connections
        self._user_connections: dict[int, list[Connection]] = {}
        # Set of admin user_ids for admin broadcasts
        self._admin_users: set[int] = set()
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

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

    async def broadcast_to_user(
        self,
        user_id: int,
        message: dict[str, Any],
    ) -> int:
        """Send a message to all connections for a specific user.

        Args:
            user_id: Target user ID
            message: Message to send

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0
        async with self._lock:
            connections = self._user_connections.get(user_id, [])
            disconnected = []

            for conn in connections:
                try:
                    await conn.websocket.send_json({
                        "type": "notification",
                        "payload": message,
                    })
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to user {user_id}: {e}")
                    disconnected.append(conn)

            # Clean up disconnected connections
            for conn in disconnected:
                if conn in connections:
                    connections.remove(conn)

            if not connections and user_id in self._user_connections:
                del self._user_connections[user_id]
                self._admin_users.discard(user_id)

        return sent_count

    async def broadcast_to_admins(self, message: dict[str, Any]) -> int:
        """Broadcast a message to all admin users.

        Args:
            message: Message to send

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0
        async with self._lock:
            for user_id in list(self._admin_users):
                connections = self._user_connections.get(user_id, [])
                disconnected = []

                for conn in connections:
                    if conn.is_admin:
                        try:
                            await conn.websocket.send_json({
                                "type": "notification",
                                "payload": message,
                            })
                            sent_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to send to admin {user_id}: {e}")
                            disconnected.append(conn)

                # Clean up disconnected connections
                for conn in disconnected:
                    if conn in connections:
                        connections.remove(conn)

                if not connections and user_id in self._user_connections:
                    del self._user_connections[user_id]
                    self._admin_users.discard(user_id)

        return sent_count

    async def broadcast_to_all(self, message: dict[str, Any]) -> int:
        """Broadcast a message to all connected users.

        Args:
            message: Message to send

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0
        async with self._lock:
            for user_id, connections in list(self._user_connections.items()):
                disconnected = []

                for conn in connections:
                    try:
                        await conn.websocket.send_json({
                            "type": "notification",
                            "payload": message,
                        })
                        sent_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to broadcast to user {user_id}: {e}")
                        disconnected.append(conn)

                # Clean up disconnected connections
                for conn in disconnected:
                    if conn in connections:
                        connections.remove(conn)

                if not connections and user_id in self._user_connections:
                    del self._user_connections[user_id]
                    self._admin_users.discard(user_id)

        return sent_count

    async def send_unread_count(self, user_id: int, count: int) -> int:
        """Send updated unread count to a user's connections.

        Args:
            user_id: Target user ID
            count: Unread notification count

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0
        async with self._lock:
            connections = self._user_connections.get(user_id, [])
            disconnected = []

            for conn in connections:
                try:
                    await conn.websocket.send_json({
                        "type": "unread_count",
                        "payload": {"count": count},
                    })
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send unread count to user {user_id}: {e}")
                    disconnected.append(conn)

            # Clean up disconnected connections
            for conn in disconnected:
                if conn in connections:
                    connections.remove(conn)

        return sent_count

    def get_connected_user_ids(self) -> list[int]:
        """Get list of all connected user IDs.

        Returns:
            List of user IDs with active connections
        """
        return list(self._user_connections.keys())

    def get_connection_count(self, user_id: Optional[int] = None) -> int:
        """Get connection count.

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
    from app.services.notification_service import get_notification_service
    notification_service = get_notification_service()
    notification_service.set_websocket_manager(manager)

    logger.info("WebSocket manager initialized")
    return manager
