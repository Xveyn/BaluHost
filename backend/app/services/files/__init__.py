"""
Files services package.

Provides file management with:
- File operations (upload, delete, rename, move)
- File metadata (ownership, permissions)
- Database-backed metadata
- File sharing (public links, user shares)
"""

from app.services.files.operations import (
    FileAccessError,
    QuotaExceededError,
    SystemDirectoryError,
    is_system_directory,
    is_path_shared_with_user,
    SHARED_WITH_ME_DIR,
    get_owner,
    ensure_can_view,
    get_absolute_path,
    list_directory,
    calculate_used_bytes,
    calculate_available_bytes,
    save_uploads,
    delete_path,
    create_folder,
    rename_path,
    move_path,
)
from app.services.files.metadata import (
    get_owner as get_owner_legacy,
    set_owner as set_owner_legacy,
    clear_path,
    move_path as move_path_metadata,
    ensure_root_metadata,
)
from app.services.files.metadata_db import (
    get_metadata,
    create_metadata,
    update_metadata,
    delete_metadata,
    rename_metadata,
    list_children,
    get_owner_id,
    set_owner_id,
    ensure_metadata,
)
from app.services.files.shares import ShareService

__all__ = [
    # Operations
    "FileAccessError",
    "QuotaExceededError",
    "SystemDirectoryError",
    "is_system_directory",
    "is_path_shared_with_user",
    "SHARED_WITH_ME_DIR",
    "get_owner",
    "ensure_can_view",
    "get_absolute_path",
    "list_directory",
    "calculate_used_bytes",
    "calculate_available_bytes",
    "save_uploads",
    "delete_path",
    "create_folder",
    "rename_path",
    "move_path",
    # Metadata (legacy JSON-based)
    "get_owner_legacy",
    "set_owner_legacy",
    "clear_path",
    "move_path_metadata",
    "ensure_root_metadata",
    # Metadata (database-backed)
    "get_metadata",
    "create_metadata",
    "update_metadata",
    "delete_metadata",
    "rename_metadata",
    "list_children",
    "get_owner_id",
    "set_owner_id",
    "ensure_metadata",
    # Shares
    "ShareService",
]
