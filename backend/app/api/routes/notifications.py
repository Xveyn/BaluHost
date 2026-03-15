"""Notification API endpoints."""
from datetime import time, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.core.database import get_db
from app.schemas.user import UserPublic
from app.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadRequest,
    MarkReadResponse,
    NotificationPreferencesUpdate,
    NotificationPreferencesResponse,
    NotificationCategoryEnum,
)
from app.services.notifications import get_notification_service
from app.services import auth as auth_service
from app.services.permissions import is_privileged

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_notifications(
    request: Request, response: Response,
    unread_only: bool = Query(False, description="Only return unread notifications"),
    include_dismissed: bool = Query(False, description="Include dismissed notifications"),
    category: Optional[NotificationCategoryEnum] = Query(None, description="Filter by category"),
    notification_type: Optional[str] = Query(None, description="Filter by type (info, warning, critical)"),
    created_after: Optional[datetime] = Query(None, description="Only return notifications after this time"),
    created_before: Optional[datetime] = Query(None, description="Only return notifications before this time"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    """Get notifications for the current user.

    Returns paginated list of notifications with optional filters.
    """
    service = get_notification_service()
    offset = (page - 1) * page_size
    admin = is_privileged(current_user)

    notifications = service.get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        include_dismissed=include_dismissed,
        category=category,
        notification_type=notification_type,
        created_after=created_after,
        created_before=created_before,
        limit=page_size,
        offset=offset,
        is_admin=admin,
    )

    unread_count = service.get_unread_count(db, current_user.id, is_admin=admin)

    # Get total count for pagination using SQL COUNT(*)
    total = service.count_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        include_dismissed=include_dismissed,
        category=category,
        notification_type=notification_type,
        created_after=created_after,
        created_before=created_before,
        is_admin=admin,
    )

    return NotificationListResponse(
        notifications=[
            NotificationResponse.from_db(n) for n in notifications
        ],
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_unread_count(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCountResponse:
    """Get count of unread notifications for the current user.

    Also returns breakdown by category.
    """
    service = get_notification_service()

    # Single GROUP BY query instead of 9 separate queries
    counts = service.get_unread_counts(db, current_user.id, is_admin=is_privileged(current_user))
    total = counts.pop("total", 0)

    return UnreadCountResponse(
        count=total,
        by_category=counts if counts else None,
    )


@router.post("/{notification_id}/read", response_model=NotificationResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def mark_notification_as_read(
    request: Request, response: Response,
    notification_id: int,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Mark a specific notification as read."""
    service = get_notification_service()
    notification = service.mark_as_read(db, notification_id, current_user.id, is_admin=is_privileged(current_user))

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return NotificationResponse.from_db(notification)


@router.post("/read-all", response_model=MarkReadResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def mark_all_as_read(
    request: Request, response: Response,
    body: Optional[MarkReadRequest] = None,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> MarkReadResponse:
    """Mark all notifications as read.

    Optionally filter by category.
    """
    service = get_notification_service()
    category = body.category if body else None

    count = service.mark_all_as_read(db, current_user.id, category=category, is_admin=is_privileged(current_user))

    return MarkReadResponse(success=True, count=count)


@router.post("/{notification_id}/dismiss", response_model=NotificationResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def dismiss_notification(
    request: Request, response: Response,
    notification_id: int,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Dismiss a notification.

    Dismissed notifications are hidden from the default list but can be retrieved with include_dismissed=true.
    """
    service = get_notification_service()
    notification = service.dismiss(db, notification_id, current_user.id, is_admin=is_privileged(current_user))

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return NotificationResponse.from_db(notification)


@router.post("/{notification_id}/snooze", response_model=NotificationResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def snooze_notification(
    request: Request, response: Response,
    notification_id: int,
    duration_hours: int = Query(..., ge=1, le=168, description="Hours to snooze (1-168)"),
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Snooze a notification for a given number of hours.

    The notification will be hidden from unread counts and default lists
    until the snooze period expires.
    """
    service = get_notification_service()
    notification = service.snooze(db, notification_id, current_user.id, duration_hours, is_admin=is_privileged(current_user))

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return NotificationResponse.from_db(notification)


# Preferences endpoints
@router.get("/preferences", response_model=NotificationPreferencesResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_notification_preferences(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferencesResponse:
    """Get notification preferences for the current user.

    Returns default preferences if none are set.
    """
    service = get_notification_service()
    prefs = service.get_user_preferences(db, current_user.id)

    if not prefs:
        # Create default preferences
        prefs = service.update_user_preferences(db, current_user.id)

    return NotificationPreferencesResponse.from_db(prefs)


@router.put("/preferences", response_model=NotificationPreferencesResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_notification_preferences(
    request: Request, response: Response,
    body: NotificationPreferencesUpdate,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferencesResponse:
    """Update notification preferences for the current user."""
    service = get_notification_service()

    # Parse quiet hours if provided
    quiet_start = None
    quiet_end = None
    if body.quiet_hours_start:
        try:
            parts = body.quiet_hours_start.split(":")
            quiet_start = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid quiet_hours_start format. Use HH:MM",
            )
    if body.quiet_hours_end:
        try:
            parts = body.quiet_hours_end.split(":")
            quiet_end = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid quiet_hours_end format. Use HH:MM",
            )

    # Convert category preferences if provided
    cat_prefs = None
    if body.category_preferences:
        cat_prefs = {
            cat: pref.model_dump() for cat, pref in body.category_preferences.items()
        }

    prefs = service.update_user_preferences(
        db=db,
        user_id=current_user.id,
        push_enabled=body.push_enabled,
        in_app_enabled=body.in_app_enabled,
        category_preferences=cat_prefs,
        quiet_hours_enabled=body.quiet_hours_enabled,
        quiet_hours_start=quiet_start,
        quiet_hours_end=quiet_end,
        min_priority=body.min_priority,
    )

    return NotificationPreferencesResponse.from_db(prefs)


# Admin endpoints for creating notifications
@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def create_notification(
    request: Request, response: Response,
    body: NotificationCreate,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Create a new notification (admin only).

    Can create notifications for specific users or broadcast to all admins.
    """
    service = get_notification_service()

    notification = await service.create(
        db=db,
        user_id=body.user_id,
        category=body.category,
        notification_type=body.notification_type,
        title=body.title,
        message=body.message,
        action_url=body.action_url,
        metadata=body.metadata,
        priority=body.priority,
    )

    return NotificationResponse.from_db(notification)


# WebSocket token endpoint
@router.post("/ws-token")
@user_limiter.limit(get_limit("user_operations"))
async def get_ws_token(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
):
    """Get a short-lived, scoped token for WebSocket authentication.

    The returned token is valid for 60 seconds and only grants access
    to the notification WebSocket endpoint. This avoids passing the
    full access token (which carries broader permissions) as a query
    parameter where it would be logged by proxies and browsers.
    """
    from app.core.security import create_ws_token
    token = create_ws_token(current_user.id, current_user.username)
    return {"token": token}


# WebSocket endpoint for real-time notifications
@router.websocket("/ws")
async def notification_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """WebSocket endpoint for real-time notification delivery.

    Requires a scoped WS token (from POST /ws-token) as query parameter.
    Also accepts full access tokens for backwards compatibility (deprecated).
    """
    import logging
    from app.services.websocket_manager import get_websocket_manager
    from app.core.database import SessionLocal
    from app.core.security import decode_token as decode_raw_token
    import jwt as pyjwt

    logger = logging.getLogger(__name__)

    # Validate token before accepting connection
    if not token:
        logger.warning("WebSocket connection attempt without token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Authenticate user using scoped WS token (preferred) or access token (deprecated)
    user_id = None
    is_admin = False
    db = None

    try:
        db = SessionLocal()

        # First try to decode as a scoped WS token
        try:
            payload = decode_raw_token(token, token_type="ws")
        except pyjwt.InvalidTokenError:
            # Fall back to access token for backwards compatibility
            try:
                payload = decode_raw_token(token, token_type="access")
                logger.warning(
                    "WebSocket: client used access token instead of scoped ws token "
                    "(deprecated, use POST /api/notifications/ws-token)"
                )
            except pyjwt.InvalidTokenError:
                raise auth_service.InvalidTokenError("Invalid WebSocket token")

        user_sub = payload.get("sub")
        from app.services import users as user_service
        user = user_service.get_user(user_sub, db=db)
        if not user:
            logger.warning(f"WebSocket: User not found for token sub={user_sub}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_id = user.id
        is_admin = user.role == "admin"
        logger.info(f"WebSocket: Authenticated user_id={user_id}, is_admin={is_admin}")
    except auth_service.InvalidTokenError as e:
        logger.warning(f"WebSocket: Invalid token - {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except Exception as e:
        logger.error(f"WebSocket: Authentication error - {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return
    finally:
        if db:
            db.close()

    # Accept connection after successful authentication
    try:
        await websocket.accept()
        logger.info(f"WebSocket: Connection accepted for user_id={user_id}")
    except Exception as e:
        logger.error(f"WebSocket: Failed to accept connection - {e}")
        return

    # Register with WebSocket manager
    manager = get_websocket_manager()
    await manager.connect(websocket, user_id, is_admin=is_admin)

    try:
        # Send initial unread count with fresh db session
        service = get_notification_service()
        db = SessionLocal()
        try:
            unread_count = service.get_unread_count(db, user_id, is_admin=is_admin)
            await websocket.send_json({
                "type": "unread_count",
                "payload": {"count": unread_count},
            })
        except Exception as e:
            logger.error(f"WebSocket: Failed to send initial unread count - {e}")
        finally:
            db.close()

        # Keep connection alive and handle messages
        while True:
            try:
                data = await websocket.receive_json()

                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "payload": {}})
                elif data.get("type") == "mark_read":
                    notification_id = data.get("payload", {}).get("notification_id")
                    if notification_id:
                        # Use fresh db session for mark_read
                        db = SessionLocal()
                        try:
                            service.mark_as_read(db, notification_id, user_id, is_admin=is_admin)
                            unread_count = service.get_unread_count(db, user_id, is_admin=is_admin)
                            await websocket.send_json({
                                "type": "unread_count",
                                "payload": {"count": unread_count},
                            })
                        except Exception as e:
                            logger.error(f"WebSocket: Failed to mark_read - {e}")
                        finally:
                            db.close()

            except WebSocketDisconnect:
                logger.info(f"WebSocket: Client disconnected user_id={user_id}")
                break
            except Exception as e:
                logger.error(f"WebSocket: Error handling message - {e}")
                break

    finally:
        await manager.disconnect(websocket)
        logger.info(f"WebSocket: Connection closed for user_id={user_id}")
