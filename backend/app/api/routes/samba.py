"""Samba (SMB/CIFS) management API endpoints."""

import logging
import socket

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.samba import (
    SambaStatusResponse,
    SambaConnection,
    SambaUserStatus,
    SambaUsersResponse,
    SambaUserToggleRequest,
    SambaConnectionInfo,
)
from app.schemas.webdav import OsConnectionInfo
from app.services import samba_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/samba", tags=["samba"])


def _get_local_ip() -> str:
    """Detect the primary local IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


@router.get("/status", response_model=SambaStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_samba_status(
    request: Request, response: Response,
    _admin=Depends(deps.get_current_admin),
):
    """Get Samba server status (admin only)."""
    raw = await samba_service.get_samba_status()
    return SambaStatusResponse(
        is_running=raw["is_running"],
        version=raw["version"],
        active_connections=[SambaConnection(**c) for c in raw["active_connections"]],
        smb_users_count=raw["smb_users_count"],
    )


@router.get("/users", response_model=SambaUsersResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_samba_users(
    request: Request, response: Response,
    _admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """List all users with their SMB status (admin only)."""
    users = db.query(User).order_by(User.username).all()
    return SambaUsersResponse(
        users=[
            SambaUserStatus(
                user_id=u.id,
                username=u.username,
                role=u.role,
                smb_enabled=u.smb_enabled,
                is_active=u.is_active,
            )
            for u in users
        ]
    )


@router.post("/users/{user_id}/toggle")
@user_limiter.limit(get_limit("admin_operations"))
async def toggle_smb_user(
    request: Request, response: Response,
    user_id: int,
    payload: SambaUserToggleRequest,
    _admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Toggle SMB access for a user (admin only).

    When enabling, an optional password can be provided for immediate sync.
    Without a password the user must change their password for SMB to work.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.smb_enabled = payload.enabled
    db.commit()
    db.refresh(user)

    if payload.enabled:
        # Sync password if provided
        if payload.password:
            await samba_service.sync_smb_password(user.username, payload.password)
        await samba_service.enable_smb_user(user.username)
    else:
        await samba_service.disable_smb_user(user.username)

    # Regenerate shares config and reload
    await samba_service.regenerate_shares_config()
    await samba_service.reload_samba()

    return {
        "user_id": user.id,
        "username": user.username,
        "smb_enabled": user.smb_enabled,
    }


@router.get("/connection-info", response_model=SambaConnectionInfo)
@user_limiter.limit(get_limit("admin_operations"))
async def get_samba_connection_info(
    request: Request, response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Get SMB mount instructions for the current user."""
    user = db.query(User).filter(User.id == current_user.id).first()
    is_admin = current_user.role == "admin"

    share_name = "BaluHost" if is_admin else f"BaluHost-{current_user.username}"

    local_ip = _get_local_ip()
    smb_path = f"\\\\{local_ip}\\{share_name}"

    # Get Samba status for is_running
    raw_status = await samba_service.get_samba_status()

    instructions = [
        OsConnectionInfo(
            os="windows",
            label="Windows",
            command=f"net use Z: {smb_path} /user:{current_user.username} *",
            notes="Or use File Explorer → Map Network Drive → enter the path above. Windows shows the full RAID capacity correctly.",
        ),
        OsConnectionInfo(
            os="macos",
            label="macOS",
            command=f"open smb://{current_user.username}@{local_ip}/{share_name}",
            notes="Or use Finder → Go → Connect to Server (Cmd+K).",
        ),
        OsConnectionInfo(
            os="linux",
            label="Linux",
            command=f"sudo mount -t cifs //{local_ip}/{share_name} /mnt/baluhost -o username={current_user.username}",
            notes="Install cifs-utils first: sudo apt install cifs-utils",
        ),
    ]

    return SambaConnectionInfo(
        is_running=raw_status["is_running"],
        share_name=share_name,
        smb_path=smb_path,
        username=current_user.username,
        instructions=instructions,
    )
