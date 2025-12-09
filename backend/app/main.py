from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from app.compat import apply_asyncio_patches

apply_asyncio_patches()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router
from app.core.config import settings
from app.core.database import init_db
from app.services.users import ensure_admin_user
from app.services import disk_monitor, jobs, seed, telemetry, sync_background
from app.services.network_discovery import NetworkDiscoveryService

logger = logging.getLogger(__name__)

# Network discovery service instance
_discovery_service = None

@asynccontextmanager
async def _lifespan(_: FastAPI):  # pragma: no cover - startup/shutdown hook
    global _discovery_service
    
    # Initialize database tables
    init_db()
    logger.info("Database initialized")
    
    ensure_admin_user(settings)
    logger.info("Admin user ensured with username '%s'", settings.admin_username)
    seed.seed_dev_data()
    await jobs.start_health_monitor()
    await telemetry.start_telemetry_monitor()
    disk_monitor.start_monitoring()
    await sync_background.start_sync_scheduler()
    logger.info("Sync scheduler started")
    
    # Start network discovery (mDNS/Bonjour)
    try:
        port = int(settings.api_port) if hasattr(settings, 'api_port') else 8000
        _discovery_service = NetworkDiscoveryService(port=port)
        _discovery_service.start()
    except Exception as e:
        logger.warning(f"Network discovery could not start: {e}")
    
    try:
        yield
    finally:
        await jobs.stop_health_monitor()
        await telemetry.stop_telemetry_monitor()
        disk_monitor.stop_monitoring()
        await sync_background.stop_sync_scheduler()
        logger.info("Sync scheduler stopped")
        
        # Stop network discovery
        if _discovery_service:
            _discovery_service.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=_lifespan,
        docs_url=None,  # Disable default docs
        redoc_url=None,  # Disable default redoc
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    
    # Include custom styled docs
    from app.api.docs import router as docs_router
    app.include_router(docs_router)

    return app


app = create_app()


def run(**kwargs: Any) -> None:  # pragma: no cover - convenience launcher
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
        **kwargs,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
