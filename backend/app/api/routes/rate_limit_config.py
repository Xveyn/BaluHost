"""API routes for rate limit configuration (admin only)."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_admin
from app.schemas.user import UserPublic
from app.schemas.rate_limit_config import (
    RateLimitConfigResponse,
    RateLimitConfigCreate,
    RateLimitConfigUpdate,
    RateLimitConfigList
)
from app.services.rate_limit_config import RateLimitConfigService
from app.services.audit_logger_db import get_audit_logger_db
from app.core.rate_limiter import user_limiter, get_limit

router = APIRouter(prefix="/rate-limits", tags=["admin", "rate-limits"])


@router.get("", response_model=RateLimitConfigList)
@user_limiter.limit(get_limit("admin_operations"))
async def get_rate_limits(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get all rate limit configurations (admin only)."""
    configs = RateLimitConfigService.get_all(db)
    response_configs = [RateLimitConfigResponse.from_orm(config) for config in configs]
    return RateLimitConfigList(
        configs=response_configs,
        total=len(response_configs)
    )


@router.get("/{endpoint_type}", response_model=RateLimitConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_rate_limit(
    request: Request,
    response: Response,
    endpoint_type: str,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get a specific rate limit configuration (admin only)."""
    config = RateLimitConfigService.get_by_endpoint_type(db, endpoint_type)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rate limit configuration for '{endpoint_type}' not found"
        )
    
    return config


@router.post("", response_model=RateLimitConfigResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def create_rate_limit(
    request: Request,
    response: Response,
    config: RateLimitConfigCreate,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new rate limit configuration (admin only)."""
    audit_logger = get_audit_logger_db()
    
    # Check if already exists
    existing = RateLimitConfigService.get_by_endpoint_type(db, config.endpoint_type)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rate limit configuration for '{config.endpoint_type}' already exists"
        )
    
    # Create configuration
    db_config = RateLimitConfigService.create(db, config, current_user.id)
    
    # Log action
    audit_logger.log_security_event(
        action="rate_limit_created",
        user=current_user.username,
        details={
            "endpoint_type": config.endpoint_type,
            "limit": config.limit_string,
            "enabled": config.enabled
        },
        success=True,
        db=db
    )
    
    return db_config


@router.put("/{endpoint_type}", response_model=RateLimitConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_rate_limit(
    request: Request,
    response: Response,
    endpoint_type: str,
    config_update: RateLimitConfigUpdate,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update a rate limit configuration (admin only)."""
    audit_logger = get_audit_logger_db()
    
    # Get existing config
    existing = RateLimitConfigService.get_by_endpoint_type(db, endpoint_type)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rate limit configuration for '{endpoint_type}' not found"
        )
    
    # Store old values for audit log
    old_limit = existing.limit_string
    old_enabled = existing.enabled
    
    # Update configuration
    updated_config = RateLimitConfigService.update(db, endpoint_type, config_update, current_user.id)
    
    # Log action
    changes = {}
    if config_update.limit_string and config_update.limit_string != old_limit:
        changes["limit"] = {"old": old_limit, "new": config_update.limit_string}
    if config_update.enabled is not None and config_update.enabled != old_enabled:
        changes["enabled"] = {"old": old_enabled, "new": config_update.enabled}
    
    audit_logger.log_security_event(
        action="rate_limit_updated",
        user=current_user.username,
        details={
            "endpoint_type": endpoint_type,
            "changes": changes
        },
        success=True,
        db=db
    )
    
    return updated_config


@router.delete("/{endpoint_type}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_rate_limit(
    request: Request,
    response: Response,
    endpoint_type: str,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Delete a rate limit configuration (admin only)."""
    audit_logger = get_audit_logger_db()
    
    success = RateLimitConfigService.delete(db, endpoint_type)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rate limit configuration for '{endpoint_type}' not found"
        )
    
    # Log action
    audit_logger.log_security_event(
        action="rate_limit_deleted",
        user=current_user.username,
        details={"endpoint_type": endpoint_type},
        success=True,
        db=db
    )
    
    return None


@router.post("/seed-defaults", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def seed_default_rate_limits(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Seed default rate limit configurations (admin only)."""
    audit_logger = get_audit_logger_db()
    
    RateLimitConfigService.seed_defaults(db)
    
    # Log action
    audit_logger.log_security_event(
        action="rate_limit_defaults_seeded",
        user=current_user.username,
        details={},
        success=True,
        db=db
    )
    
    return None
