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
from app.services import disk_monitor, jobs, seed, telemetry

logger = logging.getLogger(__name__)
@asynccontextmanager
async def _lifespan(_: FastAPI):  # pragma: no cover - startup/shutdown hook
    # Initialize database tables
    init_db()
    logger.info("Database initialized")
    
    ensure_admin_user(settings)
    logger.info("Admin user ensured with username '%s'", settings.admin_username)
    seed.seed_dev_data()
    await jobs.start_health_monitor()
    await telemetry.start_telemetry_monitor()
    disk_monitor.start_monitoring()
    try:
        yield
    finally:
        await jobs.stop_health_monitor()
        await telemetry.stop_telemetry_monitor()
        disk_monitor.stop_monitoring()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

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
