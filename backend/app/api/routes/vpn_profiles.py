"""API routes for VPN Profile management."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Request, Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models import User, VPNType
from app.schemas.vpn_profile import (
    VPNProfileResponse,
    VPNProfileList,
    VPNConnectionTest,
)
from app.services.vpn.profile_crud import (
    list_user_profiles,
    get_user_profile,
    create_profile,
    update_profile_fields,
    delete_profile,
)
from app.services.vpn.profiles import VPNService as VPNProfileValidator
from app.services.vpn import VPNEncryption

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vpn-profiles", tags=["vpn-profiles"])


@router.post("", response_model=VPNProfileResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("vpn_operations"))
async def create_vpn_profile(
    request: Request,
    response: Response,
    name: str = Form(...),
    vpn_type: str = Form(...),
    config_file: UploadFile = File(...),
    certificate_file: UploadFile = File(None),
    private_key_file: UploadFile = File(None),
    auto_connect: bool = Form(False),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> VPNProfileResponse:
    """Create a new VPN profile."""
    try:
        # Validate and convert vpn_type
        try:
            vpn_type_enum = VPNType(vpn_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid VPN type. Must be one of: {', '.join([t.value for t in VPNType])}",
            )

        # Read config file
        config_content = (await config_file.read()).decode('utf-8')

        # Validate config
        valid, error = VPNProfileValidator.validate_config(vpn_type_enum, config_content)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid VPN configuration: {error}",
            )

        # Read optional certificate and key files
        certificate_content = None
        if certificate_file:
            certificate_content = (await certificate_file.read()).decode('utf-8')

        private_key_content = None
        if private_key_file:
            private_key_content = (await private_key_file.read()).decode('utf-8')

        profile = create_profile(
            db,
            user_id=current_user.id,
            name=name,
            vpn_type=vpn_type_enum,
            config_content=config_content,
            certificate_content=certificate_content,
            private_key_content=private_key_content,
            auto_connect=auto_connect,
            description=description,
        )
        return VPNProfileResponse.from_orm(profile)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating VPN profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create VPN profile"
        )


@router.get("", response_model=List[VPNProfileList])
@user_limiter.limit(get_limit("vpn_operations"))
async def list_vpn_profiles(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> List[VPNProfileList]:
    """List all VPN profiles for current user."""
    profiles = list_user_profiles(db, current_user.id)
    return [VPNProfileList.from_orm(p) for p in profiles]


@router.get("/{profile_id}", response_model=VPNProfileResponse)
@user_limiter.limit(get_limit("vpn_operations"))
async def get_vpn_profile(
    request: Request,
    response: Response,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> VPNProfileResponse:
    """Get specific VPN profile."""
    profile = get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )
    return VPNProfileResponse.from_orm(profile)


@router.put("/{profile_id}", response_model=VPNProfileResponse)
@user_limiter.limit(get_limit("vpn_operations"))
async def update_vpn_profile(
    request: Request,
    response: Response,
    profile_id: int,
    name: str = Form(None),
    description: str = Form(None),
    auto_connect: bool = Form(None),
    config_file: UploadFile = File(None),
    certificate_file: UploadFile = File(None),
    private_key_file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> VPNProfileResponse:
    """Update VPN profile."""
    profile = get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )

    try:
        # Read and validate config if provided
        config_content = None
        if config_file:
            config_content = (await config_file.read()).decode('utf-8')
            valid, error = VPNProfileValidator.validate_config(profile.vpn_type, config_content)
            if not valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid VPN configuration: {error}",
                )

        certificate_content = None
        if certificate_file:
            certificate_content = (await certificate_file.read()).decode('utf-8')

        private_key_content = None
        if private_key_file:
            private_key_content = (await private_key_file.read()).decode('utf-8')

        updated = update_profile_fields(
            db,
            profile,
            name=name,
            description=description,
            auto_connect=auto_connect,
            config_content=config_content,
            certificate_content=certificate_content,
            private_key_content=private_key_content,
            user_id=current_user.id,
        )
        return VPNProfileResponse.from_orm(updated)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating VPN profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update VPN profile"
        )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("vpn_operations"))
async def delete_vpn_profile(
    request: Request,
    response: Response,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Delete VPN profile."""
    profile = get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )

    try:
        delete_profile(db, profile, current_user.id)
    except Exception as e:
        logger.error("Error deleting VPN profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete VPN profile"
        )


@router.post("/{profile_id}/test-connection", response_model=VPNConnectionTest)
@user_limiter.limit(get_limit("vpn_operations"))
async def test_vpn_connection(
    request: Request,
    response: Response,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> VPNConnectionTest:
    """Test VPN configuration validity."""
    profile = get_user_profile(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )

    try:
        # Decrypt config
        config_content = VPNEncryption.decrypt_vpn_config(profile.config_file_encrypted)

        # Validate
        valid, error = VPNProfileValidator.validate_config(profile.vpn_type, config_content)

        return VPNConnectionTest(
            profile_id=profile_id,
            connected=valid,
            error_message=error or None,
        )

    except Exception as e:
        logger.error("Error testing VPN connection: %s", e)
        return VPNConnectionTest(
            profile_id=profile_id,
            connected=False,
            error_message=f"Test failed: {str(e)}",
            server_info=None,
        )
