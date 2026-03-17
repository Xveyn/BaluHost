"""VCL (Version Control Light) API Routes — Tracking Endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.schemas.vcl import (
    FileTrackingEntry,
    FileTrackingRequest,
    FileTrackingListResponse,
    FileTrackingCheckResponse,
    BulkTrackingRequest,
)
from app.services.versioning.tracking import VCLTrackingService
from app.models.vcl import VCLSettings
from app.models.file_metadata import FileMetadata

router = APIRouter()


# ============================================================================
# TRACKING ENDPOINTS
# ============================================================================

@router.get("/tracking", response_model=FileTrackingListResponse)
@user_limiter.limit(get_limit("file_list"))
async def get_tracking_rules(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileTrackingListResponse:
    """Get current user's VCL tracking rules and mode."""
    tracking = VCLTrackingService(db)
    settings = db.query(VCLSettings).filter(VCLSettings.user_id == user.id).first()
    mode = str(settings.vcl_mode) if settings is not None and settings.vcl_mode is not None else "automatic"

    rules = tracking.get_user_tracking_rules(user.id)
    entries = []
    for rule in rules:
        file_path = None
        file_name = None
        if rule.file_id is not None:
            f = db.query(FileMetadata.path, FileMetadata.name).filter(
                FileMetadata.id == rule.file_id
            ).first()
            if f:
                file_path = str(f[0])
                file_name = str(f[1])
        entries.append(FileTrackingEntry(
            id=int(rule.id),  # type: ignore[arg-type]
            file_id=int(rule.file_id) if rule.file_id is not None else None,  # type: ignore[arg-type]
            file_path=file_path,
            file_name=file_name,
            path_pattern=str(rule.path_pattern) if rule.path_pattern is not None else None,  # type: ignore[arg-type]
            action=str(rule.action),  # type: ignore[arg-type]
            is_directory=bool(rule.is_directory),  # type: ignore[arg-type]
            created_at=rule.created_at,  # type: ignore[arg-type]
        ))

    return FileTrackingListResponse(
        mode=mode,
        rules=entries,
        total=len(entries),
    )


@router.post("/tracking", response_model=FileTrackingEntry, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("file_write"))
async def add_tracking_rule(
    request: Request,
    response: Response,
    rule_req: FileTrackingRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileTrackingEntry:
    """Add a tracking/exclusion rule for VCL."""
    tracking = VCLTrackingService(db)

    if rule_req.file_id:
        # Validate file exists and user owns it (or is admin)
        file = db.query(FileMetadata).filter(FileMetadata.id == rule_req.file_id).first()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        if user.role != "admin" and int(file.owner_id) != user.id:
            raise HTTPException(status_code=403, detail="Not file owner")
        # Reject path traversal
        if '..' in str(file.path):
            raise HTTPException(status_code=400, detail="Invalid file path")

        rule = tracking.set_file_tracking(
            user.id, rule_req.file_id, rule_req.action, rule_req.is_directory
        )
    elif rule_req.path_pattern:
        rule = tracking.add_pattern_rule(user.id, rule_req.path_pattern, rule_req.action)
    else:
        raise HTTPException(
            status_code=400, detail="Either file_id or path_pattern is required"
        )

    db.commit()

    file_path = None
    file_name = None
    if rule.file_id is not None:
        f = db.query(FileMetadata.path, FileMetadata.name).filter(
            FileMetadata.id == rule.file_id
        ).first()
        if f:
            file_path = str(f[0])
            file_name = str(f[1])

    return FileTrackingEntry(
        id=int(rule.id),  # type: ignore[arg-type]
        file_id=int(rule.file_id) if rule.file_id is not None else None,  # type: ignore[arg-type]
        file_path=file_path,
        file_name=file_name,
        path_pattern=str(rule.path_pattern) if rule.path_pattern is not None else None,  # type: ignore[arg-type]
        action=str(rule.action),  # type: ignore[arg-type]
        is_directory=bool(rule.is_directory),  # type: ignore[arg-type]
        created_at=rule.created_at,  # type: ignore[arg-type]
    )


@router.delete("/tracking/{rule_id}", status_code=status.HTTP_200_OK)
@user_limiter.limit(get_limit("file_write"))
async def remove_tracking_rule(
    request: Request,
    response: Response,
    rule_id: int,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a tracking rule."""
    tracking = VCLTrackingService(db)
    deleted = tracking.remove_file_tracking(user.id, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.commit()
    return {"success": True, "message": "Rule removed"}


@router.get("/tracking/check/{file_id}", response_model=FileTrackingCheckResponse)
@user_limiter.limit(get_limit("file_list"))
async def check_file_tracking(
    request: Request,
    response: Response,
    file_id: int,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileTrackingCheckResponse:
    """Check if a specific file is tracked for versioning."""
    tracking = VCLTrackingService(db)
    result = tracking.get_tracking_status(file_id, user.id)
    return FileTrackingCheckResponse(**result)


@router.post("/tracking/bulk", status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("file_write"))
async def bulk_add_tracking(
    request: Request,
    response: Response,
    bulk_req: BulkTrackingRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk add tracking rules."""
    tracking = VCLTrackingService(db)
    added = 0
    for rule_req in bulk_req.rules:
        if rule_req.file_id:
            file = db.query(FileMetadata).filter(FileMetadata.id == rule_req.file_id).first()
            if not file:
                continue
            if user.role != "admin" and int(file.owner_id) != user.id:
                continue
            tracking.set_file_tracking(
                user.id, rule_req.file_id, rule_req.action, rule_req.is_directory
            )
            added += 1
        elif rule_req.path_pattern:
            tracking.add_pattern_rule(user.id, rule_req.path_pattern, rule_req.action)
            added += 1

    db.commit()
    return {"success": True, "added": added}
