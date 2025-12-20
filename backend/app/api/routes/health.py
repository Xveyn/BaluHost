"""Health check endpoint for server connectivity testing."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "1.0.0"


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Simple health check endpoint.
    
    Used by mobile apps to verify server connectivity.
    Returns immediately with minimal processing.
    """
    return HealthResponse(status="ok", version="1.0.0")


@router.get("/ping", response_model=HealthResponse)
async def ping():
    """
    Alias for health check.
    Ultra-lightweight endpoint for connectivity testing.
    """
    return HealthResponse(status="ok")
