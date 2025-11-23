"""Storage mountpoint schemas."""
from typing import List, Optional

from pydantic import BaseModel


class StorageMountpoint(BaseModel):
    """Represents a mounted storage location (RAID array, disk, etc.)."""
    id: str  # e.g., "md0", "sda", "dev-storage"
    name: str  # Display name, e.g., "RAID 1 Setup Main Storage"
    type: str  # "raid", "disk", "dev-storage"
    path: str  # Virtual path prefix, e.g., "/md0", "/dev-storage"
    size_bytes: int
    used_bytes: int
    available_bytes: int
    raid_level: Optional[str] = None  # e.g., "raid1", "raid5"
    status: str  # "optimal", "degraded", "rebuilding", "n/a"
    is_default: bool = False  # Whether this is the default storage location


class MountpointsResponse(BaseModel):
    """Response containing all available storage mountpoints."""
    mountpoints: List[StorageMountpoint]
    default_mountpoint: str  # ID of default mountpoint
