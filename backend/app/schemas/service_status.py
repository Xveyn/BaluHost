"""
Pydantic schemas for service status and admin debugging API.

Provides request/response models for:
- Background service status monitoring
- System dependency availability
- Application-level metrics
- Admin debug dashboard
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ServiceStateEnum(str, Enum):
    """Service runtime state."""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DISABLED = "disabled"


class ServiceStatusResponse(BaseModel):
    """Status information for a single background service."""
    name: str = Field(..., description="Service identifier (e.g., 'telemetry_monitor')")
    display_name: str = Field(..., description="Human-readable service name")
    state: ServiceStateEnum = Field(..., description="Current service state")
    started_at: Optional[datetime] = Field(None, description="When the service was started")
    uptime_seconds: Optional[float] = Field(None, description="Time since service started")
    sample_count: Optional[int] = Field(None, description="Number of samples/iterations processed")
    error_count: int = Field(0, description="Number of errors since start")
    last_error: Optional[str] = Field(None, description="Most recent error message")
    last_error_at: Optional[datetime] = Field(None, description="When the last error occurred")
    config_enabled: bool = Field(True, description="Whether service is enabled in settings")
    interval_seconds: Optional[float] = Field(None, description="Service polling interval")
    restartable: bool = Field(True, description="Whether service can be restarted via API")

    class Config:
        from_attributes = True


class DependencyStatusResponse(BaseModel):
    """Status of a system dependency/tool."""
    name: str = Field(..., description="Dependency name (e.g., 'smartctl')")
    available: bool = Field(..., description="Whether the dependency is available")
    path: Optional[str] = Field(None, description="Path to the executable if found")
    version: Optional[str] = Field(None, description="Version string if detectable")
    required_for: List[str] = Field(default_factory=list, description="Features that need this dependency")

    class Config:
        from_attributes = True


class DbPoolStatus(BaseModel):
    """Database connection pool status."""
    pool_size: int = Field(..., description="Maximum pool size")
    checked_in: int = Field(..., description="Connections available in pool")
    checked_out: int = Field(..., description="Connections currently in use")
    overflow: int = Field(..., description="Connections over pool size")

    class Config:
        from_attributes = True


class CacheStatsResponse(BaseModel):
    """Cache statistics for a specific cache."""
    name: str = Field(..., description="Cache identifier")
    hits: int = Field(0, description="Cache hit count")
    misses: int = Field(0, description="Cache miss count")
    size: int = Field(0, description="Current number of cached items")
    max_size: Optional[int] = Field(None, description="Maximum cache size")

    class Config:
        from_attributes = True


class ApplicationMetricsResponse(BaseModel):
    """Application-level metrics for debugging."""
    server_uptime_seconds: float = Field(..., description="Time since server started")
    error_count_4xx: int = Field(0, description="Total 4xx responses since start")
    error_count_5xx: int = Field(0, description="Total 5xx responses since start")
    active_tasks: int = Field(0, description="Number of active asyncio tasks")
    memory_bytes: int = Field(0, description="BaluHost process memory usage")
    memory_percent: float = Field(0.0, description="BaluHost process memory percentage")
    db_pool_status: Optional[DbPoolStatus] = Field(None, description="Database connection pool status")
    cache_stats: List[CacheStatsResponse] = Field(default_factory=list, description="Cache statistics")

    class Config:
        from_attributes = True


class AdminDebugResponse(BaseModel):
    """Combined debug snapshot for admin dashboard."""
    timestamp: datetime = Field(..., description="When this snapshot was taken")
    services: List[ServiceStatusResponse] = Field(default_factory=list, description="All service statuses")
    dependencies: List[DependencyStatusResponse] = Field(default_factory=list, description="System dependencies")
    metrics: ApplicationMetricsResponse = Field(..., description="Application metrics")

    class Config:
        from_attributes = True


class ServiceRestartRequest(BaseModel):
    """Request to restart a service."""
    force: bool = Field(False, description="Force restart even if service appears healthy")


class ServiceRestartResponse(BaseModel):
    """Response after attempting to restart a service."""
    success: bool = Field(..., description="Whether the restart succeeded")
    service_name: str = Field(..., description="Name of the service")
    previous_state: ServiceStateEnum = Field(..., description="State before restart")
    current_state: ServiceStateEnum = Field(..., description="State after restart")
    message: Optional[str] = Field(None, description="Additional information or error message")

    class Config:
        from_attributes = True


class ServiceStopRequest(BaseModel):
    """Request to stop a service."""
    force: bool = Field(False, description="Force stop even if service appears healthy")


class ServiceStopResponse(BaseModel):
    """Response after attempting to stop a service."""
    success: bool = Field(..., description="Whether the stop succeeded")
    service_name: str = Field(..., description="Name of the service")
    previous_state: ServiceStateEnum = Field(..., description="State before stop")
    current_state: ServiceStateEnum = Field(..., description="State after stop")
    message: Optional[str] = Field(None, description="Additional information or error message")

    class Config:
        from_attributes = True


class ServiceStartRequest(BaseModel):
    """Request to start a service."""
    force: bool = Field(False, description="Force start even if service appears running")


class ServiceStartResponse(BaseModel):
    """Response after attempting to start a service."""
    success: bool = Field(..., description="Whether the start succeeded")
    service_name: str = Field(..., description="Name of the service")
    previous_state: ServiceStateEnum = Field(..., description="State before start")
    current_state: ServiceStateEnum = Field(..., description="State after start")
    message: Optional[str] = Field(None, description="Additional information or error message")

    class Config:
        from_attributes = True
