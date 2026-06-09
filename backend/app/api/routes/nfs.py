"""NFS export management API endpoints (admin only)."""
import logging
import socket

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.nfs_export import NfsExport
from app.schemas.nfs import (
    NfsExportCreate,
    NfsExportUpdate,
    NfsExportResponse,
    NfsExportsResponse,
    NfsStatusResponse,
)
from app.services import nfs_service
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfs", tags=["nfs"])


def _get_local_ip() -> str:
    """Detect the primary local IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _to_response(exp: NfsExport, server_ip: str) -> NfsExportResponse:
    try:
        abs_path = nfs_service.validate_export_path(exp.path)
        mount_target = f"{server_ip}:{abs_path}"
    except ValueError:
        mount_target = f"{server_ip}:<invalid path>"
    return NfsExportResponse(
        id=exp.id,
        path=exp.path,
        clients=exp.clients,
        read_only=exp.read_only,
        root_squash=exp.root_squash,
        enabled=exp.enabled,
        comment=exp.comment,
        mount_target=mount_target,
    )


@router.get("/status", response_model=NfsStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_nfs_status(
    request: Request, response: Response,
    _admin=Depends(deps.get_current_admin),
):
    """Get NFS server status (admin only)."""
    raw = await nfs_service.get_nfs_status()
    return NfsStatusResponse(**raw)


@router.get("/exports", response_model=NfsExportsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_nfs_exports(
    request: Request, response: Response,
    _admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """List all NFS exports (admin only)."""
    ip = _get_local_ip()
    exports = db.query(NfsExport).order_by(NfsExport.id).all()
    return NfsExportsResponse(exports=[_to_response(e, ip) for e in exports])


@router.post("/exports", response_model=NfsExportResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def create_nfs_export(
    request: Request, response: Response,
    payload: NfsExportCreate,
    current_admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Create an NFS export (admin only)."""
    audit = get_audit_logger_db()
    if db.query(NfsExport).filter(NfsExport.path == payload.path).first():
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_created", resource=payload.path,
            success=False, error_message="An export for this path already exists", db=db,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An export for this path already exists")
    exp = NfsExport(
        path=payload.path, clients=payload.clients, read_only=payload.read_only,
        root_squash=payload.root_squash, enabled=payload.enabled, comment=payload.comment,
    )
    details = {
        "clients": payload.clients, "read_only": payload.read_only,
        "root_squash": payload.root_squash, "enabled": payload.enabled,
    }
    try:
        db.add(exp)
        db.commit()
        db.refresh(exp)
        await nfs_service.regenerate_exports_config()
        await nfs_service.apply_exports()
    except Exception as e:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_created", resource=payload.path,
            success=False, error_message=str(e), db=db,
        )
        raise
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_created", resource=exp.path,
        success=True, details=details, db=db,
    )
    return _to_response(exp, _get_local_ip())


@router.put("/exports/{export_id}", response_model=NfsExportResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_nfs_export(
    request: Request, response: Response,
    export_id: int,
    payload: NfsExportUpdate,
    current_admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Update an NFS export (admin only)."""
    audit = get_audit_logger_db()
    exp = db.query(NfsExport).filter(NfsExport.id == export_id).first()
    if not exp:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_updated", resource=str(export_id),
            success=False, error_message="Export not found", db=db,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    if payload.path != exp.path and db.query(NfsExport).filter(NfsExport.path == payload.path).first():
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_updated", resource=payload.path,
            success=False, error_message="An export for this path already exists", db=db,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An export for this path already exists")
    exp.path = payload.path
    exp.clients = payload.clients
    exp.read_only = payload.read_only
    exp.root_squash = payload.root_squash
    exp.enabled = payload.enabled
    exp.comment = payload.comment
    details = {
        "clients": payload.clients, "read_only": payload.read_only,
        "root_squash": payload.root_squash, "enabled": payload.enabled,
    }
    try:
        db.commit()
        db.refresh(exp)
        await nfs_service.regenerate_exports_config()
        await nfs_service.apply_exports()
    except Exception as e:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_updated", resource=payload.path,
            success=False, error_message=str(e), db=db,
        )
        raise
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_updated", resource=exp.path,
        success=True, details=details, db=db,
    )
    return _to_response(exp, _get_local_ip())


@router.delete("/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_nfs_export(
    request: Request, response: Response,
    export_id: int,
    current_admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete an NFS export (admin only)."""
    audit = get_audit_logger_db()
    exp = db.query(NfsExport).filter(NfsExport.id == export_id).first()
    if not exp:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_deleted", resource=str(export_id),
            success=False, error_message="Export not found", db=db,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    path = exp.path
    try:
        db.delete(exp)
        db.commit()
        await nfs_service.regenerate_exports_config()
        await nfs_service.apply_exports()
    except Exception as e:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_deleted", resource=path,
            success=False, error_message=str(e), db=db,
        )
        raise
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_deleted", resource=path,
        success=True, details={"export_id": export_id}, db=db,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
