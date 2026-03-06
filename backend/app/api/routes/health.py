"""Health check endpoint for server connectivity testing."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from app.core.config import settings
from app.core.rate_limiter import limiter, get_limit
from app import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = __version__
    api_version: str = settings.api_version
    min_api_version: str = settings.api_min_version


@router.get("/health", response_model=HealthResponse)
@limiter.limit(get_limit("system_monitor"))
async def health_check(request: Request, response: Response):
    """
    Simple health check endpoint.

    Used by mobile apps to verify server connectivity.
    Returns immediately with minimal processing.
    """
    return HealthResponse()


@router.get("/ping", response_model=HealthResponse)
@limiter.limit(get_limit("system_monitor"))
async def ping(request: Request, response: Response):
    """
    Alias for health check.
    Ultra-lightweight endpoint for connectivity testing.
    """
    return HealthResponse()
