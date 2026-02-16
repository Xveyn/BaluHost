"""Notification API endpoints."""
from datetime import time
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
from app.services.notification_service import get_notification_service
from app.services import auth as auth_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_notifications(
    request: Request, response: Response,
    unread_only: bool = Query(False, description="Only return unread notifications"),
    include_dismissed: bool = Query(False, description="Include dismissed notifications"),
    category: Optional[NotificationCategoryEnum] = Query(None, description="Filter by category"),
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

    notifications = service.get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        include_dismissed=include_dismissed,
        category=category,
        limit=page_size,
        offset=offset,
    )

    unread_count = service.get_unread_count(db, current_user.id)

    # Get total count for pagination
    total_notifications = service.get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        include_dismissed=include_dismissed,
        category=category,
        limit=10000,
        offset=0,
    )

    return NotificationListResponse(
        notifications=[
            NotificationResponse.from_db(n) for n in notifications
        ],
        total=len(total_notifications),
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
    total = service.get_unread_count(db, current_user.id)

    # Get breakdown by category
    categories = ["raid", "smart", "backup", "scheduler", "system", "security", "sync", "vpn"]
    by_category = {}
    for cat in categories:
        count = service.get_unread_count(db, current_user.id, category=cat)
        if count > 0:
            by_category[cat] = count

    return UnreadCountResponse(
        count=total,
        by_category=by_category if by_category else None,
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
    notification = service.mark_as_read(db, notification_id, current_user.id)

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

    count = service.mark_all_as_read(db, current_user.id, category=category)

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
    notification = service.dismiss(db, notification_id, current_user.id)

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
        email_enabled=body.email_enabled,
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


# WebSocket endpoint for real-time notifications
@router.websocket("/ws")
async def notification_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """WebSocket endpoint for real-time notification delivery.

    Requires JWT token as query parameter for authentication.
    Sends notification events as they occur.
    """
    import logging
    from app.services.websocket_manager import get_websocket_manager
    from app.core.database import SessionLocal

    logger = logging.getLogger(__name__)

    # Validate token before accepting connection
    if not token:
        logger.warning("WebSocket connection attempt without token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Authenticate user
    user_id = None
    is_admin = False
    db = None

    try:
        db = SessionLocal()
        payload = auth_service.decode_token(token)
        from app.services import users as user_service
        user = user_service.get_user(payload.sub, db=db)
        if not user:
            logger.warning(f"WebSocket: User not found for token sub={payload.sub}")
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
            unread_count = service.get_unread_count(db, user_id)
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
                            service.mark_as_read(db, notification_id, user_id)
                            unread_count = service.get_unread_count(db, user_id)
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
