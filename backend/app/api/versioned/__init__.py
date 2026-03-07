"""
Versioned API router factory.

Current API (v1) is served without a version prefix — URLs remain /api/{resource}.
When a breaking change is needed, add a v2/ subpackage with only the affected
endpoints and uncomment the v2 include below.
"""

from fastapi import APIRouter
from app.api.routes import api_router as v1_router


def create_versioned_router() -> APIRouter:
    """Create the root API router with version-aware structure."""
    root = APIRouter()
    # v1 = default, no prefix (backwards-compatible)
    root.include_router(v1_router)
    # When v2 is needed:
    # from app.api.versioned.v2 import v2_overrides
    # root.include_router(v2_overrides, prefix="/v2")
    return root
