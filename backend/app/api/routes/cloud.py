"""Cloud import API endpoints."""
import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.user import User
from app.schemas.cloud import (
    CloudConnectionResponse,
    CloudFileResponse,
    CloudImportJobResponse,
    CloudImportRequest,
    CloudOAuthConfigCreate,
    CloudOAuthConfigResponse,
    DevConnectRequest,
    ICloud2FARequest,
    ICloudConnectRequest,
    OAuthCallbackRequest,
)
from app.schemas.user import UserPublic
from app.services.audit_logger_db import AuditLoggerDB
from app.services.cloud.import_job import CloudImportJobService
from app.services.cloud.oauth_config import CloudOAuthConfigService
from app.services.cloud.service import CloudService

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Provider Status ──────────────────────────────────────────────

@router.get("/providers")
async def get_providers(
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return which cloud providers are available/configured."""
    oauth_svc = CloudOAuthConfigService(db)
    return {
        "is_dev_mode": settings.is_dev_mode,
        "providers": {
            "google_drive": {
                "configured": oauth_svc.is_configured("google_drive", current_user.id),
                "label": "Google Drive",
                "auth_type": "oauth",
            },
            "onedrive": {
                "configured": oauth_svc.is_configured("onedrive", current_user.id),
                "label": "OneDrive",
                "auth_type": "oauth",
            },
            "icloud": {
                "configured": True,  # iCloud uses user credentials, always available
                "label": "iCloud",
                "auth_type": "credentials",
            },
        },
    }


# ─── OAuth Config (Per-User) ─────────────────────────────────────

@router.put("/oauth-config", response_model=CloudOAuthConfigResponse)
async def save_oauth_config(
    request: CloudOAuthConfigCreate,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save or update OAuth credentials for a cloud provider (per-user)."""
    svc = CloudOAuthConfigService(db)
    config = svc.save_credentials(
        provider=request.provider,
        client_id=request.client_id,
        client_secret=request.client_secret,
        user_id=current_user.id,
    )

    audit = AuditLoggerDB()
    audit.log_event(
        event_type="SYSTEM_CONFIG",
        action="cloud_oauth_config_updated",
        user=current_user.username,
        resource=f"provider:{request.provider}",
        db=db,
    )

    return CloudOAuthConfigResponse(
        provider=config.provider,
        is_configured=True,
        client_id_hint=svc.get_client_id_hint(config.provider, current_user.id),
        user_id=config.user_id,
        updated_at=config.updated_at,
    )


@router.delete("/oauth-config/{provider}")
async def delete_oauth_config(
    provider: str,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete DB-stored OAuth credentials for a provider (own credentials only)."""
    if provider not in ("google_drive", "onedrive"):
        raise HTTPException(status_code=400, detail="Invalid provider")

    svc = CloudOAuthConfigService(db)
    deleted = svc.delete_credentials(provider, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No DB credentials found for this provider")

    audit = AuditLoggerDB()
    audit.log_event(
        event_type="SYSTEM_CONFIG",
        action="cloud_oauth_config_deleted",
        user=current_user.username,
        resource=f"provider:{provider}",
        db=db,
    )

    return {"success": True, "message": f"OAuth credentials for {provider} deleted"}


# ─── Connections ──────────────────────────────────────────────────

@router.get("/connections", response_model=list[CloudConnectionResponse])
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all cloud connections for the current user."""
    service = CloudService(db)
    connections = service.get_connections(current_user.id)
    return [CloudConnectionResponse.model_validate(c) for c in connections]


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a cloud connection."""
    service = CloudService(db)
    try:
        service.delete_connection(connection_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True, "message": "Connection deleted"}


# ─── OAuth Flow ───────────────────────────────────────────────────

@router.get("/oauth/{provider}/start")
async def start_oauth(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the OAuth authorization URL for a provider."""
    service = CloudService(db)
    try:
        url = service.get_oauth_url(provider, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"oauth_url": url}


@router.get("/oauth/callback")
async def oauth_callback_redirect(
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    """Handle OAuth redirect from provider (browser GET redirect)."""
    from starlette.responses import RedirectResponse
    from urllib.parse import quote

    try:
        state_data = json.loads(state)
        provider = state_data["provider"]
        user_id = state_data["user_id"]
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    service = CloudService(db)
    try:
        service.handle_oauth_callback(provider, code, user_id)
    except Exception as e:
        logger.error("OAuth callback failed: %s", e)
        return RedirectResponse(url=f"/cloud-import?oauth_error={quote(str(e))}")

    return RedirectResponse(url="/cloud-import?oauth=success")


@router.post("/oauth/callback", response_model=CloudConnectionResponse)
async def oauth_callback(
    request: OAuthCallbackRequest,
    db: Session = Depends(get_db),
):
    """Handle OAuth callback via POST (programmatic use)."""
    try:
        state_data = json.loads(request.state)
        provider = state_data["provider"]
        user_id = state_data["user_id"]
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    service = CloudService(db)
    try:
        conn = service.handle_oauth_callback(provider, request.code, user_id)
    except Exception as e:
        logger.error("OAuth callback failed: %s", e)
        raise HTTPException(status_code=400, detail=f"OAuth failed: {e}")

    return CloudConnectionResponse.model_validate(conn)


# ─── iCloud Connection ───────────────────────────────────────────

@router.post("/icloud/connect")
async def connect_icloud(
    request: ICloudConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Connect an iCloud account with Apple ID credentials."""
    service = CloudService(db)
    try:
        conn, requires_2fa = service.connect_icloud(
            current_user.id, request.apple_id, request.password
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "connection": CloudConnectionResponse.model_validate(conn),
        "requires_2fa": requires_2fa,
    }


@router.post("/icloud/2fa")
async def icloud_2fa(
    request: ICloud2FARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a 2FA code for iCloud authentication."""
    service = CloudService(db)
    try:
        success = service.validate_icloud_2fa(
            request.connection_id, current_user.id, request.code
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not success:
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    return {"success": True, "message": "2FA verified"}


# ─── Dev Mode Connection ─────────────────────────────────────────

@router.post("/dev/connect", response_model=CloudConnectionResponse)
async def dev_connect(
    request: DevConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a mock connection (dev mode only)."""
    if not settings.is_dev_mode:
        raise HTTPException(status_code=403, detail="Only available in dev mode")

    service = CloudService(db)
    conn = service.create_dev_connection(current_user.id, request.provider)
    return CloudConnectionResponse.model_validate(conn)


# ─── File Browser ─────────────────────────────────────────────────

@router.get("/browse/{connection_id}", response_model=list[CloudFileResponse])
async def browse_files(
    connection_id: int,
    path: str = Query(default="/", description="Path to browse"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Browse files in a cloud connection."""
    service = CloudService(db)
    try:
        files = await service.list_files(connection_id, current_user.id, path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to browse cloud files: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to list files: {e}")

    return [
        CloudFileResponse(
            name=f.name,
            path=f.path,
            is_directory=f.is_directory,
            size_bytes=f.size_bytes,
            modified_at=f.modified_at,
        )
        for f in files
    ]


# ─── Import Jobs ──────────────────────────────────────────────────

@router.post("/import", response_model=CloudImportJobResponse)
async def start_import(
    request: CloudImportRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a cloud import job."""
    job_service = CloudImportJobService(db)
    try:
        job = job_service.start_import(
            connection_id=request.connection_id,
            user_id=current_user.id,
            source_path=request.source_path,
            destination_path=request.destination_path,
            job_type=request.job_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Execute in background
    background_tasks.add_task(_run_import_async, job.id, db)

    return CloudImportJobResponse.model_validate(job)


@router.get("/jobs", response_model=list[CloudImportJobResponse])
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all import jobs for the current user."""
    job_service = CloudImportJobService(db)
    jobs = job_service.get_user_jobs(current_user.id, limit=limit)
    return [CloudImportJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=CloudImportJobResponse)
async def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a specific import job."""
    job_service = CloudImportJobService(db)
    job = job_service.get_job_status(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return CloudImportJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a running or pending import job."""
    job_service = CloudImportJobService(db)
    success = job_service.cancel_job(job_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=400, detail="Job cannot be cancelled (not running or pending)"
        )
    return {"success": True, "message": "Job cancellation requested"}


# ─── Background task helper ──────────────────────────────────────

async def _run_import_async(job_id: int, db: Session) -> None:
    """Execute import job in background."""
    try:
        job_service = CloudImportJobService(db)
        await job_service.execute_import(job_id)
    except Exception as e:
        logger.exception("Background import failed for job %d: %s", job_id, e)
