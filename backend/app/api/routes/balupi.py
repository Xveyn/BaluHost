"""BaluPi setup & management routes (admin only).

Provides endpoints to configure, test, and monitor the BaluPi companion device
connection from the NAS admin UI.
"""

import logging
import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db
from app.services import env_config as env_config_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/balupi", tags=["admin", "balupi"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BaluPiConfigResponse(BaseModel):
    """Current BaluPi configuration (sensitive values masked)."""
    enabled: bool
    url: str
    has_secret: bool
    secret_preview: str  # first 4 chars + "..." or empty


class BaluPiConfigUpdate(BaseModel):
    """Update BaluPi configuration."""
    enabled: bool | None = None
    url: str | None = None
    secret: str | None = None


class BaluPiTestResult(BaseModel):
    """Result of a connection test to the BaluPi."""
    reachable: bool
    version: str | None = None
    hostname: str | None = None
    error: str | None = None


class BaluPiGenerateSecretResponse(BaseModel):
    """Generated shared secret."""
    secret: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/config", response_model=BaluPiConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_balupi_config(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
) -> BaluPiConfigResponse:
    """Get current BaluPi configuration (admin only)."""
    secret = settings.balupi_handshake_secret
    return BaluPiConfigResponse(
        enabled=settings.balupi_enabled,
        url=settings.balupi_url,
        has_secret=bool(secret),
        secret_preview=f"{secret[:4]}..." if secret and len(secret) >= 4 else "",
    )


@router.put("/config")
@user_limiter.limit(get_limit("admin_operations"))
async def update_balupi_config(
    request: Request,
    response: Response,
    payload: BaluPiConfigUpdate,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update BaluPi configuration (admin only).

    Writes changes to the backend .env file and updates runtime settings.
    """
    audit_logger = get_audit_logger_db()
    updates = []
    changed_fields = []

    if payload.enabled is not None:
        updates.append({"key": "BALUPI_ENABLED", "value": str(payload.enabled).lower()})
        changed_fields.append("enabled")

    if payload.url is not None:
        url = payload.url.rstrip("/")
        updates.append({"key": "BALUPI_URL", "value": url})
        changed_fields.append("url")

    if payload.secret is not None:
        if payload.secret and len(payload.secret) < 32:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Handshake secret must be at least 32 characters",
            )
        updates.append({"key": "BALUPI_HANDSHAKE_SECRET", "value": payload.secret})
        changed_fields.append("secret")

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Write to .env file
    try:
        env_config_service.update_vars("backend", updates)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write config: {e}",
        )

    # Update runtime settings (take effect immediately without restart)
    if payload.enabled is not None:
        settings.balupi_enabled = payload.enabled
    if payload.url is not None:
        settings.balupi_url = payload.url.rstrip("/")
    if payload.secret is not None:
        settings.balupi_handshake_secret = payload.secret

    audit_logger.log_security_event(
        action="balupi_config_updated",
        user=current_user.username,
        details={"changed_fields": changed_fields},
        success=True,
        db=db,
    )

    return {"changed": changed_fields}


@router.post("/test", response_model=BaluPiTestResult)
@user_limiter.limit(get_limit("admin_operations"))
async def test_balupi_connection(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
) -> BaluPiTestResult:
    """Test connection to the BaluPi device (admin only).

    Sends a GET request to the Pi's /api/health endpoint.
    """
    url = settings.balupi_url
    if not url:
        return BaluPiTestResult(
            reachable=False,
            error="BaluPi URL not configured",
        )

    health_url = f"{url.rstrip('/')}/api/health"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
            resp = await client.get(health_url)

        if resp.status_code == 200:
            data = resp.json()
            return BaluPiTestResult(
                reachable=True,
                version=data.get("version"),
                hostname=data.get("hostname"),
            )
        else:
            return BaluPiTestResult(
                reachable=False,
                error=f"HTTP {resp.status_code}",
            )
    except httpx.ConnectError:
        return BaluPiTestResult(
            reachable=False,
            error="Connection refused — is BaluPi running?",
        )
    except httpx.TimeoutException:
        return BaluPiTestResult(
            reachable=False,
            error="Connection timed out",
        )
    except httpx.HTTPError as exc:
        return BaluPiTestResult(
            reachable=False,
            error=str(exc),
        )


@router.post("/generate-secret", response_model=BaluPiGenerateSecretResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def generate_shared_secret(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
) -> BaluPiGenerateSecretResponse:
    """Generate a cryptographically secure shared secret (admin only).

    Returns a 48-character URL-safe token. The admin must copy this
    to the BaluPi's .env as BALUPI_HANDSHAKE_SECRET.
    """
    return BaluPiGenerateSecretResponse(
        secret=secrets.token_urlsafe(36),
    )
