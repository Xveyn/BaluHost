"""WebDAV status and connection info API endpoints."""

import logging
import socket

from fastapi import APIRouter, Depends, Request, Response

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.webdav import (
    WebdavStatusResponse,
    WebdavConnectionInfo,
    OsConnectionInfo,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.webdav_state import WebdavState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webdav", tags=["webdav"])


def _get_local_ip() -> str:
    """Detect the primary local IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _read_webdav_state() -> WebdavState | None:
    """Read the current webdav_state row from the database."""
    db = SessionLocal()
    try:
        return db.query(WebdavState).first()
    finally:
        db.close()


@router.get("/status", response_model=WebdavStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_webdav_status(
    request: Request, response: Response,
    _admin=Depends(deps.get_current_admin),
):
    """Get detailed WebDAV server status (admin only)."""
    state = _read_webdav_state()

    if state is None or not state.is_running:
        return WebdavStatusResponse(
            is_running=False,
            port=settings.webdav_port,
            ssl_enabled=settings.webdav_ssl_enabled,
            error_message=state.error_message if state else None,
        )

    local_ip = _get_local_ip()
    scheme = "https" if state.ssl_enabled else "http"
    connection_url = f"{scheme}://{local_ip}:{state.port}/"

    return WebdavStatusResponse(
        is_running=True,
        port=state.port,
        ssl_enabled=state.ssl_enabled,
        started_at=state.started_at,
        worker_pid=state.worker_pid,
        last_heartbeat=state.last_heartbeat,
        error_message=state.error_message,
        connection_url=connection_url,
    )


@router.get("/connection-info", response_model=WebdavConnectionInfo)
@user_limiter.limit(get_limit("admin_operations"))
async def get_webdav_connection_info(
    request: Request, response: Response,
    current_user=Depends(deps.get_current_user),
):
    """Get OS-specific mount instructions with the authenticated user's name."""
    state = _read_webdav_state()
    is_running = state.is_running if state else False
    port = state.port if state else settings.webdav_port
    ssl_enabled = state.ssl_enabled if state else settings.webdav_ssl_enabled

    local_ip = _get_local_ip()
    scheme = "https" if ssl_enabled else "http"
    connection_url = f"{scheme}://{local_ip}:{port}/"

    win_notes = (
        "Or use File Explorer → Map Network Drive → "
        f"enter {connection_url} as folder path."
    )
    if ssl_enabled:
        win_notes += (
            " Self-signed certificate: import webdav.crt from the server"
            " into Windows' Trusted Root Certification Authorities."
        )

    linux_notes = (
        f"Enter username '{current_user.username}' when prompted. "
        "Install davfs2 first: sudo apt install davfs2"
    )
    if ssl_enabled:
        linux_notes += " Add 'trust_server_cert' to /etc/davfs2/davfs2.conf for self-signed certs."

    instructions = [
        OsConnectionInfo(
            os="windows",
            label="Windows",
            command=f"net use Z: {connection_url} /user:{current_user.username} *",
            notes=win_notes,
        ),
        OsConnectionInfo(
            os="macos",
            label="macOS",
            command=f"Finder → Go → Connect to Server → {connection_url}",
            notes=f"Authenticate with username '{current_user.username}' and your BaluHost password.",
        ),
        OsConnectionInfo(
            os="linux",
            label="Linux",
            command=f"sudo mount -t davfs {connection_url} /mnt/baluhost",
            notes=linux_notes,
        ),
    ]

    return WebdavConnectionInfo(
        is_running=is_running,
        port=port,
        ssl_enabled=ssl_enabled,
        username=current_user.username,
        connection_url=connection_url,
        instructions=instructions,
    )
