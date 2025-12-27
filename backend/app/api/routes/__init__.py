from fastapi import APIRouter

from app.api.routes import auth, files, logging, system, users, upload_progress, shares, backup, sync, sync_advanced, mobile, vpn, health, admin_db, sync_compat

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])  # Health check endpoint (no prefix)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(upload_progress.router, prefix="/files", tags=["files"])
api_router.include_router(logging.router, prefix="/logging", tags=["logging"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(shares.router, prefix="/shares", tags=["shares"])
api_router.include_router(backup.router, prefix="/backups", tags=["backups"])
api_router.include_router(sync.router)
api_router.include_router(sync_advanced.router)
api_router.include_router(sync_compat.router)
api_router.include_router(mobile.router)
api_router.include_router(vpn.router)
api_router.include_router(admin_db.router)

__all__ = ["api_router"]
