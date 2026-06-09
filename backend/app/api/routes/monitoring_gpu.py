"""GPU monitoring API routes.

Kept separate from monitoring.py because that file is already large.
Registered under the same /api/monitoring prefix in routes/__init__.py.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.schemas.monitoring import (
    CurrentGpuResponse,
    DataSource,
    GpuDeviceInfo,
    GpuHistoryResponse,
    TimeRangeEnum,
)
from app.services.monitoring.orchestrator import get_monitoring_orchestrator

router = APIRouter(prefix="/monitoring", tags=["system-monitoring"])


def _parse_time_range(time_range: TimeRangeEnum) -> timedelta:
    mapping = {
        TimeRangeEnum.TEN_MINUTES: timedelta(minutes=10),
        TimeRangeEnum.ONE_HOUR: timedelta(hours=1),
        TimeRangeEnum.TWENTY_FOUR_HOURS: timedelta(hours=24),
        TimeRangeEnum.SEVEN_DAYS: timedelta(days=7),
    }
    return mapping.get(time_range, timedelta(hours=1))


@router.get("/gpu/info", response_model=GpuDeviceInfo)
@user_limiter.limit(get_limit("system_monitor"))
async def get_gpu_info(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_user),
):
    """Get dedicated GPU device metadata. 404 when no GPU is detected."""
    orch = get_monitoring_orchestrator()
    if not orch.gpu_collector.detected:
        raise HTTPException(status_code=404, detail="No dedicated GPU detected")
    try:
        return orch.gpu_collector.backend.device_info()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GPU info unavailable: {exc}")


@router.get("/gpu/current", response_model=CurrentGpuResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_gpu_current(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current GPU sample.

    - 404 when no GPU is detected.
    - 503 when detected but the memory buffer is empty and no DB history exists yet.
    """
    orch = get_monitoring_orchestrator()
    if not orch.gpu_collector.detected:
        raise HTTPException(status_code=404, detail="No dedicated GPU detected")

    sample = orch.get_gpu_current_with_db_fallback(db)
    if sample is None:
        raise HTTPException(status_code=503, detail="No GPU data available yet")
    return sample


@router.get("/gpu/history", response_model=GpuHistoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_gpu_history(
    request: Request,
    response: Response,
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    """Get GPU history with memory/database selection matching /cpu/history."""
    orch = get_monitoring_orchestrator()
    if not orch.gpu_collector.detected:
        raise HTTPException(status_code=404, detail="No dedicated GPU detected")

    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        samples = orch.get_gpu_history(limit)
        source_str = "memory"
        if not samples:
            start = datetime.now(timezone.utc) - duration
            samples = orch.gpu_collector.get_history_db(db, start=start, limit=limit)
            source_str = "database (fallback)"
    else:
        start = datetime.now(timezone.utc) - duration
        samples = orch.gpu_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        if not samples:
            samples = orch.get_gpu_history(limit)
            source_str = "memory (fallback)"

    return GpuHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )
