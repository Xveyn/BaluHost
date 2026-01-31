"""Plugin permission system.

Defines granular permissions that plugins can request.
Dangerous permissions require explicit admin approval.
"""
from enum import Enum
from typing import List, Set


class PluginPermission(str, Enum):
    """Available plugin permissions.

    Plugins must declare required permissions in their metadata.
    Dangerous permissions (marked below) require explicit admin approval.
    """

    # File Operations
    FILE_READ = "file:read"           # Read files from storage
    FILE_WRITE = "file:write"         # Write/modify files (dangerous)
    FILE_DELETE = "file:delete"       # Delete files (dangerous)

    # System Information
    SYSTEM_INFO = "system:info"       # Read system metrics (CPU, RAM, etc.)
    SYSTEM_EXECUTE = "system:execute" # Execute system commands (dangerous)

    # Network
    NETWORK_OUTBOUND = "network:outbound"  # Make outbound HTTP requests

    # Database
    DB_READ = "db:read"               # Read from database
    DB_WRITE = "db:write"             # Write to database (dangerous)

    # User Data
    USER_READ = "user:read"           # Read user information
    USER_WRITE = "user:write"         # Modify user data (dangerous)

    # Notifications
    NOTIFICATION_SEND = "notification:send"  # Send notifications

    # Background Tasks
    TASK_BACKGROUND = "task:background"  # Run background tasks

    # Events
    EVENT_SUBSCRIBE = "event:subscribe"  # Subscribe to system events
    EVENT_EMIT = "event:emit"            # Emit custom events


# Permissions that require explicit admin approval
DANGEROUS_PERMISSIONS: Set[PluginPermission] = {
    PluginPermission.FILE_WRITE,
    PluginPermission.FILE_DELETE,
    PluginPermission.SYSTEM_EXECUTE,
    PluginPermission.DB_WRITE,
    PluginPermission.USER_WRITE,
}


class PermissionManager:
    """Manages plugin permission checks."""

    @staticmethod
    def is_dangerous(permission: PluginPermission) -> bool:
        """Check if a permission is considered dangerous."""
        return permission in DANGEROUS_PERMISSIONS

    @staticmethod
    def get_dangerous_permissions(permissions: List[str]) -> List[str]:
        """Get list of dangerous permissions from a permission list."""
        return [
            p for p in permissions
            if p in [dp.value for dp in DANGEROUS_PERMISSIONS]
        ]

    @staticmethod
    def validate_permissions(
        required: List[str],
        granted: List[str]
    ) -> bool:
        """Check if all required permissions are granted.

        Args:
            required: List of permission strings the plugin requires
            granted: List of permission strings that have been granted

        Returns:
            True if all required permissions are in granted list
        """
        return all(perm in granted for perm in required)

    @staticmethod
    def get_all_permissions() -> List[dict]:
        """Get all available permissions with metadata.

        Returns:
            List of permission info dicts with name, value, and dangerous flag
        """
        return [
            {
                "name": perm.name,
                "value": perm.value,
                "dangerous": perm in DANGEROUS_PERMISSIONS,
                "description": _get_permission_description(perm),
            }
            for perm in PluginPermission
        ]


def _get_permission_description(perm: PluginPermission) -> str:
    """Get human-readable description for a permission."""
    descriptions = {
        PluginPermission.FILE_READ: "Read files from storage",
        PluginPermission.FILE_WRITE: "Write and modify files in storage",
        PluginPermission.FILE_DELETE: "Delete files from storage",
        PluginPermission.SYSTEM_INFO: "Access system metrics and information",
        PluginPermission.SYSTEM_EXECUTE: "Execute system shell commands",
        PluginPermission.NETWORK_OUTBOUND: "Make outbound network requests",
        PluginPermission.DB_READ: "Read data from the database",
        PluginPermission.DB_WRITE: "Write data to the database",
        PluginPermission.USER_READ: "Access user information",
        PluginPermission.USER_WRITE: "Modify user accounts and data",
        PluginPermission.NOTIFICATION_SEND: "Send push notifications",
        PluginPermission.TASK_BACKGROUND: "Run background tasks",
        PluginPermission.EVENT_SUBSCRIBE: "Subscribe to system events",
        PluginPermission.EVENT_EMIT: "Emit custom events",
    }
    return descriptions.get(perm, "No description available")
