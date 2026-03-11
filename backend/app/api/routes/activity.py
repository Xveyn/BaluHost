"""File activity tracking API endpoints."""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.file_activity import (
    VALID_ACTION_TYPES,
    ActivityListResponse,
    RecentFilesResponse,
    ReportActivitiesRequest,
    ReportActivitiesResponse,
)
from app.schemas.user import UserPublic
from app.services.file_activity import FileActivityService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/recent", response_model=ActivityListResponse)
@user_limiter.limit(get_limit("file_list"))
async def get_recent_activities(
    request: Request,
    response: Response,
    limit: int = 20,
    offset: int = 0,
    action_types: Optional[str] = None,
    file_type: Optional[str] = None,
    since: Optional[datetime] = None,
    path_prefix: Optional[str] = None,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Get recent file activities for the current user.

    Args:
        limit: Max items (1-100, default 20).
        offset: Pagination offset.
        action_types: Comma-separated filter, e.g. ``file.open,file.download``.
        file_type: Filter by type: file, directory, image, video, document.
        since: ISO timestamp — only activities after this time.
        path_prefix: Only activities within this directory.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    parsed_types: Optional[List[str]] = None
    if action_types:
        parsed_types = [t.strip() for t in action_types.split(",") if t.strip()]

    svc = FileActivityService(db)
    items, total = svc.get_recent_activities(
        user_id=user.id,
        limit=limit,
        offset=offset,
        action_types=parsed_types,
        file_type=file_type,
        since=since,
        path_prefix=path_prefix,
    )

    return ActivityListResponse(
        activities=items,
        total=total,
        has_more=(offset + limit) < total,
    )


@router.get("/recent-files", response_model=RecentFilesResponse)
@user_limiter.limit(get_limit("file_list"))
async def get_recent_files(
    request: Request,
    response: Response,
    limit: int = 10,
    actions: Optional[str] = None,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> RecentFilesResponse:
    """Get recently used files (deduplicated by path).

    Args:
        limit: Max files (1-50, default 10).
        actions: Comma-separated action types that count as "used".
                 Default: file.open,file.download,file.upload,file.edit
    """
    limit = max(1, min(limit, 50))

    parsed_actions: Optional[List[str]] = None
    if actions:
        parsed_actions = [a.strip() for a in actions.split(",") if a.strip()]

    svc = FileActivityService(db)
    files = svc.get_recent_files(user_id=user.id, limit=limit, actions=parsed_actions)

    return RecentFilesResponse(files=files)


@router.post("/report", response_model=ReportActivitiesResponse)
@user_limiter.limit(get_limit("file_upload"))
async def report_activities(
    request: Request,
    response: Response,
    payload: ReportActivitiesRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> ReportActivitiesResponse:
    """Accept client-reported file activities (batch-capable).

    Clients (e.g. BaluApp) call this to report actions that happened
    on the device (file.open, file.view, download, etc.). Events are
    deduplicated against recent server-side entries.
    """
    svc = FileActivityService(db)
    accepted = 0
    deduplicated = 0
    rejected = 0

    for item in payload.activities:
        # Validate action type
        if item.action_type not in VALID_ACTION_TYPES:
            rejected += 1
            continue

        # Reject path-traversal attempts
        if ".." in item.file_path:
            rejected += 1
            continue

        result = svc.record(
            user_id=user.id,
            action_type=item.action_type,
            file_path=item.file_path,
            file_name=item.file_name,
            is_directory=item.is_directory,
            file_size=item.file_size,
            mime_type=item.mime_type,
            device_id=item.device_id,
            source="client",
            occurred_at=item.occurred_at,
        )
        if result is None:
            deduplicated += 1
        else:
            accepted += 1

    db.commit()

    return ReportActivitiesResponse(
        accepted=accepted,
        deduplicated=deduplicated,
        rejected=rejected,
    )
