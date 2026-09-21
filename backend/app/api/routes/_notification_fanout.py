"""Fan-out of notification state changes to a user's open connections.

Lives in the route layer on purpose: the NotificationService state methods
are synchronous (def, Session), the send is async. A fan-out inside the
service would have to schedule a task on a foreign event loop from
synchronous code. All eight routes that change state call this one helper so
they cannot drift apart.
"""

import logging

from sqlalchemy.orm import Session

from app.services.notifications.service import get_notification_service
from app.services.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)

# The bulk actions carry no ids on purpose: mark_all_as_read takes an optional
# category filter, so "everything" would be a lie whenever one is set. These
# actions mean "reload" — the client asks instead of guessing.
BULK_ACTIONS = frozenset({"read_all", "dismissed_all", "deleted_all"})
SINGLE_ACTIONS = frozenset({"read", "dismissed", "snoozed", "deleted", "restored"})
VALID_ACTIONS = SINGLE_ACTIONS | BULK_ACTIONS


async def fanout_state(
    db: Session,
    user_id: int,
    ids: list[int],
    action: str,
    is_admin: bool,
) -> None:
    """Tell the user's other clients that these notifications changed.

    Never raises: the database write has already happened when we get here,
    and a dead socket must not turn a successful state change into a failed
    request.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"unknown action: {action!r}")
    if not ids and action not in BULK_ACTIONS:
        return

    manager = get_websocket_manager()
    if not manager.is_user_connected(user_id):
        # Nobody listening — skip the work, including the COUNT query.
        return

    try:
        await manager.send_notification_state(user_id, ids, action)
        count = get_notification_service().get_unread_count(
            db, user_id, is_admin=is_admin
        )
        await manager.send_unread_count(user_id, count)
    except Exception as e:
        logger.warning(f"notification fan-out failed for user {user_id}: {e}")
