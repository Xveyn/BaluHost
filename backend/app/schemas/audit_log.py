"""Audit log schemas for API responses."""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuditLogBase(BaseModel):
    """Base audit log schema."""
    event_type: str = Field(..., description="Type of event (FILE_ACCESS, SECURITY, etc.)")
    user: Optional[str] = Field(None, description="Username who performed the action")
    action: str = Field(..., description="Action performed")
    resource: Optional[str] = Field(None, description="Resource affected")
    success: bool = Field(True, description="Whether the operation succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class AuditLogCreate(AuditLogBase):
    """Schema for creating audit logs."""
    ip_address: Optional[str] = Field(None, description="IP address of requester")
    user_agent: Optional[str] = Field(None, description="User agent of requester")


class AuditLogPublic(AuditLogBase):
    """Public audit log schema for API responses."""
    id: int
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    model_config = {"from_attributes": True}


class AuditLogQuery(BaseModel):
    """Schema for querying audit logs."""
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of logs")
    page: int = Field(1, ge=1, description="Page number for pagination")
    page_size: int = Field(50, ge=1, le=100, description="Logs per page")
    event_type: Optional[str] = Field(None, description="Filter by event type")
    user: Optional[str] = Field(None, description="Filter by username")
    action: Optional[str] = Field(None, description="Filter by action")
    success: Optional[bool] = Field(None, description="Filter by success status")
    days: int = Field(7, ge=1, le=365, description="Days to look back")


class AuditLogResponse(BaseModel):
    """Response schema for audit log queries."""
    logs: list[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
