"""API routes for VPN configuration and management."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.schemas.user import UserPublic
from app.schemas.vpn import (
    VPNClient as VPNClientSchema,
    VPNClientCreate,
    VPNClientUpdate,
    VPNConfigResponse,
    VPNServerConfig,
    VPNStatusResponse,
)
from app.services.vpn import VPNService

router = APIRouter(prefix="/vpn", tags=["vpn"])


@router.post("/generate-config", response_model=VPNConfigResponse)
async def generate_vpn_config(
    request: Request,
    config_data: VPNClientCreate,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Generate WireGuard VPN configuration for mobile device.
    
    Returns configuration file and QR code data for easy setup.
    """
    try:
        config = VPNService.create_client_config(
            db=db,
            user_id=current_user.id,
            device_name=config_data.device_name,
            server_public_endpoint=config_data.server_public_endpoint,
        )
        return config
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/clients", response_model=List[VPNClientSchema])
async def list_vpn_clients(
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    List all VPN clients for the current user.
    """
    clients = VPNService.get_clients_by_user(db, current_user.id)
    return clients


@router.get("/clients/{client_id}", response_model=VPNClientSchema)
async def get_vpn_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get details of a specific VPN client.
    """
    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found"
        )
    
    # Check ownership
    if client.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this VPN client"
        )
    
    return client


@router.patch("/clients/{client_id}", response_model=VPNClientSchema)
async def update_vpn_client(
    client_id: int,
    update_data: VPNClientUpdate,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Update VPN client settings (name, active status).
    """
    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found"
        )
    
    # Check ownership
    if client.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this VPN client"
        )
    
    # Update fields
    if update_data.device_name is not None:
        client.device_name = update_data.device_name
    if update_data.is_active is not None:
        client.is_active = update_data.is_active
    
    db.commit()
    db.refresh(client)
    return client


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vpn_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Delete a VPN client configuration.
    """
    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found"
        )
    
    # Check ownership
    if client.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this VPN client"
        )
    
    success = VPNService.delete_client(db, client_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete VPN client"
        )


@router.post("/clients/{client_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_vpn_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Revoke VPN access for a client (deactivate without deleting).
    """
    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found"
        )
    
    # Check ownership
    if client.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to revoke this VPN client"
        )
    
    success = VPNService.revoke_client(db, client_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke VPN client"
        )


@router.get("/server-config", response_model=VPNServerConfig)
async def get_server_config(
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get VPN server configuration (admin only).
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    config = VPNService.get_server_config(db)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN server not configured"
        )
    
    # Count active clients
    active_clients = db.query(VPNService).filter_by(is_active=True).count()
    
    return VPNServerConfig(
        server_ip=config.server_ip,
        server_port=config.server_port,
        server_public_key=config.server_public_key,
        network_cidr=config.network_cidr,
        active_clients=active_clients,
    )


@router.post("/handshake/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_handshake(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Update last handshake timestamp (called by mobile client on connect).
    """
    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found"
        )
    
    # Check ownership
    if client.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    VPNService.update_last_handshake(db, client_id)
