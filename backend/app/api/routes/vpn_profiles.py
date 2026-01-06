"""API routes for VPN Profile management."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_current_user
from app.models import VPNProfile, User, VPNType, ServerProfile
from app.schemas.vpn_profile import (
    VPNProfileCreate,
    VPNProfileResponse,
    VPNProfileList,
    VPNProfileUpdate,
    VPNConnectionTest,
)
from app.services.vpn_service import VPNService
from app.services.vpn_encryption import VPNEncryption

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vpn-profiles", tags=["vpn-profiles"])


@router.post("", response_model=VPNProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_vpn_profile(
    name: str = Form(...),
    vpn_type: str = Form(...),
    config_file: UploadFile = File(...),
    certificate_file: UploadFile = File(None),
    private_key_file: UploadFile = File(None),
    auto_connect: bool = Form(False),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        valid, error = VPNService.validate_config(vpn_type_enum.value, config_content)
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
        
        # Encrypt sensitive data
        encrypted_config = VPNEncryption.encrypt_vpn_config(config_content)
        encrypted_cert = VPNEncryption.encrypt_vpn_config(certificate_content) if certificate_content else None
        encrypted_key = VPNEncryption.encrypt_vpn_config(private_key_content) if private_key_content else None
        
        # Create profile
        db_profile = VPNProfile(
            user_id=current_user.id,
            name=name,
            vpn_type=vpn_type_enum,
            config_file_encrypted=encrypted_config,
            certificate_encrypted=encrypted_cert,
            private_key_encrypted=encrypted_key,
            auto_connect=auto_connect,
            description=description,
        )
        
        db.add(db_profile)
        db.commit()
        db.refresh(db_profile)
        
        logger.info(f"VPN profile '{name}' created by user {current_user.id}")
        return VPNProfileResponse.from_orm(db_profile)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating VPN profile: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create VPN profile"
        )


@router.get("", response_model=List[VPNProfileList])
async def list_vpn_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[VPNProfileList]:
    """List all VPN profiles for current user."""
    profiles = db.query(VPNProfile).filter(
        VPNProfile.user_id == current_user.id
    ).order_by(VPNProfile.created_at.desc()).all()
    
    return [VPNProfileList.from_orm(p) for p in profiles]


@router.get("/{profile_id}", response_model=VPNProfileResponse)
async def get_vpn_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VPNProfileResponse:
    """Get specific VPN profile."""
    profile = db.query(VPNProfile).filter(
        VPNProfile.id == profile_id,
        VPNProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )
    
    return VPNProfileResponse.from_orm(profile)


@router.put("/{profile_id}", response_model=VPNProfileResponse)
async def update_vpn_profile(
    profile_id: int,
    name: str = Form(None),
    description: str = Form(None),
    auto_connect: bool = Form(None),
    config_file: UploadFile = File(None),
    certificate_file: UploadFile = File(None),
    private_key_file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VPNProfileResponse:
    """Update VPN profile."""
    profile = db.query(VPNProfile).filter(
        VPNProfile.id == profile_id,
        VPNProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )
    
    try:
        # Update basic fields
        if name is not None:
            profile.name = name
        if description is not None:
            profile.description = description
        if auto_connect is not None:
            profile.auto_connect = auto_connect
        
        # Update config if provided
        if config_file:
            config_content = (await config_file.read()).decode('utf-8')
            valid, error = VPNService.validate_config(profile.vpn_type, config_content)
            if not valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid VPN configuration: {error}",
                )
            profile.config_file_encrypted = VPNEncryption.encrypt_vpn_config(config_content)
        
        # Update certificate if provided
        if certificate_file:
            cert_content = (await certificate_file.read()).decode('utf-8')
            profile.certificate_encrypted = VPNEncryption.encrypt_vpn_config(cert_content)
        
        # Update private key if provided
        if private_key_file:
            key_content = (await private_key_file.read()).decode('utf-8')
            profile.private_key_encrypted = VPNEncryption.encrypt_vpn_config(key_content)
        
        db.commit()
        db.refresh(profile)
        
        logger.info(f"VPN profile {profile_id} updated by user {current_user.id}")
        return VPNProfileResponse.from_orm(profile)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating VPN profile: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update VPN profile"
        )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vpn_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete VPN profile."""
    profile = db.query(VPNProfile).filter(
        VPNProfile.id == profile_id,
        VPNProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )
    
    try:
        db.delete(profile)
        db.commit()
        logger.info(f"VPN profile {profile_id} deleted by user {current_user.id}")
    except Exception as e:
        logger.error(f"Error deleting VPN profile: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete VPN profile"
        )


@router.post("/{profile_id}/test-connection", response_model=VPNConnectionTest)
async def test_vpn_connection(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VPNConnectionTest:
    """Test VPN configuration validity."""
    profile = db.query(VPNProfile).filter(
        VPNProfile.id == profile_id,
        VPNProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN profile not found"
        )
    
    try:
        # Decrypt config
        config_content = VPNEncryption.decrypt_vpn_config(profile.config_file_encrypted)
        
        # Validate
        valid, error = VPNService.validate_config(profile.vpn_type, config_content)
        
        return VPNConnectionTest(
            profile_id=profile_id,
            connected=valid,
            error_message=error or None,
        )
        
    except Exception as e:
        logger.error(f"Error testing VPN connection: {str(e)}")
        return VPNConnectionTest(
            profile_id=profile_id,
            connected=False,
            error_message=f"Test failed: {str(e)}",
            server_info=None,
        )
