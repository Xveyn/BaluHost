"""API routes for Server Profile management."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.models import ServerProfile, User
from app.schemas.server_profile import (
    ServerProfileCreate,
    ServerProfileResponse,
    ServerProfileList,
    ServerProfileUpdate,
    ServerStartResponse,
    SSHConnectionTest,
)
from app.services.ssh_service import SSHService
from app.services.vpn_encryption import VPNEncryption

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/server-profiles", tags=["server-profiles"])


@router.post("", response_model=ServerProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_server_profile(
    profile_data: ServerProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerProfileResponse:
    """Create a new server profile."""
    try:
        # Encrypt SSH private key
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(profile_data.ssh_private_key)
        
        # Create profile
        db_profile = ServerProfile(
            user_id=current_user.id,
            name=profile_data.name,
            ssh_host=profile_data.ssh_host,
            ssh_port=profile_data.ssh_port,
            ssh_username=profile_data.ssh_username,
            ssh_key_encrypted=encrypted_key,
            vpn_profile_id=profile_data.vpn_profile_id,
            power_on_command=profile_data.power_on_command,
        )
        
        db.add(db_profile)
        db.commit()
        db.refresh(db_profile)
        
        logger.info(f"Server profile '{profile_data.name}' created by user {current_user.id}")
        return ServerProfileResponse.from_orm(db_profile)
        
    except ValueError as e:
        logger.error(f"Validation error creating profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating profile: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create profile"
        )


@router.get("", response_model=List[ServerProfileList])
async def list_server_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> List[ServerProfileList]:
    """List all server profiles for current user."""
    profiles = db.query(ServerProfile).filter(
        ServerProfile.user_id == current_user.id
    ).order_by(ServerProfile.created_at.desc()).all()
    
    return [ServerProfileList.from_orm(p) for p in profiles]


@router.get("/{profile_id}", response_model=ServerProfileResponse)
async def get_server_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerProfileResponse:
    """Get specific server profile."""
    profile = db.query(ServerProfile).filter(
        ServerProfile.id == profile_id,
        ServerProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )
    
    return ServerProfileResponse.from_orm(profile)


@router.put("/{profile_id}", response_model=ServerProfileResponse)
async def update_server_profile(
    profile_id: int,
    profile_data: ServerProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerProfileResponse:
    """Update server profile."""
    profile = db.query(ServerProfile).filter(
        ServerProfile.id == profile_id,
        ServerProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )
    
    try:
        # Update fields
        if profile_data.name is not None:
            profile.name = profile_data.name
        if profile_data.ssh_host is not None:
            profile.ssh_host = profile_data.ssh_host
        if profile_data.ssh_port is not None:
            profile.ssh_port = profile_data.ssh_port
        if profile_data.ssh_username is not None:
            profile.ssh_username = profile_data.ssh_username
        if profile_data.ssh_private_key is not None:
            profile.ssh_key_encrypted = VPNEncryption.encrypt_ssh_private_key(
                profile_data.ssh_private_key
            )
        if profile_data.vpn_profile_id is not None:
            profile.vpn_profile_id = profile_data.vpn_profile_id
        if profile_data.power_on_command is not None:
            profile.power_on_command = profile_data.power_on_command
        
        db.commit()
        db.refresh(profile)
        
        logger.info(f"Server profile {profile_id} updated by user {current_user.id}")
        return ServerProfileResponse.from_orm(profile)
        
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Delete server profile."""
    profile = db.query(ServerProfile).filter(
        ServerProfile.id == profile_id,
        ServerProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )
    
    try:
        db.delete(profile)
        db.commit()
        logger.info(f"Server profile {profile_id} deleted by user {current_user.id}")
    except Exception as e:
        logger.error(f"Error deleting profile: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile"
        )


@router.post("/{profile_id}/check-connectivity", response_model=SSHConnectionTest)
async def check_ssh_connection(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SSHConnectionTest:
    """Test SSH connectivity to server."""
    profile = db.query(ServerProfile).filter(
        ServerProfile.id == profile_id,
        ServerProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )
    
    try:
        # Decrypt SSH key
        private_key = VPNEncryption.decrypt_ssh_private_key(profile.ssh_key_encrypted)
        
        # Test connection
        success, error = SSHService.test_connection(
            profile.ssh_host,
            profile.ssh_port,
            profile.ssh_username,
            private_key,
        )
        
        return SSHConnectionTest(
            ssh_reachable=success,
            local_network=success,  # TODO: Implement network detection
            needs_vpn=profile.vpn_profile_id is not None,
            error_message=error,
        )
        
    except Exception as e:
        logger.error(f"Error testing SSH connection: {str(e)}")
        return SSHConnectionTest(
            ssh_reachable=False,
            local_network=False,
            needs_vpn=profile.vpn_profile_id is not None,
            error_message=f"Connection test failed: {str(e)}",
        )


@router.post("/{profile_id}/start", response_model=ServerStartResponse)
async def start_remote_server(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ServerStartResponse:
    """Start remote BaluHost server."""
    profile = db.query(ServerProfile).filter(
        ServerProfile.id == profile_id,
        ServerProfile.user_id == current_user.id,
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server profile not found"
        )
    
    if not profile.power_on_command:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No power on command configured for this profile"
        )
    
    try:
        # Decrypt SSH key
        private_key = VPNEncryption.decrypt_ssh_private_key(profile.ssh_key_encrypted)
        
        # Start server
        success, message = SSHService.start_server(
            profile.ssh_host,
            profile.ssh_port,
            profile.ssh_username,
            private_key,
            profile.power_on_command,
        )
        
        if success:
            # Update last_used
            from datetime import datetime
            profile.last_used = datetime.utcnow()
            db.commit()
            
            logger.info(f"Server {profile_id} started by user {current_user.id}")
            return ServerStartResponse(
                profile_id=profile_id,
                status="starting",
                message=message,
            )
        else:
            logger.warning(f"Failed to start server {profile_id}: {message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message,
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start server"
        )
