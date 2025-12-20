"""Pydantic schemas for VPN configuration."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class VPNClientBase(BaseModel):
    """Base schema for VPN client."""
    device_name: str = Field(..., description="Device name (e.g., 'iPhone 13 Pro')")


class VPNClientCreate(VPNClientBase):
    """Schema for creating a VPN client."""
    server_public_endpoint: str = Field(..., description="Server public IP or domain")


class VPNClient(VPNClientBase):
    """Schema for VPN client response."""
    id: int
    user_id: int
    assigned_ip: str
    public_key: str
    is_active: bool
    created_at: datetime
    last_handshake: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class VPNConfigResponse(BaseModel):
    """Schema for VPN configuration response."""
    client_id: int
    device_name: str
    assigned_ip: str
    client_public_key: str
    server_public_key: str
    server_endpoint: str
    config_content: str = Field(..., description="WireGuard config file content")
    config_base64: str = Field(..., description="Base64-encoded config for QR code")


class VPNServerConfig(BaseModel):
    """Schema for VPN server configuration."""
    server_ip: str
    server_port: int
    server_public_key: str
    network_cidr: str
    active_clients: int
    
    class Config:
        from_attributes = True


class VPNStatusResponse(BaseModel):
    """Schema for VPN connection status."""
    is_connected: bool
    server_endpoint: Optional[str] = None
    last_handshake: Optional[datetime] = None
    bytes_sent: Optional[int] = None
    bytes_received: Optional[int] = None


class VPNClientUpdate(BaseModel):
    """Schema for updating VPN client."""
    device_name: Optional[str] = None
    is_active: Optional[bool] = None


class FritzBoxConfigUpload(BaseModel):
    """Schema for uploading Fritz!Box WireGuard config."""
    config_content: str = Field(..., description="Raw .conf file content")


class FritzBoxConfigResponse(BaseModel):
    """Schema for Fritz!Box config response."""
    id: int
    address: str
    dns_servers: str
    endpoint: str
    allowed_ips: str
    persistent_keepalive: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    config_base64: str = Field(..., description="Base64 encoded config for QR codes")
    
    class Config:
        from_attributes = True


class FritzBoxConfigSummary(BaseModel):
    """Summary info (ohne sensitive Daten)."""
    id: int
    endpoint: str
    dns_servers: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
