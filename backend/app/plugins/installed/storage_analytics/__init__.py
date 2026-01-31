"""Storage Analytics Plugin for BaluHost.

Provides storage usage analytics and insights including:
- Per-user storage usage breakdown
- File type distribution
- Storage trends over time
- Top files by size
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.plugins.base import (
    BackgroundTaskSpec,
    PluginBase,
    PluginMetadata,
    PluginNavItem,
    PluginUIManifest,
)
from app.plugins.hooks import hookimpl


class StorageAnalyticsConfig(BaseModel):
    """Configuration for the storage analytics plugin."""

    scan_interval_hours: int = Field(
        default=6,
        description="Hours between storage scans",
        ge=1,
        le=168,
    )
    keep_history_days: int = Field(
        default=30,
        description="Days to keep historical data",
        ge=1,
        le=365,
    )
    track_file_types: bool = Field(
        default=True,
        description="Track file type distribution",
    )


class StorageStats(BaseModel):
    """Current storage statistics."""

    total_files: int
    total_size_bytes: int
    total_folders: int
    last_scan: Optional[datetime] = None


class UserStorageUsage(BaseModel):
    """Storage usage for a single user."""

    user_id: int
    username: str
    file_count: int
    total_size_bytes: int
    percentage: float


class FileTypeDistribution(BaseModel):
    """Distribution of file types."""

    extension: str
    count: int
    total_size_bytes: int
    percentage: float


# In-memory cache for demo purposes
# In production, this would be stored in the database
_storage_cache: Dict[str, Any] = {
    "stats": None,
    "user_usage": [],
    "file_types": [],
    "top_files": [],
    "last_scan": None,
}


def _perform_storage_scan() -> None:
    """Perform a storage scan and update cache.

    In a real implementation, this would scan the file system
    and aggregate storage statistics.
    """
    from app.core.config import settings

    # Simulated data for demonstration
    _storage_cache["stats"] = {
        "total_files": 1234,
        "total_size_bytes": 50 * 1024 * 1024 * 1024,  # 50 GB
        "total_folders": 89,
    }

    _storage_cache["user_usage"] = [
        {"user_id": 1, "username": "admin", "file_count": 500, "total_size_bytes": 20 * 1024 * 1024 * 1024, "percentage": 40.0},
        {"user_id": 2, "username": "user", "file_count": 734, "total_size_bytes": 30 * 1024 * 1024 * 1024, "percentage": 60.0},
    ]

    _storage_cache["file_types"] = [
        {"extension": ".jpg", "count": 450, "total_size_bytes": 5 * 1024 * 1024 * 1024, "percentage": 10.0},
        {"extension": ".mp4", "count": 50, "total_size_bytes": 25 * 1024 * 1024 * 1024, "percentage": 50.0},
        {"extension": ".pdf", "count": 200, "total_size_bytes": 2 * 1024 * 1024 * 1024, "percentage": 4.0},
        {"extension": ".docx", "count": 150, "total_size_bytes": 1 * 1024 * 1024 * 1024, "percentage": 2.0},
        {"extension": "other", "count": 384, "total_size_bytes": 17 * 1024 * 1024 * 1024, "percentage": 34.0},
    ]

    _storage_cache["top_files"] = [
        {"path": "/videos/movie.mp4", "size_bytes": 4 * 1024 * 1024 * 1024, "owner": "user"},
        {"path": "/backups/system.tar.gz", "size_bytes": 3 * 1024 * 1024 * 1024, "owner": "admin"},
        {"path": "/videos/documentary.mp4", "size_bytes": 2.5 * 1024 * 1024 * 1024, "owner": "user"},
    ]

    _storage_cache["last_scan"] = datetime.utcnow().isoformat()


# Create the API router
router = APIRouter()


@router.get("/stats")
async def get_storage_stats(
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Get current storage statistics."""
    if _storage_cache["stats"] is None:
        _perform_storage_scan()

    return {
        "stats": _storage_cache["stats"],
        "last_scan": _storage_cache["last_scan"],
    }


@router.get("/users")
async def get_user_usage(
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Get storage usage per user."""
    if _storage_cache["user_usage"] is None:
        _perform_storage_scan()

    return {
        "users": _storage_cache["user_usage"],
        "last_scan": _storage_cache["last_scan"],
    }


@router.get("/file-types")
async def get_file_type_distribution(
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Get file type distribution."""
    if _storage_cache["file_types"] is None:
        _perform_storage_scan()

    return {
        "file_types": _storage_cache["file_types"],
        "last_scan": _storage_cache["last_scan"],
    }


@router.get("/top-files")
async def get_top_files(
    limit: int = 10,
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Get top files by size."""
    if _storage_cache["top_files"] is None:
        _perform_storage_scan()

    return {
        "files": _storage_cache["top_files"][:limit],
        "last_scan": _storage_cache["last_scan"],
    }


@router.post("/scan")
async def trigger_scan(
    current_user=Depends(get_current_user),
) -> Dict[str, str]:
    """Manually trigger a storage scan."""
    _perform_storage_scan()
    return {"message": "Storage scan completed", "timestamp": _storage_cache["last_scan"]}


class StorageAnalyticsPlugin(PluginBase):
    """Storage Analytics plugin implementation."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="storage_analytics",
            version="1.0.0",
            display_name="Storage Analytics",
            description="Provides storage usage analytics and insights",
            author="BaluHost Team",
            category="storage",
            required_permissions=["file:read", "system:info"],
            homepage="https://github.com/baluhost/storage-analytics",
        )

    def get_router(self) -> APIRouter:
        return router

    async def on_startup(self) -> None:
        """Initialize the plugin."""
        # Perform initial scan
        _perform_storage_scan()

    async def on_shutdown(self) -> None:
        """Cleanup on shutdown."""
        _storage_cache.clear()

    def get_background_tasks(self) -> List[BackgroundTaskSpec]:
        """Register periodic storage scan."""
        async def periodic_scan():
            _perform_storage_scan()

        return [
            BackgroundTaskSpec(
                name="storage_scan",
                func=periodic_scan,
                interval_seconds=6 * 3600,  # Every 6 hours
                run_on_startup=False,  # Already run in on_startup
            )
        ]

    def get_ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(
            enabled=True,
            nav_items=[
                PluginNavItem(
                    path="analytics",
                    label="Storage Analytics",
                    icon="bar-chart-2",
                    admin_only=False,
                    order=50,
                )
            ],
            bundle_path="bundle.js",
            dashboard_widgets=["StorageOverviewWidget"],
        )

    def get_config_schema(self) -> type:
        return StorageAnalyticsConfig

    def get_default_config(self) -> Dict[str, Any]:
        return StorageAnalyticsConfig().model_dump()

    # Hook implementations
    @hookimpl
    def on_file_uploaded(self, path: str, user_id: int, size: int, content_type: Optional[str] = None) -> None:
        """Track new file uploads for analytics."""
        # In production, this would update the analytics database
        pass

    @hookimpl
    def on_file_deleted(self, path: str, user_id: int) -> None:
        """Track file deletions for analytics."""
        # In production, this would update the analytics database
        pass
