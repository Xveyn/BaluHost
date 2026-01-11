"""Pydantic schemas for VPN Profile requests and responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.vpn_profile import VPNType


class VPNProfileBase(BaseModel):
    """Base schema for VPN profile fields."""
    
    name: str = Field(..., min_length=1, max_length=255, description="VPN profile name")
    vpn_type: VPNType = Field(..., description="VPN type: openvpn, wireguard, custom")
    auto_connect: bool = Field(default=False, description="Auto-connect on startup")
    description: Optional[str] = Field(None, max_length=500, description="Profile description")
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate VPN profile name."""
        if not v or not v.strip():
            raise ValueError("VPN profile name cannot be empty")
        return v.strip()


class VPNProfileCreate(VPNProfileBase):
    """Schema for creating a VPN profile."""
    
    config_file: str = Field(..., description="VPN config file content (.ovpn or .conf)")
    certificate: Optional[str] = Field(None, description="Client certificate (optional)")
    private_key: Optional[str] = Field(None, description="Private key (optional)")
    
    @field_validator("config_file")
    @classmethod
    def validate_config(cls, v: str) -> str:
        """Validate VPN config file has content."""
        if not v or not v.strip():
            raise ValueError("VPN config file cannot be empty")
        return v.strip()


class VPNProfileUpdate(BaseModel):
    """Schema for updating a VPN profile."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    auto_connect: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=500)
    config_file: Optional[str] = None
    certificate: Optional[str] = None
    private_key: Optional[str] = None


class VPNProfileResponse(VPNProfileBase):
    """Schema for VPN profile response (without sensitive data)."""
    
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class VPNProfileList(BaseModel):
    """Schema for listing VPN profiles."""
    
    id: int
    user_id: int
    name: str
    vpn_type: VPNType
    auto_connect: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class VPNConnectionTest(BaseModel):
    """Response from VPN connection test."""
    
    profile_id: int
    connected: bool
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
