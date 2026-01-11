"""Pydantic schemas for Server Profile requests and responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ServerProfileBase(BaseModel):
    """Base schema for server profile fields."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Profile name")
    ssh_host: str = Field(..., min_length=1, max_length=255, description="SSH hostname or IP")
    ssh_port: int = Field(default=22, ge=1, le=65535, description="SSH port")
    ssh_username: str = Field(..., min_length=1, max_length=255, description="SSH username")
    vpn_profile_id: Optional[int] = Field(None, description="Optional VPN profile ID")
    power_on_command: Optional[str] = Field(None, max_length=500, description="Command to start server")
    
    @field_validator("ssh_host")
    @classmethod
    def validate_ssh_host(cls, v: str) -> str:
        """Validate SSH host is not empty."""
        if not v or not v.strip():
            raise ValueError("SSH host cannot be empty")
        return v.strip()
    
    @field_validator("ssh_username")
    @classmethod
    def validate_ssh_username(cls, v: str) -> str:
        """Validate SSH username is not empty."""
        if not v or not v.strip():
            raise ValueError("SSH username cannot be empty")
        return v.strip()


class ServerProfileCreate(ServerProfileBase):
    """Schema for creating a server profile."""
    
    ssh_private_key: str = Field(..., description="SSH private key (will be encrypted)")
    
    @field_validator("ssh_private_key")
    @classmethod
    def validate_private_key(cls, v: str) -> str:
        """Validate SSH private key format."""
        if not v or not v.strip():
            raise ValueError("SSH private key cannot be empty")
        if "PRIVATE KEY" not in v.upper():
            raise ValueError("Invalid SSH private key format - must contain 'PRIVATE KEY'")
        return v.strip()


class ServerProfileUpdate(BaseModel):
    """Schema for updating a server profile."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    ssh_host: Optional[str] = Field(None, min_length=1, max_length=255)
    ssh_port: Optional[int] = Field(None, ge=1, le=65535)
    ssh_username: Optional[str] = Field(None, min_length=1, max_length=255)
    ssh_private_key: Optional[str] = Field(None, description="Updated SSH private key (optional)")
    vpn_profile_id: Optional[int] = None
    power_on_command: Optional[str] = Field(None, max_length=500)


class ServerProfileResponse(ServerProfileBase):
    """Schema for server profile response."""
    
    id: int
    user_id: int
    created_at: datetime
    last_used: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ServerProfileList(BaseModel):
    """Schema for listing server profiles."""
    
    id: int
    user_id: int
    name: str
    ssh_host: str
    ssh_port: int
    vpn_profile_id: Optional[int] = None
    created_at: datetime
    last_used: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ServerStartRequest(BaseModel):
    """Request to start a remote server."""
    
    profile_id: int = Field(..., description="Server profile ID")


class ServerStartResponse(BaseModel):
    """Response from starting a remote server."""
    
    profile_id: int
    status: str = Field(..., description="Status: starting, started, failed")
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SSHConnectionTest(BaseModel):
    """Response from SSH connection test."""
    
    ssh_reachable: bool
    local_network: bool
    needs_vpn: bool
    error_message: Optional[str] = None
