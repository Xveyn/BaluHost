"""API routes for VPN configuration and management."""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.vpn import VPNClient
from app.core.rate_limiter import user_limiter, get_limit
from app.api.deps import get_current_user, get_current_admin
from app.schemas.user import UserPublic
from app.schemas.vpn import (
    VPNClient as VPNClientSchema,
    VPNClientCreate,
    VPNClientUpdate,
    VPNConfigResponse,
    VPNServerConfig,
    VPNStatusResponse,
    FritzBoxConfigUpload,
    FritzBoxConfigResponse,
    FritzBoxConfigSummary,
    VPNAvailableTypesResponse,
    FetchConfigByTypeRequest,
)
from app.services.vpn import VPNService
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vpn", tags=["vpn"])


@router.get("/available-types", response_model=VPNAvailableTypesResponse)
@user_limiter.limit(get_limit("vpn_operations"))
async def get_available_vpn_types(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Get available VPN config types.

    Returns which config sources are available:
    - 'fritzbox': Admin has uploaded an active Fritz!Box config
    - 'wireguard': Always available (per-client generated configs)
    """
    from app.models.vpn import FritzBoxVPNConfig

    has_fritzbox = db.query(FritzBoxVPNConfig).filter(
        FritzBoxVPNConfig.is_active == True
    ).first() is not None

    available: list[str] = []
    if has_fritzbox:
        available.append("fritzbox")
    available.append("wireguard")

    return VPNAvailableTypesResponse(available_types=available)


@router.post("/fetch-config-by-type")
@user_limiter.limit(get_limit("vpn_operations"))
async def fetch_config_by_type(
    request: Request,
    response: Response,
    body: FetchConfigByTypeRequest,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Fetch a VPN config of a specific type.

    Allows the client (e.g. Android app) to explicitly choose between
    Fritz!Box shared config and a per-client WireGuard server config.
    """
    audit_logger = get_audit_logger_db()

    if body.vpn_type == "fritzbox":
        try:
            config_base64 = VPNService.get_fritzbox_config_base64(db)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active Fritz!Box VPN config available",
            )

        audit_logger.log_vpn_operation(
            action="vpn_config_fetched",
            user=current_user.username,
            vpn_client=body.device_name,
            details={"vpn_type": "fritzbox"},
            success=True,
            db=db,
        )

        return {
            "vpn_type": "fritzbox",
            "config_base64": config_base64,
            "device_name": body.device_name,
        }
    else:
        # Generate a new per-client WireGuard config
        try:
            vpn_response = VPNService.create_client_config(
                db=db,
                user_id=current_user.id,
                device_name=body.device_name,
                server_public_endpoint=body.server_public_endpoint,
            )
        except RuntimeError as e:
            audit_logger.log_vpn_operation(
                action="vpn_config_fetch_failed",
                user=current_user.username,
                vpn_client=body.device_name,
                details={"vpn_type": "wireguard", "error": str(e)},
                success=False,
                error_message=str(e),
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

        audit_logger.log_vpn_operation(
            action="vpn_config_fetched",
            user=current_user.username,
            vpn_client=body.device_name,
            details={"vpn_type": "wireguard", "client_id": vpn_response.client_id},
            success=True,
            db=db,
        )

        return {
            "vpn_type": "wireguard",
            "config_base64": vpn_response.config_base64,
            "device_name": body.device_name,
            "client_id": vpn_response.client_id,
            "assigned_ip": vpn_response.assigned_ip,
        }


@router.post("/generate-config", response_model=VPNConfigResponse)
@user_limiter.limit(get_limit("vpn_operations"))
async def generate_vpn_config(
    request: Request,
    response: Response,
    config_data: VPNClientCreate,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Generate WireGuard VPN configuration for mobile device.

    Returns configuration file and QR code data for easy setup.
    """
    audit_logger = get_audit_logger_db()

    try:
        config = VPNService.create_client_config(
            db=db,
            user_id=current_user.id,
            device_name=config_data.device_name,
            server_public_endpoint=config_data.server_public_endpoint,
        )

        audit_logger.log_vpn_operation(
            action="vpn_client_created",
            user=current_user.username,
            vpn_client=config_data.device_name,
            details={
                "server_endpoint": config_data.server_public_endpoint
            },
            success=True,
            db=db
        )

        return config
    except RuntimeError as e:
        audit_logger.log_vpn_operation(
            action="vpn_client_create_failed",
            user=current_user.username,
            vpn_client=config_data.device_name,
            details={"error": str(e)},
            success=False,
            error_message=str(e),
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/clients", response_model=List[VPNClientSchema])
@user_limiter.limit(get_limit("vpn_operations"))
async def list_vpn_clients(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    List all VPN clients for the current user.
    """
    clients = VPNService.get_clients_by_user(db, current_user.id)
    return clients


@router.get("/clients/{client_id}", response_model=VPNClientSchema)
@user_limiter.limit(get_limit("vpn_operations"))
async def get_vpn_client(
    request: Request,
    response: Response,
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
    if str(client.user_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this VPN client"
        )
    
    return client


@router.patch("/clients/{client_id}", response_model=VPNClientSchema)
@user_limiter.limit(get_limit("vpn_operations"))
async def update_vpn_client(
    request: Request,
    response: Response,
    client_id: int,
    update_data: VPNClientUpdate,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Update VPN client settings (name, active status).
    """
    audit_logger = get_audit_logger_db()

    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found"
        )

    # Check ownership
    if str(client.user_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this VPN client"
        )

    old_device_name = client.device_name
    old_is_active = client.is_active

    # Update fields
    changes = {}
    if update_data.device_name is not None:
        client.device_name = update_data.device_name
        changes["device_name"] = f"{old_device_name} -> {update_data.device_name}"
    if update_data.is_active is not None:
        client.is_active = update_data.is_active
        changes["is_active"] = f"{old_is_active} -> {update_data.is_active}"

    db.commit()
    db.refresh(client)

    audit_logger.log_vpn_operation(
        action="vpn_client_updated",
        user=current_user.username,
        vpn_client=client.device_name,
        details=changes,
        success=True,
        db=db
    )

    return client


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("vpn_operations"))
async def delete_vpn_client(
    request: Request,
    response: Response,
    client_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Delete a VPN client configuration.
    """
    audit_logger = get_audit_logger_db()

    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found"
        )

    # Check ownership
    if str(client.user_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this VPN client"
        )

    device_name = client.device_name
    success = VPNService.delete_client(db, client_id)

    if not success:
        audit_logger.log_vpn_operation(
            action="vpn_client_delete_failed",
            user=current_user.username,
            vpn_client=device_name,
            success=False,
            error_message="Failed to delete VPN client",
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete VPN client"
        )

    audit_logger.log_vpn_operation(
        action="vpn_client_deleted",
        user=current_user.username,
        vpn_client=device_name,
        details={"client_id": client_id},
        success=True,
        db=db
    )


@router.post("/clients/{client_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("vpn_operations"))
async def revoke_vpn_client(
    request: Request,
    response: Response,
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
    if str(client.user_id) != str(current_user.id) and current_user.role != "admin":
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


@router.post("/sync-server")
@user_limiter.limit(get_limit("vpn_operations"))
async def sync_server_config(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_admin),
):
    """Regenerate and apply WireGuard server config from DB state (admin only)."""
    audit_logger = get_audit_logger_db()

    success, message = VPNService.apply_server_config(db)

    audit_logger.log_vpn_operation(
        action="vpn_server_config_sync",
        user=current_user.username,
        vpn_client="server",
        details={"message": message},
        success=success,
        error_message=message if not success else None,
        db=db,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message,
        )

    return {"success": True, "message": message}


@router.post("/sync-server-keys")
@user_limiter.limit(get_limit("vpn_operations"))
async def sync_server_keys(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_admin),
):
    """Sync server keys in DB from the running wg0 interface (admin only).

    Use this if client configs were generated with a wrong server public
    key.  After syncing, regenerate affected client configs.
    """
    audit_logger = get_audit_logger_db()

    success, message = VPNService.sync_server_keys_from_interface(db)

    audit_logger.log_vpn_operation(
        action="vpn_server_keys_synced",
        user=current_user.username,
        vpn_client="server",
        details={"message": message},
        success=success,
        error_message=message if not success else None,
        db=db,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message,
        )

    return {"success": True, "message": message}


@router.post(
    "/clients/{client_id}/regenerate-config",
    response_model=VPNConfigResponse,
)
@user_limiter.limit(get_limit("vpn_operations"))
async def regenerate_client_config(
    request: Request,
    response: Response,
    client_id: int,
    config_data: VPNClientCreate,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    """Regenerate config for an existing VPN client.

    Generates a new client keypair (the old private key is not stored)
    and returns a fresh config with the current server public key.
    The client must import this new config to replace the old one.
    """
    audit_logger = get_audit_logger_db()

    # Verify ownership
    client = VPNService.get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found",
        )
    if (
        str(client.user_id) != str(current_user.id)
        and current_user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to regenerate this VPN client config",
        )

    try:
        config = VPNService.regenerate_client_config(
            db=db,
            client_id=client_id,
            server_public_endpoint=config_data.server_public_endpoint,
        )

        audit_logger.log_vpn_operation(
            action="vpn_client_config_regenerated",
            user=current_user.username,
            vpn_client=client.device_name,
            details={
                "client_id": client_id,
                "server_endpoint": config_data.server_public_endpoint,
            },
            success=True,
            db=db,
        )

        return config
    except (ValueError, RuntimeError) as e:
        audit_logger.log_vpn_operation(
            action="vpn_client_config_regenerate_failed",
            user=current_user.username,
            vpn_client=client.device_name,
            details={"error": str(e)},
            success=False,
            error_message=str(e),
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/server-config", response_model=VPNServerConfig)
@user_limiter.limit(get_limit("vpn_operations"))
async def get_server_config(
    request: Request,
    response: Response,
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
    active_clients = db.query(VPNClient).filter_by(is_active=True).count()
    
    return VPNServerConfig(
        server_ip=config.server_ip,
        server_port=config.server_port,
        server_public_key=config.server_public_key,
        network_cidr=config.network_cidr,
        active_clients=active_clients,
    )


@router.post("/handshake/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("vpn_operations"))
async def update_handshake(
    request: Request,
    response: Response,
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
    if str(client.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    VPNService.update_last_handshake(db, client_id)


# Fritz!Box VPN Configuration Routes

@router.post("/fritzbox/upload", response_model=FritzBoxConfigResponse)
@user_limiter.limit(get_limit("vpn_operations"))
async def upload_fritzbox_config(
    request: Request,
    response: Response,
    config_data: FritzBoxConfigUpload,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_admin)  # Admin only!
):
    """
    Upload Fritz!Box WireGuard configuration (Admin only).
    
    - Parses .conf file content
    - Encrypts sensitive keys
    - Deactivates old configs
    - Returns config with Base64 for QR codes
    """
    try:
        config = VPNService.upload_fritzbox_config(
            db=db,
            config_content=config_data.config_content,
            user_id=current_user.id,
            public_endpoint=config_data.public_endpoint
        )
        return config
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid config format: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload config: {str(e)}"
        )


@router.get("/fritzbox/config", response_model=FritzBoxConfigSummary)
@user_limiter.limit(get_limit("vpn_operations"))
async def get_fritzbox_config(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get active Fritz!Box VPN config summary (ohne sensitive Daten).
    """
    config = VPNService.get_active_fritzbox_config(db)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Fritz!Box VPN config found"
        )
    
    return FritzBoxConfigSummary(
        id=config.id,
        endpoint=config.endpoint,
        dns_servers=config.dns_servers,
        is_active=config.is_active,
        created_at=config.created_at
    )


@router.delete("/fritzbox/config/{config_id}")
@user_limiter.limit(get_limit("vpn_operations"))
async def delete_fritzbox_config(
    request: Request,
    response: Response,
    config_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_admin)  # Admin only!
):
    """
    Delete Fritz!Box VPN config (Admin only).
    """
    success = VPNService.delete_fritzbox_config(db, config_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found"
        )
    
    return {"message": "Config deleted successfully"}


@router.get("/fritzbox/qr")
@user_limiter.limit(get_limit("vpn_operations"))
async def get_fritzbox_qr_code(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get Fritz!Box config as Base64 for QR code generation.
    """
    try:
        config_base64 = VPNService.get_fritzbox_config_base64(db)
        return {"config_base64": config_base64}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Failed to generate Fritz!Box QR data: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR code data"
        )
