"""
Versioned API router factory.

Current API (v1) is served without a version prefix — URLs remain /api/{resource}.
When a breaking change is needed, add a v2/ subpackage with only the affected
endpoints and uncomment the v2 include below.
"""

from fastapi import APIRouter
from app.api.routes import api_router as v1_router


def create_versioned_router() -> APIRouter:
    """Create the root API router with version-aware structure.

    v1 is served without a version prefix, so it is returned directly rather
    than re-wrapped in a prefix-less parent router. Since FastAPI 0.137,
    ``include_router`` nests lazily and rejects an empty-prefix include whose
    leaf routes have empty paths (``@router.get("")``) with
    ``FastAPIError: Prefix and path cannot be both empty`` — which the prior
    ``root.include_router(v1_router)`` wrapper triggered at startup (#234).

    When v2 is introduced, mount v1 and v2 at the app level with explicit
    prefixes instead of wrapping v1 in a prefix-less router, e.g.::

        app.include_router(v1_router, prefix=settings.api_prefix)
        app.include_router(v2_overrides, prefix=f"{settings.api_prefix}/v2")
    """
    return v1_router
