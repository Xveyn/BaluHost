"""API routes for Server Profile management."""

import datetime
import logging
from typing import List, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.config import settings
from app.models import User
from app.schemas.server_profile import (
    ServerProfileCreate,
    ServerProfileResponse,
    ServerProfileList,
    ServerProfileUpdate,
    ServerStartResponse,
    SSHConnectionTest,
)
from app.services import server_profile_service
from app.services.ssh_service import SSHService
from app.services.vpn.encryption import VPNEncryption
from app.core.rate_limiter import limiter, user_limiter, get_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/server-profiles", tags=["server-profiles"])


@router.get("/public", response_model=List[ServerProfileList])
@limiter.limit(get_limit("admin_operations"))
async def list_server_profiles_public(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> List[ServerProfileList]:
    """
    List ALL server profiles without authentication (for login screen).

    Only enabled when ALLOW_PUBLIC_PROFILE_LIST=true in config.
    Returns profile names and owners to help users select their server.
    SSH keys and sensitive data are excluded.

    Security note: This is safe for local-only deployments where
    profile discovery is needed before login. For production, disable
    or ensure enforce_local_only is enabled.
    """
    if not settings.allow_public_profile_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public profile listing is disabled"
        )

    profiles = server_profile_service.list_all_profiles(db)
    return [
        ServerProfileList(
            id=cast(int, p.id),
            name=cast(str, p.name),
            ssh_host=cast(str, p.ssh_host),
            ssh_port=cast(int,p.ssh_port),
            ##ssh_username=p.ssh_username,
            last_used=cast(None, p.last_used),
            created_at=cast(datetime.datetime, p.created_at),
            # Include owner info for client to filter/display
            user_id=cast(int, p.user_id),
        )
        for p in profiles
    ]


@router.post("", response_model=ServerProfileResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def create_server_profile(
    request: Request,
    response: Response,
    profile_data: ServerProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerProfileResponse:
    """Create a new server profile."""
    try:
        profile = server_profile_service.create_profile(db, current_user.id, profile_data)
        return ServerProfileResponse.from_orm(profile)
    except ValueError as e:
        logger.error("Validation error creating profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create profile"
        )


@router.get("", response_model=List[ServerProfileList])
@user_limiter.limit(get_limit("admin_operations"))
async def list_server_profiles(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> List[ServerProfileList]:
    """List all server profiles for current user."""
    profiles = server_profile_service.list_user_profiles(db, current_user.id)
    return [ServerProfileList.from_orm(p) for p in profiles]


@router.get("/{profile_id}", response_model=ServerProfileResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_server_profile(
    request: Request,
    response: Response,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerProfileResponse:
    """Get specific server profile."""
    profile = server_profile_service.get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )
    return ServerProfileResponse.from_orm(profile)


@router.put("/{profile_id}", response_model=ServerProfileResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_server_profile(
    request: Request,
    response: Response,
    profile_id: int,
    profile_data: ServerProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerProfileResponse:
    """Update server profile."""
    profile = server_profile_service.get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )

    try:
        updated = server_profile_service.update_profile(
            db, profile, profile_data, current_user.id
        )
        return ServerProfileResponse.from_orm(updated)
    except Exception as e:
        logger.error("Error updating profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_server_profile(
    request: Request,
    response: Response,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Delete server profile."""
    profile = server_profile_service.get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )

    try:
        server_profile_service.delete_profile(db, profile, current_user.id)
    except Exception as e:
        logger.error("Error deleting profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile"
        )


@router.post("/{profile_id}/check-connectivity", response_model=SSHConnectionTest)
@user_limiter.limit(get_limit("admin_operations"))
async def check_ssh_connection(
    request: Request,
    response: Response,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SSHConnectionTest:
    """Test SSH connectivity to server."""
    profile = server_profile_service.get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )

    try:
        # Decrypt SSH key
        private_key = VPNEncryption.decrypt_ssh_private_key(cast(str, profile.ssh_key_encrypted))

        # Test connection
        success, error = SSHService.test_connection(
            cast(str, profile.ssh_host),
            cast(int, profile.ssh_port),
            cast(str, profile.ssh_username),
            private_key,
        )

        return SSHConnectionTest(
            ssh_reachable=success,
            local_network=success,  # TODO: Implement network detection
            needs_vpn=profile.vpn_profile_id is not None,
            error_message=error,
        )

    except Exception as e:
        logger.error("Error testing SSH connection: %s", e)
        return SSHConnectionTest(
            ssh_reachable=False,
            local_network=False,
            needs_vpn=profile.vpn_profile_id is not None,
            error_message=f"Connection test failed: {str(e)}",
        )


@router.post("/{profile_id}/start", response_model=ServerStartResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_remote_server(
    request: Request,
    response: Response,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerStartResponse:
    """Start remote BaluHost server."""
    profile = server_profile_service.get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )

    if not cast(str | None, profile.power_on_command):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No power on command configured for this profile"
        )

    try:
        # Decrypt SSH key
        private_key = VPNEncryption.decrypt_ssh_private_key(cast(str, profile.ssh_key_encrypted))

        # Start server
        success, message = SSHService.start_server(
            cast(str, profile.ssh_host),
            cast(int, profile.ssh_port),
            cast(str, profile.ssh_username),
            private_key,
            cast(str, profile.power_on_command),
        )

        if success:
            server_profile_service.mark_last_used(db, profile)
            logger.info("Server %d started by user %d", profile_id, current_user.id)
            return ServerStartResponse(
                profile_id=profile_id,
                status="starting",
                message=message,
            )
        else:
            logger.warning("Failed to start server %d: %s", profile_id, message)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error starting server: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start server"
        )
