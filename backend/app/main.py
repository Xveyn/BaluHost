from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from pathlib import Path

from app.compat import apply_asyncio_patches

apply_asyncio_patches()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.api.routes import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.services.users import ensure_admin_user
from app.services import disk_monitor, jobs, seed, telemetry, sync_background
from app.services.network_discovery import NetworkDiscoveryService
from app.services.firebase_service import FirebaseService
from app.services.notification_scheduler import NotificationScheduler
from app.middleware.device_tracking import DeviceTrackingMiddleware
from app.middleware.local_only import LocalOnlyMiddleware

logger = logging.getLogger(__name__)

# Network discovery service instance
_discovery_service = None
# APScheduler instance for notifications
_notification_scheduler = None

@asynccontextmanager
async def _lifespan(_: FastAPI):  # pragma: no cover - startup/shutdown hook
    global _discovery_service
    # Allow tests to skip full app initialization by setting SKIP_APP_INIT=1
    import os
    skip_init = os.environ.get('SKIP_APP_INIT') == '1'
    if skip_init:
        logger.info('SKIP_APP_INIT set; skipping full app startup (tests)')
        # Do not perform the normal initialization steps, but still enter
        # the lifespan so the `finally` block runs to perform cleanup.
        try:
            yield
        finally:
            # Proceed to cleanup below; avoid starting background services.
            pass
        return

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
    
    # Initialize Firebase (optional, warnings if not configured)
    FirebaseService.initialize()
    
    # Start notification scheduler (only if Firebase is available)
    if FirebaseService.is_available():
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            global _notification_scheduler
            _notification_scheduler = BackgroundScheduler()
            
            # Run every hour to check for expiring devices
            _notification_scheduler.add_job(
                func=NotificationScheduler.run_periodic_check,
                trigger="interval",
                hours=1,
                id="device_expiration_check",
                name="Check and send device expiration warnings",
                replace_existing=True
            )
            
            _notification_scheduler.start()
            logger.info("✅ Notification scheduler started (running every hour)")
        except Exception as e:
            logger.warning(f"Notification scheduler could not start: {e}")
    else:
        logger.info("⏭️  Notification scheduler skipped (Firebase not configured)")
    
    try:
        yield
    finally:
        # Stop background services if they were started
        try:
            if not skip_init:
                await jobs.stop_health_monitor()
                await telemetry.stop_telemetry_monitor()
                disk_monitor.stop_monitoring()
                await sync_background.stop_sync_scheduler()
                logger.info("Sync scheduler stopped")
        except Exception:
            logger.debug("Error while stopping background services")

        # Always attempt to shutdown the upload progress manager to cancel any
        # pending cleanup tasks created during tests or runtime.
        try:
            from app.services.upload_progress import get_upload_progress_manager
            mgr = get_upload_progress_manager()
            await mgr.shutdown()
        except Exception:
            logger.debug("Upload progress manager shutdown skipped or failed")
        
        # Stop network discovery
        if _discovery_service:
            _discovery_service.stop()
        
        # Stop notification scheduler
        if _notification_scheduler:
            _notification_scheduler.shutdown()
            logger.info("Notification scheduler stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=_lifespan,
        docs_url=None,  # Disable default docs
        redoc_url=None,  # Disable default redoc
    )
    
    # Add rate limiting state and exception handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Add local-only enforcement middleware (Option B security)
    if settings.enforce_local_only:
        app.add_middleware(
            LocalOnlyMiddleware,
            enforce=True,
            protected_prefixes=[
                "/api/server-profiles",
                "/api/auth/login",
                "/api/auth/register",
            ]
        )

    # Add device tracking middleware (updates last_seen for mobile devices)
    app.add_middleware(DeviceTrackingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    
    # Mount static files for avatars
    avatars_path = Path("storage/avatars")
    avatars_path.mkdir(parents=True, exist_ok=True)
    app.mount("/avatars", StaticFiles(directory=str(avatars_path)), name="avatars")
    
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
