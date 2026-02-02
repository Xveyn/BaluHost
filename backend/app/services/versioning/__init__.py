"""
Version Control Light (VCL) services package.

Provides file versioning with:
- Core VCL operations (blob storage, deduplication, compression)
- Intelligent caching with debouncing for rapid changes
- Priority-based cleanup and quota management
"""

from app.services.versioning.vcl import VCLService
from app.services.versioning.cache import VCLCache, VCLCacheSync, PendingVersion
from app.services.versioning.priority import VCLPriorityMode, VCLMonitor

__all__ = [
    "VCLService",
    "VCLCache",
    "VCLCacheSync",
    "PendingVersion",
    "VCLPriorityMode",
    "VCLMonitor",
]
