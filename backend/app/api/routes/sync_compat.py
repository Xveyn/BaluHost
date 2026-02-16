"""Compatibility helpers for legacy sync endpoints used by older tests/clients.

This module exposes a minimal POST /sync/devices endpoint in dev mode
to register a device without the one-time registration token used by
the newer secure registration flow.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
import uuid

from app.core.config import get_settings
from app.api.deps import get_current_user
from app.core.database import get_db
from app.services.file_sync import FileSyncService
from app.core.rate_limiter import user_limiter, get_limit

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync_service(db: Session = Depends(get_db)) -> FileSyncService:
    return FileSyncService(db)


@router.post("/devices", status_code=201)
@user_limiter.limit(get_limit("sync_operations"))
async def legacy_register_device(
    request: Request,
    response: Response,
    payload: dict,
    current_user=Depends(get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service),
):
    """Legacy endpoint: create a device entry without token (dev mode only)."""
    settings = get_settings()
    if not settings.is_dev_mode:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Legacy device registration disabled")

    name = payload.get("name") or payload.get("device_name") or "unnamed"
    device_id = str(uuid.uuid4())

    sync_state = sync_service.register_device(user_id=current_user.id, device_id=device_id, device_name=name)

    return {"device_id": device_id, "device_name": sync_state.device_name}


@router.get("/devices")
@user_limiter.limit(get_limit("sync_operations"))
async def legacy_list_devices(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List devices registered for the current user (compatibility endpoint)."""
    # Query SyncState model directly to avoid circular imports
    from app.models.sync_state import SyncState

    devices = db.query(SyncState).filter(SyncState.user_id == current_user.id).all()
    result = [
        {"device_id": d.device_id, "name": d.device_name, "last_sync": d.last_sync.isoformat() if d.last_sync else None}
        for d in devices
    ]
    return result
