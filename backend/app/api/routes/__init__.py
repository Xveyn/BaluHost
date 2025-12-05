from fastapi import APIRouter

from app.api.routes import auth, files, logging, system, users, upload_progress, shares, backup

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(upload_progress.router, prefix="/files", tags=["files"])
api_router.include_router(logging.router, prefix="/logging", tags=["logging"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(shares.router, prefix="/shares", tags=["shares"])
api_router.include_router(backup.router, prefix="/backups", tags=["backups"])

__all__ = ["api_router"]
