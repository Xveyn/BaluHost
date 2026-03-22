"""Fritz!Box TR-064 integration API routes."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.fritzbox import FritzBoxConfig
from app.models.user import User
from app.schemas.fritzbox import (
    FritzBoxConfigResponse,
    FritzBoxConfigUpdate,
    FritzBoxTestResponse,
    FritzBoxWolResponse,
)
from app.services.audit.logger_db import get_audit_logger_db
from app.services.power.fritzbox_wol import get_fritzbox_wol_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fritzbox", tags=["fritzbox"])


def _get_or_create_config(db: Session) -> FritzBoxConfig:
    """Load or create the singleton config row."""
    config = db.execute(
        select(FritzBoxConfig).where(FritzBoxConfig.id == 1)
    ).scalar_one_or_none()
    if not config:
        config = FritzBoxConfig(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _config_to_response(config: FritzBoxConfig) -> FritzBoxConfigResponse:
    """Convert DB model to response schema (never expose password)."""
    return FritzBoxConfigResponse(
        host=config.host,
        port=config.port,
        username=config.username,
        nas_mac_address=config.nas_mac_address,
        enabled=config.enabled,
        has_password=bool(config.password_encrypted),
    )


@router.get("/config", response_model=FritzBoxConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_fritzbox_config(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> FritzBoxConfigResponse:
    """Get Fritz!Box integration configuration (admin only)."""
    config = _get_or_create_config(db)
    return _config_to_response(config)


@router.put("/config", response_model=FritzBoxConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_fritzbox_config(
    request: Request, response: Response,
    body: FritzBoxConfigUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> FritzBoxConfigResponse:
    """Update Fritz!Box integration configuration (admin only)."""
    config = db.execute(
        select(FritzBoxConfig).where(FritzBoxConfig.id == 1)
    ).scalar_one_or_none()
    if not config:
        config = FritzBoxConfig(id=1)
        db.add(config)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "password":
            # Encrypt password before storage
            if value is not None and value != "":
                from app.services.vpn.encryption import VPNEncryption
                config.password_encrypted = VPNEncryption.encrypt_key(value)
            elif value == "":
                config.password_encrypted = ""
            # None means "don't update"
        elif value is not None:
            setattr(config, field, value)

    db.commit()
    db.refresh(config)
    result = _config_to_response(config)

    # Audit log
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="SYSTEM_CONFIG",
        user=current_user.username,
        action="fritzbox_config_update",
        resource="fritzbox_config",
        details={"fields_updated": list(update_data.keys())},
    )
    logger.info("Fritz!Box config updated by %s", current_user.username)
    return result


@router.post("/test", response_model=FritzBoxTestResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def test_fritzbox_connection(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
) -> FritzBoxTestResponse:
    """Test Fritz!Box TR-064 connection (admin only)."""
    service = get_fritzbox_wol_service()
    success, message = await service.test_connection()
    return FritzBoxTestResponse(success=success, message=message)


@router.post("/wol", response_model=FritzBoxWolResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def send_fritzbox_wol(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> FritzBoxWolResponse:
    """Send WoL via Fritz!Box (admin only)."""
    service = get_fritzbox_wol_service()

    # Pre-check: is it enabled and configured?
    config = _get_or_create_config(db)
    if not config.enabled:
        raise HTTPException(status_code=400, detail="Fritz!Box integration not enabled")
    if not config.nas_mac_address:
        raise HTTPException(status_code=400, detail="No NAS MAC address configured")

    success = await service.send_wol()

    # Audit log
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="SYSTEM",
        user=current_user.username,
        action="fritzbox_wol_send",
        resource="fritzbox",
        details={"mac": config.nas_mac_address},
        success=success,
    )

    if not success:
        raise HTTPException(status_code=503, detail="Fritz!Box WoL failed — check connection and credentials")

    logger.info("Fritz!Box WoL sent by %s", current_user.username)
    return FritzBoxWolResponse(success=True, message="WoL sent via Fritz!Box")
