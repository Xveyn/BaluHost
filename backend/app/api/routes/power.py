"""
Power Management API Routes.

Provides endpoints for CPU power profile management and monitoring.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.api import deps
from app.core.config import settings

logger = logging.getLogger(__name__)

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False)


async def _get_admin_or_service_token(
    request: Request,
    token: Optional[str] = Depends(_oauth2_scheme),
) -> None:
    """
    Accept either a valid admin JWT or the scheduler service token.

    The service token is sent as ``X-Service-Token`` header by the
    scheduler worker process.  This avoids having to create a fake
    user session for internal IPC.
    """
    # 1. Check X-Service-Token header
    service_token = request.headers.get("X-Service-Token")
    if service_token and service_token == settings.scheduler_service_token:
        return  # Service token valid

    # 2. Fall back to normal admin JWT auth
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    # Delegate to the standard admin dependency (re-uses get_current_admin logic)
    from app.services import auth as auth_service, users as user_service
    from app.core.database import SessionLocal
    try:
        payload = auth_service.decode_token(token)
    except auth_service.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    db = SessionLocal()
    try:
        user = user_service.get_user(payload.sub, db=db)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        user_pub = user_service.serialize_user(user)
        if user_pub.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    finally:
        db.close()
from app.schemas.power import (
    AutoScalingConfig,
    AutoScalingConfigResponse,
    DynamicModeConfig,
    DynamicModeConfigResponse,
    DynamicModeUpdateRequest,
    PowerDemandInfo,
    PowerHistoryResponse,
    PowerProfile,
    PowerProfileConfig,
    PowerProfilesResponse,
    PowerStatusResponse,
    RegisterDemandRequest,
    RegisterDemandResponse,
    ServiceIntensityResponse,
    SetProfileRequest,
    SetProfileResponse,
    SwitchBackendRequest,
    SwitchBackendResponse,
    UnregisterDemandRequest,
    UnregisterDemandResponse,
)
from app.schemas.user import UserPublic
from app.services.power_manager import get_power_manager

router = APIRouter(prefix="/power", tags=["power-management"])


@router.get("/status", response_model=PowerStatusResponse)
async def get_power_status(
    _: UserPublic = Depends(deps.get_current_user)
) -> PowerStatusResponse:
    """
    Get current power management status.

    Returns the active power profile, current CPU frequency,
    active demands, and auto-scaling state.
    """
    manager = get_power_manager()
    return await manager.get_power_status()


@router.get("/profiles", response_model=PowerProfilesResponse)
async def get_power_profiles(
    _: UserPublic = Depends(deps.get_current_user)
) -> PowerProfilesResponse:
    """
    Get all available power profiles.

    Returns configuration details for each profile including
    governor, EPP, and frequency limits.
    """
    manager = get_power_manager()
    profiles = manager.get_profiles()
    status = await manager.get_power_status()

    return PowerProfilesResponse(
        profiles=list(profiles.values()),
        current_profile=status.current_profile
    )


@router.post("/profile", response_model=SetProfileResponse)
async def set_power_profile(
    request: SetProfileRequest,
    user: UserPublic = Depends(deps.get_current_admin)
) -> SetProfileResponse:
    """
    Manually set a power profile (admin only).

    This overrides automatic scaling until the duration expires
    or another profile is set manually.
    """
    manager = get_power_manager()
    status_before = await manager.get_power_status()

    reason = request.reason or f"Manual override by {user.username}"
    success, error_msg = await manager.apply_profile(
        profile=request.profile,
        reason=reason,
        duration_seconds=request.duration_seconds
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg or "Failed to apply power profile"
        )

    return SetProfileResponse(
        success=True,
        message=f"Profile changed to {request.profile.value}",
        previous_profile=status_before.current_profile,
        new_profile=request.profile,
        applied_at=datetime.utcnow()
    )


@router.get("/demands", response_model=list[PowerDemandInfo])
async def get_power_demands(
    _: UserPublic = Depends(deps.get_current_user)
) -> list[PowerDemandInfo]:
    """
    Get all active power demands.

    Returns the list of sources that have registered power
    requirements, along with their levels and expiration times.
    """
    manager = get_power_manager()
    return manager.get_active_demands()


@router.post("/demands", response_model=RegisterDemandResponse)
async def register_power_demand(
    request: RegisterDemandRequest,
    _auth: None = Depends(_get_admin_or_service_token),
) -> RegisterDemandResponse:
    """
    Register a power demand programmatically (admin or service token).

    Use this for custom integrations that need to request
    specific power levels for their operations.
    """
    manager = get_power_manager()

    demand_id = await manager.register_demand(
        source=request.source,
        level=request.level,
        timeout_seconds=request.timeout_seconds,
        description=request.description
    )

    status_after = await manager.get_power_status()

    return RegisterDemandResponse(
        success=True,
        message=f"Demand registered: {request.source} -> {request.level.value}",
        demand_id=demand_id,
        resulting_profile=status_after.current_profile
    )


@router.delete("/demands", response_model=UnregisterDemandResponse)
async def unregister_power_demand(
    request: UnregisterDemandRequest,
    _auth: None = Depends(_get_admin_or_service_token),
) -> UnregisterDemandResponse:
    """
    Unregister a power demand (admin or service token).

    Removes a previously registered demand, potentially allowing
    the system to scale down to a lower power profile.
    """
    manager = get_power_manager()

    success = await manager.unregister_demand(request.source)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demand not found: {request.source}"
        )

    status_after = await manager.get_power_status()

    return UnregisterDemandResponse(
        success=True,
        message=f"Demand unregistered: {request.source}",
        resulting_profile=status_after.current_profile
    )


@router.get("/intensities", response_model=ServiceIntensityResponse)
async def get_service_intensities(
    _: UserPublic = Depends(deps.get_current_user)
) -> ServiceIntensityResponse:
    """
    Get intensity information for all tracked services and processes.

    Returns a combined view of:
    - Services with active power demands (backup, RAID rebuild, etc.)
    - Tracked BaluHost processes with CPU/RAM metrics
    - Inferred intensity levels based on CPU usage

    Services are sorted by intensity level (highest first) to show
    the most demanding services at the top.
    """
    manager = get_power_manager()
    return await manager.get_service_intensities()


@router.get("/history", response_model=PowerHistoryResponse)
async def get_power_history(
    limit: int = 100,
    offset: int = 0,
    _: UserPublic = Depends(deps.get_current_user)
) -> PowerHistoryResponse:
    """
    Get power profile change history.

    Returns a paginated list of profile changes with timestamps
    and reasons for each change.
    """
    manager = get_power_manager()
    entries, total = manager.get_history(limit=limit, offset=offset)

    from_ts = entries[-1].timestamp if entries else None
    to_ts = entries[0].timestamp if entries else None

    return PowerHistoryResponse(
        entries=entries,
        total_entries=total,
        from_timestamp=from_ts,
        to_timestamp=to_ts
    )


@router.get("/auto-scaling", response_model=AutoScalingConfigResponse)
async def get_auto_scaling_config(
    _: UserPublic = Depends(deps.get_current_user)
) -> AutoScalingConfigResponse:
    """
    Get auto-scaling configuration.

    Returns the current auto-scaling settings including
    CPU thresholds and cooldown period.
    """
    manager = get_power_manager()

    # Get config from manager (in-memory state)
    config = manager.get_auto_scaling_config()

    # Try to get current CPU usage from telemetry
    cpu_usage = None
    try:
        from app.services import telemetry as telemetry_service
        history = telemetry_service.get_history()
        if history.cpu:
            cpu_usage = history.cpu[-1].usage
    except Exception:
        pass

    return AutoScalingConfigResponse(
        config=config,
        current_cpu_usage=cpu_usage
    )


@router.put("/auto-scaling", response_model=AutoScalingConfigResponse)
async def update_auto_scaling_config(
    config: AutoScalingConfig,
    user: UserPublic = Depends(deps.get_current_admin)
) -> AutoScalingConfigResponse:
    """
    Update auto-scaling configuration (admin only).

    Note: Changes are not persisted and will reset on restart.
    Use environment variables for permanent configuration.
    """
    manager = get_power_manager()
    manager.set_auto_scaling_config(config)

    return AutoScalingConfigResponse(
        config=config,
        current_cpu_usage=None
    )


@router.get("/dynamic-mode", response_model=DynamicModeConfigResponse)
async def get_dynamic_mode_config(
    _: UserPublic = Depends(deps.get_current_user)
) -> DynamicModeConfigResponse:
    """
    Get dynamic mode configuration.

    Returns the current dynamic mode settings including available
    governors and system frequency range.
    """
    manager = get_power_manager()
    return await manager.get_dynamic_mode_config()


@router.put("/dynamic-mode", response_model=DynamicModeConfigResponse)
async def update_dynamic_mode(
    request: DynamicModeUpdateRequest,
    user: UserPublic = Depends(deps.get_current_admin)
) -> DynamicModeConfigResponse:
    """
    Update dynamic mode configuration (admin only).

    Handles enable/disable and config changes in a single call.
    When enabling, validates governor availability and freq bounds.
    """
    manager = get_power_manager()

    # Get current config as base
    current = await manager.get_dynamic_mode_config()
    config = current.config

    # Apply partial updates
    if request.governor is not None:
        if request.governor not in current.available_governors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Governor '{request.governor}' not available. Available: {', '.join(current.available_governors)}"
            )
        config.governor = request.governor
    if request.min_freq_mhz is not None:
        config.min_freq_mhz = request.min_freq_mhz
    if request.max_freq_mhz is not None:
        config.max_freq_mhz = request.max_freq_mhz

    # Validate freq range
    if config.min_freq_mhz > config.max_freq_mhz:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_freq_mhz must be <= max_freq_mhz"
        )

    # Enable or disable
    if request.enabled is not None:
        if request.enabled:
            config.enabled = True
            success, error = await manager.enable_dynamic_mode(config)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error or "Failed to enable dynamic mode"
                )
        else:
            success, error = await manager.disable_dynamic_mode()
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error or "Failed to disable dynamic mode"
                )
    elif config.enabled:
        # Config update while already enabled - re-apply
        success, error = await manager.enable_dynamic_mode(config)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error or "Failed to update dynamic mode"
            )

    return await manager.get_dynamic_mode_config()


@router.post("/backend", response_model=SwitchBackendResponse)
async def switch_power_backend(
    request: SwitchBackendRequest,
    user: UserPublic = Depends(deps.get_current_admin)
) -> SwitchBackendResponse:
    """
    Switch between dev simulation and real Linux cpufreq backend (admin only).

    This allows testing real CPU frequency control even when running
    in dev mode. Requires Linux with cpufreq support and appropriate
    permissions (root or cpufreq group).
    """
    import logging
    logger = logging.getLogger(__name__)

    manager = get_power_manager()

    # Check if Linux backend is available when requesting it
    try:
        linux_available = manager.is_linux_backend_available()
        logger.info(f"Linux backend available: {linux_available}, requested: {request.use_linux_backend}")
    except Exception as e:
        logger.error(f"Error checking Linux backend availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking backend availability: {str(e)}"
        )

    if request.use_linux_backend and not linux_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Linux cpufreq backend not available. Check if running on Linux with cpufreq support."
        )

    try:
        success, previous, new = await manager.switch_backend(request.use_linux_backend)
        logger.info(f"Backend switch result: success={success}, {previous} -> {new}")
    except Exception as e:
        logger.error(f"Error switching backend: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error switching backend: {str(e)}"
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to switch power backend"
        )

    return SwitchBackendResponse(
        success=True,
        message=f"Switched from {previous} to {new} backend",
        is_using_linux_backend=(new == "Linux"),
        previous_backend=previous,
        new_backend=new
    )
