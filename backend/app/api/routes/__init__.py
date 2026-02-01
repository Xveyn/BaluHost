from fastapi import APIRouter

from app.api.routes import (
    auth, files, logging, system, users, upload_progress, shares, backup, sync,
    sync_advanced, mobile, vpn, health, admin_db, sync_compat, rate_limit_config,
    vcl, server_profiles, vpn_profiles, metrics, tapo, energy, devices, monitoring,
    power, power_presets, fans, service_status, schedulers, plugins, benchmark,
    notifications, updates
)

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
api_router.include_router(vcl.router, prefix="/vcl", tags=["vcl"])
api_router.include_router(sync.router)
api_router.include_router(sync_advanced.router)
api_router.include_router(sync_compat.router)
api_router.include_router(mobile.router)
api_router.include_router(devices.router)
api_router.include_router(vpn.router)
api_router.include_router(admin_db.router)
api_router.include_router(rate_limit_config.router, prefix="/admin", tags=["admin"])
api_router.include_router(server_profiles.router)
api_router.include_router(vpn_profiles.router)
api_router.include_router(metrics.router, tags=["monitoring"])
api_router.include_router(tapo.router, prefix="/tapo", tags=["power-monitoring"])
api_router.include_router(energy.router, prefix="/energy", tags=["energy-monitoring"])
api_router.include_router(monitoring.router, tags=["system-monitoring"])
api_router.include_router(power.router, tags=["power-management"])
api_router.include_router(power_presets.router, tags=["power-presets"])
api_router.include_router(fans.router, prefix="/fans", tags=["fan-control"])
api_router.include_router(service_status.router, tags=["admin"])
api_router.include_router(schedulers.router, prefix="/schedulers", tags=["schedulers"])
api_router.include_router(plugins.router, tags=["plugins"])
api_router.include_router(benchmark.router, tags=["benchmark"])
api_router.include_router(notifications.router, tags=["notifications"])
api_router.include_router(updates.router, tags=["updates"])

__all__ = ["api_router"]
