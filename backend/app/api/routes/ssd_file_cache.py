"""SSD File Cache API Routes (per-array)."""
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.schemas.ssd_file_cache import (
    SSDCacheStats,
    SSDCacheConfigResponse,
    SSDCacheConfigUpdate,
    SSDCacheEntryResponse,
    SSDCacheEntriesResponse,
    EvictionResult,
    CacheHealthResponse,
)
from app.models.ssd_file_cache import SSDCacheEntry, SSDCacheConfig
from app.services.cache.ssd_file_cache import SSDFileCacheService
from app.services.cache.eviction import EvictionManager
from app.services.audit.logger_db import get_audit_logger_db

router = APIRouter()


def _resolve_disk_usage(cache_path: str) -> tuple:
    """Check SSD mount by walking up to nearest existing ancestor.

    Returns (is_mounted, total, available, used_pct).
    Auto-creates cache dir if the mount is available.
    """
    cache_dir = Path(cache_path)
    # Walk up to find nearest existing ancestor (= the mount point)
    check_path = cache_dir
    while not check_path.exists() and check_path.parent != check_path:
        check_path = check_path.parent
    try:
        disk = shutil.disk_usage(str(check_path))
        # Mount exists — ensure cache dir is created
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)
        used_pct = ((disk.total - disk.free) / disk.total * 100) if disk.total > 0 else 0
        return True, disk.total, disk.free, used_pct
    except OSError:
        return False, 0, 0, 0


def _build_stats(config: SSDCacheConfig, db: Session) -> SSDCacheStats:
    """Build SSDCacheStats from a config row."""
    array_name = str(config.array_name)
    total_entries = (
        db.query(func.count(SSDCacheEntry.id))
        .filter(SSDCacheEntry.array_name == array_name)
        .scalar() or 0
    )
    valid_entries = (
        db.query(func.count(SSDCacheEntry.id))
        .filter(
            SSDCacheEntry.array_name == array_name,
            SSDCacheEntry.is_valid.is_(True),
        )
        .scalar() or 0
    )

    current = int(config.current_size_bytes)
    max_size = int(config.max_size_bytes)
    usage_pct = (current / max_size * 100) if max_size > 0 else 0.0

    hits = int(config.total_hits)
    misses = int(config.total_misses)
    total_reqs = hits + misses
    hit_rate = (hits / total_reqs * 100) if total_reqs > 0 else 0.0

    cache_path = str(config.cache_path)
    _is_mounted, ssd_total, ssd_available, _used_pct = _resolve_disk_usage(cache_path)

    return SSDCacheStats(
        array_name=array_name,
        is_enabled=bool(config.is_enabled),
        cache_path=cache_path,
        max_size_bytes=max_size,
        current_size_bytes=current,
        usage_percent=round(usage_pct, 1),
        total_entries=total_entries,
        valid_entries=valid_entries,
        total_hits=hits,
        total_misses=misses,
        hit_rate_percent=round(hit_rate, 1),
        total_bytes_served=int(config.total_bytes_served_from_cache),
        ssd_available_bytes=ssd_available,
        ssd_total_bytes=ssd_total,
    )


def _config_to_response(config: SSDCacheConfig) -> SSDCacheConfigResponse:
    """Convert ORM config to response schema."""
    return SSDCacheConfigResponse(
        array_name=str(config.array_name),
        is_enabled=bool(config.is_enabled),
        cache_path=str(config.cache_path),
        max_size_bytes=int(config.max_size_bytes),
        current_size_bytes=int(config.current_size_bytes),
        eviction_policy=str(config.eviction_policy),
        min_file_size_bytes=int(config.min_file_size_bytes),
        max_file_size_bytes=int(config.max_file_size_bytes),
        sequential_cutoff_bytes=int(config.sequential_cutoff_bytes),
        total_hits=int(config.total_hits),
        total_misses=int(config.total_misses),
        total_bytes_served_from_cache=int(config.total_bytes_served_from_cache),
        updated_at=config.updated_at,
    )


# ============================================================================
# OVERVIEW (all arrays)
# ============================================================================

