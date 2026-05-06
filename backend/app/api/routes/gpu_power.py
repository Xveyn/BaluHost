"""GPU power management API routes."""
# NB: do not add ``from __future__ import annotations`` here. Combined with
# Pydantic v2 + FastAPI's body detection through slowapi's ``@limiter.limit``
# wrapper, deferred annotations turn body params into ForwardRefs that
# FastAPI can no longer resolve as Pydantic models — the request body would
# be misinterpreted as a query parameter and every PUT/POST returns 422.
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api import deps
from app.core.rate_limiter import limiter, get_limit
from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerHistoryResponse,
    GpuPowerStatus,
    RegisterGpuDemandRequest,
)
from app.schemas.user import UserPublic
from app.services.power.gpu.manager import get_gpu_power_manager

router = APIRouter(prefix="/gpu-power", tags=["gpu-power-management"])


@router.get("/status", response_model=GpuPowerStatus)
@limiter.limit(get_limit("gpu_power"))
async def get_status(
    request: Request,
    response: Response,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerStatus:
    return await get_gpu_power_manager().get_status()


@router.get("/config", response_model=GpuPowerConfig)
@limiter.limit(get_limit("gpu_power"))
async def get_config(
    request: Request,
    response: Response,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerConfig:
    return get_gpu_power_manager().get_config()


@router.put("/config", response_model=GpuPowerConfig)
@limiter.limit(get_limit("gpu_power"))
async def put_config(
    request: Request,
    response: Response,
    body: GpuPowerConfig,
    _admin: UserPublic = Depends(deps.get_current_admin),
) -> GpuPowerConfig:
    mgr = get_gpu_power_manager()
    # Validate clocks against capabilities
    caps = mgr.get_capabilities()
    err = _validate_against_capabilities(body, caps)
    if err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)
    ok, err = await mgr.set_config(body)
    if not ok:
        raise HTTPException(status_code=500, detail=err or "Failed to save config")
    return mgr.get_config()


def _validate_against_capabilities(config: GpuPowerConfig, caps: GpuPowerCapabilities) -> str | None:
    """Reject NVIDIA clocks/power outside hardware-reported range."""
    if caps.vendor != "nvidia":
        return None
    for state_name, sc in [
        ("nvidia_active", config.nvidia_active),
        ("nvidia_standby", config.nvidia_standby),
        ("nvidia_deep_idle", config.nvidia_deep_idle),
    ]:
        if sc.min_clock_mhz is not None and caps.nvidia_min_clock_mhz is not None:
            if sc.min_clock_mhz < caps.nvidia_min_clock_mhz:
                return f"{state_name}.min_clock_mhz < hardware min ({caps.nvidia_min_clock_mhz})"
        if sc.max_clock_mhz is not None and caps.nvidia_max_clock_mhz is not None:
            if sc.max_clock_mhz > caps.nvidia_max_clock_mhz:
                return f"{state_name}.max_clock_mhz > hardware max ({caps.nvidia_max_clock_mhz})"
        if sc.power_limit_watts is not None and caps.nvidia_max_power_watts is not None:
            if sc.power_limit_watts > caps.nvidia_max_power_watts:
                return f"{state_name}.power_limit_watts > hardware max ({caps.nvidia_max_power_watts})"
        if sc.power_limit_watts is not None and caps.nvidia_min_power_watts is not None:
            if sc.power_limit_watts < caps.nvidia_min_power_watts:
                return f"{state_name}.power_limit_watts < hardware min ({caps.nvidia_min_power_watts})"
    return None


@router.get("/capabilities", response_model=GpuPowerCapabilities)
@limiter.limit(get_limit("gpu_power"))
async def get_capabilities(
    request: Request,
    response: Response,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerCapabilities:
    return get_gpu_power_manager().get_capabilities()


@router.post("/demand")
@limiter.limit(get_limit("gpu_power"))
async def register_demand(
    request: Request,
    response: Response,
    body: RegisterGpuDemandRequest,
    _user: UserPublic = Depends(deps.get_current_user),
) -> dict:
    src = await get_gpu_power_manager().register_demand(
        source=body.source,
        timeout_seconds=body.timeout_seconds,
        description=body.description,
    )
    return {"source": src, "success": True}


@router.delete("/demand/{source}")
@limiter.limit(get_limit("gpu_power"))
async def unregister_demand(
    request: Request,
    response: Response,
    source: str,
    _user: UserPublic = Depends(deps.get_current_user),
) -> dict:
    removed = await get_gpu_power_manager().unregister_demand(source)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Demand '{source}' not found")
    return {"source": source, "removed": True}


@router.get("/history", response_model=GpuPowerHistoryResponse)
@limiter.limit(get_limit("gpu_power"))
async def get_history(
    request: Request,
    response: Response,
    limit: int = 100,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerHistoryResponse:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be 1..1000")
    entries, total = get_gpu_power_manager().get_history(limit=limit)
    return GpuPowerHistoryResponse(entries=entries, total=total)
