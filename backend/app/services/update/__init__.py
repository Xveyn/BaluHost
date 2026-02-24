"""
Update Service for BaluHost.

Provides self-update functionality with:
- Version checking via Git tags
- Update installation with progress tracking
- Rollback capability
- Dev/Prod backend abstraction
"""
from app.services.update.utils import (
    ProgressCallback,
    parse_version,
    version_to_string,
    COMMIT_TYPE_MAP,
    _CONVENTIONAL_RE,
    _parse_conventional_commits,
)
from app.services.update.backend import UpdateBackend
from app.services.update.dev_backend import DevUpdateBackend
from app.services.update.prod_backend import ProdUpdateBackend
from app.services.update.service import UpdateService
from app.services.update.api import (
    get_update_backend,
    get_update_service,
    finalize_pending_updates,
    register_update_service,
)

__all__ = [
    # Utils
    "ProgressCallback",
    "parse_version",
    "version_to_string",
    "COMMIT_TYPE_MAP",
    "_CONVENTIONAL_RE",
    "_parse_conventional_commits",
    # Backend ABC + implementations
    "UpdateBackend",
    "DevUpdateBackend",
    "ProdUpdateBackend",
    # Service
    "UpdateService",
    # Factories & registration
    "get_update_backend",
    "get_update_service",
    "finalize_pending_updates",
    "register_update_service",
]