@router.get("/cache/overview", response_model=List[SSDCacheStats])
@user_limiter.limit(get_limit("file_list"))
async def get_cache_overview(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> List[SSDCacheStats]:
    """Get SSD cache stats for all configured arrays."""
    configs = SSDFileCacheService.get_all_configs(db)
    return [_build_stats(cfg, db) for cfg in configs]


# ============================================================================
# PER-ARRAY ENDPOINTS
# ============================================================================

@router.get("/cache/{array_name}/stats", response_model=SSDCacheStats)
@user_limiter.limit(get_limit("file_list"))
async def get_cache_stats(
    array_name: str,
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> SSDCacheStats:
    """Get SSD cache statistics for a specific array."""
    service = SSDFileCacheService(db, array_name)
    config = service.get_config()
    return _build_stats(config, db)


@router.get("/cache/{array_name}/config", response_model=SSDCacheConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_cache_config(
    array_name: str,
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> SSDCacheConfigResponse:
    """Get full SSD cache configuration for an array (Admin only)."""
    service = SSDFileCacheService(db, array_name)
    config = service.get_config()
    return _config_to_response(config)


@router.put("/cache/{array_name}/config", response_model=SSDCacheConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_cache_config(
    array_name: str,
    request: Request,
    response: Response,
    config_update: SSDCacheConfigUpdate,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> SSDCacheConfigResponse:
    """Update SSD cache configuration for an array (Admin only)."""
    from sqlalchemy import update as sql_update

    update_values = config_update.model_dump(exclude_unset=True)
    if not update_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    service = SSDFileCacheService(db, array_name)
    config = service.get_config()

    # If enabling, verify cache path is writable
    if update_values.get("is_enabled"):
        cache_path = update_values.get("cache_path", str(config.cache_path))
        try:
            Path(cache_path).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cache path not writable: {e}",
            )

    db.execute(
        sql_update(SSDCacheConfig)
        .where(SSDCacheConfig.array_name == array_name)
        .values(**update_values)
    )
    db.commit()

    audit = get_audit_logger_db()
    audit.log_system_config_change(
        action="update_ssd_cache_config",
        user=admin.username,
        config_key=f"ssd_file_cache.{array_name}",
        new_value=update_values,
        db=db,
    )

    # Return updated config
    config = service.get_config()
    return _config_to_response(config)


@router.get("/cache/{array_name}/entries", response_model=SSDCacheEntriesResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_cache_entries(
    array_name: str,
    request: Request,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    valid_only: bool = False,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> SSDCacheEntriesResponse:
    """List cached file entries for an array (Admin only)."""
    query = db.query(SSDCacheEntry).filter(SSDCacheEntry.array_name == array_name)
    if valid_only:
        query = query.filter(SSDCacheEntry.is_valid.is_(True))

    total = query.count()
    entries = (
        query.order_by(SSDCacheEntry.last_accessed.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return SSDCacheEntriesResponse(
        entries=[
            SSDCacheEntryResponse(
                id=int(e.id),
                array_name=str(e.array_name),
                source_path=str(e.source_path),
                file_size_bytes=int(e.file_size_bytes),
                access_count=int(e.access_count),
                last_accessed=e.last_accessed,
                first_cached=e.first_cached,
                is_valid=bool(e.is_valid),
            )
            for e in entries
        ],
        total=total,
    )


@router.delete("/cache/{array_name}/entries/{entry_id}")
@user_limiter.limit(get_limit("admin_operations"))
async def evict_cache_entry(
    array_name: str,
    entry_id: int,
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Manually evict a specific cache entry (Admin only)."""
    entry = (
        db.query(SSDCacheEntry)
        .filter(
            SSDCacheEntry.id == entry_id,
            SSDCacheEntry.array_name == array_name,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Cache entry not found")

    service = SSDFileCacheService(db, array_name)
    freed = service.delete_cache_file(entry)
    db.commit()

    return {"freed_bytes": freed, "source_path": str(entry.source_path)}


@router.post("/cache/{array_name}/evict", response_model=EvictionResult)
@user_limiter.limit(get_limit("admin_operations"))
async def trigger_eviction(
    array_name: str,
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> EvictionResult:
    """Trigger manual eviction cycle for an array (Admin only)."""
    service = SSDFileCacheService(db, array_name)
    eviction = EvictionManager(db, array_name)
    result = eviction.run_eviction(service)
    db.commit()

    audit = get_audit_logger_db()
    audit.log_system_event(
        action="ssd_cache_eviction",
        user=admin.username,
        details={"array": array_name, **result},
        db=db,
    )

    return EvictionResult(**result)


@router.post("/cache/{array_name}/clear")
@user_limiter.limit(get_limit("admin_operations"))
async def clear_cache(
    array_name: str,
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Clear entire SSD cache for an array (Admin only)."""
    service = SSDFileCacheService(db, array_name)
    entries = (
        db.query(SSDCacheEntry)
        .filter(SSDCacheEntry.array_name == array_name)
        .all()
    )

    freed = 0
    count = 0
    for entry in entries:
        freed += service.delete_cache_file(entry)
        count += 1
    db.commit()

    audit = get_audit_logger_db()
    audit.log_system_config_change(
        action="clear_ssd_cache",
        user=admin.username,
        config_key=f"ssd_file_cache.{array_name}",
        new_value={"freed_bytes": freed, "deleted_count": count},
        db=db,
    )

    return {"freed_bytes": freed, "deleted_count": count}


@router.get("/cache/{array_name}/health", response_model=CacheHealthResponse)
@user_limiter.limit(get_limit("file_list"))
async def get_cache_health(
    array_name: str,
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> CacheHealthResponse:
    """Check SSD mount and cache health for an array."""
    service = SSDFileCacheService(db, array_name)
    config = service.get_config()
    cache_path = str(config.cache_path)

    is_mounted, ssd_total, ssd_available, ssd_used_pct = _resolve_disk_usage(cache_path)

    return CacheHealthResponse(
        array_name=array_name,
        is_mounted=is_mounted,
        ssd_total_bytes=ssd_total,
        ssd_available_bytes=ssd_available,
        ssd_used_percent=round(ssd_used_pct, 1),
        cache_dir_exists=Path(cache_path).exists(),
    )
